"""Scanner and Watchlist consumption of the system-global metadata snapshot."""

import csv
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from test_scanner_v2 import BASE as SCANNER_BASE
from test_scanner_v2 import config, install_market
from test_watchlists import BASE as WATCHLIST_BASE
from test_watchlists import HEADERS, add, create, provider
from test_watchlists import client as client  # noqa: F401

from twf.instrument_metadata.importer import SnapshotImporter
from twf.watchlists.service import WatchlistService
from twf.watchlists.system import SystemUniverseCatalog

SNAPSHOT = Path(__file__).parent / "fixtures" / "instrument_metadata_product.csv"


def seed(client: TestClient, snapshot: Path = SNAPSHOT) -> None:
    factory = cast(Any, client.app).state.session_factory
    SnapshotImporter(factory, minimum_rows=1).import_snapshot(snapshot)


def metadata_selects(client: TestClient) -> tuple[list[str], Any]:
    statements: list[str] = []
    engine = cast(Any, client.app).state.database_engine

    def observe(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        lowered = statement.lower()
        if " from instrument_metadata " in f" {lowered.replace(chr(10), ' ')} ":
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    return statements, (engine, observe)


def stop_observing(handle: Any) -> None:
    event.remove(handle[0], "before_cursor_execute", handle[1])


def stale_without_reliance(tmp_path: Path) -> Path:
    target = tmp_path / "instrument_metadata_next.csv"
    with SNAPSHOT.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        rows = [row for row in reader if row["symbol"] != "RELIANCE"]
    assert fields is not None
    for row in rows:
        row["dataset_run_id"] = "44444444-4444-4444-8444-444444444444"
        row["dataset_generated_at"] = "2026-11-09T09:15:00+05:30"
        row["retrieved_at"] = "2026-11-09T09:20:00+05:30"
    with target.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_scanner_and_watchlist_share_one_bulk_metadata_source_without_behavior_change(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_market(client, monkeypatch)
    before = client.post(SCANNER_BASE + "/runs", json=config(), headers=HEADERS).json()
    assert before["rows"][0]["instrument_metadata"] is None

    seed(client)
    statements, handle = metadata_selects(client)
    try:
        after_response = client.post(SCANNER_BASE + "/runs", json=config(), headers=HEADERS)
    finally:
        stop_observing(handle)
    assert after_response.status_code == 200, after_response.text
    after = after_response.json()
    assert len(statements) == 1
    assert after["counts"] == before["counts"]
    assert after["rows"][0]["outcome"] == before["rows"][0]["outcome"]
    assert after["rows"][0]["metrics"] == before["rows"][0]["metrics"]
    assert (
        after["rows"][0]["analysis"]["technical_score"]
        == before["rows"][0]["analysis"]["technical_score"]
    )
    assert (
        after["rows"][0]["analysis"]["final_relevance"]
        == before["rows"][0]["analysis"]["final_relevance"]
    )
    scanner_metadata = after["rows"][0]["instrument_metadata"]
    assert scanner_metadata["sector"] == "Energy"
    assert scanner_metadata["industry"] == "Oil & Gas Exploration"
    assert scanner_metadata["market_cap"] == 20_000_000_000_000
    assert scanner_metadata["market_cap_category"] == "LARGE"
    assert scanner_metadata["twf_cap_tier"] == "LARGE"
    assert scanner_metadata["context_benchmark"] == "NIFTY OIL & GAS"

    key = create(client, "Metadata consistency")
    add(client, key)
    statements, handle = metadata_selects(client)
    try:
        detail_response = client.get(f"{WATCHLIST_BASE}/{key}")
    finally:
        stop_observing(handle)
    assert detail_response.status_code == 200, detail_response.text
    assert len(statements) == 1
    detail = detail_response.json()
    by_symbol = {item["instrument"]["symbol"]: item for item in detail["items"]}
    assert by_symbol["RELIANCE"]["instrument_metadata"] == scanner_metadata
    assert by_symbol["INFY"]["instrument_metadata"]["sector"] == "Technology"
    assert by_symbol["NIFTY"]["instrument_metadata"] is None
    assert by_symbol["NIFTY99DECFUT"]["instrument_metadata"] is None
    assert by_symbol["NIFTY99DEC25000CE"]["instrument_metadata"] is None

    factory = cast(Any, client.app).state.session_factory
    SnapshotImporter(factory, minimum_rows=1).import_snapshot(stale_without_reliance(tmp_path))
    stale = client.get(f"{WATCHLIST_BASE}/{key}").json()
    stale_reliance = next(
        item for item in stale["items"] if item["instrument"]["symbol"] == "RELIANCE"
    )["instrument_metadata"]
    assert stale_reliance["sector"] == "Energy"
    assert stale_reliance["present_in_latest_snapshot"] is False


def test_built_in_watchlist_uses_same_metadata_enrichment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(client)

    async def fetch(definition: Any) -> bytes:
        return (
            b"Company Name,Industry,Symbol,Series\n"
            b"Reliance Industries,Energy,RELIANCE,EQ\n"
            b"Infosys,IT,INFY,EQ\n"
        )

    app = cast(Any, client.app)
    app.state.system_universes = SystemUniverseCatalog(fetch)
    dhan = provider()
    monkeypatch.setattr(
        app.state.dhan_credentials,
        "capture",
        lambda *args, **kwargs: SimpleNamespace(
            provider=dhan, status=SimpleNamespace(generation=12)
        ),
    )
    built_in = next(
        row for row in client.get(WATCHLIST_BASE).json() if row["system_code"] == "NIFTY_500"
    )
    statements, handle = metadata_selects(client)
    try:
        response = client.get(f"{WATCHLIST_BASE}/{built_in['id']}")
    finally:
        stop_observing(handle)
    assert response.status_code == 200, response.text
    assert len(statements) == 1
    items = {item["instrument"]["symbol"]: item for item in response.json()["items"]}
    assert items["INFY"]["instrument_metadata"]["sector"] == "Technology"
    assert items["RELIANCE"]["instrument_metadata"]["context_benchmark"] == "NIFTY OIL & GAS"


def test_derivative_metadata_target_requires_canonical_unambiguous_underlying() -> None:
    future = next(
        item for item in __import__("test_watchlists").instruments() if item.symbol.endswith("FUT")
    )
    assert WatchlistService._metadata_target(future, "FUTURE") == (
        ("NSE", "NIFTY"),
        "UNDERLYING",
    )
    ambiguous = future.model_copy(
        update={"underlying": future.underlying.model_copy(update={"ambiguous": True})}
    )
    assert WatchlistService._metadata_target(ambiguous, "FUTURE") is None
    assert WatchlistService._metadata_target(future, "INDEX") is None
