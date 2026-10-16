"""Permanent DB1-R1/R2 independent-review reproductions and bounded regressions."""

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, MetaData, Numeric, Table, create_engine, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_broker_v1 import HEADERS, service
from test_twf_orders_oe2 import payload
from test_twf_queue_oe3 import account as account
from test_twf_queue_oe3 import client as client
from test_twf_queue_oe3 import queue_service, ready_order

from twf.config.settings import Settings
from twf.infrastructure.database import DATABASE_SCHEMA_HEAD, create_database_engine
from twf.infrastructure.sqlite_migration import (
    MigrationFailure,
    NumericMigrationFailure,
    _numeric_value,
    _source_rows,
    migrate_snapshot,
)
from twf.queue.errors import QueueError
from twf.queue.service import QueueService


def numeric_pair(
    tmp_path: Path, declaration: str, values: list[str | None]
) -> tuple[Path, dict[str, Any], Engine]:
    engine = create_database_engine(Settings())
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("Import fidelity requires disposable live PostgreSQL")
    source = tmp_path / "precision.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE alembic_version(version_num VARCHAR(128) PRIMARY KEY)")
        db.execute("INSERT INTO alembic_version VALUES (?)", (DATABASE_SCHEMA_HEAD,))
        db.execute(f"CREATE TABLE precision_probe(id INTEGER PRIMARY KEY, amount {declaration})")
        db.executemany("INSERT INTO precision_probe VALUES (?, ?)", enumerate(values, 1))
    with engine.begin() as db:
        db.execute(text("CREATE TABLE alembic_version(version_num VARCHAR(128) PRIMARY KEY)"))
        db.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": DATABASE_SCHEMA_HEAD})
        db.execute(
            text(f"CREATE TABLE precision_probe(id INTEGER PRIMARY KEY, amount {declaration})")
        )
    source.chmod(0o400)
    manifest = {
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "bytes": source.stat().st_size,
    }
    return source, manifest, engine


def test_review_numeric_conversion_adversary(tmp_path: Path) -> None:
    """Original R1: never certify 12345678901.12340 for source .12345."""
    source, manifest, engine = numeric_pair(tmp_path, "NUMERIC(20,5)", ["12345678901.12345"])
    source_engine = create_engine(f"sqlite:///{source}")
    table = Table(
        "precision_probe",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("amount", Numeric(20, 5)),
    )
    try:
        # Independent original review oracle, not the migration extractor.
        with source_engine.connect() as db:
            before = db.scalar(select(table.c.amount))
        try:
            report = migrate_snapshot(source, manifest, Settings().database_url)
        except MigrationFailure:
            with engine.connect() as db:
                assert db.scalar(text("SELECT COUNT(*) FROM precision_probe")) == 0
        else:
            with engine.connect() as db:
                after = db.scalar(text("SELECT amount FROM precision_probe"))
            assert report["status"] == "IMPORTED_AND_VERIFIED"
            assert before == after, (before, after, report["status"])
    finally:
        source_engine.dispose()
        engine.dispose()


