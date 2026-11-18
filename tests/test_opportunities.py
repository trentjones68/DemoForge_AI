import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx2
import pytest
from demoforge_api.db import workspace_transaction
from demoforge_api.main import create_app
from demoforge_api.opportunities import OpportunityWrite
from demoforge_api.settings import Settings
from fastapi.testclient import TestClient
from pydantic import HttpUrl, ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from test_auth import bearer
from test_supabase_integration import LocalSupabase, user_token

PAYLOAD: dict[str, object] = {
    "name": "Synthetic pipeline review",
    "company": "Northstar Demo Co.",
    "product": "Workflow Studio",
    "stage": "discovery",
    "demo_date": "2027-02-12",
    "use_case": "Review a synthetic approvals workflow",
    "notes": "Synthetic test notes",
}


@pytest.mark.parametrize(
    "override",
    [
        {"name": " "},
        {"company": "X" * 121},
        {"stage": "unknown"},
        {"demo_date": "2027-02-30"},
        {"demo_date": 0},
        {"demo_date": "2027-02-12T00:00:00"},
        {"notes": "x" * 5001},
        {"workspace_id": str(uuid4())},
    ],
)
def test_opportunity_input_validation(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OpportunityWrite.model_validate(PAYLOAD | override)


@pytest.mark.integration
@pytest.mark.supabase
def test_opportunity_lifecycle_permissions_pagination_and_audit() -> None:
    status_file = os.environ.get("TEST_SUPABASE_STATUS_FILE")
    if not status_file:
        pytest.skip("Set TEST_SUPABASE_STATUS_FILE for a disposable Supabase instance")
    local = LocalSupabase.model_validate_json(Path(status_file).read_text())
    auth_url = local.auth_url or HttpUrl(local.issuer)
    assert local.api_url.host in ("127.0.0.1", "localhost")
    assert auth_url.host in ("127.0.0.1", "localhost")
    settings = Settings(
        supabase_jwt_issuer=HttpUrl(local.issuer),
        supabase_jwks_url=HttpUrl(f"{local.issuer}/.well-known/jwks.json"),
        supabase_jwt_secret=None,
    )
    assert settings.database_url and settings.migration_database_url
    for dsn in (settings.database_url, settings.migration_database_url):
        assert all(host["host"] in ("localhost", "127.0.0.1") for host in dsn.hosts())
    db = create_engine(str(settings.database_url))
    migration = create_engine(str(settings.migration_database_url))
    created_users: list[str] = []
    service = local.service_key.get_secret_value()
    service_headers = bearer(service) | {"apikey": service}

    try:
        with (
            httpx2.Client(base_url=str(auth_url).rstrip("/") + "/", timeout=10) as auth,
            TestClient(create_app(settings)) as api,
        ):
            try:
                admin = bearer(user_token(auth, local, "opp-admin", created_users))
                second_admin = bearer(user_token(auth, local, "opp-other-admin", created_users))
                engineer = bearer(user_token(auth, local, "opp-se", created_users))
                viewer = bearer(user_token(auth, local, "opp-viewer", created_users))
                admin_id, foreign_owner, engineer_id, viewer_id = (
                    UUID(uid) for uid in created_users
                )

                def workspace(headers: dict[str, str], name: str) -> str:
                    response = api.post("/v1/workspaces", headers=headers, json={"name": name})
                    assert response.status_code == 201
                    workspace_id = response.json()["id"]
                    assert isinstance(workspace_id, str)
                    return workspace_id

                workspace_id = workspace(admin, "Synthetic sales")
                foreign_id = workspace(second_admin, "Synthetic external")
                base = f"/v1/workspaces/{workspace_id}/opportunities"
                foreign = f"/v1/workspaces/{foreign_id}/opportunities"
                members = f"/v1/workspaces/{workspace_id}/members"
                for actor, role in ((engineer_id, "sales_engineer"), (viewer_id, "viewer")):
                    assert (
                        api.put(
                            f"{members}/{actor}", headers=admin, json={"role": role}
                        ).status_code
                        == 200
                    )

                assert api.get(base).status_code == 401
                assert api.get(base, headers=viewer).json()["items"] == []
                assert api.post(base, headers=viewer, json=PAYLOAD).status_code == 403

                def create(
                    route: str, headers: dict[str, str], payload: dict[str, object]
                ) -> dict[str, object]:
                    response = api.post(route, headers=headers, json=payload)
                    assert response.status_code == 201, response.status_code
                    body: dict[str, object] = response.json()
                    return body

                assert (
                    api.post(
                        base, headers=admin, json=PAYLOAD | {"owner_id": str(foreign_owner)}
                    ).status_code
                    == 422
                )
                assert (
                    api.post(
                        base, headers=engineer, json=PAYLOAD | {"owner_id": str(admin_id)}
                    ).status_code
                    == 403
                )

                owned = create(base, engineer, PAYLOAD | {"name": "Zulu synthetic"})
                assert owned["owner_id"] == str(engineer_id)
                item = f"{base}/{owned['id']}"
                other = create(
                    base,
                    admin,
                    PAYLOAD
                    | {
                        "name": "Alpha synthetic",
                        "stage": "qualification",
                        "demo_date": None,
                    },
                )
                remote = create(foreign, second_admin, PAYLOAD | {"name": "Isolated synthetic"})
                assert api.get(foreign, headers=engineer).status_code == 404
                assert api.get(f"{foreign}/{remote['id']}", headers=engineer).status_code == 404
                assert api.get(f"{base}/{remote['id']}", headers=engineer).status_code == 404
                assert (
                    api.put(
                        f"{foreign}/{remote['id']}", headers=engineer, json=PAYLOAD | {"version": 1}
                    ).status_code
                    == 404
                )
                assert (
                    api.post(
                        f"{foreign}/{remote['id']}/archive", headers=engineer, json={"version": 1}
                    ).status_code
                    == 404
                )
                assert api.get(item, headers=viewer).json()["notes"] == PAYLOAD["notes"]
                assert (
                    api.put(
                        f"{base}/{other['id']}", headers=engineer, json=PAYLOAD | {"version": 1}
                    ).status_code
                    == 403
                )

                result = api.get(base, headers=engineer, params={"page_size": 1, "sort": "name"})
                assert result.status_code == 200
                first = result.json()
                assert first["has_next"] and first["items"][0]["id"] == other["id"]
                assert "notes" not in first["items"][0]
                assert "use_case" not in first["items"][0]
                second = api.get(
                    base, headers=engineer, params={"page": 2, "page_size": 1, "sort": "name"}
                ).json()
                assert not second["has_next"] and second["items"][0]["id"] == owned["id"]
                by_date = api.get(base, headers=viewer, params={"sort": "demo_date"}).json()
                assert [entry["id"] for entry in by_date["items"]] == [owned["id"], other["id"]]
                filtered = api.get(base, headers=admin, params={"stage": "qualification"}).json()
                assert [entry["id"] for entry in filtered["items"]] == [other["id"]]
                assert api.get(base, headers=engineer, params={"page_size": 101}).status_code == 422
                assert api.get(base, headers=engineer, params={"sort": "bogus"}).status_code == 422

                replacement = PAYLOAD | {"name": "Edited synthetic", "version": 1}
                edited = api.put(item, headers=engineer, json=replacement)
                assert edited.status_code == 200
                assert edited.json()["version"] == 2 and edited.json()["name"] == "Edited synthetic"
                assert api.put(item, headers=engineer, json=replacement).status_code == 409
                assert (
                    api.post(f"{item}/archive", headers=engineer, json={"version": 1}).status_code
                    == 409
                )
                archived = api.post(f"{item}/archive", headers=engineer, json={"version": 2})
                assert archived.status_code == 200 and archived.json()["archived_at"]
                active = api.get(base, headers=engineer).json()["items"]
                assert [entry["id"] for entry in active] == [other["id"]]
                archive_list = api.get(base, headers=engineer, params={"archive": "archived"})
                assert [entry["id"] for entry in archive_list.json()["items"]] == [owned["id"]]
                assert (
                    api.put(item, headers=admin, json=replacement | {"version": 3}).status_code
                    == 409
                )

                with workspace_transaction(db, engineer_id) as connection:
                    assert (
                        connection.execute(
                            text("""
                        SELECT id FROM demoforge.opportunities WHERE workspace_id = :workspace
                    """),
                            {"workspace": foreign_id},
                        ).first()
                        is None
                    )
                    assert (
                        connection.execute(
                            text("""
                        UPDATE demoforge.opportunities SET name = 'blocked'
                        WHERE workspace_id = :workspace RETURNING id
                    """),
                            {"workspace": foreign_id},
                        ).first()
                        is None
                    )
                    assert (
                        connection.execute(
                            text("SELECT id FROM demoforge.opportunity_audit_events")
                        ).first()
                        is None
                    )
                with workspace_transaction(db, admin_id) as connection:
                    actions = connection.execute(
                        text("""
                        SELECT action, actor_id FROM demoforge.opportunity_audit_events
                        WHERE opportunity_id = :id ORDER BY version
                    """),
                        {"id": owned["id"]},
                    ).all()
                    assert [tuple(row) for row in actions] == [
                        (action, engineer_id) for action in ("created", "updated", "archived")
                    ]

                with pytest.raises(IntegrityError) as violation, migration.begin() as connection:
                    connection.execute(
                        text("""
                        UPDATE demoforge.opportunities SET owner_id = :owner
                        WHERE workspace_id = :workspace AND id = :id
                    """),
                        {"workspace": workspace_id, "id": other["id"], "owner": foreign_owner},
                    )
                assert getattr(violation.value.orig, "sqlstate", None) == "23503"

                reassigned = api.put(
                    f"{base}/{other['id']}",
                    headers=admin,
                    json=PAYLOAD | {"version": 1, "owner_id": str(engineer_id)},
                )
                assert reassigned.status_code == 200
                assert reassigned.json()["owner_id"] == str(engineer_id)
                assert api.delete(f"{members}/{engineer_id}", headers=admin).status_code == 204
                assert api.get(base, headers=engineer).status_code == 404
                assert api.get(f"{base}/{other['id']}", headers=admin).json()["owner_id"] is None
            finally:
                for user in created_users:
                    response = auth.delete(f"admin/users/{user}", headers=service_headers)
                    assert response.is_success, response.status_code
    finally:
        db.dispose()
        migration.dispose()
