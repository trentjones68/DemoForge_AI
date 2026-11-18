from contract_support import schema_validator
from demoforge_api.main import create_app
from demoforge_api.settings import Settings
from fastapi.testclient import TestClient
from pydantic import PostgresDsn


def test_liveness_and_unconfigured_readiness() -> None:
    with TestClient(create_app(Settings(database_url=None))) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    validator = schema_validator("health-response.schema.json")
    for response in (live, ready):
        assert response.headers["cache-control"] == "no-store"
        validator.validate(response.json())
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable"}


def test_readiness_redacts_database_errors() -> None:
    database_url = PostgresDsn("postgresql+psycopg://user:secret@127.0.0.1:1/local")
    with TestClient(create_app(Settings(database_url=database_url))) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
