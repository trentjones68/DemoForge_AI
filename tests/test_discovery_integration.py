import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import httpx2
import pytest
from demoforge_api.db import database_engine, workspace_transaction
from demoforge_api.discovery.parser import FORMAT_MIME, MAX_UPLOAD
from demoforge_api.discovery.storage import BUCKET, DiscoveryStorage, object_key
from demoforge_api.main import create_app
from demoforge_api.settings import Settings
from discovery_fixtures import WORD_NS, docx, pdf
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from test_auth import bearer
from test_supabase_integration import LocalSupabase, user_token

pytestmark = [pytest.mark.integration, pytest.mark.supabase]


def workspace(api: TestClient, headers: dict[str, str]) -> str:
    response = api.post("/v1/workspaces", headers=headers, json={"name": "Synthetic workspace"})
    assert response.status_code == 201, response.status_code
    return f"/v1/workspaces/{response.json()['id']}"


def opportunity(api: TestClient, headers: dict[str, str], workspace_path: str) -> str:
    path = f"{workspace_path}/opportunities"
    response = api.post(
        path,
        headers=headers,
        json={
            "name": "Synthetic opportunity",
            "company": "Example",
            "stage": "discovery",
            "product": "Test product",
        },
    )
    assert response.status_code == 201, response.status_code
    return f"{path}/{response.json()['id']}/discovery"


def session(api: TestClient, headers: dict[str, str], opportunity_path: str) -> str:
    response = api.post(
        opportunity_path,
        headers=headers,
        json={"title": "Synthetic discovery", "occurred_on": "2026-02-01"},
    )
    assert response.status_code == 201, response.status_code
    return f"{opportunity_path}/{response.json()['id']}/sources"


def import_headers(headers: dict[str, str], mime: str = "text/plain") -> dict[str, str]:
    return headers | {"Content-Type": mime, "x-import-consent": "true"}


