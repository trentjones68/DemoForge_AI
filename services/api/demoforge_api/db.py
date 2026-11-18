from pydantic import PostgresDsn
from sqlalchemy import Engine, create_engine, text


def database_engine(dsn: PostgresDsn) -> Engine:
    # Build network connections lazily. Keep the readiness probe short.
    return create_engine(
        str(dsn),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=2000"},
    )


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
