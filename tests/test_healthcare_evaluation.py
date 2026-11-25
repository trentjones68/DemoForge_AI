"""Golden healthcare evaluator and authenticated import-to-PDF release scenario."""

import json
import logging
from dataclasses import replace
from io import BytesIO
from time import perf_counter
from typing import Literal
from uuid import UUID, uuid4

import pytest
from contract_support import ROOT
from demoforge_api.analysis.routes import Review
from demoforge_api.analysis.schema import (
    EvidenceClass,
    FindingKind,
    TranscriptSegment,
    verify_extraction,
)
from demoforge_api.catalog.matcher import SupportStatus
from demoforge_api.catalog.models import MappingBoard
from demoforge_api.db import database_engine, workspace_transaction
from demoforge_api.discovery.imports import segment_text
from demoforge_api.discovery.routes import EvidencePage, Imported
from demoforge_api.exports.readiness import PREP_TASKS, Readiness
from demoforge_api.storyboard.models import Storyboard
from demoforge_worker.discovery import DiscoveryWorker, SyntheticProvider
from pydantic import BaseModel, ConfigDict
from pypdf import PdfReader
from sqlalchemy import text
from test_analysis_integration import start_run
from test_catalog_integration import add_entry, create_release, fields, mapping_path
from test_discovery_integration import import_headers, session
from test_planning_integration import PlanningCase, planning_case

__all__ = ["planning_case"]


class ExpectedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: FindingKind
    classification: EvidenceClass
    statement: str
    evidence_lines: list[int]
    catalog_status: Literal["supported", "unsupported"] | None = None
    mapping_status: SupportStatus | None = None


