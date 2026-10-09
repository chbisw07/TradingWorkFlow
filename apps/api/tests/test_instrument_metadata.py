import csv
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from twf.api.auth import get_current_user
from twf.config.settings import Settings
from twf.infrastructure.database import Base, create_database_engine, create_session_factory
from twf.infrastructure.instrument_metadata import (
    InstrumentMetadataRefreshRow,
    InstrumentMetadataRow,
)
from twf.instrument_metadata.importer import SnapshotImporter, SnapshotValidationError
from twf.instrument_metadata.service import InstrumentMetadataService
from twf.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOT = FIXTURES / "instrument_metadata_v1.csv"
SUMMARY = FIXTURES / "instrument_metadata_v1_summary.json"


@pytest.fixture
def database() -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    engine = create_database_engine(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(engine)
    try:
        yield engine, create_session_factory(engine)
    finally:
        engine.dispose()


def copy_snapshot(tmp_path: Path) -> Path:
    path = tmp_path / "metadata.csv"
    path.write_bytes(SNAPSHOT.read_bytes())
    return path


def mutate(path: Path, operation: str) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        assert fields is not None
        rows = list(reader)
    if operation == "unsupported_schema":
        rows[0]["metadata_schema_version"] = "99"
    elif operation == "inconsistent_run":
        rows[0]["dataset_run_id"] = "different-run"
    elif operation == "duplicate_symbol":
        rows[1]["symbol"] = rows[0]["symbol"]
    elif operation == "malformed_market_cap":
        rows[0]["market_cap"] = "12.34"
    elif operation == "invalid_category":
        rows[0]["market_cap_category"] = "MEGA"
    else:
        raise AssertionError(operation)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def identity_only_snapshot(tmp_path: Path) -> Path:
    path = copy_snapshot(tmp_path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        assert fields is not None
        rows = list(reader)
    for row in rows:
        row["dataset_run_id"] = "33333333-3333-4333-8333-333333333333"
        row["dataset_generated_at"] = "2026-12-09T09:15:00+05:30"
        row["retrieved_at"] = "2026-12-09T09:20:00+05:30"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def next_snapshot(tmp_path: Path) -> Path:
    path = copy_snapshot(tmp_path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        assert fields is not None
        rows = list(reader)
    rows = [row for row in rows if row["symbol"] != "HEALTHCO"]
    for row in rows:
        row["dataset_run_id"] = "22222222-2222-4222-8222-222222222222"
        row["dataset_generated_at"] = "2026-11-09T09:15:00+05:30"
        row["retrieved_at"] = "2026-11-09T09:20:00+05:30"
        if row["symbol"] == "TECHCO":
            row["sector"] = "Industrials"
        if row["symbol"] == "CREDITCO":
            row["market_cap"] = "8500000"
    added = dict(rows[-1])
    added.update(
        symbol="NEWCO",
        isin="INE000F01006",
        company_name="New Company Limited",
        instrument_kind="EQUITY",
        underlying_symbol="",
        underlying_resolution_method="",
        notes="",
    )
    rows.append(added)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_schema_is_system_global_bigint_and_indexed(
    database: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, _ = database
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("instrument_metadata")}
    assert "owner_id" not in columns
    assert columns["market_cap"]["type"].python_type is int
    uniques = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("instrument_metadata")
    }
    assert ("exchange", "symbol") in uniques
    assert ("isin",) in uniques
    indexes = {item["name"] for item in inspector.get_indexes("instrument_metadata")}
    assert "ix_instrument_metadata_sector" in indexes
    assert "ix_instrument_metadata_context_benchmark" in indexes
    refresh_indexes = {
        item["name"] for item in inspector.get_indexes("instrument_metadata_refreshes")
    }
    assert "ix_instrument_metadata_refresh_dataset_status" in refresh_indexes


def test_valid_import_lookup_and_idempotent_replay(
    database: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = database
    importer = SnapshotImporter(factory, minimum_rows=1)
    result = importer.import_snapshot(SNAPSHOT, SUMMARY)
    assert (result.status, result.inserted_rows, result.updated_rows, result.unchanged_rows) == (
        "SUCCESS",
        5,
        0,
        0,
    )
    replay = importer.import_snapshot(SNAPSHOT, SUMMARY)
    assert replay.status == "ALREADY_IMPORTED"
    assert replay.refresh_id == result.refresh_id
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(InstrumentMetadataRefreshRow)) == 1
        service = InstrumentMetadataService(session)
        tech = service.get_by_symbol("nse", "techco")
        assert tech and tech.sector == "Technology" and tech.market_cap_category == "LARGE"
        assert tech.twf_cap_tier == "LARGE" and tech.context_benchmark_symbol == "NIFTYIT"
        assert service.get_by_isin("ine000b01002").industry == "Credit Services"  # type: ignore[union-attr]
        assert service.get_sector("NSE", "UNKNOWN") is None
        assert service.get_context_benchmark("NSE", "CREDITCO") == "NIFTY_FIN_SERVICE"
        bulk = service.get_many_by_symbols("NSE", ("TECHCO", "MISSING", "HEALTHCO"))
        assert [item.symbol for item in bulk.items] == ["TECHCO", "HEALTHCO"]
        assert bulk.missing_symbols == ("MISSING",)
        rights = service.get_by_symbol("NSE", "TECHCO-RE")
        assert rights and rights.instrument_kind == "RIGHTS_ENTITLEMENT"
        assert rights.underlying_symbol == "TECHCO"
        assert rights.notes == "INHERITED_FROM_UNDERLYING:TECHCO"
        status = service.get_last_refresh_status()
        assert status.health == "AVAILABLE" and status.total_instruments == 5
        assert status.dataset_run_id == result.dataset_run_id
        assert status.sector_coverage == 80


@pytest.mark.parametrize(
    ("operation", "code"),
    [
        ("unsupported_schema", "UNSUPPORTED_SCHEMA_VERSION"),
        ("inconsistent_run", "INCONSISTENT_DATASET_IDENTITY"),
        ("duplicate_symbol", "DUPLICATE_EXCHANGE_SYMBOL"),
        ("malformed_market_cap", "INVALID_MARKET_CAP"),
        ("invalid_category", "INVALID_MARKET_CAP_CATEGORY"),
    ],
)
def test_snapshot_validation_rejects_corruption(
    database: tuple[Engine, sessionmaker[Session]],
    tmp_path: Path,
    operation: str,
    code: str,
) -> None:
    _, factory = database
    path = copy_snapshot(tmp_path)
    mutate(path, operation)
    with pytest.raises(SnapshotValidationError) as caught:
        SnapshotImporter(factory, minimum_rows=1).import_snapshot(path)
    assert caught.value.code == code
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(InstrumentMetadataRow)) == 0
        failure = session.scalar(select(InstrumentMetadataRefreshRow))
        assert failure and failure.status == "FAILED" and failure.error_summary == code


def test_new_run_with_same_metadata_counts_unchanged_and_preserves_updated_at(
    database: tuple[Engine, sessionmaker[Session]], tmp_path: Path
) -> None:
    _, factory = database
    importer = SnapshotImporter(factory, minimum_rows=1)
    importer.import_snapshot(SNAPSHOT, SUMMARY)
    with factory() as session:
        before = session.scalar(
            select(InstrumentMetadataRow.updated_at).where(InstrumentMetadataRow.symbol == "TECHCO")
        )
    result = importer.import_snapshot(identity_only_snapshot(tmp_path))
    assert (result.inserted_rows, result.updated_rows, result.unchanged_rows) == (0, 0, 5)
    with factory() as session:
        row = session.scalar(
            select(InstrumentMetadataRow).where(InstrumentMetadataRow.symbol == "TECHCO")
        )
        assert row and row.updated_at == before
        assert row.dataset_run_id == "33333333-3333-4333-8333-333333333333"


def test_changed_snapshot_counts_and_missing_policy(
    database: tuple[Engine, sessionmaker[Session]], tmp_path: Path
) -> None:
    _, factory = database
    importer = SnapshotImporter(factory, minimum_rows=1)
    importer.import_snapshot(SNAPSHOT, SUMMARY)
    result = importer.import_snapshot(next_snapshot(tmp_path))
    assert (
        result.inserted_rows,
        result.updated_rows,
        result.unchanged_rows,
        result.missing_rows,
    ) == (1, 2, 2, 1)
    with factory() as session:
        service = InstrumentMetadataService(session)
        assert service.get_by_symbol("NSE", "TECHCO").sector == "Industrials"  # type: ignore[union-attr]
        assert service.get_by_symbol("NSE", "CREDITCO").market_cap == 8_500_000  # type: ignore[union-attr]
        missing = service.get_by_symbol("NSE", "HEALTHCO")
        assert missing and missing.present_in_latest_snapshot is False
        assert service.get_by_symbol("NSE", "NEWCO") is not None
        assert service.get_last_refresh_status().total_instruments == 5


def test_corrupt_followup_is_atomic_and_last_success_survives(
    database: tuple[Engine, sessionmaker[Session]], tmp_path: Path
) -> None:
    _, factory = database
    importer = SnapshotImporter(factory, minimum_rows=1)
    first = importer.import_snapshot(SNAPSHOT, SUMMARY)
    path = copy_snapshot(tmp_path)
    mutate(path, "malformed_market_cap")
    with pytest.raises(SnapshotValidationError):
        importer.import_snapshot(path)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(InstrumentMetadataRow)) == 5
        assert session.scalar(select(func.count()).select_from(InstrumentMetadataRefreshRow)) == 2
        tech = InstrumentMetadataService(session).get_by_symbol("NSE", "TECHCO")
        assert tech and tech.dataset_run_id == first.dataset_run_id and tech.market_cap == 9_000_000
        status = InstrumentMetadataService(session).get_last_refresh_status()
        assert status.health == "DEGRADED"
        assert status.latest_attempt_status == "FAILED"
        assert status.dataset_run_id == first.dataset_run_id


