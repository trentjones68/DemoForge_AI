"""Postgres-backed discovery worker. Run independently of the web and API processes."""

import argparse
import json
import logging
from time import monotonic, sleep
from typing import Literal
from uuid import UUID

from demoforge_api.analysis.provider import (
    FAKE_MODEL,
    AnalysisProvider,
    Completion,
    OpenAIProvider,
    estimate_cost_micros,
    request_payload,
)
from demoforge_api.analysis.schema import (
    MAX_SEGMENTS,
    PROMPT_VERSION,
    AnalysisFailure,
    FailureCode,
    TokenUsage,
    TranscriptSegment,
    verify_extraction,
)
from demoforge_api.db import database_engine
from demoforge_api.settings import Settings
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class SyntheticProvider:
    """Deterministic synthetic fixture, enabled only in explicit development mode."""

    name = "fake"
    model = FAKE_MODEL

    def extract(self, segments: list[TranscriptSegment]) -> str:
        def cite(segment: TranscriptSegment) -> dict[str, str]:
            return {"segment_id": str(segment.id), "quote": segment.text.strip()[:200]}

        findings: list[dict[str, object]] = []
        disagreements = [s for s in segments if s.text.startswith("Synthetic volume:")]
        pain = next((s for s in segments if s.text.startswith("Synthetic pain:")), None)
        if pain:
            findings.append(
                {
                    "kind": "pain_point",
                    "classification": "direct",
                    "statement": pain.text.strip().removeprefix("Synthetic pain:").strip()[:300],
                    "rationale": "The speaker explicitly describes an operational pain point.",
                    "confidence": 0.9,
                    "evidence": [cite(pain)],
                }
            )
        prefix = "Synthetic requirement:"
        for segment in [s for s in segments if s.text.startswith(prefix)][:10]:
            statement = segment.text.strip().removeprefix(prefix).strip()[:300]
            if statement:
                findings.append(
                    {
                        "kind": "requirement",
                        "classification": "direct",
                        "statement": statement,
                        "rationale": "The fixture explicitly records a requirement.",
                        "confidence": 0.9,
                        "evidence": [cite(segment)],
                    }
                )
        if len({s.text.strip() for s in disagreements}) > 1:
            first = disagreements[0]
            other = next(s for s in disagreements if s.text.strip() != first.text.strip())
            findings.append(
                {
                    "kind": "metric",
                    "classification": "contradictory",
                    "statement": "The speakers report different monthly volumes.",
                    "rationale": "Confirm which volume applies before sizing a demo.",
                    "confidence": 0.8,
                    "evidence": [cite(first), cite(other)],
                }
            )
        if not any(s.text.startswith("Synthetic budget:") for s in segments):
            findings.append(
                {
                    "kind": "unknown",
                    "classification": "unknown",
                    "statement": "The budget has not been established.",
                    "rationale": "No speaker provided a budget in this fixture.",
                    "confidence": 0.0,
                    "evidence": [],
                }
            )
        return json.dumps({"findings": findings})


class Claim(BaseModel):
    job_id: UUID
    lease: UUID
    provider: Literal["openai", "fake"]
    model: str
    prompt_version: str


class DiscoveryWorker:
    def __init__(self, engine: Engine, provider: AnalysisProvider) -> None:
        self.engine = engine
        self.provider = provider

    def verify_login(self) -> None:
        with self.engine.connect() as connection:
            valid = connection.execute(
                text("""
                SELECT rolname = 'demoforge_worker' AND NOT rolsuper AND NOT rolbypassrls
                FROM pg_roles WHERE rolname = current_user
            """)
            ).scalar_one()
        if not valid:
            raise ValueError("Configure the restricted discovery worker login")

    def run_once(self) -> bool:
        with self.engine.begin() as connection:
            row = (
                connection.execute(text("SELECT * FROM demoforge.claim_analysis()"))
                .mappings()
                .one_or_none()
            )
        if row is None:
            return False

        claim = Claim.model_validate(row)
        params = {"job": claim.job_id, "lease": claim.lease}
        started = monotonic()
        usage: TokenUsage | None = None
        code: FailureCode | None = None
        outcome = "interrupted"
        try:
            if (
                claim.provider != self.provider.name
                or claim.model != self.provider.model
                or claim.prompt_version != PROMPT_VERSION
            ):
                raise AnalysisFailure("configuration_changed")

            with self.engine.connect() as connection:
                rows = connection.execute(
                    text("SELECT * FROM demoforge.analysis_worker_segments(:job, :lease)"),
                    params,
                ).mappings()
                segments = [TranscriptSegment(id=row["id"], text=row["text"]) for row in rows]
            if not segments:
                raise AnalysisFailure("access_revoked")
            if len(segments) > MAX_SEGMENTS:
                raise AnalysisFailure("input_limit")
            # The transport-independent bound also applies to the synthetic provider.
            request_payload(claim.model, segments)
            result = self.provider.extract(segments)
            if isinstance(result, Completion):
                usage = result.usage
                raw = result.text
            else:
                raw = result
            findings = verify_extraction(raw, segments)
            payload = json.dumps([finding.model_dump(mode="json") for finding in findings])
            with self.engine.begin() as connection:
                applied = connection.execute(
                    text("SELECT demoforge.complete_analysis(:job, :lease, CAST(:data AS jsonb))"),
                    params | {"data": payload},
                ).scalar_one()
            outcome = "succeeded" if applied else "not_applied"
        except AnalysisFailure as error:
            code = error.code
            usage = error.usage or usage
            with self.engine.begin() as connection:
                applied = connection.execute(
                    text("SELECT demoforge.fail_analysis(:job, :lease, :code, :retryable)"),
                    params | {"code": error.code, "retryable": error.retryable},
                ).scalar_one()
            outcome = "failed_attempt" if applied else "not_applied"
        finally:
            logger.info(
                "%s",
                json.dumps(
                    {
                        "event": "discovery_analysis_attempt",
                        "schema_version": 1,
                        "job_id": str(claim.job_id),
                        "provider": claim.provider,
                        "outcome": outcome,
                        "error_code": code,
                        "duration_ms": round((monotonic() - started) * 1000),
                        "input_tokens": usage.input_tokens if usage else None,
                        "output_tokens": usage.output_tokens if usage else None,
                        "estimated_cost_usd_micros": estimate_cost_micros(usage)
                        if usage
                        else (0 if claim.provider == "fake" else None),
                    },
                    separators=(",", ":"),
                ),
            )
        return True


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--once", action="store_true", help="Poll for one job and exit")
    args = cli.parse_args()
    settings = Settings()
    if settings.discovery_worker_database_url is None:
        cli.error("Set DISCOVERY_WORKER_DATABASE_URL")
    provider: AnalysisProvider
    if settings.discovery_provider == "openai" and settings.openai_api_key:
        provider = OpenAIProvider(settings.openai_api_key)
    elif settings.discovery_provider == "fake":
        provider = SyntheticProvider()
    else:
        cli.error("Configure an enabled provider and its credentials")
    logging.basicConfig(level=logging.INFO)
    engine = database_engine(settings.discovery_worker_database_url)
    worker = DiscoveryWorker(engine, provider)
    try:
        worker.verify_login()
        while True:
            try:
                processed = worker.run_once()
            except SQLAlchemyError:
                # Recover through lease expiry. Never log SQL error bodies or parameters.
                logger.warning("Discovery worker database unavailable")
                if args.once:
                    raise SystemExit(1) from None
                processed = False
            if args.once:
                break
            if not processed:
                sleep(2)
    except SQLAlchemyError:
        raise SystemExit("Discovery worker database unavailable") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