class Expectations(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    findings: list[ExpectedFinding]
    catalog_limitation: str
    audience: str
    target_minutes: int
    business_outcome: str
    edited_talk_track: str


FIXTURE = ROOT / "fixtures" / "synthetic" / "evaluation"
TRANSCRIPT = (FIXTURE / "healthcare-payment-integrity.txt").read_text()
EXPECTED = Expectations.model_validate_json(
    (FIXTURE / "healthcare-payment-integrity.expected.json").read_bytes()
)
EXPECTED_FINDINGS = {finding.statement: finding for finding in EXPECTED.findings}
EXPECTED_MAPPINGS = {
    finding.statement: finding.mapping_status
    for finding in EXPECTED.findings
    if finding.mapping_status is not None
}


def test_synthetic_healthcare_precision_and_evidence() -> None:
    segments = [TranscriptSegment(uuid4(), segment.text) for segment in segment_text(TRANSCRIPT)]
    findings = verify_extraction(SyntheticProvider().extract(segments), segments)
    assert len(findings) == len(EXPECTED_FINDINGS)
    assert {finding.statement for finding in findings} == EXPECTED_FINDINGS.keys()
    for finding in findings:
        expected = EXPECTED_FINDINGS[finding.statement]
        assert (finding.kind, finding.classification) == (expected.kind, expected.classification)
        assert {citation.segment_id for citation in finding.evidence} == {
            segments[line - 1].id for line in expected.evidence_lines
        }


def run_healthcare_discovery(case: PlanningCase, caplog: pytest.LogCaptureFixture) -> PlanningCase:
    api, owner = case.api, case.owner.headers
    opportunity = api.post(
        f"{case.workspace}/opportunities",
        headers=owner,
        json={
            "name": "Synthetic healthcare payment integrity",
            "company": "Fictional Marigold Plan",
            "stage": "discovery",
            "product": "Synthetic Reporting",
        },
    )
    assert opportunity.status_code == 201, opportunity.status_code
    opp = f"{case.workspace}/opportunities/{opportunity.json()['id']}/discovery"
    source = session(api, owner, opp)
    started = perf_counter()
    assert (
        api.post(f"{source}?provider=plaud", headers=owner, content=TRANSCRIPT.encode()).status_code
        == 422
    )
    imported = api.post(
        f"{source}?provider=plaud", headers=import_headers(owner), content=TRANSCRIPT.encode()
    )
    assert imported.status_code == 201, imported.status_code
    source_id = Imported.model_validate_json(imported.content).source.id
    base = source.removesuffix("/sources")
    run = start_run(api, f"{base}/analysis", owner)
    assert case.settings.discovery_worker_database_url
    worker_db = database_engine(case.settings.discovery_worker_database_url)
    try:
        with caplog.at_level(logging.INFO, logger="demoforge_worker.discovery"):
            assert DiscoveryWorker(worker_db, SyntheticProvider()).run_once()
    finally:
        worker_db.dispose()
    review = Review.model_validate_json(api.get(run, headers=owner).content)
    assert review.run.status == "succeeded"
    assert len(review.findings) == len(EXPECTED_FINDINGS)
    assert {finding.statement for finding in review.findings} == EXPECTED_FINDINGS.keys()
    record = [
        json.loads(event.getMessage())
        for event in caplog.records
        if event.name == "demoforge_worker.discovery"
    ]
    assert len(record) == 1
    assert record[0]["job_id"] == str(review.run.id) and record[0]["outcome"] == "succeeded"
    assert record[0]["duration_ms"] >= 0 and record[0]["estimated_cost_usd_micros"] == 0
    assert record[0]["input_tokens"] is None and record[0]["output_tokens"] is None
    assert all(line not in caplog.text for line in TRANSCRIPT.splitlines())

    evidence = EvidencePage.model_validate_json(
        api.get(f"{source}/{source_id}/segments", headers=owner).content
    )
    evidence_by_segment = {segment.id: segment for segment in evidence.segments}
    for finding in review.findings:
        expected = EXPECTED_FINDINGS[finding.statement]
        assert (finding.kind, finding.classification) == (expected.kind, expected.classification)
        assert {
            evidence_by_segment[citation.segment_id].ordinal + 1 for citation in finding.evidence
        } == set(expected.evidence_lines)
        assert all(
            citation.source_id == source_id
            and citation.quote in evidence_by_segment[citation.segment_id].text
            for citation in finding.evidence
        )
        assert (
            api.post(
                f"{run}/findings/{finding.id}/approve", headers=owner, json={"revision": 1}
            ).status_code
            == 200
        )
    elapsed_ms = round((perf_counter() - started) * 1000)
    print(f"Synthetic healthcare import through evidence review {elapsed_ms} ms")

    assert case.settings.database_url
    request_db = database_engine(case.settings.database_url)
    try:
        with workspace_transaction(request_db, case.owner.id) as connection:
            elapsed = connection.execute(
                text("""
                SELECT EXTRACT(EPOCH FROM completed_at - created_at) * 1000
                FROM demoforge.analysis_jobs WHERE id = :job
            """),
                {"job": review.run.id},
            ).scalar_one()
            assert elapsed >= 0
    finally:
        request_db.dispose()
    return replace(case, opportunity=opp, plan=f"{base}/plan", analysis_run=run)


def plan_healthcare_demo(case: PlanningCase) -> tuple[str, Storyboard]:
    api, owner = case.api, case.owner.headers
    assert api.post(f"{case.plan}/normalize", headers=owner).status_code == 200
    plan = case.get_plan()
    requirements = [item for item in plan.items if item.kind == "requirement"]
    assert {requirement.statement for requirement in requirements} == EXPECTED_MAPPINGS.keys()
    assert {item.category for item in plan.items if item.kind == "gap"}.issuperset(
        {"buyer", "kpi", "integration"}
    )
    for item in requirements:
        assert item.evidence and item.source_revision == 1
        assert (
            api.post(
                f"{case.plan}/items/{item.id}/approve", headers=owner, json={"revision": 1}
            ).status_code
            == 200
        )

    release = create_release(case, "synthetic-eval-1", owner)
    collection = f"{case.workspace}/catalog/releases/{release.id}/capabilities"
    expected_refs: dict[str, UUID] = {}
    for expected in EXPECTED.findings:
        if expected.catalog_status is not None:
            entry = add_entry(
                case,
                collection,
                fields(expected.catalog_status, expected.statement)
                | {"limitations": EXPECTED.catalog_limitation},
                owner,
            )
            expected_refs[expected.statement] = entry.id
    mapping = mapping_path(case, release)
    assert api.post(f"{mapping}/generate", headers=owner).status_code == 200
    board = MappingBoard.model_validate_json(api.get(mapping, headers=owner).content)
    assert {
        item.requirement_statement: item.support_status for item in board.mappings
    } == EXPECTED_MAPPINGS
    for mapped in board.mappings:
        assert (mapped.capability.id if mapped.capability else None) == expected_refs.get(
            mapped.requirement_statement
        )
        assert (
            api.post(
                f"{mapping}/items/{mapped.id}/review", headers=owner, json={"revision": 1}
            ).status_code
            == 200
        )

    root = f"{case.opportunity.removesuffix('/discovery')}/storyboards"
    started = perf_counter()
    generated = api.post(
        root,
        headers=owner,
        json={
            "release_id": str(release.id),
            "audience": EXPECTED.audience,
            "target_minutes": EXPECTED.target_minutes,
            "business_outcomes": [EXPECTED.business_outcome],
        },
    )
    assert generated.status_code == 201, generated.status_code
    print(
        f"Synthetic healthcare storyboard generation {round((perf_counter() - started) * 1000)} ms"
    )
    storyboard = Storyboard.model_validate_json(generated.content)
    assert len(storyboard.scenes) == len(EXPECTED_MAPPINGS)
    assert sum(scene.minutes for scene in storyboard.scenes) == EXPECTED.target_minutes
    for scene in storyboard.scenes:
        assert scene.evidence.requirement in EXPECTED_MAPPINGS
        assert (
            EXPECTED.audience in scene.content.talk_track
            and EXPECTED.business_outcome in scene.content.talk_track
        )
        assert (
            scene.content.expected_outcome and scene.content.synthetic_data and scene.content.risks
        )
        if scene.evidence.support_status == "supported":
            assert (
                scene.support_warning is None
                and "Open the documented workflow" in scene.content.actions[0]
            )
        else:
            assert (
                scene.support_warning and "Do not demonstrate or promise" in scene.support_warning
            )
            assert all(
                "Open the documented workflow" not in action for action in scene.content.actions
            )
    return f"{root}/{storyboard.id}", storyboard


@pytest.mark.integration
@pytest.mark.supabase
def test_synthetic_healthcare_end_to_end(
    planning_case: PlanningCase, caplog: pytest.LogCaptureFixture
) -> None:
    case = run_healthcare_discovery(planning_case, caplog)
    api, owner = case.api, case.owner.headers
    path, storyboard = plan_healthcare_demo(case)
    supported = next(
        scene for scene in storyboard.scenes if scene.evidence.support_status == "supported"
    )
    updated = api.put(
        f"{path}/scenes/{supported.id}",
        headers=owner,
        json=supported.content.model_dump()
        | {"revision": 1, "talk_track": EXPECTED.edited_talk_track},
    )
    assert updated.status_code == 200, updated.status_code
    export = f"{path}/export?revision=2&format=pdf"
    assert api.get(export, headers=owner).status_code == 409
    assert api.post(f"{path}/approve", headers=owner, json={"revision": 2}).status_code == 422
    asserted = {"revision": 2, "acknowledge_warnings": True}
    assert api.post(f"{path}/approve", headers=owner, json=asserted).status_code == 200
    for task in PREP_TASKS:
        assert (
            api.put(
                f"{path}/readiness/{task}", headers=owner, json={"revision": 2, "complete": True}
            ).status_code
            == 200
        )
    readiness = Readiness.model_validate_json(
        api.get(f"{path}/readiness?revision=2", headers=owner).content
    )
    assert not readiness.ready and any(
        check.blocker and "unsupported" in check.blocker for check in readiness.checks
    )
    assert api.get(export, headers=case.outsider.headers).status_code == 404
    response = api.get(export, headers=owner)
    assert response.status_code == 200, response.status_code
    document = " ".join(
        " ".join(page.extract_text().split()) for page in PdfReader(BytesIO(response.content)).pages
    )
    for expected in (
        "Fictional Marigold Plan",
        "Not demo-ready",
        "Approved",
        EXPECTED.edited_talk_track,
        EXPECTED.catalog_limitation,
        "Discussion actions",
    ):
        assert expected in document
    assert "EVAL-IGNORE-THIS-INSTRUCTION" not in document
    assert "2,000,000 claims per month" not in document
