"""Real Supabase planning authorization, evidence lineage, and revision history."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import httpx2
import pytest
from demoforge_api.analysis.routes import Review
from demoforge_api.db import database_engine
from demoforge_api.discovery.storage import BUCKET
from demoforge_api.main import create_app
from demoforge_api.planning.models import Plan, PlanItem
from demoforge_api.settings import Settings
from demoforge_worker.discovery import DiscoveryWorker, SyntheticProvider
from fastapi.testclient import TestClient
from pydantic import HttpUrl, SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from test_analysis_integration import start_run
from test_auth import bearer
from test_discovery_integration import import_headers, opportunity, session, workspace
from test_supabase_integration import LocalSupabase

pytestmark = [pytest.mark.integration, pytest.mark.supabase]

REQUIREMENT = "Export a monthly audit report."
UNAPPROVED = "Publish drafts automatically."
TRANSCRIPT = f"Synthetic requirement: {REQUIREMENT}\nSynthetic requirement: {UNAPPROVED}\n".encode()


@dataclass(frozen=True)
class Account:
    id: UUID
    email: str
    password: SecretStr
    token: SecretStr

    @property
    def headers(self) -> dict[str, str]:
        return bearer(self.token.get_secret_value())

    def browser_login(self) -> dict[str, str]:
        return {"email": self.email, "password": self.password.get_secret_value()}


@dataclass(frozen=True)
class PlanningCase:
    api: TestClient
    settings: Settings
    local: LocalSupabase
    owner: Account
    peer: Account
    outsider: Account
    workspace: str
    opportunity: str
    plan: str
    analysis_run: str

    @property
    def approved(self) -> str:
        return self.opportunity.removesuffix("/discovery") + "/approved-requirements"

    def get_plan(self) -> Plan:
        response = self.api.get(self.plan, headers=self.owner.headers)
        assert response.status_code == 200, response.status_code
        return Plan.model_validate_json(response.content)


def register(auth: httpx2.Client, local: LocalSupabase, created: list[UUID]) -> Account:
    service = local.service_key.get_secret_value()
    email = f"planning-{uuid4().hex}@example.test"
    password = secrets.token_urlsafe(24)
    response = auth.post(
        "admin/users",
        headers=bearer(service) | {"apikey": service},
        json={"email": email, "password": password, "email_confirm": True},
    )
    assert response.is_success, response.status_code
    actor = UUID(response.json()["id"])
    created.append(actor)
    response = auth.post(
        "token",
        params={"grant_type": "password"},
        headers={"apikey": local.anon_key.get_secret_value()},
        json={"email": email, "password": password},
    )
    assert response.is_success, response.status_code
    return Account(actor, email, SecretStr(password), SecretStr(response.json()["access_token"]))


@pytest.fixture
def planning_case() -> Iterator[PlanningCase]:
    status = os.environ.get("TEST_SUPABASE_STATUS_FILE")
    if not status:
        pytest.skip("Set TEST_SUPABASE_STATUS_FILE for a disposable Supabase instance")
    local = LocalSupabase.model_validate_json(Path(status).read_text())
    assert local.api_url.host in ("127.0.0.1", "localhost")
    settings = Settings(
        supabase_jwt_issuer=HttpUrl(local.issuer),
        supabase_jwt_secret=None,
        supabase_jwks_url=HttpUrl(f"{local.issuer}/.well-known/jwks.json"),
        supabase_storage_url=HttpUrl(f"{str(local.api_url).rstrip('/')}/storage/v1"),
        supabase_storage_service_key=local.service_key,
        discovery_provider="fake",
        discovery_synthetic_dev=True,
    )
    assert settings.database_url and settings.migration_database_url
    assert settings.discovery_worker_database_url
    assert all(
        make_url(str(dsn)).host in ("localhost", "127.0.0.1")
        for dsn in (
            settings.database_url,
            settings.migration_database_url,
            settings.discovery_worker_database_url,
        )
    )
    migration = create_engine(str(settings.migration_database_url))
    worker = database_engine(settings.discovery_worker_database_url)
    users: list[UUID] = []
    workspaces: list[str] = []
    service = local.service_key.get_secret_value()
    service_headers = bearer(service) | {"apikey": service}
    try:
        with (
            TestClient(create_app(settings)) as api,
            httpx2.Client(base_url=f"{local.issuer}/", timeout=10) as auth,
            httpx2.Client(base_url=f"{settings.supabase_storage_url}/", timeout=10) as storage,
        ):
            try:
                owner, peer, outsider = [register(auth, local, users) for _ in range(3)]
                ws = workspace(api, owner.headers)
                workspaces.append(ws.rsplit("/", 1)[1])
                membership = api.put(
                    f"{ws}/members/{peer.id}",
                    headers=owner.headers,
                    json={"role": "sales_engineer"},
                )
                assert membership.status_code == 200, membership.status_code
                opp = opportunity(api, owner.headers, ws)
                source = session(api, owner.headers, opp)
                imported = api.post(
                    source, headers=import_headers(owner.headers), content=TRANSCRIPT
                )
                assert imported.status_code == 201, imported.status_code
                base = source.removesuffix("/sources")
                run = start_run(api, f"{base}/analysis", owner.headers)
                assert DiscoveryWorker(worker, SyntheticProvider()).run_once()
                yield PlanningCase(
                    api, settings, local, owner, peer, outsider, ws, opp, f"{base}/plan", run
                )
            finally:
                with migration.connect() as connection:
                    originals = (
                        connection.execute(
                            text("""
                        SELECT name FROM storage.objects WHERE bucket_id = :bucket
                          AND split_part(name, '/', 1) = ANY(:workspaces)
                    """),
                            {"bucket": BUCKET, "workspaces": workspaces},
                        )
                        .scalars()
                        .all()
                    )
                if originals:
                    removed = storage.request(
                        "DELETE",
                        f"object/{BUCKET}",
                        headers=service_headers,
                        json={"prefixes": list(originals)},
                    )
                    assert removed.is_success, removed.status_code
                for user in users:
                    assert auth.delete(f"admin/users/{user}", headers=service_headers).is_success
    finally:
        migration.dispose()
        worker.dispose()


def test_only_approved_current_revisions_can_feed_storyboards(planning_case: PlanningCase) -> None:
    case = planning_case
    api, headers = case.api, case.owner.headers
    assert not case.get_plan().has_approved_insights
    assert api.post(f"{case.plan}/normalize", headers=headers).status_code == 409
    assert api.get(case.approved, headers=headers).json() == []
    review = Review.model_validate_json(api.get(case.analysis_run, headers=headers).content)
    source = next(finding for finding in review.findings if finding.statement == REQUIREMENT)
    finding = f"{case.analysis_run}/findings/{source.id}"
    assert api.post(f"{finding}/approve", headers=headers, json={"revision": 1}).status_code == 200

    created = api.post(f"{case.plan}/normalize", headers=headers)
    assert created.status_code == 200, created.status_code
    assert created.json() == {"added": 5}
    assert api.post(f"{case.plan}/normalize", headers=headers).json() == {"added": 0}
    plan = case.get_plan()
    assert plan.has_approved_insights
    requirements = [item for item in plan.items if item.kind == "requirement"]
    assert [item.statement for item in requirements] == [REQUIREMENT]
    requirement = requirements[0]
    assert requirement.evidence == source.evidence and requirement.source_revision == 1
    gaps = [item for item in plan.items if item.kind == "gap"]
    assert [item.priority for item in gaps] == ["high", "high", "medium", "medium"]
    assert {item.category for item in gaps} == {"buyer", "kpi", "workflow", "integration"}
    workflow = next(item for item in gaps if item.category == "workflow")
    assert workflow.affected_requirement_ids == [requirement.id]
    assert api.get(case.approved, headers=headers).json() == []

    item = f"{case.plan}/items/{requirement.id}"
    assert api.post(f"{item}/approve", headers=headers, json={"revision": 1}).status_code == 200
    assert [row["id"] for row in api.get(case.approved, headers=headers).json()] == [
        str(requirement.id)
    ]
    update = {
        "revision": 1,
        "statement": "Export the reviewed audit report.",
        "rationale": "Confirmed by the reviewer.",
        "category": "workflow",
        "priority": "high",
    }
    response = api.put(item, headers=headers, json=update)
    assert response.status_code == 200, response.status_code
    revised = PlanItem.model_validate_json(response.content)
    assert revised.revision == 2 and revised.approved_at is None
    assert revised.evidence == requirement.evidence
    assert api.put(item, headers=headers, json=update).status_code == 409
    assert api.post(f"{item}/approve", headers=headers, json={"revision": 1}).status_code == 409
    assert api.get(case.approved, headers=headers).json() == []
    for _ in range(2):
        assert api.post(f"{item}/approve", headers=headers, json={"revision": 2}).status_code == 200

    upstream = {"revision": 1, "statement": "Export archived reports.", "rationale": "Updated."}
    assert api.put(finding, headers=headers, json=upstream).status_code == 200
    stale = next(entry for entry in case.get_plan().items if entry.id == requirement.id)
    assert stale.stale_source and stale.evidence == requirement.evidence
    assert api.get(case.approved, headers=headers).json() == []
    assert api.post(f"{item}/approve", headers=headers, json={"revision": 2}).status_code == 409
    history = api.get(f"{item}/history", headers=headers).json()
    assert [row["revision"] for row in history] == [2, 1]
    assert all(row["approved_by"] == str(case.owner.id) for row in history)
    assert api.post(f"{finding}/approve", headers=headers, json={"revision": 2}).status_code == 200
    assert api.post(f"{case.plan}/normalize", headers=headers).json() == {"added": 1}
    assert api.get(case.approved, headers=headers).json() == []


def test_manual_planning_permissions_status_and_audit(planning_case: PlanningCase) -> None:
    case = planning_case
    api, headers = case.api, case.owner.headers
    fields = {
        "statement": "Retain reports for review.",
        "rationale": "Manual requirement.",
        "category": "general",
        "priority": "medium",
    }
    result = api.post(f"{case.plan}/items", headers=headers, json=fields | {"kind": "requirement"})
    assert result.status_code == 201, result.status_code
    requirement = PlanItem.model_validate_json(result.content)
    assert (
        not requirement.generated and not requirement.evidence and requirement.approved_at is None
    )
    gap_fields = fields | {
        "statement": "Who signs off?",
        "owner_id": str(case.peer.id),
        "status": "open",
        "affected_requirement_ids": [str(requirement.id)],
    }
    for outsider in (case.peer, case.outsider):
        expected = 403 if outsider == case.peer else 404
        assert (
            api.post(
                f"{case.plan}/items", headers=outsider.headers, json=gap_fields | {"kind": "gap"}
            ).status_code
            == expected
        )
        assert api.get(case.plan, headers=outsider.headers).status_code == (
            200 if outsider == case.peer else 404
        )
    wrong_owner = gap_fields | {"kind": "gap", "owner_id": str(case.outsider.id)}
    assert api.post(f"{case.plan}/items", headers=headers, json=wrong_owner).status_code == 422

    other_session = session(api, headers, case.opportunity).removesuffix("/sources") + "/plan"
    assert (
        api.post(
            f"{other_session}/items", headers=headers, json=gap_fields | {"kind": "gap"}
        ).status_code
        == 422
    )
    response = api.post(f"{case.plan}/items", headers=headers, json=gap_fields | {"kind": "gap"})
    assert response.status_code == 201, response.status_code
    gap = PlanItem.model_validate_json(response.content)
    path = f"{case.plan}/items/{gap.id}"
    assert (
        api.put(
            path,
            headers=headers,
            json=gap_fields
            | {
                "revision": 1,
                "status": "resolved",
            },
        ).status_code
        == 200
    )
    assert (
        api.post(f"{path}/approve", headers=case.peer.headers, json={"revision": 2}).status_code
        == 403
    )
    assert api.post(f"{path}/approve", headers=headers, json={"revision": 2}).status_code == 200
    history = api.get(f"{path}/history", headers=headers).json()
    assert [row["status"] for row in history] == ["resolved", "open"]
    assert all(row["owner_id"] == str(case.peer.id) for row in history)
    assert all(row["affected_requirement_ids"] == [str(requirement.id)] for row in history)
    assert api.get(case.approved, headers=headers).json() == []
    assert (
        api.post(
            f"{case.plan}/items/{requirement.id}/approve", headers=headers, json={"revision": 1}
        ).status_code
        == 200
    )
    assert len(api.get(case.approved, headers=headers).json()) == 1
    assert api.get(case.approved, headers=case.outsider.headers).status_code == 404
    assert (
        api.put(
            f"{case.workspace}/members/{case.peer.id}", headers=headers, json={"role": "viewer"}
        ).status_code
        == 200
    )
    assert api.get(case.plan, headers=case.peer.headers).status_code == 403


def ephemeral_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def start_service(
    services: ExitStack,
    command: list[str],
    env: dict[str, str],
) -> subprocess.Popen[bytes]:
    child = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop() -> None:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

    services.callback(stop)
    return child


def wait_for_http(url: str, child: subprocess.Popen[bytes]) -> None:
    with httpx2.Client(timeout=1, trust_env=False) as client:
        for _ in range(30):
            assert child.poll() is None, "The local UI test service exited"
            try:
                if client.get(url).is_success:
                    return
            except httpx2.RequestError:
                pass
            time.sleep(1)
    raise AssertionError("The local UI test service did not become ready")


@pytest.mark.skipif(os.environ.get("DEMOFORGE_BROWSER_TEST") != "1", reason="Enable browser tests")
def test_planning_browser_state_transitions_and_permissions(planning_case: PlanningCase) -> None:
    case = planning_case
    assert case.settings.database_url
    api_port, web_port = ephemeral_port(), ephemeral_port()
    while api_port == web_port:
        web_port = ephemeral_port()
    api_url, web_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    browser_environment = {
        "PATH",
        "HOME",
        "LANG",
        "TZ",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "PLAYWRIGHT_BROWSERS_PATH",
        "DEMOFORGE_BROWSER_EXECUTABLE",
    }
    base_env = {name: value for name, value in os.environ.items() if name in browser_environment}
    with ExitStack() as services:
        api = start_service(
            services,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "demoforge_api.main:create_app",
                "--factory",
                "--app-dir",
                "services/api",
                "--port",
                str(api_port),
            ],
            base_env
            | {
                "DATABASE_URL": str(case.settings.database_url),
                "SUPABASE_JWT_ISSUER": case.local.issuer,
                "SUPABASE_JWKS_URL": f"{case.local.issuer}/.well-known/jwks.json",
                "DISCOVERY_PROVIDER": "fake",
                "DISCOVERY_SYNTHETIC_DEV": "true",
            },
        )
        web = start_service(
            services,
            [
                "node",
                "node_modules/next/dist/bin/next",
                "start",
                "apps/web",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(web_port),
            ],
            base_env
            | {
                "NEXT_PUBLIC_SUPABASE_URL": str(case.local.api_url).rstrip("/"),
                "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY": case.local.anon_key.get_secret_value(),
                "API_BASE_URL": api_url,
            },
        )
        wait_for_http(f"{api_url}/health/ready", api)
        wait_for_http(f"{web_url}/sign-in", web)
        try:
            result = subprocess.run(
                ["node", "tests/browser/planning.mjs"],
                input=json.dumps(
                    {
                        "base": web_url,
                        "plan": case.plan.removeprefix("/v1"),
                        "owner": case.owner.browser_login(),
                        "peer": case.peer.browser_login(),
                        "outsider": case.outsider.browser_login(),
                        "statement": REQUIREMENT,
                    }
                ),
                env=base_env,
                text=True,
                check=False,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            pytest.fail("The planning browser test timed out", pytrace=False)
        assert result.returncode == 0, "The planning browser test failed"
