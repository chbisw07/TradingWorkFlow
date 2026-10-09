"""Validate and transactionally import a canonical metadata snapshot."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from twf.infrastructure.instrument_metadata import (
    InstrumentMetadataRefreshRow,
    InstrumentMetadataRow,
)
from twf.instrument_metadata.contracts import ImportResult

APP_TIMEZONE = ZoneInfo("Asia/Kolkata")
SUPPORTED_SCHEMA_VERSION = "1"
MARKET_CAP_CATEGORIES = {"LARGE", "MID", "SMALL"}
TWF_CAP_TIERS = {"LARGE", "MID", "SMALL", "MICRO"}
RESOLUTION_STATUSES = {"RESOLVED", "RESOLVED_INHERITED", "UNRESOLVED"}
INSTRUMENT_KINDS = {"EQUITY", "RIGHTS_ENTITLEMENT"}

SNAPSHOT_FIELDS = (
    "exchange",
    "symbol",
    "series",
    "isin",
    "company_name",
    "listing_date",
    "metadata_schema_version",
    "dataset_run_id",
    "dataset_generated_at",
    "instrument_kind",
    "underlying_symbol",
    "underlying_resolution_method",
    "macro_sector_code",
    "macro_sector",
    "sector_code",
    "basic_industry_code",
    "basic_industry",
    "nse_classification_source",
    "nse_classification_as_of",
    "sector",
    "sector_source",
    "sector_as_of",
    "industry_code",
    "industry",
    "industry_source",
    "industry_as_of",
    "market_cap",
    "market_cap_currency",
    "market_cap_source",
    "market_cap_as_of",
    "market_cap_rank",
    "market_cap_category",
    "market_cap_category_method",
    "twf_cap_tier",
    "twf_cap_tier_method",
    "context_benchmark",
    "context_benchmark_symbol",
    "benchmark_mapping_source",
    "benchmark_mapping_basis",
    "resolution_status",
    "classification_completeness",
    "confidence",
    "retrieved_at",
    "notes",
)
DATE_FIELDS = {
    "listing_date",
    "nse_classification_as_of",
    "sector_as_of",
    "industry_as_of",
    "market_cap_as_of",
}
OPTIONAL_TEXT_FIELDS = set(SNAPSHOT_FIELDS) - {
    "exchange",
    "symbol",
    "series",
    "isin",
    "company_name",
    "metadata_schema_version",
    "dataset_run_id",
    "dataset_generated_at",
    "instrument_kind",
    "resolution_status",
    "classification_completeness",
    "confidence",
    "retrieved_at",
    "listing_date",
    "nse_classification_as_of",
    "sector_as_of",
    "industry_as_of",
    "market_cap_as_of",
    "market_cap",
    "market_cap_rank",
}
RUN_FIELDS = {
    "metadata_schema_version",
    "dataset_run_id",
    "dataset_generated_at",
    "retrieved_at",
}
CONTENT_FIELDS = tuple(field for field in SNAPSHOT_FIELDS if field not in RUN_FIELDS)


class SnapshotValidationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ImportFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ValidatedSnapshot:
    rows: tuple[dict[str, Any], ...]
    metadata_schema_version: str
    dataset_run_id: str
    dataset_generated_at: datetime
    unresolved_rows: int
    sector_coverage: Decimal
    industry_coverage: Decimal
    market_cap_coverage: Decimal


def now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def aware(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=APP_TIMEZONE)
        if value.tzinfo is None
        else value.astimezone(APP_TIMEZONE)
    )


def optional(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def required(value: str | None, code: str, maximum: int = 256) -> str:
    cleaned = (value or "").strip()
    if not cleaned or len(cleaned) > maximum:
        raise SnapshotValidationError(code)
    return cleaned


def parse_date(value: str | None, code: str, *, listing: bool = False) -> date | None:
    cleaned = optional(value)
    if cleaned is None:
        return None
    try:
        return (
            datetime.strptime(cleaned, "%d-%b-%Y").date()
            if listing
            else date.fromisoformat(cleaned)
        )
    except ValueError:
        raise SnapshotValidationError(code) from None


def parse_timestamp(value: str | None, code: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(required(value, code, 64))
    except ValueError:
        raise SnapshotValidationError(code) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SnapshotValidationError(code)
    return parsed


def parse_positive_int(value: str | None, code: str) -> int | None:
    cleaned = optional(value)
    if cleaned is None:
        return None
    try:
        parsed = int(cleaned)
    except ValueError:
        raise SnapshotValidationError(code) from None
    if parsed <= 0:
        raise SnapshotValidationError(code)
    return parsed


def parse_confidence(value: str | None) -> Decimal:
    try:
        parsed = Decimal(required(value, "INVALID_CONFIDENCE", 32))
    except InvalidOperation:
        raise SnapshotValidationError("INVALID_CONFIDENCE") from None
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        raise SnapshotValidationError("INVALID_CONFIDENCE")
    return parsed


def expected_cap_category(rank: int) -> str:
    return "LARGE" if rank <= 100 else "MID" if rank <= 250 else "SMALL"


def expected_twf_tier(rank: int) -> str:
    if rank <= 100:
        return "LARGE"
    if rank <= 250:
        return "MID"
    return "SMALL" if rank <= 1000 else "MICRO"


def parse_row(raw: dict[str, str | None]) -> dict[str, Any]:
    values: dict[str, Any] = {field: optional(raw.get(field)) for field in OPTIONAL_TEXT_FIELDS}
    values.update(
        {
            "exchange": required(raw.get("exchange"), "INVALID_EXCHANGE", 16).upper(),
            "symbol": required(raw.get("symbol"), "INVALID_SYMBOL", 128).upper(),
            "series": required(raw.get("series"), "INVALID_SERIES", 32).upper(),
            "isin": required(raw.get("isin"), "INVALID_ISIN", 32).upper(),
            "company_name": required(raw.get("company_name"), "INVALID_COMPANY_NAME"),
            "metadata_schema_version": required(
                raw.get("metadata_schema_version"), "MISSING_SCHEMA_VERSION", 16
            ),
            "dataset_run_id": required(raw.get("dataset_run_id"), "MISSING_DATASET_RUN_ID", 64),
            "dataset_generated_at": parse_timestamp(
                raw.get("dataset_generated_at"), "INVALID_DATASET_GENERATED_AT"
            ),
            "instrument_kind": required(raw.get("instrument_kind"), "INVALID_INSTRUMENT_KIND", 32),
            "resolution_status": required(
                raw.get("resolution_status"), "INVALID_RESOLUTION_STATUS", 32
            ),
            "classification_completeness": required(
                raw.get("classification_completeness"), "INVALID_CLASSIFICATION_COMPLETENESS", 32
            ),
            "confidence": parse_confidence(raw.get("confidence")),
            "retrieved_at": parse_timestamp(raw.get("retrieved_at"), "INVALID_RETRIEVED_AT"),
            "listing_date": parse_date(
                raw.get("listing_date"), "INVALID_LISTING_DATE", listing=True
            ),
            "market_cap": parse_positive_int(raw.get("market_cap"), "INVALID_MARKET_CAP"),
            "market_cap_rank": parse_positive_int(
                raw.get("market_cap_rank"), "INVALID_MARKET_CAP_RANK"
            ),
        }
    )
    for field in DATE_FIELDS - {"listing_date"}:
        values[field] = parse_date(raw.get(field), f"INVALID_{field.upper()}")

    schema = cast(str, values["metadata_schema_version"])
    if schema != SUPPORTED_SCHEMA_VERSION:
        raise SnapshotValidationError("UNSUPPORTED_SCHEMA_VERSION")
    if values["instrument_kind"] not in INSTRUMENT_KINDS:
        raise SnapshotValidationError("INVALID_INSTRUMENT_KIND")
    if values["resolution_status"] not in RESOLUTION_STATUSES:
        raise SnapshotValidationError("INVALID_RESOLUTION_STATUS")

    category = values.get("market_cap_category")
    tier = values.get("twf_cap_tier")
    if category is not None and category not in MARKET_CAP_CATEGORIES:
        raise SnapshotValidationError("INVALID_MARKET_CAP_CATEGORY")
    if tier is not None and tier not in TWF_CAP_TIERS:
        raise SnapshotValidationError("INVALID_TWF_CAP_TIER")
    rank = cast(int | None, values["market_cap_rank"])
    if rank is None and (category is not None or tier is not None):
        raise SnapshotValidationError("CAP_CLASSIFICATION_WITHOUT_RANK")
    if rank is not None:
        if values["market_cap"] is None:
            raise SnapshotValidationError("RANK_WITHOUT_MARKET_CAP")
        if category != expected_cap_category(rank):
            raise SnapshotValidationError("MARKET_CAP_CATEGORY_MISMATCH")
        if tier != expected_twf_tier(rank):
            raise SnapshotValidationError("TWF_CAP_TIER_MISMATCH")
    return values


def percentage(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.00")
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(Decimal("0.01"))


def validate_summary(path: Path, snapshot: ValidatedSnapshot) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SnapshotValidationError("INVALID_SUMMARY_JSON") from None
    if not isinstance(payload, dict):
        raise SnapshotValidationError("INVALID_SUMMARY_JSON")
    validation = payload.get("validation")
    if not isinstance(validation, dict) or validation.get("status") != "PASS":
        raise SnapshotValidationError("SUMMARY_VALIDATION_NOT_PASS")
    expected = (
        str(payload.get("metadata_schema_version", "")),
        str(payload.get("dataset_run_id", "")),
        str(payload.get("dataset_generated_at", "")),
        payload.get("total_rows"),
    )
    actual = (
        snapshot.metadata_schema_version,
        snapshot.dataset_run_id,
        snapshot.dataset_generated_at.isoformat(),
        len(snapshot.rows),
    )
    if expected != actual:
        raise SnapshotValidationError("SUMMARY_SNAPSHOT_MISMATCH")
    unresolved_output_rows = payload.get("unresolved_output_rows")
    if not isinstance(unresolved_output_rows, (str, int)):
        raise SnapshotValidationError("INVALID_SUMMARY_METRICS")
    try:
        summary_metrics = (
            Decimal(str(payload.get("sector_coverage_percent"))),
            Decimal(str(payload.get("industry_coverage_percent"))),
            Decimal(str(payload.get("market_cap_coverage_percent"))),
            int(unresolved_output_rows),
        )
    except (InvalidOperation, TypeError, ValueError):
        raise SnapshotValidationError("INVALID_SUMMARY_METRICS") from None
    snapshot_metrics = (
        snapshot.sector_coverage,
        snapshot.industry_coverage,
        snapshot.market_cap_coverage,
        snapshot.unresolved_rows,
    )
    if summary_metrics != snapshot_metrics:
        raise SnapshotValidationError("SUMMARY_COVERAGE_MISMATCH")


def load_snapshot(path: Path, summary_path: Path | None, minimum_rows: int) -> ValidatedSnapshot:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            if headers is None:
                raise SnapshotValidationError("MISSING_HEADER")
            if len(headers) != len(set(headers)):
                raise SnapshotValidationError("DUPLICATE_HEADER")
            if missing := set(SNAPSHOT_FIELDS) - set(headers):
                del missing
                raise SnapshotValidationError("MISSING_REQUIRED_COLUMNS")
            rows = tuple(parse_row(raw) for raw in reader)
    except OSError:
        raise SnapshotValidationError("SNAPSHOT_NOT_READABLE") from None
    if len(rows) < minimum_rows:
        raise SnapshotValidationError("SNAPSHOT_ROW_COUNT_BELOW_MINIMUM")

    keys = [(cast(str, row["exchange"]), cast(str, row["symbol"])) for row in rows]
    if len(keys) != len(set(keys)):
        raise SnapshotValidationError("DUPLICATE_EXCHANGE_SYMBOL")
    isins = [cast(str, row["isin"]) for row in rows]
    if len(isins) != len(set(isins)):
        raise SnapshotValidationError("DUPLICATE_ISIN")
    schemas = {cast(str, row["metadata_schema_version"]) for row in rows}
    run_ids = {cast(str, row["dataset_run_id"]) for row in rows}
    generated = {cast(datetime, row["dataset_generated_at"]) for row in rows}
    if len(schemas) != 1 or len(run_ids) != 1 or len(generated) != 1:
        raise SnapshotValidationError("INCONSISTENT_DATASET_IDENTITY")

    total = len(rows)
    snapshot = ValidatedSnapshot(
        rows=rows,
        metadata_schema_version=schemas.pop(),
        dataset_run_id=run_ids.pop(),
        dataset_generated_at=generated.pop(),
        unresolved_rows=sum(row["resolution_status"] == "UNRESOLVED" for row in rows),
        sector_coverage=percentage(sum(row.get("sector") is not None for row in rows), total),
        industry_coverage=percentage(sum(row.get("industry") is not None for row in rows), total),
        market_cap_coverage=percentage(
            sum(row.get("market_cap") is not None for row in rows), total
        ),
    )
    if summary_path is not None:
        validate_summary(summary_path, snapshot)
    return snapshot


def refresh_result(
    row: InstrumentMetadataRefreshRow, status: Literal["SUCCESS", "ALREADY_IMPORTED"]
) -> ImportResult:
    return ImportResult(
        refresh_id=row.id,
        dataset_run_id=row.dataset_run_id or "",
        status=status,
        total_rows=row.total_rows,
        inserted_rows=row.inserted_rows,
        updated_rows=row.updated_rows,
        unchanged_rows=row.unchanged_rows,
        missing_rows=row.removed_or_missing_rows,
        unresolved_rows=row.unresolved_rows,
        imported_at=aware(row.import_completed_at),
    )


class SnapshotImporter:
    def __init__(self, factory: sessionmaker[Session], minimum_rows: int = 2001) -> None:
        if minimum_rows < 1:
            raise ValueError("minimum_rows must be positive")
        self.factory = factory
        self.minimum_rows = minimum_rows

    def record_failure(self, source: Path, summary: Path | None, code: str) -> None:
        timestamp = now()
        try:
            with self.factory() as db:
                db.add(
                    InstrumentMetadataRefreshRow(
                        id=uuid4(),
                        metadata_schema_version=None,
                        dataset_run_id=None,
                        dataset_generated_at=None,
                        import_started_at=timestamp,
                        import_completed_at=timestamp,
                        source_file=str(source.resolve()),
                        source_summary_file=str(summary.resolve()) if summary else None,
                        total_rows=0,
                        imported_rows=0,
                        inserted_rows=0,
                        updated_rows=0,
                        unchanged_rows=0,
                        removed_or_missing_rows=0,
                        unresolved_rows=0,
                        sector_coverage=Decimal("0"),
                        industry_coverage=Decimal("0"),
                        market_cap_coverage=Decimal("0"),
                        validation_status="FAIL",
                        status="FAILED",
                        error_summary=code,
                    )
                )
                db.commit()
        except SQLAlchemyError:
            return

    def import_snapshot(self, source: Path, summary: Path | None = None) -> ImportResult:
        try:
            snapshot = load_snapshot(source, summary, self.minimum_rows)
        except SnapshotValidationError as exc:
            self.record_failure(source, summary, exc.code)
            raise

        started = now()
        try:
            with self.factory() as db:
                previous = db.scalar(
                    select(InstrumentMetadataRefreshRow).where(
                        InstrumentMetadataRefreshRow.dataset_run_id == snapshot.dataset_run_id,
                        InstrumentMetadataRefreshRow.status == "SUCCESS",
                    )
                )
                if previous is not None:
                    return refresh_result(previous, "ALREADY_IMPORTED")

                existing = {
                    (row.exchange, row.symbol): row
                    for row in db.scalars(select(InstrumentMetadataRow))
                }
                incoming_keys: set[tuple[str, str]] = set()
                inserted = updated = unchanged = 0
                timestamp = now()
                for parsed in snapshot.rows:
                    key = (cast(str, parsed["exchange"]), cast(str, parsed["symbol"]))
                    incoming_keys.add(key)
                    current = existing.get(key)
                    if current is None:
                        db.add(
                            InstrumentMetadataRow(
                                id=uuid4(),
                                **parsed,
                                present_in_latest_snapshot=True,
                                created_at=timestamp,
                                updated_at=timestamp,
                            )
                        )
                        inserted += 1
                        continue

                    changed = not current.present_in_latest_snapshot or any(
                        getattr(current, field) != parsed[field] for field in CONTENT_FIELDS
                    )
                    for field in SNAPSHOT_FIELDS:
                        setattr(current, field, parsed[field])
                    current.present_in_latest_snapshot = True
                    if changed:
                        current.updated_at = timestamp
                        updated += 1
                    else:
                        unchanged += 1

                missing = 0
                for key, current in existing.items():
                    if key not in incoming_keys:
                        missing += 1
                        if current.present_in_latest_snapshot:
                            current.present_in_latest_snapshot = False
                            current.updated_at = timestamp

                completed = now()
                refresh = InstrumentMetadataRefreshRow(
                    id=uuid4(),
                    metadata_schema_version=snapshot.metadata_schema_version,
                    dataset_run_id=snapshot.dataset_run_id,
                    dataset_generated_at=snapshot.dataset_generated_at,
                    import_started_at=started,
                    import_completed_at=completed,
                    source_file=str(source.resolve()),
                    source_summary_file=str(summary.resolve()) if summary else None,
                    total_rows=len(snapshot.rows),
                    imported_rows=len(snapshot.rows),
                    inserted_rows=inserted,
                    updated_rows=updated,
                    unchanged_rows=unchanged,
                    removed_or_missing_rows=missing,
                    unresolved_rows=snapshot.unresolved_rows,
                    sector_coverage=snapshot.sector_coverage,
                    industry_coverage=snapshot.industry_coverage,
                    market_cap_coverage=snapshot.market_cap_coverage,
                    validation_status="PASS",
                    status="SUCCESS",
                    error_summary=None,
                )
                db.add(refresh)
                db.commit()
                return refresh_result(refresh, "SUCCESS")
        except SQLAlchemyError as exc:
            self.record_failure(source, summary, "DATABASE_IMPORT_FAILED")
            raise ImportFailure("DATABASE_IMPORT_FAILED") from exc
