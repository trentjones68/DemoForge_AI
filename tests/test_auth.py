import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from demoforge_api.main import create_app
from demoforge_api.settings import Settings
from fastapi.testclient import TestClient
from pydantic import HttpUrl, SecretStr

ISSUER = "http://127.0.0.1:54321/auth/v1"
TEST_SIGNING_KEY = "synthetic-test-signing-key-for-jwt-verification"
TEST_SUBJECT = uuid4()


def claims(issuer: str = ISSUER) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "iss": issuer,
        "aud": "authenticated",
        "role": "authenticated",
        "sub": str(TEST_SUBJECT),
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def token_for(subject: str) -> str:
    return jwt.encode(claims() | {"sub": subject}, TEST_SIGNING_KEY, algorithm="HS256")


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://untrusted.example/auth/v1"},
        {"aud": "other"},
        {"role": "service_role"},
        {"is_anonymous": True},
        {"sub": "invalid"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"iat": datetime.now(UTC) + timedelta(minutes=1)},
    ],
    ids=["issuer", "audience", "service-role", "anonymous", "subject", "expired", "future"],
)
def test_claim_rejection(overrides: dict[str, object]) -> None:
    token = jwt.encode(claims() | overrides, TEST_SIGNING_KEY, algorithm="HS256")
    with TestClient(
        create_app(
            Settings(
                database_url=None,
                supabase_jwt_issuer=HttpUrl(ISSUER),
                supabase_jwt_secret=SecretStr(TEST_SIGNING_KEY),
                supabase_jwks_url=None,
            )
        )
    ) as client:
        response = client.get("/v1/workspaces", headers=bearer(token))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.fixture
def jwks_server() -> Iterator[tuple[str, ec.EllipticCurvePrivateKey, list[str]]]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    key = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    payload = json.dumps({"keys": [key | {"alg": "ES256", "kid": "local-test", "use": "sig"}]})
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload.encode())

        def log_message(self, format: str, *args: object) -> None:
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/auth/v1", private_key, requests
        finally:
            server.shutdown()
            worker.join()


def test_public_keys_verify_only_trusted_signatures(
    jwks_server: tuple[str, ec.EllipticCurvePrivateKey, list[str]],
) -> None:
    issuer, key, requests = jwks_server
    valid = jwt.encode(claims(issuer), key, algorithm="ES256", headers={"kid": "local-test"})
    wrong_key = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode(claims(issuer), wrong_key, algorithm="ES256", headers={"kid": "local-test"})
    unknown = jwt.encode(claims(issuer), key, algorithm="ES256", headers={"kid": "unknown"})
    unsigned = jwt.encode(claims(issuer), "", algorithm="none")
    app = create_app(
        Settings(
            database_url=None,
            supabase_jwt_issuer=HttpUrl(issuer),
            supabase_jwks_url=HttpUrl(f"{issuer}/.well-known/jwks.json"),
            supabase_jwt_secret=None,
        )
    )
    with TestClient(app) as client:
        assert client.get("/v1/workspaces").status_code == 401
        for token in (forged, unknown, unsigned, "not-a-jwt"):
            assert client.get("/v1/workspaces", headers=bearer(token)).status_code == 401
        # A verified token reaches the downstream DB configuration check.
        assert client.get("/v1/workspaces", headers=bearer(valid)).status_code == 503
    assert requests == ["/auth/v1/.well-known/jwks.json"]
