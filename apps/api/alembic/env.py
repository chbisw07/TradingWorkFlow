"""Migration entry point; URL comes from the same typed settings as the API."""

from typing import Any

from alembic import context
from alembic.ddl.postgresql import PostgresqlImpl
from sqlalchemy import String, Table, text

import twf.infrastructure.broker  # noqa: F401 -- register metadata
import twf.infrastructure.dhan  # noqa: F401 -- register metadata
import twf.infrastructure.discovery  # noqa: F401 -- register metadata
import twf.infrastructure.identity  # noqa: F401 -- register metadata
import twf.infrastructure.instrument_metadata  # noqa: F401 -- register metadata
import twf.infrastructure.mcp  # noqa: F401 -- register metadata
import twf.infrastructure.order_intent  # noqa: F401 -- register metadata
import twf.infrastructure.preferences  # noqa: F401 -- register metadata
import twf.infrastructure.scanner_v2  # noqa: F401 -- register metadata
import twf.infrastructure.watchlists  # noqa: F401 -- register metadata
from twf.config.settings import Settings
from twf.infrastructure.database import Base, create_database_engine

settings = Settings()
target_metadata = Base.metadata


class TWFPostgresqlImpl(PostgresqlImpl):
    __dialect__ = "postgresql"

    def version_table_impl(self, **kw: Any) -> Table:
        table = super().version_table_impl(**kw)
        table.c.version_num.type = String(128)
        return table


def ensure_revision_capacity() -> None:
    # Preserve published IDs: 0016 exceeds Alembic's default VARCHAR(32).
    # Fresh tables use the documented dialect hook above. Existing tables are
    # widened without rewriting any revision; IF EXISTS also works in offline SQL.
    if context.get_context().dialect.name == "postgresql":
        context.execute(
            text("ALTER TABLE IF EXISTS alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
        )


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        ensure_revision_capacity()
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                ensure_revision_capacity()
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
