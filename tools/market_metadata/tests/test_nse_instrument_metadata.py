from __future__ import annotations

import csv
import json
import logging
import re
import sys
from argparse import Namespace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools.market_metadata import nse_instrument_metadata as metadata

FIXTURES = Path(__file__).parent / "fixtures"
UNIVERSE = FIXTURES / "nse_equity_universe.csv"
CLASSIFICATION = FIXTURES / "nse_classification.csv"


def run_identity() -> metadata.DatasetRun:
    return metadata.DatasetRun("1", "test-run", "2026-10-09T00:00:00+00:00")


def row(symbol: str, cap: int | None = None, **values: str) -> metadata.MetadataRow:
    item = metadata.MetadataRow(
        exchange="NSE",
        symbol=symbol,
        series="EQ",
        isin=values.pop("isin", f"ISIN-{symbol}"),
        company_name=f"{symbol} Limited",
        listing_date="01-JAN-2000",
        metadata_schema_version="1",
        dataset_run_id="test-run",
        dataset_generated_at="2026-10-09T00:00:00+00:00",
        market_cap=str(cap) if cap is not None else "",
        **values,
    )
    return item


def output_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--input-csv",
        str(UNIVERSE),
        "--classification-csv",
        str(CLASSIFICATION),
        "--output",
        str(tmp_path / "metadata.csv"),
        "--unresolved-output",
        str(tmp_path / "unresolved.csv"),
        "--summary-output",
        str(tmp_path / "summary.json"),
        "--checkpoint",
        str(tmp_path / "checkpoint.json"),
        "--checkpoint-every",
        "2",
        *extra,
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def assert_ist_timestamp(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(hours=5, minutes=30)
    assert value.endswith("+05:30")


def assert_date_only(value: str) -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
    date.fromisoformat(value)


def test_operational_timestamp_helpers_use_asia_kolkata() -> None:
    assert metadata.APP_TIMEZONE.key == "Asia/Kolkata"
    assert_ist_timestamp(metadata.now_iso())
    assert_date_only(metadata.today_iso())


def test_console_log_formatter_uses_asia_kolkata() -> None:
    record = logging.LogRecord("metadata", logging.INFO, "", 0, "ready", (), None)
    record.created = datetime(2026, 10, 9, 3, 39, 41, 229000, tzinfo=UTC).timestamp()
    formatted = metadata.AppTimezoneFormatter("%(asctime)s %(levelname)s %(message)s").format(
        record
    )
    assert formatted == "2026-10-09 09:09:41,229+05:30 INFO ready"


def test_nse_parsing_and_isin_first_series_deduplication() -> None:
    text = UNIVERSE.read_text(encoding="utf-8")
    parsed = metadata.parse_nse_universe(text)
    assert len(parsed) == 6
    loaded = metadata.load_universe(Namespace(input_csv=UNIVERSE, timeout=1.0, retries=1))
    assert len(loaded) == 5
    tech = next(item for item in loaded if item.isin == "INE000A01001")
    assert (tech.symbol, tech.series) == ("TECHCO", "EQ")


def test_yahoo_enrichment_normalizes_values_and_preserves_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTicker:
        def get_info(self) -> dict[str, Any]:
            return {
                "sector": "Technology",
                "industry": "Information Technology Services",
                "marketCap": "1,234,567",
                "currency": "INR",
            }

    monkeypatch.setitem(
        sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: FakeTicker())
    )
    item = row("TECHCO")
    assert metadata.yahoo_lookup(item, 0, False) is True
    assert item.market_cap == "1234567"
    assert item.market_cap_currency == "INR"
    assert item.market_cap_source == "YAHOO"
    assert item.sector_source == "YAHOO"
    assert item.industry_source == "YAHOO"
    assert item.sector_as_of and item.industry_as_of and item.market_cap_as_of
    assert_date_only(item.sector_as_of)
    assert_date_only(item.industry_as_of)
    assert_date_only(item.market_cap_as_of)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1,234", 1234), (123.9, 123), ("", None), ("nan", None), (True, None)],
)
def test_market_cap_parsing(value: object, expected: int | None) -> None:
    assert metadata.parse_int(value) == expected


