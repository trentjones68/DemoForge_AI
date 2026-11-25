"""Catalog roles, exact evidence, and current mapping eligibility in Supabase."""

from typing import Literal

import pytest
from demoforge_api.catalog.models import Capability, MappingBoard, Release
from demoforge_api.db import database_engine, workspace_transaction
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_discovery_integration import workspace
from test_planning_integration import PlanningCase, planning_case

__all__ = ["planning_case"]
pytestmark = [pytest.mark.integration, pytest.mark.supabase]

SUPPORTED = "Export a monthly audit report."
PARTIAL = "Deliver reports over SFTP."
UNSUPPORTED = "Publish reports to an external portal."
UNKNOWN = "Schedule reports at an arbitrary time."
MISSING = "Export a monthly audit report and notify the compliance team."

CapabilityStatus = Literal["supported", "partial", "unsupported", "unknown"]


def fields(status: CapabilityStatus, phrase: str) -> dict[str, object]:
    return {
        "name": f"Synthetic {status} capability",
        "description": "Catalog documentation for a synthetic product.",
        "support_status": status,
        "limitations": "Available only for the documented workflow.",
        "dependencies": ["Synthetic reporting connector"],
        "source_title": "Synthetic release guide",
        "source_url": "https://docs.example.test/release#reports",
        "source_locator": "Reports, section 2",
        "match_phrases": [phrase],
    }


def create_requirement(case: PlanningCase, statement: str, approve: bool = True) -> str:
    response = case.api.post(
        f"{case.plan}/items",
        headers=case.owner.headers,
        json={
            "kind": "requirement",
            "statement": statement,
            "rationale": "Synthetic customer need.",
            "category": "workflow",
            "priority": "high",
        },
    )
    assert response.status_code == 201, response.status_code
    item = str(response.json()["id"])
    if approve:
        response = case.api.post(
            f"{case.plan}/items/{item}/approve", headers=case.owner.headers, json={"revision": 1}
        )
        assert response.status_code == 200, response.status_code
    return item


def create_release(case: PlanningCase, version: str, headers: dict[str, str]) -> Release:
    response = case.api.post(
        f"{case.workspace}/catalog/releases",
        headers=headers,
        json={
            "product": "Synthetic Reporting",
            "version": version,
        },
    )
    assert response.status_code == 201, response.status_code
    return Release.model_validate_json(response.content)


def add_entry(
    case: PlanningCase, path: str, data: dict[str, object], headers: dict[str, str]
) -> Capability:
    response = case.api.post(path, headers=headers, json=data)
    assert response.status_code == 201, response.status_code
    return Capability.model_validate_json(response.content)


def mapping_path(case: PlanningCase, release: Release) -> str:
    return f"{case.opportunity.removesuffix('/discovery')}/capability-mappings/{release.id}"


