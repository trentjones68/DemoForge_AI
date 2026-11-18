import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from demoforge_api.db import workspace_transaction
from demoforge_api.main import create_app
from demoforge_api.settings import Settings
from fastapi.testclient import TestClient
from pydantic import HttpUrl, SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from test_auth import ISSUER, TEST_SIGNING_KEY, bearer, token_for

pytestmark = pytest.mark.integration


@pytest.fixture
def databases() -> Iterator[tuple[Engine, Engine, Settings]]:
    if os.environ.get("DEMOFORGE_TEST_DATABASE") != "1":
        pytest.skip("Set DEMOFORGE_TEST_DATABASE=1 with a disposable migrated local database")
    settings = Settings(
        supabase_jwt_issuer=HttpUrl(ISSUER),
        supabase_jwt_secret=SecretStr(TEST_SIGNING_KEY),
        supabase_jwks_url=None,
    )
    assert settings.database_url and settings.migration_database_url
    for dsn in (settings.database_url, settings.migration_database_url):
        assert make_url(str(dsn)).host in ("localhost", "127.0.0.1")
    request = create_engine(str(settings.database_url), pool_size=1, max_overflow=0)
    migration = create_engine(str(settings.migration_database_url))
    try:
        yield request, migration, settings
    finally:
        request.dispose()
        migration.dispose()


@pytest.fixture
def seeded_workspaces(
    databases: tuple[Engine, Engine, Settings],
) -> Iterator[tuple[UUID, UUID, UUID, UUID]]:
    _, migration, _ = databases
    actor_a, actor_b, workspace_a, workspace_b = (uuid4() for _ in range(4))
    with migration.begin() as connection:
        for workspace, actor, name in (
            (workspace_a, actor_a, "Synthetic workspace A"),
            (workspace_b, actor_b, "Synthetic workspace B"),
        ):
            connection.execute(
                text("INSERT INTO demoforge.workspaces VALUES (:id, :name)"),
                {"id": workspace, "name": name},
            )
            connection.execute(
                text("INSERT INTO demoforge.memberships VALUES (:id, :actor, 'admin')"),
                {"id": workspace, "actor": actor},
            )
    try:
        yield actor_a, actor_b, workspace_a, workspace_b
    finally:
        with migration.begin() as connection:
            connection.execute(
                text("DELETE FROM demoforge.workspaces WHERE id IN (:a, :b)"),
                {"a": workspace_a, "b": workspace_b},
            )