def test_no_refresh_status(database: tuple[Engine, sessionmaker[Session]]) -> None:
    _, factory = database
    with factory() as session:
        status = InstrumentMetadataService(session).get_last_refresh_status()
        assert status.health == "NOT_IMPORTED"
        assert status.total_instruments == 0


def test_authenticated_bounded_read_api(database: tuple[Engine, sessionmaker[Session]]) -> None:
    engine, factory = database
    SnapshotImporter(factory, minimum_rows=1).import_snapshot(SNAPSHOT, SUMMARY)
    app = create_app(Settings(), engine_factory=lambda _: engine)
    with TestClient(app) as client:
        assert client.get("/api/v1/instrument-metadata/status").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: object()
        status = client.get("/api/v1/instrument-metadata/status")
        assert status.status_code == 200 and status.json()["total_instruments"] == 5
        item = client.get("/api/v1/instrument-metadata/NSE/TECHCO")
        assert item.status_code == 200 and item.json()["context_benchmark_symbol"] == "NIFTYIT"
        assert item.json()["macro_sector"] == "Information Technology"
        assert item.json()["basic_industry"] == "Software"
        by_isin = client.get("/api/v1/instrument-metadata/by-isin/INE000B01002")
        assert by_isin.status_code == 200 and by_isin.json()["symbol"] == "CREDITCO"
        bulk = client.post(
            "/api/v1/instrument-metadata/lookup",
            headers={"Origin": "http://localhost:3000"},
            json={"exchange": "NSE", "symbols": ["TECHCO", "MISSING"]},
        )
        assert bulk.status_code == 200 and bulk.json()["missing_symbols"] == ["MISSING"]
        assert client.get("/api/v1/instrument-metadata/NSE/NOPE").status_code == 404
        oversized = [f"S{index}" for index in range(101)]
        response = client.post(
            "/api/v1/instrument-metadata/lookup",
            headers={"Origin": "http://localhost:3000"},
            json={"exchange": "NSE", "symbols": oversized},
        )
        assert response.status_code == 422
