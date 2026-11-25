"""Supabase integration for exact-revision readiness, exports, and audit events."""

from io import BytesIO
from uuid import UUID

import pytest
from demoforge_api.exports.readiness import PREP_TASKS, Readiness
from demoforge_api.storyboard.models import Storyboard
from pypdf import PdfReader
from sqlalchemy import create_engine, text
from test_catalog_integration import (
    SUPPORTED,
    UNKNOWN,
    add_entry,
    create_release,
    create_requirement,
    fields,
    mapping_path,
)
from test_discovery_integration import workspace
from test_planning_integration import PlanningCase, planning_case

__all__ = ["planning_case"]
pytestmark = [pytest.mark.integration, pytest.mark.supabase]


def test_approved_downloads_are_audited_and_readiness_stays_revision_scoped(
    planning_case: PlanningCase,
) -> None:
    case, api = planning_case, planning_case.api
    owner, peer, outsider = case.owner.headers, case.peer.headers, case.outsider.headers
    outsider_workspace = workspace(api, outsider)
    release = create_release(case, "2026.1", owner)
    collection = f"{case.workspace}/catalog/releases/{release.id}/capabilities"
    add_entry(case, collection, fields("supported", SUPPORTED), owner)
    requirement = create_requirement(case, SUPPORTED)
    gap_fields = {
        "statement": "Confirm the fictional totals for rehearsal.",
        "rationale": "Verify the totals with the demo owner.",
        "category": "workflow",
        "priority": "high",
        "affected_requirement_ids": [requirement],
    }
    gap = api.post(
        f"{case.plan}/items", headers=owner, json=gap_fields | {"kind": "gap", "status": "open"}
    )
    assert gap.status_code == 201, gap.status_code
    gap_url = f"{case.plan}/items/{gap.json()['id']}"
    assert api.post(f"{gap_url}/approve", headers=owner, json={"revision": 1}).status_code == 200
    mapping = mapping_path(case, release)
    assert api.post(f"{mapping}/generate", headers=owner).status_code == 200
    mapping_id = api.get(mapping, headers=owner).json()["mappings"][0]["id"]
    assert (
        api.post(
            f"{mapping}/items/{mapping_id}/review", headers=owner, json={"revision": 1}
        ).status_code
        == 200
    )
    root = f"{case.opportunity.removesuffix('/discovery')}/storyboards"
    created = api.post(
        root,
        headers=owner,
        json={
            "release_id": str(release.id),
            "audience": "Synthetic leads",
            "target_minutes": 11,
            "business_outcomes": ["Verify fictional totals."],
        },
    )
    assert created.status_code == 201, created.status_code
    board = Storyboard.model_validate_json(created.content)
    path = f"{root}/{board.id}"
    readiness = f"{path}/readiness?revision=1"
    md = f"{path}/export?revision=1&format=md"
    pdf = f"{path}/export?revision=1&format=pdf"
    assert api.get(md, headers=owner).status_code == 409
    assert api.get(f"{path}/export?format=pdf", headers=owner).status_code == 422
    assert api.get(readiness, headers=outsider).status_code == 404
    assert (
        api.get(md.replace(case.workspace, outsider_workspace), headers=outsider).status_code == 404
    )
    assert api.get(md).status_code == 401
    assert (
        api.put(
            f"{path}/readiness/rehearsal", headers=peer, json={"revision": 1, "complete": True}
        ).status_code
        == 403
    )

    for task in PREP_TASKS:
        response = api.put(
            f"{path}/readiness/{task}", headers=owner, json={"revision": 1, "complete": True}
        )
        assert response.status_code == 200, response.status_code
        assert not Readiness.model_validate_json(response.content).ready
    assert api.post(f"{path}/approve", headers=owner, json={"revision": 1}).status_code == 200
    assert not Readiness.model_validate_json(api.get(readiness, headers=peer).content).ready
    gap_change = api.put(
        gap_url,
        headers=owner,
        json=gap_fields | {"revision": 1, "status": "resolved", "affected_requirement_ids": []},
    )
    assert gap_change.status_code == 200, gap_change.status_code
    assert not Readiness.model_validate_json(api.get(readiness, headers=peer).content).ready
    assert api.post(f"{gap_url}/approve", headers=owner, json={"revision": 2}).status_code == 200
    assert Readiness.model_validate_json(api.get(readiness, headers=peer).content).ready
    markdown = api.get(md, headers=owner)
    assert markdown.status_code == 200, markdown.status_code
    assert "Demo-ready" in markdown.text and "Not demo-ready" not in markdown.text
    assert f"?history={requirement}#plan-{requirement}-r1" in markdown.text
    assert "no-store" in markdown.headers["cache-control"]
    assert markdown.headers["content-type"] == "text/markdown; charset=utf-8"
    assert (
        markdown.headers["content-disposition"]
        == f'attachment; filename="demo-storyboard-{board.id}-r1.md"'
    )
    assert api.get(md, headers=outsider).status_code == 404

    create_requirement(case, UNKNOWN)
    changed_scope = Readiness.model_validate_json(api.get(readiness, headers=owner).content)
    assert not changed_scope.ready
    assert any(
        check.blocker and "approved requirements changed" in check.blocker
        for check in changed_scope.checks
    )
    download = api.get(pdf, headers=peer)
    assert download.status_code == 200, download.status_code
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["x-content-type-options"] == "nosniff"
    pdf_text = " ".join(
        " ".join(page.extract_text().split()) for page in PdfReader(BytesIO(download.content)).pages
    )
    assert "Not demo-ready" in pdf_text and "approved requirements changed" in pdf_text

    scene = board.scenes[0]
    edited = api.put(
        f"{path}/scenes/{scene.id}",
        headers=owner,
        json=scene.content.model_dump()
        | {"revision": 1, "talk_track": "Review the fictional totals in order."},
    )
    assert edited.status_code == 200, edited.status_code
    new_readiness = Readiness.model_validate_json(
        api.get(f"{path}/readiness?revision=2", headers=owner).content
    )
    assert all(not check.complete for check in new_readiness.checks if check.task)
    assert (
        api.put(
            f"{path}/readiness/rehearsal", headers=owner, json={"revision": 1, "complete": False}
        ).status_code
        == 409
    )
    assert api.get(f"{path}/export?revision=2&format=pdf", headers=owner).status_code == 409
    assert api.get(md, headers=owner).status_code == 200

    assert case.settings.migration_database_url
    engine = create_engine(str(case.settings.migration_database_url), hide_parameters=True)
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    text("""
                SELECT event, format, delivery_id, revision, demo_ready, actor_id, byte_count
                FROM demoforge.storyboard_export_events WHERE storyboard_id = :storyboard
            """),
                    {"storyboard": board.id},
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()
    assert len(rows) == 6
    deliveries: dict[UUID, set[str]] = {}
    for row in rows:
        deliveries.setdefault(row["delivery_id"], set()).add(row["event"])
        assert row["revision"] == 1 and row["byte_count"] > 0
    assert len(deliveries) == 3
    assert all(
        events == {"export_generated", "artifact_accessed"} for events in deliveries.values()
    )
    assert {row["actor_id"] for row in rows if row["format"] == "md"} == {case.owner.id}
    assert {row["actor_id"] for row in rows if row["format"] == "pdf"} == {case.peer.id}
    assert {row["demo_ready"] for row in rows if row["format"] == "md"} == {True, False}
