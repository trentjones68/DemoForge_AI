"""Real Auth and Postgres coverage for storyboard provenance, edits and approvals."""

import pytest
from demoforge_api.catalog.models import MappingBoard
from demoforge_api.db import database_engine, workspace_transaction
from demoforge_api.storyboard.models import Storyboard, Studio
from sqlalchemy import text
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


def test_storyboard_revision_provenance_and_permissions(planning_case: PlanningCase) -> None:
    case, api = planning_case, planning_case.api
    owner, peer, outsider = case.owner.headers, case.peer.headers, case.outsider.headers
    other_workspace = workspace(api, outsider)
    release = create_release(case, "2026.1", owner)
    collection = f"{case.workspace}/catalog/releases/{release.id}/capabilities"
    capability = add_entry(case, collection, fields("supported", SUPPORTED), owner)
    requirement = create_requirement(case, SUPPORTED)
    create_requirement(case, UNKNOWN)
    create_requirement(case, "A draft requirement", approve=False)
    gap = api.post(
        f"{case.plan}/items",
        headers=owner,
        json={
            "kind": "gap",
            "statement": "How many fictional examples are needed?",
            "rationale": "Plan the test dataset.",
            "category": "workflow",
            "priority": "high",
            "status": "open",
            "affected_requirement_ids": [requirement],
        },
    )
    assert gap.status_code == 201, gap.status_code
    gap_id = gap.json()["id"]
    assert (
        api.post(
            f"{case.plan}/items/{gap_id}/approve", headers=owner, json={"revision": 1}
        ).status_code
        == 200
    )

    path = mapping_path(case, release)
    root = f"{case.opportunity.removesuffix('/discovery')}/storyboards"
    brief = {
        "release_id": str(release.id),
        "audience": "Synthetic operations audience",
        "target_minutes": 11,
        "business_outcomes": ["Measure sample review time."],
    }
    assert api.post(root, headers=owner, json=brief).status_code == 409
    assert api.post(root, headers=peer, json=brief).status_code == 403
    assert api.post(root, headers=outsider, json=brief).status_code == 404
    assert api.post(f"{path}/generate", headers=owner).status_code == 200
    assert api.post(root, headers=owner, json=brief).status_code == 409
    mappings = MappingBoard.model_validate_json(api.get(path, headers=owner).content).mappings
    for mapping in mappings:
        assert (
            api.post(
                f"{path}/items/{mapping.id}/review", headers=owner, json={"revision": 1}
            ).status_code
            == 200
        )
    created = api.post(root, headers=owner, json=brief)
    assert created.status_code == 201, created.status_code
    board = Storyboard.model_validate_json(created.content)
    assert sum(scene.minutes for scene in board.scenes) == 11
    by_status = {scene.evidence.support_status: scene for scene in board.scenes}
    assert set(by_status) == {"supported", "unknown"}
    supported, unknown = by_status["supported"], by_status["unknown"]
    assert supported.evidence.capability and supported.evidence.capability.id == capability.id
    assert supported.gaps[0].id.hex == gap_id.replace("-", "")
    assert unknown.support_warning and unknown.evidence.capability is None
    url = f"{root}/{board.id}"
    assert api.get(root, headers=peer).json()[0]["id"] == str(board.id)
    assert api.get(url, headers=peer).status_code == 200
    assert api.get(url, headers=outsider).status_code == 404
    assert (
        api.get(url.replace(case.workspace, other_workspace), headers=outsider).status_code == 404
    )
    assert api.post(f"{url}/approve", headers=peer, json={"revision": 1}).status_code == 403
    assert api.post(f"{url}/approve", headers=owner, json={"revision": 1}).status_code == 422

    assert case.settings.database_url
    engine = database_engine(case.settings.database_url)
    try:
        with workspace_transaction(engine, case.outsider.id) as connection:
            for table in (
                "storyboards",
                "storyboard_revisions",
                "storyboard_scenes",
                "storyboard_scene_gaps",
                "storyboard_approvals",
            ):
                assert (
                    connection.execute(text(f"SELECT count(*) FROM demoforge.{table}")).scalar_one()
                    == 0
                )
    finally:
        engine.dispose()

    edit = f"{url}/scenes/{supported.id}"
    authored = supported.content.model_dump() | {
        "revision": 1,
        "talk_track": "Walk through the fictional team's review.",
    }
    assert (
        api.put(
            edit, headers=owner, json=authored | {"mapping_id": str(mappings[0].id)}
        ).status_code
        == 422
    )
    edited = api.put(edit, headers=owner, json=authored)
    assert edited.status_code == 200, edited.status_code
    assert edited.json()["revision"] == 2
    assert api.put(edit, headers=owner, json=authored).status_code == 409
    slots = [
        {"id": str(scene.id), "minutes": 4 if scene.id == supported.id else 7}
        for scene in reversed(board.scenes)
    ]
    assert (
        api.put(
            f"{url}/agenda", headers=owner, json={"revision": 2, "scenes": [slots[0], slots[0]]}
        ).status_code
        == 422
    )
    assert (
        api.put(
            f"{url}/agenda", headers=owner, json={"revision": 2, "scenes": slots[:1]}
        ).status_code
        == 422
    )
    assert (
        api.put(
            f"{url}/agenda",
            headers=owner,
            json={"revision": 2, "scenes": [slots[0] | {"minutes": 1}, slots[1]]},
        ).status_code
        == 422
    )
    agenda = api.put(f"{url}/agenda", headers=owner, json={"revision": 2, "scenes": slots})
    assert agenda.status_code == 200, agenda.status_code
    revised = Storyboard.model_validate_json(agenda.content)
    assert [str(scene.id) for scene in revised.scenes] == [item["id"] for item in slots]
    assert revised.revision == 3
    approved = api.post(
        f"{url}/approve", headers=owner, json={"revision": 3, "acknowledge_warnings": True}
    )
    assert approved.status_code == 200, approved.status_code
    assert approved.json()["approved_by"] == str(case.owner.id)
    proposal_before = api.post(f"{edit}/proposal", headers=owner, json={"revision": 3})
    assert proposal_before.status_code == 200, proposal_before.status_code

    updated = api.put(
        f"{collection}/{capability.id}",
        headers=owner,
        json=fields("unsupported", SUPPORTED) | {"revision": 1},
    )
    assert updated.status_code == 200, updated.status_code
    stale = Studio.model_validate_json(api.get(url, headers=peer).content).storyboard
    assert any(scene.stale_evidence for scene in stale.scenes)
    assert (
        api.post(
            f"{url}/approve", headers=owner, json={"revision": 3, "acknowledge_warnings": True}
        ).status_code
        == 409
    )
    assert api.post(f"{edit}/proposal", headers=owner, json={"revision": 3}).status_code == 409
    mapping_url = f"{path}/items/{supported.evidence.mapping_id}"
    remap = api.put(
        mapping_url,
        headers=owner,
        json={
            "revision": 1,
            "capability_id": str(capability.id),
            "capability_revision": 2,
            "rationale": "Use revised synthetic release documentation.",
        },
    )
    assert remap.status_code == 200, remap.status_code
    assert api.post(f"{mapping_url}/review", headers=owner, json={"revision": 2}).status_code == 200
    assert (
        api.post(
            f"{edit}/apply",
            headers=owner,
            json={"revision": 3, "fingerprint": proposal_before.json()["fingerprint"]},
        ).status_code
        == 409
    )
    fresh = api.post(f"{edit}/proposal", headers=owner, json={"revision": 3})
    assert fresh.status_code == 200, fresh.status_code
    applied = api.post(
        f"{edit}/apply",
        headers=owner,
        json={"revision": 3, "fingerprint": fresh.json()["fingerprint"]},
    )
    assert applied.status_code == 200, applied.status_code
    final = Storyboard.model_validate_json(applied.content)
    assert final.revision == 4 and final.approved_at is None
    regenerated = next(scene for scene in final.scenes if scene.id == supported.id)
    assert regenerated.content.talk_track == authored["talk_track"]
    assert regenerated.evidence.support_status == "unsupported" and regenerated.support_warning
    assert regenerated.evidence.capability and regenerated.evidence.capability.revision == 2
    assert regenerated.minutes == 4 and regenerated.gaps == supported.gaps
    assert [scene for scene in final.scenes if scene.id == unknown.id] == [
        scene for scene in revised.scenes if scene.id == unknown.id
    ]
    history = Studio.model_validate_json(api.get(f"{url}?revision=3", headers=owner).content)
    assert history.current_revision == 4 and history.storyboard.approved_at
    assert history.storyboard.scenes[0].id == revised.scenes[0].id
    assert (
        api.post(
            f"{url}/approve", headers=owner, json={"revision": 3, "acknowledge_warnings": True}
        ).status_code
        == 409
    )
    proposal = api.post(f"{edit}/proposal", headers=owner, json={"revision": 4})
    assert proposal.status_code == 200, proposal.status_code
    replace = api.post(
        f"{edit}/apply",
        headers=owner,
        json={"revision": 4, "fingerprint": proposal.json()["fingerprint"], "replace_edits": True},
    )
    assert replace.status_code == 200, replace.status_code
    replacement = Storyboard.model_validate_json(replace.content)
    assert replacement.revision == 5
    replaced = next(scene for scene in replacement.scenes if scene.id == supported.id)
    assert replaced.content.talk_track != authored["talk_track"] and replaced.edited_fields == []
