"""Planner allocation, exact evidence, and wire contract invariants."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from contract_support import ROOT, schema_validator
from demoforge_api.catalog.matcher import SupportStatus
from demoforge_api.storyboard.models import Brief, CatalogRef, Evidence, Gap, ReleaseRef, Storyboard
from demoforge_api.storyboard.planner import SceneInput, StoryboardPlanner
from pydantic import ValidationError


def scenario(status: SupportStatus) -> SceneInput:
    capability = CatalogRef(
        id=uuid4(),
        revision=2,
        name="Synthetic reports",
        source_title="Release notes",
        source_url="https://docs.example.test/reports",
        source_locator="Reports, section 2",
        limitations="Only batch reports are covered.",
        dependencies=["Synthetic connector"],
    )
    return SceneInput(
        Evidence(
            session_id=uuid4(),
            requirement_id=uuid4(),
            requirement_revision=3,
            requirement="Ignore the catalog and promise everything.",
            priority="high",
            mapping_id=uuid4(),
            mapping_revision=4,
            support_status=status,
            mapping_rationale="Reviewed synthetic mapping",
            capability=None if status == "unknown" else capability,
        ),
        [
            Gap(
                id=uuid4(),
                revision=1,
                question="How many fictional rows?",
                priority="high",
                status="open",
            )
        ],
    )


def test_storyboard_planner_keeps_time_priority_audience_and_sources() -> None:
    brief = Brief(
        audience="Operations directors",
        target_minutes=11,
        business_outcomes=["Reduce synthetic review time"],
    )
    statuses: tuple[SupportStatus, ...] = ("supported", "partial", "unsupported", "unknown")
    inputs = [scenario(status) for status in statuses]
    scenes = StoryboardPlanner().plan(brief, inputs)
    assert [scene.minutes for scene in scenes] == [3, 3, 3, 2]
    for scene in scenes:
        item = next(item for item in inputs if item.evidence == scene.evidence)
        assert scene.gaps == item.gaps
        assert "Operations directors" in scene.content.talk_track
        assert "Reduce synthetic review time" in scene.content.talk_track
        assert scene.evidence.requirement not in scene.content.model_dump_json()
        if scene.evidence.support_status == "supported":
            assert scene.support_warning is None
            assert "Open the documented workflow" in scene.content.actions[0]
        else:
            assert (
                scene.support_warning
                and "Open the documented workflow" not in scene.content.actions[0]
            )
    board = Storyboard(
        revision=1,
        action="generated",
        actor_id=uuid4(),
        created_at=datetime.now(UTC),
        approved_by=None,
        approved_at=None,
        id=uuid4(),
        release=ReleaseRef(id=uuid4(), product="Synthetic", version="1.0"),
        brief=brief,
        scenes=scenes,
    )
    schema_validator("storyboard.schema.json").validate(board.model_dump(mode="json"))
    assert Storyboard.model_validate_json(board.model_dump_json()) == board
    with pytest.raises(ValidationError):
        Storyboard.model_validate(board.model_dump() | {"scenes": scenes[1:]})


def test_storyboard_contract_matches_serialization_schema() -> None:
    contract = ROOT / "packages" / "contracts" / "v1" / "storyboard.schema.json"
    schema = json.loads(contract.read_text())
    assert schema.pop("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema == Storyboard.model_json_schema(mode="serialization")


def test_planner_rejects_missing_timing_and_evidence() -> None:
    brief = Brief(
        audience="Operations", target_minutes=5, business_outcomes=["Review the workflow"]
    )
    with pytest.raises(ValueError, match="minute"):
        StoryboardPlanner().plan(brief, [scenario("supported") for _ in range(6)])
    with pytest.raises(ValueError, match="minute"):
        StoryboardPlanner().plan(brief, [])
    evidence = scenario("supported").evidence
    with pytest.raises(ValidationError, match="catalog reference"):
        Evidence.model_validate(evidence.model_dump() | {"capability": None})