def test_catalog_roles_and_exact_mapping_review(planning_case: PlanningCase) -> None:
    case = planning_case
    api = case.api
    owner, peer, outsider = case.owner.headers, case.peer.headers, case.outsider.headers
    releases = f"{case.workspace}/catalog/releases"
    membership = f"{case.workspace}/members/{case.peer.id}"
    assert (
        api.post(releases, headers=peer, json={"product": "Demo", "version": "1"}).status_code
        == 403
    )
    assert api.get(releases, headers=outsider).status_code == 404
    assert api.put(membership, headers=owner, json={"role": "product_admin"}).status_code == 200
    release = create_release(case, "2026.1", peer)
    assert (
        api.post(
            releases, headers=peer, json={"product": "synthetic REPORTING", "version": "2026.1"}
        ).status_code
        == 409
    )
    collection = f"{releases}/{release.id}/capabilities"
    assert (
        api.post(
            collection,
            headers=peer,
            json=fields("partial", PARTIAL)
            | {
                "limitations": "",
            },
        ).status_code
        == 422
    )
    assert (
        api.post(
            collection,
            headers=peer,
            json=fields("supported", SUPPORTED)
            | {
                "source_url": "https://user:invalid@docs.example.test/",
            },
        ).status_code
        == 422
    )
    supported = add_entry(case, collection, fields("supported", SUPPORTED), peer)
    add_entry(case, collection, fields("partial", PARTIAL), peer)
    add_entry(case, collection, fields("unsupported", UNSUPPORTED), peer)
    unknown = add_entry(case, collection, fields("unknown", UNKNOWN), peer)
    other_release = create_release(case, "2026.2", owner)
    other = add_entry(
        case, f"{releases}/{other_release.id}/capabilities", fields("supported", UNKNOWN), owner
    )
    path = mapping_path(case, release)
    assert api.get(path, headers=peer).status_code == 403
    found = api.get(f"{collection}?q=monthly%20audit", headers=peer)
    assert [item["id"] for item in found.json()["entries"]] == [str(supported.id)]
    found = api.get(f"{collection}?q=reporting%20connector", headers=peer)
    assert len(found.json()["entries"]) == 4
    assert api.get(f"{collection}?q=%00", headers=peer).status_code == 422

    for statement in (SUPPORTED, PARTIAL, UNSUPPORTED, UNKNOWN, MISSING):
        create_requirement(case, statement)
    create_requirement(case, "A draft requirement.", approve=False)
    assert api.put(membership, headers=owner, json={"role": "sales_engineer"}).status_code == 200
    assert api.post(f"{path}/generate", headers=peer).status_code == 403
    assert api.post(f"{path}/generate", headers=outsider).status_code == 404
    assert api.get(f"{collection}/{supported.id}", headers=outsider).status_code == 404
    response = api.post(f"{path}/generate", headers=owner)
    assert response.status_code == 200, response.status_code
    assert response.json() == {"added": 5}
    assert api.post(f"{path}/generate", headers=owner).json() == {"added": 0}
    board = MappingBoard.model_validate_json(api.get(path, headers=peer).content)
    by_statement = {item.requirement_statement: item for item in board.mappings}
    assert set(by_statement) == {SUPPORTED, PARTIAL, UNSUPPORTED, UNKNOWN, MISSING}
    assert {stmt: item.support_status for stmt, item in by_statement.items()} == {
        SUPPORTED: "supported",
        PARTIAL: "partial",
        UNSUPPORTED: "unsupported",
        UNKNOWN: "unknown",
        MISSING: "unknown",
    }
    assert by_statement[MISSING].capability is None
    assert by_statement[UNKNOWN].capability == unknown
    assert by_statement[SUPPORTED].capability == supported
    assert api.get(f"{path}/reviewed", headers=owner).json() == []

    unmapped = f"{path}/items/{by_statement[MISSING].id}"
    missing_reference = {
        "revision": 1,
        "rationale": "No relevant documentation.",
        "capability_id": None,
        "capability_revision": None,
    }
    assert (
        api.put(
            unmapped,
            headers=owner,
            json=missing_reference
            | {
                "support_status": "supported",
            },
        ).status_code
        == 422
    )
    assert (
        api.put(
            unmapped,
            headers=owner,
            json=missing_reference
            | {
                "capability_id": str(supported.id),
                "capability_revision": 1,
            },
        ).status_code
        == 422
    )
    assert (
        api.put(
            unmapped,
            headers=owner,
            json=missing_reference
            | {
                "capability_id": str(other.id),
                "capability_revision": 1,
            },
        ).status_code
        == 404
    )
    assert (
        api.put(unmapped, headers=owner, json=missing_reference).json()["support_status"]
        == "unknown"
    )

    uncertain = f"{path}/items/{by_statement[UNKNOWN].id}"
    uncertain_change = missing_reference | {
        "capability_id": str(unknown.id),
        "capability_revision": 1,
    }
    assert (
        api.put(uncertain, headers=owner, json=uncertain_change).json()["support_status"]
        == "unknown"
    )
    assert api.post(f"{uncertain}/review", headers=owner, json={"revision": 2}).status_code == 200

    verified = f"{path}/items/{by_statement[SUPPORTED].id}"
    assert api.post(f"{verified}/review", headers=peer, json={"revision": 1}).status_code == 403
    assert api.post(f"{verified}/review", headers=owner, json={"revision": 1}).status_code == 200
    changed = api.put(
        f"{collection}/{supported.id}",
        headers=owner,
        json=fields("partial", SUPPORTED)
        | {
            "revision": 1,
            "source_locator": "Revised reports, section 4",
        },
    )
    assert changed.status_code == 200, changed.status_code
    assert changed.json()["revision"] == 2
    updated = MappingBoard.model_validate_json(api.get(path, headers=owner).content)
    pinned = next(item for item in updated.mappings if item.id == by_statement[SUPPORTED].id)
    assert pinned.stale_evidence and pinned.capability == supported
    assert api.post(f"{verified}/review", headers=owner, json={"revision": 1}).status_code == 409
    assert {
        item["support_status"] for item in api.get(f"{path}/reviewed", headers=owner).json()
    } == {"unknown"}

    newer = missing_reference | {"capability_id": str(supported.id), "capability_revision": 2}
    assert api.put(verified, headers=owner, json=newer).json()["support_status"] == "partial"
    assert api.put(verified, headers=owner, json=newer).status_code == 409
    assert api.post(f"{verified}/review", headers=owner, json={"revision": 2}).status_code == 200
    archived = api.post(f"{collection}/{supported.id}/archive", headers=owner, json={"revision": 2})
    assert archived.status_code == 200, archived.status_code
    assert archived.json()["archived"] is True
    assert api.get(f"{collection}?q=monthly%20audit", headers=peer).json()["entries"] == []
    assert (
        len(
            api.get(f"{collection}?include_archived=true&q=monthly%20audit", headers=peer).json()[
                "entries"
            ]
        )
        == 1
    )
    assert {
        item["support_status"] for item in api.get(f"{path}/reviewed", headers=owner).json()
    } == {"unknown"}

    plan = case.get_plan()
    requirement = next(item for item in plan.items if item.statement == UNKNOWN)
    changed_requirement = api.put(
        f"{case.plan}/items/{requirement.id}",
        headers=owner,
        json={
            "revision": requirement.revision,
            "statement": "Updated synthetic requirement.",
            "rationale": "Edited after approval.",
            "category": "workflow",
            "priority": "high",
        },
    )
    assert changed_requirement.status_code == 200, changed_requirement.status_code
    assert api.get(f"{path}/reviewed", headers=owner).json() == []


