import json

import pytest
from contract_support import ROOT, schema_validator
from demoforge_api.discovery.imports import TextImport
from demoforge_worker.queue import JobMessageV1
from pydantic import ValidationError


def test_job_reference_round_trip() -> None:
    fixture = (ROOT / "fixtures" / "synthetic" / "contracts" / "job-message.v1.json").read_text()
    message = JobMessageV1.model_validate_json(fixture)
    serialized = message.model_dump(mode="json")
    schema_validator("job-message.schema.json").validate(serialized)
    assert serialized == json.loads(fixture)


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 1, "job_id": "bad-id"},
        {"schema_version": 2, "job_id": "e5cf3ba0-a5e8-4049-847a-99dbfc16d3eb"},
        {"schema_version": True, "job_id": "e5cf3ba0-a5e8-4049-847a-99dbfc16d3eb"},
        {
            "schema_version": 1,
            "job_id": "e5cf3ba0-a5e8-4049-847a-99dbfc16d3eb",
            "workspace_id": "untrusted-workspace",
        },
    ],
)
def test_invalid_job_reference_is_rejected(payload: dict[str, object]) -> None:
    assert not schema_validator("job-message.schema.json").is_valid(payload)
    with pytest.raises(ValidationError):
        JobMessageV1.model_validate_json(json.dumps(payload))


def test_discovery_text_import_contract_matches_api() -> None:
    name = "discovery-text-import.schema.json"
    schema = json.loads((ROOT / "packages" / "contracts" / "v1" / name).read_text())
    assert schema.pop("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema == TextImport.model_json_schema()
    validator = schema_validator(name)
    payload = {"kind": "summary", "text": "Synthetic rehearsal notes.\r\n"}
    validator.validate(payload)
    assert TextImport.model_validate_json(json.dumps(payload)).model_dump() == (
        payload | {"provider": "manual"}
    )
    for invalid in (
        {"text": ""},
        {"text": 42},
        {"provider": "unverified"},
        {"workspace_id": "untrusted"},
        {"file_url": "https://files.example.test/input"},
    ):
        assert not validator.is_valid(payload | invalid)
        with pytest.raises(ValidationError):
            TextImport.model_validate_json(json.dumps(payload | invalid))
