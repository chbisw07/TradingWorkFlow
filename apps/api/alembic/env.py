"""Alembic migration entry point with dedicated migration-role credentials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from alembic import context
from alembic.ddl.postgresql import PostgresqlImpl
from dotenv import load_dotenv
from sqlalchemy import String, Table, text
from sqlalchemy.engine import make_url

import twf.infrastructure.broker  # noqa: F401 -- register metadata
import twf.infrastructure.dhan  # noqa: F401 -- register metadata
import twf.infrastructure.discovery  # noqa: F401 -- register metadata
import twf.infrastructure.fno_liquidity  # noqa: F401 -- register metadata
import twf.infrastructure.identity  # noqa: F401 -- register metadata
import twf.infrastructure.instrument_metadata  # noqa: F401 -- register metadata
import twf.infrastructure.mcp  # noqa: F401 -- register metadata
import twf.infrastructure.order_intent  # noqa: F401 -- register metadata
import twf.infrastructure.order_preview  # noqa: F401 -- register metadata
import twf.infrastructure.preferences  # noqa: F401 -- register metadata
import twf.infrastructure.scanner_v2  # noqa: F401 -- register metadata
import twf.infrastructure.twf_order  # noqa: F401 -- register metadata
import twf.infrastructure.twf_queue  # noqa: F401 -- register metadata
import twf.infrastructure.watchlists  # noqa: F401 -- register metadata
from twf.config.settings import Settings
from twf.infrastructure.database import Base, create_database_engine

# Alembic uses a dedicated migration credential instead of the normal API
# runtime credential.  This keeps the runtime role (twf_app) least-privileged
# while restoring the normal `alembic upgrade head` workflow.
REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_ENV_FILE = REPO_ROOT / ".env.oe3-migrator"

# An explicitly supplied shell value wins.  Otherwise load the private,
# repo-root migration environment file.
load_dotenv(MIGRATION_ENV_FILE, override=False)

migration_database_url = os.getenv("TWF_MIGRATION_DATABASE_URL")
if migration_database_url:
    # Settings/create_database_engine already contain TWF's canonical DB engine
    # setup (including PostgreSQL session behavior).  Feed the migration URL
    # through that same path for this Alembic process only.
    os.environ["TWF_DATABASE_URL"] = migration_database_url

settings = Settings()
target_metadata = Base.metadata


def validate_migration_identity() -> None:
    """Refuse PostgreSQL migrations through the normal runtime role."""

    database_url = make_url(str(settings.database_url))
    if database_url.get_backend_name() != "postgresql":
        # Explicit SQLite migration/test environments remain supported.
        return

    # In normal local/production PostgreSQL use, the dedicated migration URL is
    # required.  Test harnesses may supply another non-runtime PostgreSQL owner.
    if database_url.username == "twf_app":
        raise RuntimeError(
            "Alembic migrations must not run as the runtime role 'twf_app'. "
            f"Set TWF_MIGRATION_DATABASE_URL in {MIGRATION_ENV_FILE} "
            "to the twf_migrator PostgreSQL URL."
        )


validate_migration_identity()


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