def test_database_catalog_scope_and_support_invariants(planning_case: PlanningCase) -> None:
    case = planning_case
    owner = case.owner.headers
    other_workspace = workspace(case.api, case.outsider.headers)
    release = create_release(case, "2026.1", owner)
    collection = f"{case.workspace}/catalog/releases/{release.id}/capabilities"
    unknown = add_entry(case, collection, fields("unknown", UNKNOWN), owner)
    create_requirement(case, UNKNOWN)
    path = mapping_path(case, release)
    assert case.api.post(f"{path}/generate", headers=owner).status_code == 200
    item = MappingBoard.model_validate_json(case.api.get(path, headers=owner).content).mappings[0]
    assert (
        case.api.get(
            f"{other_workspace}/catalog/releases/{release.id}/capabilities/{unknown.id}",
            headers=case.outsider.headers,
        ).status_code
        == 404
    )

    assert case.settings.database_url
    engine = database_engine(case.settings.database_url)
    scope = {
        "workspace": case.workspace.rsplit("/", 1)[1],
        "opportunity": case.opportunity.removesuffix("/discovery").rsplit("/", 1)[1],
        "release": release.id,
        "mapping": item.id,
    }
    insert = text("""
        INSERT INTO demoforge.mapping_revisions (
            workspace_id, opportunity_id, release_id, mapping_id, revision,
            capability_id, capability_revision, support_status, rationale
        ) VALUES (
            :workspace, :opportunity, :release, :mapping, 2,
            :capability, :capability_revision, :status, 'Synthetic direct database check'
        )
    """)
    try:
        with workspace_transaction(engine, case.outsider.id) as connection:
            for view in ("current_catalog_capabilities", "current_capability_mappings"):
                assert (
                    connection.execute(
                        text(f"SELECT count(*) FROM demoforge.{view} WHERE release_id = :release"),
                        scope,
                    ).scalar_one()
                    == 0
                )
            with pytest.raises(DBAPIError) as denied, connection.begin_nested():
                connection.execute(
                    insert,
                    scope | {"capability": None, "capability_revision": None, "status": "unknown"},
                )
            assert getattr(denied.value.orig, "sqlstate", None) == "42501"

        with workspace_transaction(engine, case.owner.id) as connection:
            for capability, revision, code in ((None, None, "23514"), (unknown.id, 1, "23503")):
                with pytest.raises(DBAPIError) as denied, connection.begin_nested():
                    connection.execute(
                        insert,
                        scope
                        | {
                            "capability": capability,
                            "capability_revision": revision,
                            "status": "supported",
                        },
                    )
                assert getattr(denied.value.orig, "sqlstate", None) == code
    finally:
        engine.dispose()
