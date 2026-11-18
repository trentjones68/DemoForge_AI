import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import httpx2
import pytest
from demoforge_api.main import create_app
from demoforge_api.settings import Settings
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, HttpUrl, SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from test_auth import bearer

pytestmark = [pytest.mark.integration, pytest.mark.supabase]
BUCKET = "workspace-files"


class LocalSupabase(BaseModel):
    api_url: HttpUrl = Field(alias="API_URL")
    anon_key: SecretStr = Field(alias="ANON_KEY")
    service_key: SecretStr = Field(alias="SERVICE_ROLE_KEY")
    auth_url: HttpUrl | None = Field(default=None, alias="AUTH_URL")
    storage_url: HttpUrl | None = Field(default=None, alias="STORAGE_URL")

    @property
    def issuer(self) -> str:
        return f"{str(self.api_url).rstrip('/')}/auth/v1"


def user_token(
    auth: httpx2.Client, local: LocalSupabase, label: str, created_users: list[str]
) -> str:
    email = f"{label}-{uuid4().hex}@example.test"
    password = secrets.token_urlsafe(24)
    service = local.service_key.get_secret_value()
    response = auth.post(
        "admin/users",
        headers=bearer(service) | {"apikey": service},
        json={"email": email, "password": password, "email_confirm": True},
    )
    assert response.status_code in (200, 201), response.status_code
    created_users.append(response.json()["id"])
    response = auth.post(
        "token",
        params={"grant_type": "password"},
        headers={"apikey": local.anon_key.get_secret_value()},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.status_code
    token = response.json()["access_token"]
    assert isinstance(token, str)
    return token


@contextmanager
def overlapping_storage_policy(migration_dsn: str) -> Iterator[None]:
    # The DemoForge boundary must still hold if a project has a permissive policy.
    assert make_url(migration_dsn).host in ("localhost", "127.0.0.1")
    engine = create_engine(migration_dsn)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                    CREATE POLICY demoforge_test_overlap ON storage.objects FOR ALL TO authenticated
                    USING (bucket_id = 'workspace-files') WITH CHECK (bucket_id = 'workspace-files')
                """)
            )
        try:
            yield
        finally:
            with engine.begin() as connection:
                connection.execute(text("DROP POLICY demoforge_test_overlap ON storage.objects"))
    finally:
        engine.dispose()


def test_real_supabase_auth_and_storage_are_workspace_scoped() -> None:
    status_file = os.environ.get("TEST_SUPABASE_STATUS_FILE")
    if not status_file:
        pytest.skip("Set TEST_SUPABASE_STATUS_FILE for a disposable Supabase instance")
    local = LocalSupabase.model_validate_json(Path(status_file).read_text())
    assert all(
        url.host in ("127.0.0.1", "localhost")
        for url in (local.api_url, local.auth_url, local.storage_url)
        if url is not None
    ), "Use a disposable local stack"
    settings = Settings(
        supabase_jwt_issuer=HttpUrl(local.issuer),
        supabase_jwt_secret=None,
        supabase_jwks_url=HttpUrl(f"{local.issuer}/.well-known/jwks.json"),
    )
    assert settings.migration_database_url and settings.database_url
    assert make_url(str(settings.database_url)).host in ("localhost", "127.0.0.1")
    app = create_app(settings)
    auth_url = str(local.auth_url or local.issuer).rstrip("/") + "/"
    storage_url = str(local.storage_url or f"{str(local.api_url).rstrip('/')}/storage/v1")
    created_users: list[str] = []
    created_workspaces: list[UUID] = []
    created_objects: list[str] = []
    anon = local.anon_key.get_secret_value()
    service = local.service_key.get_secret_value()
    service_headers = bearer(service) | {"apikey": service}
    suffix = uuid4().hex

    with (
        overlapping_storage_policy(str(settings.migration_database_url)),
        httpx2.Client(base_url=auth_url, timeout=10) as auth,
        httpx2.Client(base_url=storage_url, timeout=10) as storage,
        TestClient(app) as api,
    ):
        try:
            head_a = bearer(user_token(auth, local, "a", created_users)) | {"apikey": anon}
            head_b = bearer(user_token(auth, local, "b", created_users)) | {"apikey": anon}
            for label, headers in (("A", head_a), ("B", head_b)):
                response = api.post(
                    "/v1/workspaces", headers=headers, json={"name": f"Synthetic {label}"}
                )
                assert response.status_code == 201, response.status_code
                created_workspaces.append(UUID(response.json()["id"]))
            workspace_a, workspace_b = created_workspaces
            path_a, path_b = (f"{workspace}/{suffix}.txt" for workspace in created_workspaces)
            assert api.get(f"/v1/workspaces/{workspace_b}", headers=head_a).status_code == 404

            for path, headers, content in (
                (path_a, head_a, b"Synthetic A"),
                (path_b, head_b, b"Synthetic B"),
            ):
                response = storage.post(
                    f"object/{BUCKET}/{path}",
                    content=content,
                    headers=headers | {"Content-Type": "text/plain"},
                )
                assert response.is_success, response.status_code
                created_objects.append(path)

            private_b = f"object/authenticated/{BUCKET}/{path_b}"
            public_b = f"object/public/{BUCKET}/{path_b}"
            assert not storage.get(public_b).is_success
            assert storage.get(private_b, headers=head_b).content == b"Synthetic B"
            assert not storage.get(private_b, headers=head_a).is_success
            assert not storage.post(
                f"object/sign/{BUCKET}/{path_b}", headers=head_a, json={"expiresIn": 60}
            ).is_success
            assert not storage.post(
                f"object/{BUCKET}/{path_b}",
                content=b"Overwrite attempt",
                headers=head_a | {"Content-Type": "text/plain", "x-upsert": "true"},
            ).is_success
            assert not storage.post(
                f"object/{BUCKET}/{workspace_b}/blocked-{suffix}.txt",
                content=b"Insert attempt",
                headers=head_a | {"Content-Type": "text/plain"},
            ).is_success
            assert not storage.post(
                "object/move",
                headers=head_a,
                json={
                    "bucketId": BUCKET,
                    "sourceKey": path_a,
                    "destinationKey": f"{workspace_b}/moved-{suffix}.txt",
                },
            ).is_success
            listed = storage.post(
                f"object/list/{BUCKET}", headers=head_a, json={"prefix": f"{workspace_b}/"}
            )
            assert listed.is_success and listed.json() == []
            # Storage may return success with an empty deletion list for invisible objects.
            storage.request(
                "DELETE", f"object/{BUCKET}", headers=head_a, json={"prefixes": [path_b]}
            )
            assert storage.get(private_b, headers=head_b).content == b"Synthetic B"

            missing_member = f"/v1/workspaces/{workspace_b}/members/{uuid4()}"
            assert (
                api.put(missing_member, headers=head_b, json={"role": "viewer"}).status_code == 404
            )
            members_b = f"/v1/workspaces/{workspace_b}/members/{created_users[0]}"
            for role in ("viewer", "product_admin", "sales_engineer"):
                assert api.put(members_b, headers=head_b, json={"role": role}).status_code == 200
                assert storage.get(private_b, headers=head_a).is_success == (
                    role == "sales_engineer"
                )
            assert api.delete(members_b, headers=head_b).status_code == 204
            assert not storage.get(private_b, headers=head_a).is_success
        finally:
            if created_objects:
                deleted = storage.request(
                    "DELETE",
                    f"object/{BUCKET}",
                    headers=service_headers,
                    json={"prefixes": created_objects},
                )
                assert deleted.is_success, deleted.status_code
            # The test uses disposable databases. The test runner rolls back its migrations.
            for user in created_users:
                response = auth.delete(f"admin/users/{user}", headers=service_headers)
                assert response.is_success, response.status_code
