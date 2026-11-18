from alembic import context
from demoforge_api.settings import Settings
from sqlalchemy import create_engine, pool

migration_url = Settings().migration_database_url
if migration_url is None:
    raise RuntimeError("Set MIGRATION_DATABASE_URL before running Alembic")

if context.is_offline_mode():
    context.configure(url=str(migration_url), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(str(migration_url), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