def test_full_universe_rank_categories_and_twf_tiers() -> None:
    rows = [row(f"S{index:04}", 2_000_000 - index) for index in range(1, 1002)]
    metadata.apply_market_cap_ranking(rows, allow_relative_ranking=True)
    ranked = sorted(rows, key=lambda item: int(item.market_cap_rank))
    assert ranked[0].market_cap_category == "LARGE"
    assert ranked[99].market_cap_category == "LARGE"
    assert ranked[100].market_cap_category == "MID"
    assert ranked[249].market_cap_category == "MID"
    assert ranked[250].market_cap_category == "SMALL"
    assert ranked[999].twf_cap_tier == "SMALL"
    assert ranked[1000].twf_cap_tier == "MICRO"
    assert [int(item.market_cap_rank) for item in ranked] == list(range(1, 1002))


def test_partial_universe_never_has_rank_or_categories() -> None:
    rows = [row("A", 300), row("B", 200)]
    metadata.apply_market_cap_ranking(rows, allow_relative_ranking=True)
    metadata.apply_market_cap_ranking(rows, allow_relative_ranking=False)
    assert all(
        not any(
            (
                item.market_cap_rank,
                item.market_cap_category,
                item.market_cap_category_method,
                item.twf_cap_tier,
                item.twf_cap_tier_method,
            )
        )
        for item in rows
    )


def test_exact_benchmark_mapping_and_credit_services_regression() -> None:
    credit = row("CREDITCO", sector="Financial Services", industry="Credit Services")
    metadata.apply_context_benchmark(credit)
    assert credit.context_benchmark == "NIFTY FINANCIAL SERVICES"
    assert credit.context_benchmark_symbol == "NIFTY_FIN_SERVICE"
    assert credit.benchmark_mapping_basis == "INDUSTRY:Credit Services"
    similar = row("SIMILAR", sector="Other", industry="Credit Services Platform")
    metadata.apply_context_benchmark(similar)
    assert similar.context_benchmark == ""
    assert similar.context_benchmark != "NIFTY IT"


def test_rights_inference_inheritance_and_note_idempotence() -> None:
    kind, underlying, method = metadata.infer_instrument_relationship(
        "CENTEXT-RE", "EQ", "Centext Rights"
    )
    assert (kind, underlying, method) == (
        "RIGHTS_ENTITLEMENT",
        "CENTEXT",
        "SYMBOL_SUFFIX_INFERRED",
    )
    equity = row(
        "CENTEXT",
        10_000,
        sector="Technology",
        sector_source="YAHOO",
        sector_as_of="2026-10-09",
        industry="Software - Application",
        industry_source="YAHOO",
        industry_as_of="2026-10-09",
        resolution_status="RESOLVED",
        classification_completeness="SECTOR_INDUSTRY",
        confidence="0.85",
    )
    metadata.apply_context_benchmark(equity)
    rights = row(
        "CENTEXT-RE",
        isin="ISIN-CENTEXT-RE",
        instrument_kind="RIGHTS_ENTITLEMENT",
        underlying_symbol="CENTEXT",
        underlying_resolution_method="SYMBOL_SUFFIX_INFERRED",
    )
    rows = [equity, rights]
    metadata.inherit_rights_entitlement_metadata(rows)
    metadata.inherit_rights_entitlement_metadata(rows)
    metadata.apply_market_cap_ranking(rows, allow_relative_ranking=True)
    assert rights.sector == equity.sector
    assert rights.industry == equity.industry
    assert rights.context_benchmark == "NIFTY IT"
    assert rights.market_cap == equity.market_cap
    assert rights.market_cap_rank == equity.market_cap_rank
    assert rights.market_cap_category == equity.market_cap_category
    assert rights.twf_cap_tier == equity.twf_cap_tier
    assert rights.notes.count("INHERITED_FROM_UNDERLYING:CENTEXT") == 1
    assert metadata.has_duplicate_notes(rights.notes) is False


def test_dataset_run_identity_and_schema_are_consistent_across_rows() -> None:
    dataset = metadata.new_dataset_run()
    items = metadata.parse_nse_universe(UNIVERSE.read_text(encoding="utf-8"))[:3]
    rows = [metadata.metadata_row_from_universe(item, dataset) for item in items]
    assert dataset.metadata_schema_version == metadata.METADATA_SCHEMA_VERSION == "1"
    assert {item.dataset_run_id for item in rows} == {dataset.dataset_run_id}
    assert {item.dataset_generated_at for item in rows} == {dataset.dataset_generated_at}
    assert metadata.dataset_run_from_rows(rows) == dataset
    assert_ist_timestamp(dataset.dataset_generated_at)