@contextmanager
def permissive_storage_policy(engine: Engine) -> Iterator[None]:
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE POLICY discovery_test_overlap ON storage.objects FOR ALL TO authenticated
            USING (bucket_id = 'discovery-originals') WITH CHECK (bucket_id = 'discovery-originals')
        """)
        )
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP POLICY discovery_test_overlap ON storage.objects"))


def discovery_checks(
    api: TestClient,
    storage: httpx2.Client,
    headers_a: dict[str, str],
    headers_b: dict[str, str],
    db_engine: Engine,
    actor_b: UUID,
    workspace_a: str,
    workspace_b: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_a = opportunity(api, headers_a, workspace_a)
    path_b = opportunity(api, headers_b, workspace_b)
    sources_a = session(api, headers_a, path_a)
    sources_b = session(api, headers_b, path_b)
    other_a = session(api, headers_a, opportunity(api, headers_a, workspace_a))

    body = ("[00:01:03.200] Ana: Synthetic line.\n" + "Bo: Next.\n" * 52).encode()
    without_consent = api.post(
        sources_a, headers=headers_a | {"Content-Type": "text/plain"}, content=body
    )
    assert without_consent.status_code == 422 and "consent" in without_consent.json()["detail"]
    assert api.post(sources_a, headers=import_headers(headers_b), content=body).status_code == 404
    assert (
        api.post(
            sources_a, headers=import_headers(headers_a), content=b"x" * (MAX_UPLOAD + 1)
        ).status_code
        == 413
    )
    streamed = api.post(
        sources_a, headers=import_headers(headers_a), content=iter([b"x" * MAX_UPLOAD, b"y"])
    )
    assert streamed.status_code == 413
    assert (
        api.post(
            sources_a,
            headers=import_headers(headers_a, "image/png") | {"x-source-filename": "Fake.pdf"},
            content=body,
        ).status_code
        == 415
    )
    first_save = DiscoveryStorage.save

    def lose_response(self: DiscoveryStorage, key: str, fmt: str, raw: bytes) -> None:
        first_save(self, key, fmt, raw)
        raise HTTPException(503, "Synthetic interrupted storage reply")

    with monkeypatch.context() as patch:
        patch.setattr(DiscoveryStorage, "save", lose_response)
        assert (
            api.post(sources_a, headers=import_headers(headers_a), content=body).status_code == 503
        )
    assert api.get(sources_a, headers=headers_a).json() == []

    response = api.post(sources_a, headers=import_headers(headers_a), content=body)
    assert response.status_code == 201, response.json()
    source_id = response.json()["source"]["id"]
    duplicate = api.post(sources_a, headers=import_headers(headers_a), content=body)
    assert duplicate.status_code == 200
    assert duplicate.json()["source"]["id"] == source_id and duplicate.json()["duplicate"] is True
    assert duplicate.headers["Cache-Control"] == "no-store"

    separate = api.post(
        f"{sources_a}?kind=summary&provider=plaud", headers=import_headers(headers_a), content=body
    )
    assert separate.status_code == 201 and separate.json()["source"]["id"] != source_id
    other_session = api.post(other_a, headers=import_headers(headers_a), content=body)
    assert other_session.status_code == 201 and other_session.json()["source"]["id"] != source_id

    word = docx(
        f'<w:document xmlns:w="{WORD_NS}"><w:body><w:p><w:r>'
        "<w:t>Example summary</w:t></w:r></w:p></w:body></w:document>"
    )
    file_headers = import_headers(headers_a, FORMAT_MIME["docx"]) | {
        "x-source-filename": "Plaud%20export.docx",
    }
    summary = api.post(
        f"{sources_a}?kind=summary&provider=plaud", headers=file_headers, content=word
    )
    assert summary.status_code == 201
    assert summary.json()["source"]["provider"] == "plaud"
    assert summary.json()["source"]["kind"] == "summary"

    pdf_headers = import_headers(headers_a, FORMAT_MIME["pdf"]) | {
        "x-source-filename": "Export.pdf",
    }
    scanned = api.post(sources_a, headers=pdf_headers, content=pdf(False))
    assert scanned.status_code == 422 and "Run OCR" in scanned.json()["detail"]
    assert api.post(sources_a, headers=pdf_headers, content=pdf(True)).status_code == 201
    assert (
        api.post(
            sources_a,
            headers=import_headers(headers_a, "text/markdown")
            | {
                "x-source-filename": "Export.md",
            },
            content=b"# Synthetic Markdown",
        ).status_code
        == 201
    )

    segment_path = f"{sources_a}/{source_id}/segments"
    evidence = api.get(segment_path, headers=headers_a)
    assert evidence.status_code == 200
    segment = evidence.json()["segments"][0]
    assert (segment["speaker"], segment["start_ms"], segment["start_offset"]) == ("Ana", 63200, 0)
    assert evidence.json()["has_next"]
    page_two = api.get(f"{segment_path}?page=2", headers=headers_a)
    assert page_two.json()["segments"][0]["ordinal"] == 50
    assert api.get(segment_path, headers=headers_a).json()["segments"][0]["id"] == segment["id"]
    assert api.get(segment_path, headers=headers_b).status_code == 404
    assert api.get(f"{sources_b}/{source_id}/segments", headers=headers_b).status_code == 404
    assert api.get(f"{other_a}/{source_id}/segments", headers=headers_a).status_code == 404
    wrong_parent = f"{path_b}/{sources_a.split('/')[-2]}/sources"
    assert api.get(wrong_parent, headers=headers_b).status_code == 404

    original_path = f"{sources_a}/{source_id}/original"
    assert api.post(original_path, headers=headers_b).status_code == 404
    key = object_key(
        UUID(workspace_a.split("/")[-1]), UUID(sources_a.split("/")[-2]), UUID(source_id), "txt"
    )
    for headers in (headers_a, headers_b):
        assert not storage.get(f"object/authenticated/{BUCKET}/{key}", headers=headers).is_success
        assert not storage.post(
            f"object/sign/{BUCKET}/{key}", headers=headers, json={"expiresIn": 60}
        ).is_success
        assert not storage.post(
            f"object/{BUCKET}/{key}",
            content=b"Override",
            headers=(headers | {"Content-Type": "text/plain", "x-upsert": "true"}),
        ).is_success
    assert not storage.get(f"object/public/{BUCKET}/{key}").is_success
    signed = api.post(original_path, headers=headers_a)
    assert signed.status_code == 200, signed.json()
    downloaded = storage.get(signed.json()["url"])
    assert downloaded.status_code == 200 and downloaded.content == body
    assert "attachment" in downloaded.headers["Content-Disposition"]
    assert len(api.get(sources_a, headers=headers_a).json()) == 5

    member_url = f"{workspace_a}/members/{actor_b}"
    assert api.put(member_url, headers=headers_a, json={"role": "viewer"}).status_code == 200
    assert api.get(sources_a, headers=headers_b).status_code == 403
    assert (
        api.put(member_url, headers=headers_a, json={"role": "sales_engineer"}).status_code == 200
    )
    assert api.get(sources_a, headers=headers_b).status_code == 200
    assert api.post(sources_a, headers=import_headers(headers_b), content=body).status_code == 403
    assert api.delete(member_url, headers=headers_a).status_code == 204
    assert api.post(original_path, headers=headers_b).status_code == 404

    with workspace_transaction(db_engine, actor_b) as connection:
        for table in (
            "discovery_sessions",
            "source_documents",
            "transcript_segments",
            "discovery_audit_events",
        ):
            assert (
                connection.execute(
                    text(f"""
                SELECT count(*) FROM demoforge.{table} WHERE workspace_id = :workspace
            """),
                    {"workspace": workspace_a.split("/")[-1]},
                ).scalar_one()
                == 0
            )
    with pytest.raises(DBAPIError) as rejected, workspace_transaction(db_engine, actor_b) as conn:
        conn.execute(
            text("""
            INSERT INTO demoforge.discovery_sessions (workspace_id, opportunity_id, id, title)
            VALUES (:workspace, :opportunity, :id, 'Synthetic cross-tenant insert')
        """),
            {
                "workspace": workspace_a.split("/")[-1],
                "opportunity": path_a.split("/")[-2],
                "id": uuid4(),
            },
        )
    assert getattr(rejected.value.orig, "sqlstate", None) == "42501"


def test_discovery_is_private_and_recoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    status_file = os.environ.get("TEST_SUPABASE_STATUS_FILE")
    if not status_file:
        pytest.skip("Set TEST_SUPABASE_STATUS_FILE for a disposable Supabase instance")
    local = LocalSupabase.model_validate_json(Path(status_file).read_text())
    assert all(
        url.host in ("127.0.0.1", "localhost")
        for url in (local.api_url, local.auth_url, local.storage_url)
        if url is not None
    )
    storage_url = HttpUrl(f"{str(local.api_url).rstrip('/')}/storage/v1")
    settings = Settings(
        supabase_jwt_issuer=HttpUrl(local.issuer),
        supabase_jwt_secret=None,
        supabase_jwks_url=HttpUrl(f"{local.issuer}/.well-known/jwks.json"),
        supabase_storage_url=storage_url,
        supabase_storage_service_key=local.service_key,
    )
    assert settings.migration_database_url and settings.database_url
    assert all(
        make_url(str(dsn)).host in ("localhost", "127.0.0.1")
        for dsn in (settings.database_url, settings.migration_database_url)
    )
    migration_engine = create_engine(str(settings.migration_database_url))
    request_engine = database_engine(settings.database_url)
    service = local.service_key.get_secret_value()
    service_headers = bearer(service) | {"apikey": service}
    users: list[str] = []
    workspaces: list[str] = []
    try:
        with (
            TestClient(create_app(settings)) as api,
            httpx2.Client(base_url=f"{local.issuer}/", timeout=10) as auth,
            httpx2.Client(base_url=f"{str(storage_url).rstrip('/')}/", timeout=10) as storage,
            permissive_storage_policy(migration_engine),
        ):
            a = bearer(user_token(auth, local, "discovery-a", users))
            b = bearer(user_token(auth, local, "discovery-b", users))
            anon = {"apikey": local.anon_key.get_secret_value()}
            try:
                workspaces.append(workspace(api, a))
                workspaces.append(workspace(api, b))
                discovery_checks(
                    api,
                    storage,
                    a | anon,
                    b | anon,
                    request_engine,
                    UUID(users[1]),
                    workspaces[0],
                    workspaces[1],
                    monkeypatch,
                )
            finally:
                # Remove only originals created by this test.
                with migration_engine.connect() as connection:
                    objects = (
                        connection.execute(
                            text("""
                                SELECT name FROM storage.objects WHERE bucket_id = :bucket
                                    AND split_part(name, '/', 1) = ANY(:workspaces)
                            """),
                            {
                                "bucket": BUCKET,
                                "workspaces": [path.split("/")[-1] for path in workspaces],
                            },
                        )
                        .scalars()
                        .all()
                    )
                if objects:
                    removed = storage.request(
                        "DELETE",
                        f"object/{BUCKET}",
                        headers=service_headers,
                        json={"prefixes": list(objects)},
                    )
                    assert removed.is_success, removed.status_code
                for user in users:
                    assert auth.delete(f"admin/users/{user}", headers=service_headers).is_success
    finally:
        migration_engine.dispose()
        request_engine.dispose()
