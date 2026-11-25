"""Readiness decisions and both export formats on synthetic inputs."""

import json
from datetime import UTC, date, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from contract_support import ROOT, schema_validator
from demoforge_api.catalog.matcher import SupportStatus
from demoforge_api.exports.document import Block, storyboard_document
from demoforge_api.exports.readiness import PREP_TASKS, Readiness, RequirementKey, assess
from demoforge_api.exports.render import MAX_CHARACTERS, ExportBoundsError, render
from demoforge_api.opportunities import Opportunity, Stage
from demoforge_api.settings import Settings
from demoforge_api.storyboard.models import Brief, ReleaseRef, RevisionSummary, Storyboard, Studio
from demoforge_api.storyboard.planner import StoryboardPlanner
from pydantic import HttpUrl, ValidationError
from pypdf import PdfReader
from test_storyboard_planner import scenario

ORIGIN = "https://app.example.test"


def sample(
    status: SupportStatus = "supported", *, approved: bool = True
) -> tuple[Opportunity, Studio, set[RequirementKey]]:
    now, actor = datetime.now(UTC), uuid4()
    opp = Opportunity(
        id=uuid4(),
        workspace_id=uuid4(),
        owner_id=actor,
        name="Synthetic audit walkthrough",
        company="Société Example",
        stage=Stage.DEMO_PLANNING,
        product="Reporting",
        use_case="Validate fictional audit data.",
        notes="Private opportunity note excluded from export",
        demo_date=date(2026, 12, 1),
        archived_at=None,
        created_at=now,
        updated_at=now,
        version=1,
    )
    meta = RevisionSummary(
        revision=2,
        action="scene_edited",
        actor_id=actor,
        created_at=now,
        approved_at=now if approved else None,
        approved_by=actor if approved else None,
    )
    brief = Brief(
        audience="Audit leads", target_minutes=12, business_outcomes=["Review sample totals"]
    )
    scenes = StoryboardPlanner().plan(brief, [scenario(status)])
    scene = scenes[0]
    scene.content.talk_track = (
        '<img src="https://attacker.example.test/track" /> [risky](https://attacker.example.test)'
    )
    capability = scene.evidence.capability
    if capability:
        capability.source_url = "https://docs.example.test/manual?token=synthetic-secret"
    board = Storyboard(
        **meta.model_dump(),
        id=uuid4(),
        release=ReleaseRef(id=uuid4(), product="Reporting", version="2.1"),
        brief=brief,
        scenes=scenes,
    )
    key = (
        scene.evidence.session_id,
        scene.evidence.requirement_id,
        scene.evidence.requirement_revision,
    )
    return opp, Studio(current_revision=2, revisions=[meta], storyboard=board), {key}


def pdf_uris(reader: PdfReader) -> list[str]:
    links: list[str] = []
    for page in reader.pages:
        for reference in page.annotations or []:
            action = reference.get_object()["/A"]
            assert action["/S"] == "/URI"
            links.append(str(action["/URI"]))
    return links


def test_markdown_and_pdf_share_sections_citations_and_sanitized_content() -> None:
    opp, studio, current = sample("partial")
    readiness = assess(studio, current, 1, {"synthetic_data": True})
    blocks = storyboard_document(opp, studio.storyboard, readiness, ORIGIN)
    md = render(blocks, "md").decode()
    reader = PdfReader(BytesIO(render(blocks, "pdf")))
    pdf = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    for content in (md, pdf):
        for phrase in (
            "Demo storyboard",
            "Société Example",
            "Approved",
            "Agenda",
            "Talk track",
            "Expected outcome",
            "Demo prep checklist",
            "Only batch reports are covered.",
            "Discovery gaps at planning",
            "Not demo-ready",
            "Full product support is missing for scenes 1",
        ):
            assert phrase in content
        assert "synthetic-secret" not in content
        assert opp.notes not in content
    assert "- [x] Prepare and verify fictional demo data" in md
    assert "- [ ] Rehearse the flow" in md
    assert "<img" not in md and "[risky](https://" not in md
    assert "<img" in pdf
    scene = studio.storyboard.scenes[0]
    req = scene.evidence.requirement_id
    assert f"?history={req}#plan-{req}-r3" in md
    assert any(link.endswith(f"?history={req}#plan-{req}-r3") for link in pdf_uris(reader))
    assert all(
        link.startswith(f"{ORIGIN}/workspaces/{opp.workspace_id}/") for link in pdf_uris(reader)
    )


def test_only_fully_prepared_current_approved_evidence_is_ready() -> None:
    _, studio, current = sample()
    completed = dict.fromkeys(PREP_TASKS, True)
    assert assess(studio, current, 0, completed).ready
    assert not assess(studio, current, 0, completed, archived=True).ready
    assert not assess(studio, current, 2, completed).ready
    assert not assess(studio, current | {(uuid4(), uuid4(), 1)}, 0, completed).ready
    assert not assess(studio, current, 0, {"synthetic_data": True}).ready
    studio.current_revision += 1
    assert not assess(studio, current, 0, completed).ready
    studio.current_revision -= 1
    studio.storyboard.scenes[0].stale_evidence = True
    assert not assess(studio, current, 0, completed).ready
    _, draft, draft_current = sample(approved=False)
    assert not assess(draft, draft_current, 0, completed).ready
    for status in ("unknown", "unsupported"):
        _, limited, limited_current = sample(status)
        assert not assess(limited, limited_current, 0, completed).ready


def test_readiness_wire_contract_matches_api() -> None:
    filename = "storyboard-readiness.schema.json"
    contract = ROOT / "packages" / "contracts" / "v1" / filename
    schema = json.loads(contract.read_text())
    assert schema.pop("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema == Readiness.model_json_schema(mode="serialization")
    _, studio, current = sample()
    schema_validator(filename).validate(assess(studio, current, 1, {}).model_dump(mode="json"))


@pytest.mark.parametrize("fmt", ["md", "pdf"])
def test_export_bounds(fmt: str) -> None:
    with pytest.raises(ExportBoundsError):
        render([Block("text", "x" * (MAX_CHARACTERS + 1))], "pdf" if fmt == "pdf" else "md")


@pytest.mark.parametrize(
    "origin",
    [
        "http://app.example.test",
        "https://user:pass@app.example.test",
        "https://app.example.test/path",
        "https://app.example.test/?token=abc",
    ],
)
def test_source_origin_disallows_untrusted_url_components(origin: str) -> None:
    with pytest.raises(ValidationError, match="trusted HTTPS web origin"):
        Settings(export_web_origin=HttpUrl(origin))