def test_legacy_seed_reuse_renames_cap_fields_and_keeps_new_run_identity(
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "seed.csv"
    seed_path.write_text(
        "isin,symbol,sector,sector_source,official_cap_category,official_cap_category_method,dataset_run_id\n"
        "INE000A01001,TECHCO,Technology,YAHOO,LARGE,OLD_METHOD,old-run\n",
        encoding="utf-8",
    )
    seed = metadata.load_seed_csv(seed_path)
    item = metadata.metadata_row_from_universe(
        metadata.UniverseInstrument("NSE", "TECHCO", "EQ", "INE000A01001", "Tech", "01-JAN-2000"),
        run_identity(),
    )
    metadata.apply_seed(item, seed)
    assert item.sector == "Technology"
    assert item.market_cap_category == "LARGE"
    assert item.market_cap_category_method == "OLD_METHOD"
    assert item.dataset_run_id == "test-run"


def test_market_cap_only_refresh_preserves_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTicker:
        def get_info(self) -> dict[str, Any]:
            return {
                "sector": "Wrong Sector",
                "industry": "Wrong Industry",
                "marketCap": 9_999,
                "currency": "INR",
            }

    monkeypatch.setitem(
        sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: FakeTicker())
    )
    item = row(
        "TECHCO",
        100,
        sector="Technology",
        sector_source="NSE_BULK_CLASSIFICATION",
        industry="Information Technology Services",
        industry_source="NSE_BULK_CLASSIFICATION",
    )
    assert metadata.yahoo_lookup(item, 0, True) is True
    assert item.market_cap == "9999"
    assert item.sector == "Technology"
    assert item.industry == "Information Technology Services"


