import json
import os
from urllib.request import urlopen

from contract_support import schema_validator


def main() -> None:
    web_url = os.environ.get("SMOKE_WEB_URL", "http://127.0.0.1:3000")
    api_url = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8000")
    with urlopen(web_url, timeout=10) as response:
        assert response.status == 200
        assert "<title>DemoForge AI</title>" in response.read().decode()

    validator = schema_validator("health-response.schema.json")
    for path in ("live", "ready"):
        with urlopen(f"{api_url}/health/{path}", timeout=10) as response:
            assert response.status == 200
            body = json.load(response)
            validator.validate(body)
            assert body == {"status": "ok"}
    print("Web, API liveness and database readiness passed.")


if __name__ == "__main__":
    main()
