from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from pydantic import PostgresDsn
from sqlalchemy import Connection, Engine, create_engine, text


def database_engine(dsn: PostgresDsn) -> Engine:
    # Build network connections lazily. Keep the readiness probe short.
    return create_engine(
        str(dsn),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=2000"},
    )


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


class DatabaseIdentityError(RuntimeError):
    """The request connection does not use the restricted application login."""


@contextmanager
def workspace_transaction(engine: Engine, actor: UUID) -> Iterator[Connection]:
    with engine.begin() as connection:
        # The verified subject is set anew and cleared by commit or rollback.
        identity = connection.execute(
            text("""
                SELECT set_config('demoforge.user_id', :actor, true)
                FROM pg_catalog.pg_roles
                WHERE rolname = current_user AND rolname = 'demoforge_api'
                  AND NOT rolsuper AND NOT rolbypassrls
            """),
            {"actor": str(actor)},
        ).scalar_one_or_none()
        if identity is None:
            raise DatabaseIdentityError
        yield connection