def test_checkpoint_round_trip_is_atomic_and_preserves_run_identity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "checkpoint.json"
    dataset = run_identity()
    metadata.save_checkpoint(path, {"ISIN:A", "ISIN:B"}, dataset)
    loaded = metadata.load_checkpoint(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.completed_keys == frozenset({"ISIN:A", "ISIN:B"})
    assert loaded.dataset_run == dataset
    assert_ist_timestamp(payload["updated_at"])
    assert not path.with_suffix(".json.tmp").exists()


def test_summary_statistics_and_change_summary() -> None:
    rows = [
        row(
            "A",
            200,
            sector="Technology",
            industry="Software - Application",
            resolution_status="RESOLVED",
        ),
        row("B", resolution_status="UNRESOLVED"),
    ]
    for item in rows:
        metadata.apply_context_benchmark(item)
    metadata.apply_market_cap_ranking(rows, allow_relative_ranking=True)
    validation = metadata.validate_snapshot(
        rows,
        relative_ranking_applied=True,
        minimum_universe_size=1,
        minimum_sector_coverage=0,
        minimum_market_cap_coverage=0,
    )
    seed = {
        metadata.canonical_key(rows[0].isin, rows[0].symbol): {
            "symbol": "A",
            "sector": "Financial Services",
            "industry": "Credit Services",
            "market_cap": "100",
            "market_cap_category": "MID",
            "twf_cap_tier": "MID",
            "resolution_status": "UNRESOLVED",
        },
        "ISIN:REMOVED": {"symbol": "REMOVED"},
    }
    changes = metadata.build_change_summary(rows, seed)
    assert changes["rows_added"] == 1
    assert changes["rows_removed"] == 1
    assert changes["sector_changed"] == 1
    assert changes["market_cap_changed"] == 1
    assert changes["newly_resolved"] == 1
    summary = metadata.summarize(
        rows,
        dataset_run=run_identity(),
        relative_ranking_applied=True,
        unresolved_count=1,
        processed_this_run=2,
        validation=validation,
        change_summary=changes,
    )
    assert summary["metadata_schema_version"] == 1
    assert summary["utility_version"] == "3.2"
    assert summary["total_rows"] == 2
    assert summary["with_sector"] == 1
    assert summary["market_cap_category_counts"] == {"LARGE": 1}
    assert summary["change_summary"]["rows_removed"] == 1
    assert_ist_timestamp(summary["generated_at"])


def test_validation_detects_duplicate_notes_and_partial_ranking() -> None:
    item = row(
        "A",
        100,
        market_cap_rank="1",
        market_cap_category="LARGE",
        notes="X; X",
    )
    report = metadata.validate_snapshot(
        [item],
        relative_ranking_applied=False,
        minimum_universe_size=1,
        minimum_sector_coverage=0,
        minimum_market_cap_coverage=0,
    )
    assert report.passed is False
    assert any("partial universe" in error for error in report.errors)
    assert any("duplicate notes" in error for error in report.errors)


def test_offline_end_to_end_partial_run_has_no_ranking_and_atomic_outputs(
    tmp_path: Path,
) -> None:
    assert metadata.main(output_args(tmp_path, "--limit", "3")) == 0
    rows = read_csv(tmp_path / "metadata.csv")
    assert len(rows) == 3
    assert {item["metadata_schema_version"] for item in rows} == {"1"}
    assert len({item["dataset_run_id"] for item in rows}) == 1
    assert len({item["dataset_generated_at"] for item in rows}) == 1
    for item in rows:
        assert_ist_timestamp(item["dataset_generated_at"])
        assert_ist_timestamp(item["retrieved_at"])
        assert_date_only(item["nse_classification_as_of"])
        assert_date_only(item["sector_as_of"])
        assert_date_only(item["industry_as_of"])
    assert all(not item["market_cap_rank"] for item in rows)
    assert all(not item["market_cap_category"] for item in rows)
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["relative_ranking_applied"] is False
    assert summary["validation"]["status"] == "PASS"
    assert_ist_timestamp(summary["dataset_generated_at"])
    assert_ist_timestamp(summary["generated_at"])
    assert not list(tmp_path.glob("*.tmp"))


def test_resume_adds_missing_rows_without_duplicates_and_keeps_run_id(
    tmp_path: Path,
) -> None:
    assert metadata.main(output_args(tmp_path, "--limit", "3")) == 0
    first = read_csv(tmp_path / "metadata.csv")
    first_run = first[0]["dataset_run_id"]
    assert (
        metadata.main(
            output_args(
                tmp_path,
                "--resume",
                "--minimum-universe-size",
                "1",
                "--min-sector-coverage",
                "0",
                "--min-market-cap-coverage",
                "0",
            )
        )
        == 0
    )
    rows = read_csv(tmp_path / "metadata.csv")
    assert len(rows) == 5
    assert len({item["symbol"] for item in rows}) == 5
    assert {item["dataset_run_id"] for item in rows} == {first_run}
    assert {item["dataset_generated_at"] for item in rows} == {first[0]["dataset_generated_at"]}
    rights = next(item for item in rows if item["symbol"] == "TECHCO-RE")
    assert rights["resolution_status"] == "RESOLVED_INHERITED"
    assert rights["notes"].count("INHERITED_FROM_UNDERLYING:TECHCO") == 1


def test_seed_change_summary_is_written_by_offline_end_to_end_run(
    tmp_path: Path,
) -> None:
    seed = tmp_path / "seed.csv"
    seed.write_text(
        "exchange,symbol,series,isin,company_name,listing_date,sector,industry,market_cap,resolution_status\n"
        "NSE,OLD,EQ,INEOLD,Old Limited,01-JAN-2000,Other,Other,1,RESOLVED\n",
        encoding="utf-8",
    )
    args = output_args(
        tmp_path,
        "--seed-csv",
        str(seed),
        "--minimum-universe-size",
        "1",
        "--min-sector-coverage",
        "0",
        "--min-market-cap-coverage",
        "0",
    )
    assert metadata.main(args) == 0
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["change_summary"]["seed_provided"] is True
    assert summary["change_summary"]["rows_added"] == 5
    assert summary["change_summary"]["rows_removed"] == 1


def test_failed_full_validation_preserves_previous_canonical_output(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "metadata.csv"
    canonical.write_text("previous-canonical-snapshot\n", encoding="utf-8")
    assert metadata.main(output_args(tmp_path)) == 2
    assert canonical.read_text(encoding="utf-8") == "previous-canonical-snapshot\n"
    assert metadata.partial_output_path(canonical).exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["validation"]["status"] == "FAIL"
    assert any("required minimum" in error for error in summary["validation"]["errors"])
