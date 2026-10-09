"""Read-only access to system-global instrument metadata."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from twf.infrastructure.instrument_metadata import (
    InstrumentMetadataRefreshRow,
    InstrumentMetadataRow,
)
from twf.instrument_metadata.contracts import (
    BulkLookupResult,
    InstrumentMetadata,
    MetadataStatus,
)

APP_TIMEZONE = ZoneInfo("Asia/Kolkata")


def aware(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=APP_TIMEZONE)
        if value.tzinfo is None
        else value.astimezone(APP_TIMEZONE)
    )


def public(row: InstrumentMetadataRow) -> InstrumentMetadata:
    return InstrumentMetadata(
        id=row.id,
        exchange=row.exchange,
        symbol=row.symbol,
        series=row.series,
        isin=row.isin,
        company_name=row.company_name,
        listing_date=row.listing_date,
        metadata_schema_version=row.metadata_schema_version,
        dataset_run_id=row.dataset_run_id,
        dataset_generated_at=aware(row.dataset_generated_at),
        instrument_kind=row.instrument_kind,
        underlying_symbol=row.underlying_symbol,
        underlying_resolution_method=row.underlying_resolution_method,
        macro_sector_code=row.macro_sector_code,
        macro_sector=row.macro_sector,
        sector_code=row.sector_code,
        basic_industry_code=row.basic_industry_code,
        basic_industry=row.basic_industry,
        nse_classification_source=row.nse_classification_source,
        nse_classification_as_of=row.nse_classification_as_of,
        sector=row.sector,
        sector_source=row.sector_source,
        sector_as_of=row.sector_as_of,
        industry_code=row.industry_code,
        industry=row.industry,
        industry_source=row.industry_source,
        industry_as_of=row.industry_as_of,
        market_cap=row.market_cap,
        market_cap_currency=row.market_cap_currency,
        market_cap_source=row.market_cap_source,
        market_cap_as_of=row.market_cap_as_of,
        market_cap_rank=row.market_cap_rank,
        market_cap_category=cast(Literal["LARGE", "MID", "SMALL"] | None, row.market_cap_category),
        market_cap_category_method=row.market_cap_category_method,
        twf_cap_tier=cast(Literal["LARGE", "MID", "SMALL", "MICRO"] | None, row.twf_cap_tier),
        twf_cap_tier_method=row.twf_cap_tier_method,
        context_benchmark=row.context_benchmark,
        context_benchmark_symbol=row.context_benchmark_symbol,
        benchmark_mapping_source=row.benchmark_mapping_source,
        benchmark_mapping_basis=row.benchmark_mapping_basis,
        resolution_status=row.resolution_status,
        classification_completeness=row.classification_completeness,
        confidence=row.confidence,
        retrieved_at=aware(row.retrieved_at),
        notes=row.notes,
        present_in_latest_snapshot=row.present_in_latest_snapshot,
        created_at=aware(row.created_at),
        updated_at=aware(row.updated_at),
    )


class InstrumentMetadataService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_symbol(self, exchange: str, symbol: str) -> InstrumentMetadata | None:
        row = self.session.scalar(
            select(InstrumentMetadataRow).where(
                InstrumentMetadataRow.exchange == exchange.strip().upper(),
                InstrumentMetadataRow.symbol == symbol.strip().upper(),
            )
        )
        return public(row) if row else None

    def get_by_isin(self, isin: str) -> InstrumentMetadata | None:
        row = self.session.scalar(
            select(InstrumentMetadataRow).where(InstrumentMetadataRow.isin == isin.strip().upper())
        )
        return public(row) if row else None

    def get_many_by_symbols(self, exchange: str, symbols: tuple[str, ...]) -> BulkLookupResult:
        normalized_exchange = exchange.strip().upper()
        normalized = tuple(symbol.strip().upper() for symbol in symbols)
        rows = {
            row.symbol: public(row)
            for row in self.session.scalars(
                select(InstrumentMetadataRow).where(
                    InstrumentMetadataRow.exchange == normalized_exchange,
                    InstrumentMetadataRow.symbol.in_(normalized),
                )
            )
        }
        return BulkLookupResult(
            items=tuple(rows[symbol] for symbol in normalized if symbol in rows),
            missing_symbols=tuple(symbol for symbol in normalized if symbol not in rows),
        )

    def get_sector(self, exchange: str, symbol: str) -> str | None:
        item = self.get_by_symbol(exchange, symbol)
        return item.sector if item else None

    def get_context_benchmark(self, exchange: str, symbol: str) -> str | None:
        item = self.get_by_symbol(exchange, symbol)
        return item.context_benchmark_symbol if item else None

    def get_last_refresh_status(self) -> MetadataStatus:
        latest = self.session.scalar(
            select(InstrumentMetadataRefreshRow)
            .order_by(InstrumentMetadataRefreshRow.import_completed_at.desc())
            .limit(1)
        )
        successful = self.session.scalar(
            select(InstrumentMetadataRefreshRow)
            .where(InstrumentMetadataRefreshRow.status == "SUCCESS")
            .order_by(InstrumentMetadataRefreshRow.import_completed_at.desc())
            .limit(1)
        )
        latest_status = cast(Literal["SUCCESS", "FAILED"] | None, latest.status if latest else None)
        if successful is None:
            return MetadataStatus(
                health="IMPORT_FAILED" if latest else "NOT_IMPORTED",
                latest_attempt_status=latest_status,
            )
        active_count = self.session.scalar(
            select(func.count())
            .select_from(InstrumentMetadataRow)
            .where(InstrumentMetadataRow.present_in_latest_snapshot.is_(True))
        )
        degraded = latest is not None and latest.status == "FAILED"
        return MetadataStatus(
            health="DEGRADED" if degraded else "AVAILABLE",
            latest_attempt_status=latest_status or "SUCCESS",
            last_successful_refresh=aware(successful.import_completed_at),
            dataset_run_id=successful.dataset_run_id,
            dataset_generated_at=(
                aware(successful.dataset_generated_at) if successful.dataset_generated_at else None
            ),
            imported_at=aware(successful.import_completed_at),
            total_instruments=int(active_count or 0),
            sector_coverage=Decimal(successful.sector_coverage),
            industry_coverage=Decimal(successful.industry_coverage),
            market_cap_coverage=Decimal(successful.market_cap_coverage),
            unresolved_count=successful.unresolved_rows,
        )
