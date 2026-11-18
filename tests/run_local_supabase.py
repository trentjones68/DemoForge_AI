"""Run the Supabase suite against a new disposable CLI stack."""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx2
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def delete_empty_bucket(api_url: str, service_key: str) -> None:
    response = httpx2.delete(
        f"{api_url.rstrip('/')}/storage/v1/bucket/workspace-files",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        timeout=10,
    )
    if not response.is_success:
        raise SystemExit(f"Could not delete the empty test bucket (HTTP {response.status_code})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", type=Path, help="Output from supabase status -o json")
    args = parser.parse_args()
    status = json.loads(args.status.read_text())
    admin = make_url(status["DB_URL"])
    if admin.host not in ("localhost", "127.0.0.1"):
        raise SystemExit("A fresh disposable local Supabase database is required")
    api_url: str = status["API_URL"]
    if urlsplit(api_url).hostname not in ("localhost", "127.0.0.1"):
        raise SystemExit("A disposable local Supabase HTTP endpoint is required")
    service_key: str = status["SERVICE_ROLE_KEY"]

    password = secrets.token_urlsafe(32)
    with psycopg.connect(admin.render_as_string(hide_password=False)) as connection:
        exists = connection.execute(
            """
            SELECT to_regnamespace('demoforge') IS NOT NULL
                OR to_regclass('public.alembic_version') IS NOT NULL
                OR EXISTS (SELECT FROM pg_roles WHERE rolname = 'demoforge_api')
            """
        ).fetchone()
        if exists is None or exists[0]:
            raise SystemExit("Refusing to modify an existing DemoForge database")
        connection.execute(
            sql.SQL(
                "CREATE ROLE demoforge_api LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS PASSWORD {}"
            ).format(sql.Literal(password))
        )

    request = admin.set(username="demoforge_api", password=password)
    env = os.environ | {
        "DATABASE_URL": request.set(drivername="postgresql+psycopg").render_as_string(
            hide_password=False
        ),
        "MIGRATION_DATABASE_URL": admin.set(drivername="postgresql+psycopg").render_as_string(
            hide_password=False
        ),
        "TEST_SUPABASE_STATUS_FILE": str(args.status),
    }

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    subprocess.run([sys.executable, "-m", "pytest", "-m", "supabase"], env=env, check=True)
    delete_empty_bucket(api_url, service_key)
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "0002"], env=env, check=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    delete_empty_bucket(api_url, service_key)
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], env=env, check=True)


if __name__ == "__main__":
    main()
