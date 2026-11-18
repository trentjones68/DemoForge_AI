import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def schema_validator(name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "packages" / "contracts" / "v1" / name).read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())
