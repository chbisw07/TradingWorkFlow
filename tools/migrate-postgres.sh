#!/usr/bin/env bash
# Run Alembic only in a trusted operator process; do not mount migration secrets in API.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root/apps/api"
.venv/bin/python - <<'PY'
import os
from sqlalchemy import text
from sqlalchemy.engine import make_url
from twf.config.settings import Settings
from twf.infrastructure.database import create_database_engine

migration_url = os.environ.get('TWF_MIGRATION_DATABASE_URL')
if not migration_url:
    raise SystemExit('Set TWF_MIGRATION_DATABASE_URL for the operator migration process')
runtime = Settings()
migration = Settings(database_url=migration_url)
runtime_url = make_url(runtime.database_url)
operator_url = make_url(migration.database_url)
expected = os.environ.get('TWF_PG_MIGRATOR_ROLE', 'twf_migrator')
if (operator_url.get_backend_name() != 'postgresql'
        or runtime_url.get_backend_name() != 'postgresql'
        or operator_url.database != runtime_url.database
        or operator_url.username != expected
        or runtime_url.username == expected):
    raise SystemExit('Migration requires distinct PostgreSQL runtime/migrator roles on one database')
engine = create_database_engine(migration)
try:
    with engine.connect() as db:
        role = db.scalar(text('SELECT current_user'))
        if role != expected:
            raise SystemExit('Migration connection did not authenticate as the migrator role')
finally:
    engine.dispose()
PY
export TWF_DATABASE_URL="$TWF_MIGRATION_DATABASE_URL"
.venv/bin/alembic upgrade head
