"""Validate provider output without trusting model statements or citations."""

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

PROMPT_VERSION = "discovery-v1"
MAX_ATTEMPTS = 3
MAX_INPUT_TOKENS = 30_000
MAX_OUTPUT_TOKENS = 2_500
MAX_SEGMENTS = 600

FindingKind = Literal[
    "pain_point",
    "goal",
    "requirement",
    "persona",
    "integration",
    "objection",
    "metric",
    "constraint",
    "success_criterion",
    "unknown",
]
EvidenceClass = Literal["direct", "inference", "unknown", "contradictory"]
FailureCode = Literal[
    "input_limit",
    "invalid_output",
    "provider_unavailable",
    "provider_rejected",
    "access_revoked",
    "worker_interrupted",
    "configuration_changed",
]
Statement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=800)]


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


class AnalysisFailure(Exception):
    def __init__(
        self, code: FailureCode, retryable: bool = False, *, usage: TokenUsage | None = None
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.usage = usage
        super().__init__(code)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class CitationDraft(StrictModel):
    segment_id: UUID
    quote: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class FindingDraft(StrictModel):
    kind: FindingKind
    classification: EvidenceClass
    statement: Statement
    rationale: Statement
    confidence: Annotated[float, Field(ge=0, le=1)]
    evidence: Annotated[list[CitationDraft], Field(max_length=6)]


class ExtractionDraft(StrictModel):
    findings: Annotated[list[FindingDraft], Field(max_length=25)]


@dataclass(frozen=True)
class TranscriptSegment:
    id: UUID
    text: str


class VerifiedCitation(StrictModel):
    segment_id: UUID
    quote_start: int
    quote_end: int


class VerifiedFinding(StrictModel):
    kind: FindingKind
    classification: EvidenceClass
    statement: Statement
    rationale: Statement
    confidence: float
    evidence: list[VerifiedCitation]


def verify_extraction(raw: str, segments: list[TranscriptSegment]) -> list[VerifiedFinding]:
    try:
        draft = ExtractionDraft.model_validate_json(raw)
    except ValidationError:
        raise AnalysisFailure("invalid_output") from None
    texts = {segment.id: segment.text for segment in segments}
    result = []
    for finding in draft.findings:
        citations: list[VerifiedCitation] = []
        spans: set[tuple[UUID, int, int]] = set()
        for reference in finding.evidence:
            body = texts.get(reference.segment_id)
            if body is None:
                raise AnalysisFailure("invalid_output")
            start = body.find(reference.quote)
            end = start + len(reference.quote)
            span = (reference.segment_id, start, end)
            if start < 0 or not reference.quote.strip() or span in spans:
                raise AnalysisFailure("invalid_output")
            spans.add(span)
            citations.append(
                VerifiedCitation(segment_id=reference.segment_id, quote_start=start, quote_end=end)
            )
        if (
            (finding.classification == "unknown") != (finding.kind == "unknown")
            or (finding.classification != "unknown" and not citations)
            or (finding.classification == "contradictory" and len(citations) < 2)
            or "\x00" in finding.statement + finding.rationale
        ):
            raise AnalysisFailure("invalid_output")
        result.append(
            VerifiedFinding(
                kind=finding.kind,
                classification=finding.classification,
                statement=finding.statement,
                rationale=finding.rationale,
                confidence=finding.confidence,
                evidence=citations,
            )
        )
    return result
