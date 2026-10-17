"""DB-1 live platform, migration fidelity, atomicity, and concurrency gates."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from order_provider_fixture import OrderProvider
from pydantic import SecretStr
from sqlalchemy import MetaData, func, select, text
from test_broker_v1 import HEADERS, bound, service
from test_twf_orders_oe2 import payload
from test_twf_queue_oe3 import account as account
from test_twf_queue_oe3 import client as client
from test_twf_queue_oe3 import queue_service, ready_order

from twf.auth import create_user
from twf.brokers.zerodha import ZerodhaAdapter
from twf.config.settings import Settings
from twf.infrastructure.database import (
    DATABASE_SCHEMA_HEAD,
    create_database_engine,
    create_session_factory,
    database_status,
)
from twf.infrastructure.sqlite_migration import MigrationFailure, _serialize, migrate_snapshot
from twf.infrastructure.twf_order import TWFOrderEventRecord, TWFOrderRecord
from twf.infrastructure.twf_queue import TWFQueueEntryRecord, TWFQueueEventRecord
from twf.main import create_app
from twf.queue.errors import QueueError, QueueErrorCode
from twf.queue.service import QueueService

CONFIG = str(Path(__file__).parents[1] / "alembic.ini")


def test_content_hash_preserves_json_types() -> None:
    assert _serialize({"json": Decimal("1")}) != _serialize({"json": {"decimal": "1"}})
    assert _serialize({"json": ["decimal", "1"]}) != _serialize({"json": Decimal("1")})
    assert _serialize({"json": None}) != _serialize(None)
    assert _serialize({"json": {"b": Decimal("1.0"), "a": None}}) == _serialize(
        {"json": {"a": None, "b": Decimal("1")}}
    )


def test_database_down_fails_closed_without_sqlite(tmp_path: Path) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://nobody:secret_marker@127.0.0.1:1/missing",
        database_connect_timeout=1,
    )
    app = create_app(settings)
    with pytest.raises(RuntimeError, match="unavailable") as error:
        with TestClient(app):
            pass
    assert "secret_marker" not in str(error.value)
    assert app.state.initialized is False
    assert not list(tmp_path.glob("*.db"))


def test_live_head_and_schema_mismatch(migrated_database: None) -> None:
    assert ScriptDirectory.from_config(Config(CONFIG)).get_current_head() == DATABASE_SCHEMA_HEAD
    engine = create_database_engine(Settings())
    try:
        assert database_status(engine)["status"] == "ready"
        command.downgrade(Config(CONFIG), "0024_manual_order_previews")
        with pytest.raises(RuntimeError, match="schema_mismatch"):
            with TestClient(create_app()):
                pass
        command.upgrade(Config(CONFIG), "head")
        with TestClient(create_app()) as client:
            status = client.get("/ready").json()
            assert status["database_checked"] is True
            assert status["database_status"] == "ready"
            assert status["database_backend"] == (
                "PostgreSQL" if engine.dialect.name == "postgresql" else "SQLite fallback"
            )
    finally:
        engine.dispose()


@pytest.fixture
def sqlite_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, dict[str, Any]]]:
    path = tmp_path / "source.sqlite"
    with monkeypatch.context() as patch:
        snapshot_url = f"sqlite+pysqlite:///{path}"
        patch.setenv("TWF_DATABASE_URL", snapshot_url)
        patch.setenv("TWF_MIGRATION_DATABASE_URL", snapshot_url)
        command.upgrade(Config(CONFIG), "head")
        settings = Settings(
            broker_manual_trading_enabled=True,
            credential_master_key=SecretStr(Fernet.generate_key().decode()),
            cors_origins=("http://localhost:3000",),
        )
        engine = create_database_engine(settings)
        with create_session_factory(engine).begin() as db:
            create_user(db, "trader", "Test Migration", "test-only-broker-password")
        provider = OrderProvider()
        with TestClient(
            create_app(
                settings,
                engine_factory=lambda _: engine,
                broker_adapter=ZerodhaAdapter(transport=httpx.MockTransport(provider)),
            )
        ) as client:
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={"username": "trader", "password": "test-only-broker-password"},
                    headers=HEADERS,
                ).status_code
                == 200
            )
            account_id = bound(client)
            for index, (symbol, token) in enumerate(
                (("HAL", "1"), ("NIFTYFUT1", "4"), ("NIFTYCE1", "5"))
            ):
                body = payload(account_id, symbol, token)
                preview = client.post("/api/v1/twf-orders/preview", json=body, headers=HEADERS)
                assert preview.status_code == 200, preview.text
                result = client.post(
                    "/api/v1/twf-orders",
                    json={**body, "preview_id": preview.json()["preview_id"]},
                    headers=HEADERS,
                )
                assert result.status_code == 200, result.text
                if index < 2:
                    entry = client.post(
                        "/api/v1/twf-queue/admit",
                        json={"twf_order_id": result.json()["order"]["twf_order_id"]},
                        headers=HEADERS,
                    )
                    assert entry.status_code == 200, entry.text
                    if index == 1:
                        assert (
                            client.post(
                                "/api/v1/twf-queue/" + entry.json()["queue_entry_id"] + "/hold",
                                json={"expected_version": 1},
                                headers=HEADERS,
                            ).status_code
                            == 200
                        )
            # An unused Preview exercises SQL NULL vs JSON null.
            assert (
                client.post(
                    "/api/v1/twf-orders/preview",
                    json=payload(account_id, "HAL", "1"),
                    headers=HEADERS,
                ).status_code
                == 200
            )
            assert (
                client.post(
                    "/api/v1/watchlists", json={"name": "Migration watchlist"}, headers=HEADERS
                ).status_code
                == 201
            )
            assert provider.calls == []
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE db1_precision_proof (id INTEGER PRIMARY KEY, "
                "amount NUMERIC(20,5) NOT NULL, expiry DATE NOT NULL, "
                "happened TIMESTAMP NOT NULL, payload JSON, absent JSON)"
            )
            db.execute(
                "INSERT INTO db1_precision_proof VALUES (42, '1234.12345', "
                "'2026-10-29', '2026-10-28 18:30:00.123456', ?, NULL)",
                (
                    '{"decimal_string":"100.05","large":123456789012345678901234567890,"fraction":0.12345678901234567890123,"nested":[null,true,"₹"]}',
                ),
            )
        path.chmod(0o400)
    manifest = {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    yield path, manifest


def _prepare_destination() -> Any:
    engine = create_database_engine(Settings())
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("SQLite-to-PostgreSQL and row-lock probes require live PostgreSQL")
    command.upgrade(Config(CONFIG), "head")
    with engine.begin() as db:
        db.execute(
            text(
                "CREATE TABLE db1_precision_proof (id SERIAL PRIMARY KEY, "
                "amount NUMERIC(20,5) NOT NULL, expiry DATE NOT NULL, "
                "happened TIMESTAMPTZ NOT NULL, payload JSON, absent JSON)"
            )
        )
    return engine


def test_snapshot_round_trip_all_fields_and_next_sequence(
    sqlite_snapshot: tuple[Path, dict[str, Any]],
) -> None:
    source, manifest = sqlite_snapshot
    engine = _prepare_destination()
    try:
        url = Settings().database_url
        dry = migrate_snapshot(source, manifest, url, dry_run=True)
        assert dry["status"] == "DRY_RUN_VALIDATED"
        report = migrate_snapshot(source, manifest, url)
        assert report["status"] == "IMPORTED_AND_VERIFIED"
        assert (
            migrate_snapshot(source, manifest, url, verify_only=True)["status"]
            == "VERIFIED_READ_ONLY"
        )
        assert all(t["source"] == t["destination"] for t in report["tables"].values())
        assert report["sequences"] == [
            {"table": "db1_precision_proof", "column": "id", "next_value": 43}
        ]
        with create_session_factory(engine)() as db:
            orders = db.scalars(select(TWFOrderRecord)).all()
            assert len(orders) == 3
            assert {o.state for o in orders} == {"READY", "QUEUED"}
            assert {o.payload["instrument"]["asset_class"] for o in orders} == {
                "EQUITY",
                "FUTURES",
                "OPTION",
            }
            assert {o.queue_state for o in db.scalars(select(TWFQueueEntryRecord))} == {
                "READY",
                "HELD",
            }
        with engine.begin() as db:
            row = db.execute(text("SELECT * FROM db1_precision_proof")).mappings().one()
            assert row["amount"] == Decimal("1234.12345")
            assert row["expiry"].isoformat() == "2026-10-29"
            assert row["happened"] == datetime(2026, 10, 28, 18, 30, 0, 123456, tzinfo=UTC)
            assert row["absent"] is None
            assert (
                db.scalar(
                    text(
                        "INSERT INTO db1_precision_proof (amount,expiry,happened) "
                        "VALUES (0.05,'2026-10-29',now()) RETURNING id"
                    )
                )
                == 43
            )
        with pytest.raises(MigrationFailure, match="destination must be empty"):
            migrate_snapshot(source, manifest, url)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["sha256"]
    finally:
        engine.dispose()


def test_failed_import_rolls_back_every_table_and_can_restart(
    sqlite_snapshot: tuple[Path, dict[str, Any]],
) -> None:
    source, manifest = sqlite_snapshot
    engine = _prepare_destination()
    try:
        with engine.begin() as db:
            db.execute(text("ALTER TABLE twf_orders ADD CONSTRAINT db1_reject CHECK (version < 0)"))
        with pytest.raises(MigrationFailure, match="twf_orders.*rolled back"):
            migrate_snapshot(source, manifest, Settings().database_url)
        with engine.begin() as db:
            schema = MetaData()
            schema.reflect(db)
            for table in schema.tables.values():
                if table.name != "alembic_version":
                    assert db.scalar(select(func.count()).select_from(table)) == 0, table.name
            db.execute(text("ALTER TABLE twf_orders DROP CONSTRAINT db1_reject"))
        assert (
            migrate_snapshot(source, manifest, Settings().database_url)["status"]
            == "IMPORTED_AND_VERIFIED"
        )
    finally:
        engine.dispose()


def test_invalid_sqlite_integer_refuses_lossy_import(
    sqlite_snapshot: tuple[Path, dict[str, Any]],
) -> None:
    source, _ = sqlite_snapshot
    engine = _prepare_destination()
    try:
        source.chmod(0o600)
        with sqlite3.connect(source) as db:
            db.execute("ALTER TABLE db1_precision_proof ADD COLUMN whole INTEGER")
            db.execute("UPDATE db1_precision_proof SET whole=1.5")
        source.chmod(0o400)
        with engine.begin() as db:
            db.execute(text("ALTER TABLE db1_precision_proof ADD COLUMN whole INTEGER"))
        manifest = {
            "bytes": source.stat().st_size,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
        with pytest.raises(MigrationFailure, match="db1_precision_proof.*invalid.*value"):
            migrate_snapshot(source, manifest, Settings().database_url)
        with engine.connect() as db:
            assert db.scalar(text("SELECT count(*) FROM db1_precision_proof")) == 0
            assert db.scalar(text("SELECT count(*) FROM twf_orders")) == 0
    finally:
        engine.dispose()


def test_snapshot_requires_matching_backup_manifest(
    sqlite_snapshot: tuple[Path, dict[str, Any]],
) -> None:
    source, manifest = sqlite_snapshot
    with pytest.raises(MigrationFailure, match="checksum"):
        migrate_snapshot(source, {**manifest, "sha256": "forged"}, Settings().database_url)


def test_queue_fifty_separate_service_admission_races(
    client: TestClient, account: tuple[str, OrderProvider]
) -> None:
    factory = service(client).factory
    context = queue_service(client).context
    for _ in range(55):
        order = ready_order(client, account[0])
        oid = UUID(order["twf_order_id"])
        services = (QueueService(factory, context), QueueService(factory, context))
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [
                pool.submit(q.admit, oid, expected_order_version=order["version"]) for q in services
            ]
            results = [t.result() for t in tasks]
        assert results[0].queue_entry_id == results[1].queue_entry_id
        with factory() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(TWFQueueEntryRecord)
                    .where(TWFQueueEntryRecord.twf_order_id == oid)
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(TWFQueueEventRecord)
                    .where(TWFQueueEventRecord.twf_order_id == oid)
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(TWFOrderEventRecord)
                    .where(
                        TWFOrderEventRecord.twf_order_id == oid,
                        TWFOrderEventRecord.to_state == "QUEUED",
                    )
                )
                == 1
            )
            row = db.get(TWFOrderRecord, oid)
            assert row is not None and row.state == "QUEUED"
    assert account[1].calls == []


@pytest.mark.parametrize("actions", [("hold", "hold"), ("hold", "release"), ("release", "release")])
def test_queue_hold_release_races(
    client: TestClient, account: tuple[str, OrderProvider], actions: tuple[str, str]
) -> None:
    factory = service(client).factory
    context = queue_service(client).context
    services = (QueueService(factory, context), QueueService(factory, context))
    for _ in range(10):
        order = ready_order(client, account[0])
        entry = services[0].admit(UUID(order["twf_order_id"]))
        if actions[0] == "release":
            entry = services[0].hold(entry.queue_entry_id, expected_version=entry.version)

        def change(index: int, entry: Any = entry) -> str:
            try:
                return cast(
                    str,
                    getattr(services[index], actions[index])(
                        entry.queue_entry_id, expected_version=entry.version
                    ).queue_state,
                )
            except QueueError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(change, (0, 1)))
        assert sum(value in {"READY", "HELD"} for value in outcomes) == 1, outcomes
        final = services[0].get_entry(entry.queue_entry_id)
        assert final.version == entry.version + 1
        assert len(services[0].history(entry.queue_entry_id)) == final.version
        with pytest.raises(QueueError) as error:
            services[0].hold(entry.queue_entry_id, expected_version=entry.version)
        assert error.value.code == QueueErrorCode.QUEUE_VERSION_CONFLICT
    assert account[1].calls == []


def test_postgres_isolation_and_future_row_lock_capability(migrated_database: None) -> None:
    engine = create_database_engine(Settings())
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL row lock capability")
    try:
        with engine.begin() as db:
            assert db.get_isolation_level() == "READ COMMITTED"
            assert db.scalar(text("SHOW TimeZone")) == "UTC"
            db.execute(text("CREATE TABLE db1_lock_probe (id INTEGER PRIMARY KEY)"))
            db.execute(text("INSERT INTO db1_lock_probe VALUES (1),(2)"))
        with engine.begin() as first, engine.begin() as second:
            assert first.scalar(text("SELECT id FROM db1_lock_probe WHERE id=1 FOR UPDATE")) == 1
            assert second.execute(
                text("SELECT id FROM db1_lock_probe ORDER BY id FOR UPDATE SKIP LOCKED")
            ).scalars().all() == [2]
    finally:
        engine.dispose()


def test_operation_baseline(client: TestClient, account: tuple[str, OrderProvider]) -> None:
    from statistics import median
    from time import perf_counter

    timings: dict[str, list[float]] = {}

    def measure(name: str, method: str, url: str, body: Any = None) -> Any:
        start = perf_counter()
        response = client.request(method, url, json=body, headers=HEADERS)
        timings.setdefault(name, []).append((perf_counter() - start) * 1000)
        assert response.status_code == 200, response.text
        return response.json()

    for _ in range(7):
        request = payload(account[0], "HAL", "1")
        preview = measure("Preview", "POST", "/api/v1/twf-orders/preview", request)
        created = measure(
            "Create_READY",
            "POST",
            "/api/v1/twf-orders",
            {**request, "preview_id": preview["preview_id"]},
        )
        entry = measure(
            "Admission",
            "POST",
            "/api/v1/twf-queue/admit",
            {"twf_order_id": created["order"]["twf_order_id"]},
        )
        key = entry["queue_entry_id"]
        measure("Hold", "POST", f"/api/v1/twf-queue/{key}/hold", {"expected_version": 1})
        measure("Release", "POST", f"/api/v1/twf-queue/{key}/release", {"expected_version": 2})
        measure("Orders_list", "GET", "/api/v1/twf-orders")
        measure("Queue_list", "GET", "/api/v1/twf-queue")
        measure("Watchlists_read", "GET", "/api/v1/watchlists")
        measure("Scanner_history_read", "GET", "/api/v1/scanner/runs")
    dialect = service(client).factory.kw["bind"].dialect.name
    print(
        "DB1_BENCHMARK="
        + json.dumps(
            {
                "backend": dialect,
                "rounds": 7,
                "median_ms": {key: round(median(values), 3) for key, values in timings.items()},
            }
        )
    )
    assert account[1].calls == []