def test_review_queue_read_committed_torn_read(
    client: TestClient, account: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reads READY; B commits admission; A sees Entry and must replay it."""
    if cast(FastAPI, client.app).state.database_engine.dialect.name != "postgresql":
        pytest.skip("Forced two-snapshot interleaving is PostgreSQL READ COMMITTED specific")
    order = ready_order(client, account[0])
    q, other = queue_service(client), queue_service(client)
    original = q._owned_order
    winner = []

    def read_then_commit(db: Any, owner: Any, oid: Any) -> Any:
        row = original(db, owner, oid)
        assert row.state == "READY"
        winner.append(other.admit(oid))
        return row

    monkeypatch.setattr(q, "_owned_order", read_then_commit)
    replay = q.admit(UUID(order["twf_order_id"]))
    assert replay == winner[0]
    with service(client).factory() as db:
        assert db.scalar(text("SHOW transaction_isolation")) == "read committed"
        assert db.scalar(text("SELECT state FROM twf_orders")) == "QUEUED"
        assert db.scalar(text("SELECT COUNT(*) FROM twf_queue_entries")) == 1
        assert db.scalar(text("SELECT COUNT(*) FROM twf_queue_events")) == 1
        assert db.scalar(text("SELECT COUNT(*) FROM twf_order_events WHERE to_state='QUEUED'")) == 1
    assert account[1].calls == []


GRID = [
    "0",
    "0.1",
    "0.01",
    "1.23000",
    "0.000001",
    "-0.000001",
    "123456789.123456",
    "12345678901.12345",
    "1234567890123456789",
    "1.23456789",
    "1.230000000000000000",
    None,
]


@pytest.mark.parametrize("precision,scale", [(10, 2), (15, 4), (20, 5), (20, 6)])
@pytest.mark.parametrize("index", range(len(GRID) + 3))
def test_numeric_grid_preserves_or_refuses(
    tmp_path: Path, precision: int, scale: int, index: int
) -> None:
    quantum = Decimal(1).scaleb(-scale)
    limit = Decimal(10) ** (precision - scale)
    values = GRID + [str(limit - quantum * 2), str(limit - quantum), str(limit)]
    value = values[index]
    source, manifest, engine = numeric_pair(tmp_path, f"NUMERIC({precision},{scale})", [value])
    try:
        # This independent review oracle deliberately reads the raw driver value;
        # the production importer is forbidden to take this float route.
        with sqlite3.connect(source) as db:
            raw = db.execute("SELECT amount FROM precision_probe").fetchone()[0]
        expected = (
            None
            if raw is None
            else (
                Decimal.from_float(raw).quantize(quantum)
                if isinstance(raw, float)
                else Decimal(raw)
            )
        )
        try:
            result = migrate_snapshot(source, manifest, Settings().database_url)
        except NumericMigrationFailure as exc:
            assert exc.table == "precision_probe"
            assert exc.column == "amount" and exc.primary_key == '["array",[1]]'
            assert str(precision) in exc.declared_type and exc.reason
            with engine.connect() as db:
                assert db.scalar(text("SELECT COUNT(*) FROM precision_probe")) == 0
            # Ordinary exact, representable values must remain supported.
            assert index not in {0, 1, 2, 3, 10, 11}, exc
        else:
            assert result["status"] == "IMPORTED_AND_VERIFIED"
            with engine.connect() as db:
                assert db.scalar(text("SELECT amount FROM precision_probe")) == expected
            if value is not None:
                original = Decimal(value)
                assert original == original.quantize(quantum)
                assert abs(original) < limit
    finally:
        engine.dispose()


def test_numeric_refusal_rolls_back_earlier_tables(tmp_path: Path) -> None:
    source, manifest, engine = numeric_pair(tmp_path, "NUMERIC(10,2)", ["0.1", "1.234"])
    source.chmod(0o600)
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE a_before(id INTEGER PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO a_before VALUES (1,'must roll back')")
    source.chmod(0o400)
    manifest = {
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "bytes": source.stat().st_size,
    }
    with engine.begin() as db:
        db.execute(text("CREATE TABLE a_before(id INTEGER PRIMARY KEY, value TEXT)"))
    progress: list[str] = []
    try:
        with pytest.raises(NumericMigrationFailure) as error:
            migrate_snapshot(source, manifest, Settings().database_url, progress=progress.append)
        assert progress == ["a_before: 1 source rows validated"]
        assert error.value.column == "amount"
        assert error.value.primary_key == '["array",[2]]'
        assert "NUMERIC(10, 2)" in str(error.value)
        assert "1.234" not in str(error.value)
        with engine.connect() as db:
            for table in ("a_before", "precision_probe"):
                assert db.scalar(text(f"SELECT COUNT(*) FROM {table}")) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("storage", ["text", "integer", "blob"])
def test_numeric_exact_storage_classes(tmp_path: Path, storage: str) -> None:
    source, manifest, engine = numeric_pair(tmp_path, "NUMERIC(20,0)", [])
    source.chmod(0o600)
    # Valid decimal TEXT is normally coerced by NUMERIC affinity. This isolated
    # fixture preserves legacy text storage before declaring NUMERIC, without
    # converting it through a float. Never used against a real application DB.
    with sqlite3.connect(source) as db:
        db.execute("DROP TABLE precision_probe")
        db.execute("CREATE TABLE precision_probe(id INTEGER PRIMARY KEY, amount)")
        value: Any = {
            "text": "9007199254740993.0000",
            "integer": 9007199254740993,
            "blob": b"1.23",
        }[storage]
        db.execute("INSERT INTO precision_probe VALUES (1,?)", (value,))
        db.execute("PRAGMA writable_schema=ON")
        db.execute(
            "UPDATE sqlite_master SET sql='CREATE TABLE precision_probe("
            "id INTEGER PRIMARY KEY, amount NUMERIC(20,0))' WHERE name='precision_probe'"
        )
        db.execute("PRAGMA writable_schema=OFF")
    source.chmod(0o400)
    manifest = {
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "bytes": source.stat().st_size,
    }
    try:
        with sqlite3.connect(source) as db:
            assert db.execute("SELECT typeof(amount) FROM precision_probe").fetchone()[0] == storage
        if storage == "text":
            # SQLite integrity_check rejects this deliberately manufactured
            # legacy affinity mismatch. Keep that guard; independently exercise
            # exact TEXT extraction without certifying an invalid database.
            table = Table("precision_probe", MetaData(), autoload_with=engine)
            with sqlite3.connect(source) as db:
                assert list(_source_rows(db, table))[0]["amount"] == Decimal("9007199254740993")
            with pytest.raises(MigrationFailure, match="integrity_check"):
                migrate_snapshot(source, manifest, Settings().database_url)
        elif storage == "blob":
            with pytest.raises(NumericMigrationFailure, match="storage class"):
                migrate_snapshot(source, manifest, Settings().database_url)
        else:
            assert (
                migrate_snapshot(source, manifest, Settings().database_url)["status"]
                == "IMPORTED_AND_VERIFIED"
            )
            with engine.connect() as db:
                assert db.scalar(text("SELECT amount FROM precision_probe")) == Decimal(
                    "9007199254740993"
                )
    finally:
        engine.dispose()


def test_numeric_boundary_rejects_python_float() -> None:
    with pytest.raises(MigrationFailure, match="exact decimal"):
        _numeric_value(0.1, Numeric(10, 2))


def test_numeric_verifier_detects_old_loss(tmp_path: Path) -> None:
    source, manifest, engine = numeric_pair(tmp_path, "NUMERIC(20,5)", ["12345678901.12345"])
    try:
        with engine.begin() as db:
            db.execute(text("INSERT INTO precision_probe VALUES (1,12345678901.12340)"))
        with pytest.raises(MigrationFailure, match="verification failed"):
            migrate_snapshot(source, manifest, Settings().database_url, verify_only=True)
        with engine.connect() as db:
            assert db.scalar(text("SELECT amount FROM precision_probe")) == Decimal(
                "12345678901.12340"
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("series", [1, 2])
def test_review_100_preview_and_queue_races(client: TestClient, account: Any, series: int) -> None:
    factory, ctx = service(client).factory, queue_service(client).context
    rounds = (
        100 if cast(FastAPI, client.app).state.database_engine.dialect.name == "postgresql" else 10
    )
    callers = 0
    for n in range(rounds):
        workers = (2, 5, 10)[n % 3]
        callers += workers
        barrier = Barrier(workers)
        body = payload(account[0], "HAL", "1")
        preview = client.post("/api/v1/twf-orders/preview", json=body, headers=HEADERS)
        assert preview.status_code == 200
        body["preview_id"] = preview.json()["preview_id"]

        def create(_: int, gate: Barrier = barrier, request: Any = body) -> Any:
            gate.wait(timeout=30)
            return client.post("/api/v1/twf-orders", json=request, headers=HEADERS)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            responses = list(pool.map(create, range(workers)))
        assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
        ids = {r.json()["order"]["twf_order_id"] for r in responses}
        assert len(ids) == 1
        oid = UUID(next(iter(ids)))
        barrier = Barrier(workers)

        def admit(_: int, gate: Barrier = barrier, order_id: UUID = oid) -> Any:
            gate.wait(timeout=30)
            return QueueService(factory, ctx).admit(order_id)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            entries = list(pool.map(admit, range(workers)))
        assert len({e.queue_entry_id for e in entries}) == 1
        assert all(e.order.state == "QUEUED" and e.version == 1 for e in entries)
        with factory() as db:
            for sql in [
                "SELECT COUNT(*) FROM twf_orders",
                "SELECT COUNT(*) FROM manual_order_previews WHERE order_id IS NOT NULL",
                "SELECT COUNT(*) FROM twf_queue_entries",
                "SELECT COUNT(*) FROM twf_orders WHERE state='QUEUED'",
                "SELECT COUNT(*) FROM twf_queue_events",
                "SELECT COUNT(*) FROM twf_order_events WHERE to_state='QUEUED'",
            ]:
                assert db.scalar(text(sql)) == n + 1
        print(
            f"series={series} round={n + 1} callers={workers} create_success={workers} "
            f"replay_success={workers} entries=1 queue_events=1 queued_events=1 "
            "state=QUEUED false_errors=0"
        )
    assert account[1].calls == []
    print(
        f"SERIES {series}: {rounds} rounds, {callers} Preview callers, "
        f"{callers} Queue callers, no Broker writes"
    )


def test_replay_rejects_genuine_state_corruption(client: TestClient, account: Any) -> None:
    order = ready_order(client, account[0])
    q = queue_service(client)
    entry = q.admit(UUID(order["twf_order_id"]))
    # OE-3 hardening now rejects the former corruption at the database boundary.
    with pytest.raises(IntegrityError), service(client).factory.begin() as db:
        db.execute(text("UPDATE twf_orders SET state='READY'"))
    assert q.admit(entry.twf_order_id) == entry
    assert len(q.history(entry.queue_entry_id)) == 1


@pytest.mark.parametrize("column", ["owner_id", "twf_order_id"])
def test_replay_identity_constraints_remain(client: TestClient, account: Any, column: str) -> None:
    order = ready_order(client, account[0])
    entry = queue_service(client).admit(UUID(order["twf_order_id"]))
    with pytest.raises(IntegrityError), service(client).factory.begin() as db:
        db.execute(
            text(f"UPDATE twf_queue_entries SET {column}='00000000000000000000000000000001'")
        )
    assert queue_service(client).admit(entry.twf_order_id) == entry


@pytest.mark.parametrize("actions", [["hold"] * 10, ["hold", "release"] * 5, ["release"] * 10])
def test_review_hold_release_10way(client: TestClient, account: Any, actions: list[str]) -> None:
    factory, ctx = service(client).factory, queue_service(client).context
    for _ in range(10):
        order = ready_order(client, account[0])
        q = QueueService(factory, ctx)
        entry = q.admit(UUID(order["twf_order_id"]))
        if actions[0] == "release":
            entry = q.hold(entry.queue_entry_id, expected_version=entry.version)
        barrier = Barrier(10)

        def action(i: int, gate: Barrier = barrier, selected: Any = entry) -> str:
            gate.wait(timeout=30)
            try:
                return str(
                    getattr(QueueService(factory, ctx), actions[i])(
                        selected.queue_entry_id, expected_version=selected.version
                    ).queue_state
                )
            except QueueError as exc:
                return str(exc.code)

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(action, range(10)))
        assert sum(r in {"READY", "HELD"} for r in results) == 1, results
        assert q.get_entry(entry.queue_entry_id).version == entry.version + 1
        assert len(q.history(entry.queue_entry_id)) == entry.version + 1
    assert account[1].calls == []


def test_review_killed_queue_transaction_rolls_back(client: TestClient, account: Any) -> None:
    engine = cast(FastAPI, client.app).state.database_engine
    if engine.dialect.name != "postgresql":
        pytest.skip("Backend termination requires PostgreSQL")
    admin = create_engine(Settings().database_url, isolation_level="AUTOCOMMIT")
    order = ready_order(client, account[0])
    killed = False

    def kill(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        nonlocal killed
        if not killed and statement.lower().startswith("update twf_orders"):
            killed = True
            pid = conn.connection.driver_connection.info.backend_pid
            with admin.connect() as db:
                assert db.scalar(text("SELECT pg_terminate_backend(:p)"), {"p": pid})

    event.listen(engine, "after_cursor_execute", kill)
    try:
        with pytest.raises(DBAPIError):
            queue_service(client).admit(UUID(order["twf_order_id"]))
    finally:
        event.remove(engine, "after_cursor_execute", kill)
        admin.dispose()
    assert killed
    with engine.connect() as db:
        assert db.scalar(text("SELECT state FROM twf_orders")) == "READY"
        assert db.scalar(text("SELECT COUNT(*) FROM twf_queue_entries")) == 0
        assert db.scalar(text("SELECT COUNT(*) FROM twf_queue_events")) == 0
        assert db.scalar(text("SELECT COUNT(*) FROM twf_order_events WHERE to_state='QUEUED'")) == 0
    assert queue_service(client).admit(UUID(order["twf_order_id"])).queue_state == "READY"
