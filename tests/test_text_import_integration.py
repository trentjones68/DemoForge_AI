"""Authenticated generic import authorization, replay, and audit in Supabase."""

from uuid import UUID, uuid4

import pytest
from demoforge_api.db import database_engine, workspace_transaction
from demoforge_api.discovery.imports import MAX_IMPORT_JSON
from demoforge_api.discovery.storage import DiscoveryStorage
from fastapi import HTTPException
from sqlalchemy import text
from test_discovery_integration import import_headers, session
from test_planning_integration import PlanningCase, planning_case

__all__ = ["planning_case"]
pytestmark = [pytest.mark.integration, pytest.mark.supabase]


def test_json_import_uses_the_private_discovery_pipeline(
    planning_case: PlanningCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, api = planning_case, planning_case.api
    base = case.plan.removesuffix("/plan")
    url = f"{base}/imports"
    owner = import_headers(case.owner.headers, "application/json")
    other = import_headers(case.outsider.headers, "application/json")
    peer = import_headers(case.peer.headers, "application/json")
    sample = "[00:00:12] Analyst: Préparer les données fictives.\r\n"
    payload = {"text": sample, "kind": "transcript", "provider": "plaud"}
    assert api.post(url, json=payload).status_code == 401
    assert api.post(url, json=payload, headers=other).status_code == 404
    assert api.post(url, json=payload, headers=peer).status_code == 403
    assert api.post(url, json=payload, headers=case.owner.headers).status_code == 422
    assert (
        api.post(url, content=b"{}", headers=import_headers(case.owner.headers)).status_code == 415
    )
    assert (
        api.post(
            url.replace(base.rsplit("/", 1)[1], str(uuid4())), json=payload, headers=owner
        ).status_code
        == 404
    )
    rejected = api.post(
        url, json=payload | {"file_url": "https://files.example.test/source"}, headers=owner
    )
    assert rejected.status_code == 422
    assert sample.strip() not in rejected.text and "files.example.test" not in rejected.text
    assert api.post(url, json=payload | {"text": False}, headers=owner).status_code == 422
    assert (
        api.post(url, headers=owner, content=iter([b" " * MAX_IMPORT_JSON, b"x"])).status_code
        == 413
    )

    save = DiscoveryStorage.save

    def interrupt(storage: DiscoveryStorage, key: str, fmt: str, raw: bytes) -> None:
        save(storage, key, fmt, raw)
        raise HTTPException(503, "Synthetic interrupted response")

    existing = api.get(f"{base}/sources", headers=owner).json()
    with monkeypatch.context() as patch:
        patch.setattr(DiscoveryStorage, "save", interrupt)
        assert api.post(url, json=payload, headers=owner).status_code == 503
    assert api.get(f"{base}/sources", headers=owner).json() == existing

    created = api.post(url, json=payload, headers=owner)
    assert created.status_code == 201, created.status_code
    result = created.json()
    assert result["duplicate"] is False
    source = result["source"]
    assert (source["provider"], source["kind"], source["method"], source["format"]) == (
        "plaud",
        "transcript",
        "paste",
        "txt",
    )
    assert source["byte_count"] == len(sample.encode())
    replay = api.post(url, json=payload, headers=owner)
    assert replay.status_code == 200 and replay.json() == {"source": source, "duplicate": True}
    manual_replay = api.post(
        f"{base}/sources", headers=import_headers(case.owner.headers), content=sample.encode()
    )
    assert manual_replay.status_code == 200 and manual_replay.json() == replay.json()
    summary = api.post(url, json={"text": sample, "kind": "summary"}, headers=owner)
    assert summary.status_code == 201, summary.status_code
    assert summary.json()["source"]["id"] != source["id"]
    assert summary.json()["source"]["provider"] == "manual"
    other_session = session(api, case.owner.headers, case.opportunity).removesuffix("/sources")
    isolated = api.post(f"{other_session}/imports", json=payload, headers=owner)
    assert isolated.status_code == 201 and isolated.json()["source"]["id"] != source["id"]

    segment_path = f"{base}/sources/{source['id']}/segments"
    evidence = api.get(segment_path, headers=owner)
    assert evidence.headers["Cache-Control"] == "no-store"
    segment = evidence.json()["segments"][0]
    assert segment["start_ms"] == 12000 and segment["speaker"] == "Analyst"
    assert "Préparer les données fictives." in segment["text"]
    assert api.get(segment_path, headers=other).status_code == 404

    assert case.settings.database_url
    engine = database_engine(case.settings.database_url)
    try:
        with workspace_transaction(engine, case.owner.id) as connection:
            rows = (
                connection.execute(
                    text("""
                SELECT action, actor_id FROM demoforge.discovery_audit_events
                WHERE source_id = :source AND workspace_id = :workspace
            """),
                    {
                        "source": UUID(source["id"]),
                        "workspace": UUID(case.workspace.rsplit("/", 1)[1]),
                    },
                )
                .tuples()
                .all()
            )
        assert rows == [("source_imported", case.owner.id)]
    finally:
        engine.dispose()
