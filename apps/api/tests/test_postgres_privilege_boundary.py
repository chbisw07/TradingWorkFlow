"""Disposable real-role proof: runtime DML works but F1/F2 guards cannot be removed."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from order_provider_fixture import OrderProvider
from pydantic import SecretStr
from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError
from test_broker_v1 import HEADERS, bound
from test_twf_queue_oe3 import queue_service, ready_order

from twf.auth import create_user
from twf.brokers.zerodha import ZerodhaAdapter
from twf.config.settings import Settings
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.infrastructure.twf_order import TWFOrderRecord
from twf.infrastructure.twf_queue import TWFQueueEntryRecord
from twf.main import create_app

TOOL = Path(__file__).parents[3] / "tools" / "postgres_roles.py"
ALEMBIC = Path(__file__).parents[1] / "alembic.ini"


def _run(action: str, env: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, str(TOOL), action], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def _refused(action: str, env: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, str(TOOL), action], env=env, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert result.stderr.strip() == "PostgreSQL role operation refused: ValueError"


def _denied(engine: Engine, statement: str, *, sqlstate: str | None = "42501") -> None:
    with pytest.raises(DBAPIError) as error:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
            db.execute(text(statement))
    if sqlstate is not None:
        assert getattr(error.value.orig, "sqlstate", None) == sqlstate


@pytest.mark.parametrize("legacy_owner", [False, True])
def test_runtime_role_cannot_remove_queue_guards(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    legacy_owner: bool,
) -> None:
    if request.config.getoption("--db-backend") != "postgres":
        pytest.skip("PostgreSQL role boundary only")
    token = uuid4().hex[:12]
    database, migrator, app = f"twf_role_{token}", f"mig_{token}", f"app_{token}"
    base = make_url(os.environ["TWF_DATABASE_URL"]).difference_update_query(["options"])
    admin = create_engine(base, isolation_level="AUTOCOMMIT", hide_parameters=True)
    with admin.connect() as db:
        db.execute(text(f'CREATE DATABASE "{database}"'))
    target = base.set(database=database)
    mig_url = target.set(username=migrator, password="migrator-test-password")
    app_url = target.set(username=app, password="app-test-password")
    env = dict(os.environ)
    env.update(
        {
            "TWF_PG_ADMIN_URL": target.render_as_string(hide_password=False),
            "TWF_PG_MIGRATOR_ROLE": migrator,
            "TWF_PG_APP_ROLE": app,
            "TWF_PG_MIGRATOR_PASSWORD": "migrator-test-password",
            "TWF_PG_APP_PASSWORD": "app-test-password",
        }
    )
    engine = None
    restored_database = None
    try:
        _run("provision", env)
        if legacy_owner:
            with create_engine(target, isolation_level="AUTOCOMMIT").connect() as db:
                db.execute(text(f'ALTER DATABASE "{database}" OWNER TO "{app}"'))
            migration_url = app_url
        else:
            _run("prepare-fresh", env)
            migration_url = mig_url
        if legacy_owner:
            migration_env = {
                **env,
                "TWF_DATABASE_URL": migration_url.render_as_string(hide_password=False),
                "TWF_MIGRATION_DATABASE_URL": migration_url.render_as_string(hide_password=False),
            }
            migrated = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    str(ALEMBIC),
                    "upgrade",
                    "head",
                ],
                cwd=ALEMBIC.parent,
                env=migration_env,
                capture_output=True,
                text=True,
            )
            assert migrated.returncode == 0, migrated.stderr
        else:
            operator_env = {
                **env,
                "TWF_DATABASE_URL": app_url.render_as_string(hide_password=False),
                "TWF_MIGRATION_DATABASE_URL": mig_url.render_as_string(hide_password=False),
            }
            result = subprocess.run(
                [str(Path(__file__).parents[3] / "tools" / "migrate-postgres.sh")],
                env=operator_env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, "migrator-only Alembic wrapper failed"
        # Existing-schema cutover preserves rows, IDs and contents in place.
        legacy_user_id = None
        if legacy_owner:
            old = create_engine(app_url)
            with create_session_factory(old)() as db:
                legacy_user_id = create_user(
                    db, "legacy-user", "Legacy User", "test-only-legacy-password"
                ).id
                db.commit()
            old.dispose()
        _run("harden", env)
        _run("verify", env)
        runtime = Settings(
            database_url=app_url.render_as_string(hide_password=False),
            credential_master_key=SecretStr(Fernet.generate_key().decode()),
            cors_origins=("http://localhost:3000",),
            broker_manual_trading_enabled=True,
        )
        engine = create_database_engine(runtime)
        with engine.connect() as db:
            assert db.scalar(text("SELECT current_user")) == app
            assert db.scalar(text("SELECT count(*) FROM twf_queue_events")) == 0
            tables = {
                row[0]
                for row in db.execute(
                    text(
                        "SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace "
                        "AND relkind IN ('r','p')"
                    )
                )
            }
            required_delete = {
                "broker_attempts",
                "dhan_market_data_secrets",
                "discovery_active_slots",
                "manual_order_previews",
                "mcp_oauth_attempts",
                "mcp_secrets",
                "scanner_v2_derivative_templates",
                "watchlist_activity",
                "watchlist_items",
                "watchlist_notes",
                "watchlists",
            }
            assert len(tables) == 51
            assert len(required_delete) == 11
            denied_delete = tables - required_delete - {"alembic_version", "twf_queue_events"}
            assert len(denied_delete) == 38
            granted_delete = {
                name
                for name in tables
                if db.scalar(
                    text("SELECT has_table_privilege(:role,:table,'DELETE')"),
                    {"role": app, "table": f"public.{name}"},
                )
            }
            assert granted_delete == required_delete
        for table in sorted(denied_delete):
            _denied(engine, f'DELETE FROM "{table}" WHERE 1=0')
        for statement in (
            "UPDATE twf_order_events SET actor='TAMPERED' WHERE 1=0",
            "UPDATE twf_queue_policy_events SET actor='TAMPERED' WHERE 1=0",
            "UPDATE twf_order_public_ids SET public_order_id='TAMPERED' WHERE 1=0",
            "UPDATE preference_changes SET id=id WHERE 1=0",
            "UPDATE scanner_v2_runs SET id=id WHERE 1=0",
            "DELETE FROM twf_orders WHERE 1=0",
            "DELETE FROM broker_order_intents WHERE 1=0",
            "DELETE FROM twf_queue_entries WHERE 1=0",
        ):
            _denied(engine, statement)
        _denied(engine, "DELETE FROM twf_order_events WHERE 1=0")
        # Undeclared future relations fail closed instead of receiving implicit DML.
        future_table = f"future_audit_{token}"
        disposable_admin = create_engine(target, isolation_level="AUTOCOMMIT")
        try:
            with disposable_admin.connect() as db:
                db.execute(text(f'CREATE TABLE "{future_table}" (id integer)'))
            _refused("harden", env)
            _refused("verify", env)
            with engine.connect() as db:
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    assert not db.scalar(
                        text("SELECT has_table_privilege(:role,:table,:privilege)"),
                        {
                            "role": app,
                            "table": f"public.{future_table}",
                            "privilege": privilege,
                        },
                    )
            _denied(engine, f'DELETE FROM "{future_table}" WHERE 1=0')
            with disposable_admin.connect() as db:
                db.execute(text(f'DROP TABLE "{future_table}"'))
            _run("verify", env)
        finally:
            disposable_admin.dispose()
        for statement in (
            "ALTER TABLE twf_orders DROP CONSTRAINT fk_twf_orders_queue_binding",
            "ALTER TABLE twf_queue_entries DROP CONSTRAINT fk_twf_queue_entries_order_binding",
            "ALTER TABLE twf_queue_events DISABLE TRIGGER trg_twf_queue_events_immutable",
            "DROP TRIGGER trg_twf_queue_events_immutable ON twf_queue_events",
            "DROP FUNCTION twf_queue_event_immutable()",
            "DROP TABLE twf_queue_events",
            "DROP INDEX ix_twf_queue_entries_owner_fifo",
            "ALTER FUNCTION twf_queue_event_immutable() OWNER TO " + app,
            "CREATE TABLE privilege_attack(x integer)",
            "CREATE ROLE privilege_attack",
            "CREATE DATABASE privilege_attack",
            "SET ROLE " + migrator,
            "SET ROLE " + str(base.username),
            "ALTER TABLE twf_orders OWNER TO " + app,
            "ALTER SCHEMA public OWNER TO " + app,
            "REASSIGN OWNED BY " + migrator + " TO " + app,
            "GRANT " + migrator + " TO " + app,
        ):
            _denied(engine, statement)
        with create_session_factory(engine)() as db:
            create_user(db, "trader", "Trader", "test-only-broker-password")
            db.commit()
        provider = OrderProvider()
        adapter = ZerodhaAdapter(transport=httpx.MockTransport(provider))
        with TestClient(
            create_app(runtime, engine_factory=lambda _: engine, broker_adapter=adapter)
        ) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "trader", "password": "test-only-broker-password"},
                headers=HEADERS,
            )
            assert response.status_code == 200
            account = bound(client)
            current_policy = client.get(f"/api/v1/twf-queue/policy/{account}")
            assert current_policy.status_code == 200, current_policy.text
            assert current_policy.json()["current_dispatch_mode"] == "MANUAL"
            assert current_policy.json()["execution_enabled"] is False
            changed_policy = client.post(
                f"/api/v1/twf-queue/policy/{account}",
                json={"current_dispatch_mode": "AUTO", "expected_version": 1},
                headers=HEADERS,
            )
            assert changed_policy.status_code == 200, changed_policy.text
            restored_policy = client.post(
                f"/api/v1/twf-queue/policy/{account}",
                json={"current_dispatch_mode": "MANUAL", "expected_version": 2},
                headers=HEADERS,
            )
            assert restored_policy.status_code == 200, restored_policy.text
            order = ready_order(client, account)
            order_id = UUID(order["twf_order_id"])
            with engine.connect() as db:
                owner_id = db.scalar(
                    select(TWFOrderRecord.owner_id).where(TWFOrderRecord.twf_order_id == order_id)
                )
            assert owner_id is not None
            now = datetime.now(UTC)
            with pytest.raises(DBAPIError):
                with engine.begin() as db:
                    db.execute(
                        insert(TWFQueueEntryRecord).values(
                            queue_entry_id=uuid4(),
                            twf_order_id=order_id,
                            owner_id=owner_id,
                            queue_state="READY",
                            version=1,
                            admitted_at=now,
                            updated_at=now,
                            created_by="DIRECT_ATTACK",
                        )
                    )
            with pytest.raises(DBAPIError):
                with engine.begin() as db:
                    db.execute(
                        update(TWFOrderRecord)
                        .where(TWFOrderRecord.twf_order_id == order_id)
                        .values(state="QUEUED", queue_entry_id=uuid4())
                    )
            queue = queue_service(client)
            entry = queue.admit(UUID(order["twf_order_id"]))
            assert queue.admit(UUID(order["twf_order_id"])).queue_entry_id == entry.queue_entry_id
            queue.hold(entry.queue_entry_id, expected_version=1, reason="TEST")
            queue.release(entry.queue_entry_id, expected_version=2)
            assert len(queue.history(entry.queue_entry_id)) == 3
            assert client.get("/api/v1/twf-queue").status_code == 200
        _denied(engine, "UPDATE twf_queue_events SET actor='TAMPERED'", sqlstate=None)
        _denied(engine, "DELETE FROM twf_queue_events", sqlstate=None)
        if legacy_owner:
            with engine.connect() as db:
                assert db.scalar(text("SELECT count(*) FROM twf_queue_events")) == 3
                assert (
                    db.scalar(text("SELECT id FROM users WHERE username='legacy-user'"))
                    == legacy_user_id
                )
        else:
            restored_database = f"twf_restore_{token}"
            with admin.connect() as db:
                db.execute(text(f'CREATE DATABASE "{restored_database}" OWNER "{migrator}"'))
            dump = tmp_path / "role-restore.dump"
            pg_env = dict(env)
            pg_env.update(
                {
                    "PGHOST": str(target.query["host"]),
                    "PGPORT": str(target.query["port"]),
                    "PGUSER": migrator,
                    "PGPASSWORD": "migrator-test-password",
                }
            )
            pg_bin = Path(subprocess.check_output(["pg_config", "--bindir"], text=True).strip())
            subprocess.run(
                [
                    str(pg_bin / "pg_dump"),
                    "-Fc",
                    "--no-owner",
                    "--no-acl",
                    "-f",
                    str(dump),
                    database,
                ],
                env=pg_env,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    str(pg_bin / "pg_restore"),
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "-d",
                    restored_database,
                    str(dump),
                ],
                env=pg_env,
                check=True,
                capture_output=True,
            )
            restore_target = target.set(database=restored_database)
            restore_env = {
                **env,
                "TWF_PG_ADMIN_URL": restore_target.render_as_string(hide_password=False),
            }
            _run("harden", restore_env)
            _run("verify", restore_env)
            restored_runtime = create_database_engine(
                runtime.model_copy(
                    update={
                        "database_url": app_url.set(database=restored_database).render_as_string(
                            hide_password=False
                        )
                    }
                )
            )
            try:
                with restored_runtime.connect() as db:
                    assert db.scalar(text("SELECT count(*) FROM twf_queue_events")) == 3
                _denied(
                    restored_runtime,
                    "ALTER TABLE twf_queue_events DISABLE TRIGGER trg_twf_queue_events_immutable",
                )
                restored_provider = OrderProvider()
                restored_settings = runtime.model_copy(
                    update={
                        "database_url": app_url.set(database=restored_database).render_as_string(
                            hide_password=False
                        )
                    }
                )
                with TestClient(
                    create_app(
                        restored_settings,
                        engine_factory=lambda _: restored_runtime,
                        broker_adapter=ZerodhaAdapter(
                            transport=httpx.MockTransport(restored_provider)
                        ),
                    )
                ) as restored_client:
                    login = restored_client.post(
                        "/api/v1/auth/login",
                        json={
                            "username": "trader",
                            "password": "test-only-broker-password",
                        },
                        headers=HEADERS,
                    )
                    assert login.status_code == 200, login.text
                    accounts = restored_client.get("/api/v1/brokers/accounts")
                    assert accounts.status_code == 200, accounts.text
                    restored_account = accounts.json()[0]["id"]
                    policy = restored_client.get(f"/api/v1/twf-queue/policy/{restored_account}")
                    assert policy.status_code == 200, policy.text
                    assert policy.json()["current_dispatch_mode"] == "MANUAL"
                    assert policy.json()["execution_enabled"] is False
                    assert ready_order(restored_client, restored_account)["state"] == "READY"
                    assert restored_provider.calls == []
            finally:
                restored_runtime.dispose()
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as db:
            if restored_database:
                db.execute(text(f'DROP DATABASE IF EXISTS "{restored_database}" WITH (FORCE)'))
            db.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
            db.execute(text(f'DROP ROLE IF EXISTS "{app}"'))
            db.execute(text(f'DROP ROLE IF EXISTS "{migrator}"'))
        admin.dispose()