def test_api_workspaces_and_live_membership_revocation(
    databases: tuple[Engine, Engine, Settings],
    seeded_workspaces: tuple[UUID, UUID, UUID, UUID],
) -> None:
    _, migration, settings = databases
    actor_a, actor_b, workspace_a, workspace_b = seeded_workspaces
    headers_a, headers_b = (bearer(token_for(str(actor))) for actor in (actor_a, actor_b))
    created_workspace: str | None = None

    try:
        with TestClient(create_app(settings)) as client:
            assert [
                row["id"] for row in client.get("/v1/workspaces", headers=headers_a).json()
            ] == [str(workspace_a)]
            assert client.get(f"/v1/workspaces/{workspace_b}", headers=headers_a).status_code == 404
            assert (
                client.patch(
                    f"/v1/workspaces/{workspace_b}", headers=headers_a, json={"name": "Blocked"}
                ).status_code
                == 404
            )
            members_b = f"/v1/workspaces/{workspace_b}/members"
            assert client.get(members_b, headers=headers_a).status_code == 404
            assert (
                client.put(
                    f"{members_b}/{actor_a}", headers=headers_a, json={"role": "viewer"}
                ).status_code
                == 404
            )
            assert client.delete(f"{members_b}/{actor_b}", headers=headers_a).status_code == 404
            assert client.get(f"/v1/workspaces/{workspace_b}", headers=headers_b).json()[
                "name"
            ] == ("Synthetic workspace B")

            renamed = client.patch(
                f"/v1/workspaces/{workspace_a}",
                headers=headers_a,
                json={"name": "Renamed synthetic workspace"},
            )
            assert (
                renamed.status_code == 200
                and renamed.json()["name"] == "Renamed synthetic workspace"
            )
            assert (
                client.post(
                    "/v1/workspaces",
                    headers=headers_a,
                    json={"name": "Invalid", "workspace_id": str(workspace_b)},
                ).status_code
                == 422
            )

            created = client.post(
                "/v1/workspaces", headers=headers_a, json={"name": "New synthetic workspace"}
            )
            assert created.status_code == 201
            created_workspace = created.json()["id"]
            assert created.json()["role"] == "admin"
            assert (
                client.get(f"/v1/workspaces/{created_workspace}", headers=headers_b).status_code
                == 404
            )

            for role in ("viewer", "product_admin", "sales_engineer"):
                member = client.put(
                    f"{members_b}/{actor_a}", headers=headers_b, json={"role": role}
                )
                assert member.status_code == 200
                assert (
                    client.get(f"/v1/workspaces/{workspace_b}", headers=headers_a).json()["role"]
                    == role
                )
                assert {
                    row["id"] for row in client.get("/v1/workspaces", headers=headers_a).json()
                } == {str(workspace_a), str(workspace_b), created_workspace}
                assert (
                    client.patch(
                        f"/v1/workspaces/{workspace_b}", headers=headers_a, json={"name": "Blocked"}
                    ).status_code
                    == 403
                )
                assert client.get(members_b, headers=headers_a).status_code == 403

            assert (
                client.put(
                    f"{members_b}/{actor_a}", headers=headers_b, json={"role": "admin"}
                ).status_code
                == 422
            )
            assert client.put(
                f"{members_b}/{actor_b}", headers=headers_b, json={"role": "viewer"}
            ).status_code in (403, 404)
            assert client.delete(f"{members_b}/{actor_b}", headers=headers_b).status_code == 404
            assert client.delete(f"{members_b}/{actor_a}", headers=headers_b).status_code == 204
            assert client.get(f"/v1/workspaces/{workspace_b}", headers=headers_a).status_code == 404
    finally:
        if created_workspace:
            with migration.begin() as connection:
                connection.execute(
                    text("DELETE FROM demoforge.workspaces WHERE id = :id"),
                    {"id": created_workspace},
                )


def test_database_rls_and_pool_cleanup(
    databases: tuple[Engine, Engine, Settings],
    seeded_workspaces: tuple[UUID, UUID, UUID, UUID],
) -> None:
    database, _, _ = databases
    actor_a, actor_b, workspace_a, workspace_b = seeded_workspaces

    with workspace_transaction(database, actor_a) as connection:
        backend = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert connection.execute(text("SELECT id FROM demoforge.workspaces")).scalars().all() == [
            workspace_a
        ]
        for statement in (
            "UPDATE demoforge.workspaces SET name = 'blocked' WHERE id = :id RETURNING id",
            "DELETE FROM demoforge.memberships WHERE workspace_id = :id RETURNING user_id",
        ):
            assert not connection.execute(text(statement), {"id": workspace_b}).all()

    with database.connect() as connection:
        assert connection.execute(text("SELECT pg_backend_pid()")).scalar_one() == backend
        assert connection.execute(text("SELECT demoforge.request_subject()")).scalar_one() is None
        assert not connection.execute(text("SELECT id FROM demoforge.workspaces")).all()

    with pytest.raises(ProgrammingError) as denied:
        with workspace_transaction(database, actor_a) as connection:
            connection.execute(
                text("INSERT INTO demoforge.memberships VALUES (:id, :actor, 'viewer')"),
                {"id": workspace_b, "actor": actor_a},
            )
    assert getattr(denied.value.orig, "sqlstate", None) == "42501"

    with database.connect() as connection:
        assert connection.execute(text("SELECT pg_backend_pid()")).scalar_one() == backend
        assert connection.execute(text("SELECT demoforge.request_subject()")).scalar_one() is None

    with workspace_transaction(database, actor_b) as connection:
        assert connection.execute(text("SELECT pg_backend_pid()")).scalar_one() == backend
        assert connection.execute(text("SELECT id FROM demoforge.workspaces")).scalars().all() == [
            workspace_b
        ]
