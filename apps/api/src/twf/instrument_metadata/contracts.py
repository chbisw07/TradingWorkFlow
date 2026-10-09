"""Typed system-global instrument metadata contracts."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from twf.integrations.contracts import Contract


class InstrumentMetadata(Contract):
    id: UUID
    exchange: str
    symbol: str
    series: str
    isin: str
    company_name: str
    listing_date: date | None
    metadata_schema_version: str
    dataset_run_id: str
    dataset_generated_at: AwareDatetime
    instrument_kind: str
    underlying_symbol: str | None
    underlying_resolution_method: str | None
    macro_sector_code: str | None
    macro_sector: str | None
    sector_code: str | None
    basic_industry_code: str | None
    basic_industry: str | None
    nse_classification_source: str | None
    nse_classification_as_of: date | None
    sector: str | None
    sector_source: str | None
    sector_as_of: date | None
    industry_code: str | None
    industry: str | None
    industry_source: str | None
    industry_as_of: date | None
    market_cap: int | None
    market_cap_currency: str | None
    market_cap_source: str | None
    market_cap_as_of: date | None
    market_cap_rank: int | None
    market_cap_category: Literal["LARGE", "MID", "SMALL"] | None
    market_cap_category_method: str | None
    twf_cap_tier: Literal["LARGE", "MID", "SMALL", "MICRO"] | None
    twf_cap_tier_method: str | None
    context_benchmark: str | None
    context_benchmark_symbol: str | None
    benchmark_mapping_source: str | None
    benchmark_mapping_basis: str | None
    resolution_status: str
    classification_completeness: str
    confidence: Decimal
    retrieved_at: AwareDatetime
    notes: str | None
    present_in_latest_snapshot: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime


class BulkLookup(Contract):
    exchange: str = Field(min_length=1, max_length=16)
    symbols: tuple[str, ...] = Field(min_length=1, max_length=100)

    @field_validator("exchange")
    @classmethod
    def normalize_exchange(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip().upper() for value in values)
        if any(not value or len(value) > 128 for value in normalized):
            raise ValueError("Symbols must be non-empty and at most 128 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Symbols must be unique")
        return normalized


class BulkLookupResult(Contract):
    items: tuple[InstrumentMetadata, ...]
    missing_symbols: tuple[str, ...]


class MetadataStatus(Contract):
    health: Literal["NOT_IMPORTED", "AVAILABLE", "DEGRADED", "IMPORT_FAILED"]
    latest_attempt_status: Literal["SUCCESS", "FAILED"] | None = None
    last_successful_refresh: AwareDatetime | None = None
    dataset_run_id: str | None = None
    dataset_generated_at: AwareDatetime | None = None
    imported_at: AwareDatetime | None = None
    total_instruments: int = 0
    sector_coverage: Decimal = Decimal("0")
    industry_coverage: Decimal = Decimal("0")
    market_cap_coverage: Decimal = Decimal("0")
    unresolved_count: int = 0


class ImportResult(Contract):
    refresh_id: UUID
    dataset_run_id: str
    status: Literal["SUCCESS", "ALREADY_IMPORTED"]
    total_rows: int
    inserted_rows: int
    updated_rows: int
    unchanged_rows: int
    missing_rows: int
    unresolved_rows: int
    imported_at: datetime
