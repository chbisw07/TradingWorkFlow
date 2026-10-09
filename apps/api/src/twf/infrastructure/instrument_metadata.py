"""System-global instrument metadata and immutable refresh audit records."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class InstrumentMetadataRow(Base):
    __tablename__ = "instrument_metadata"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol"),
        UniqueConstraint("isin"),
        Index("ix_instrument_metadata_sector", "sector"),
        Index("ix_instrument_metadata_industry", "industry"),
        Index("ix_instrument_metadata_market_cap_category", "market_cap_category"),
        Index("ix_instrument_metadata_twf_cap_tier", "twf_cap_tier"),
        Index("ix_instrument_metadata_context_benchmark", "context_benchmark_symbol"),
        Index("ix_instrument_metadata_present", "present_in_latest_snapshot"),
        CheckConstraint("market_cap IS NULL OR market_cap > 0", name="market_cap_positive"),
        CheckConstraint("market_cap_rank IS NULL OR market_cap_rank > 0", name="rank_positive"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16))
    symbol: Mapped[str] = mapped_column(String(128))
    series: Mapped[str] = mapped_column(String(32))
    isin: Mapped[str] = mapped_column(String(32))
    company_name: Mapped[str] = mapped_column(String(256))
    listing_date: Mapped[date | None] = mapped_column(Date)

    metadata_schema_version: Mapped[str] = mapped_column(String(16))
    dataset_run_id: Mapped[str] = mapped_column(String(64), index=True)
    dataset_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    instrument_kind: Mapped[str] = mapped_column(String(32))
    underlying_symbol: Mapped[str | None] = mapped_column(String(128))
    underlying_resolution_method: Mapped[str | None] = mapped_column(String(64))

    macro_sector_code: Mapped[str | None] = mapped_column(String(32))
    macro_sector: Mapped[str | None] = mapped_column(String(128))
    sector_code: Mapped[str | None] = mapped_column(String(32))
    basic_industry_code: Mapped[str | None] = mapped_column(String(32))
    basic_industry: Mapped[str | None] = mapped_column(String(128))
    nse_classification_source: Mapped[str | None] = mapped_column(String(64))
    nse_classification_as_of: Mapped[date | None] = mapped_column(Date)

    sector: Mapped[str | None] = mapped_column(String(128))
    sector_source: Mapped[str | None] = mapped_column(String(64))
    sector_as_of: Mapped[date | None] = mapped_column(Date)
    industry_code: Mapped[str | None] = mapped_column(String(32))
    industry: Mapped[str | None] = mapped_column(String(160))
    industry_source: Mapped[str | None] = mapped_column(String(64))
    industry_as_of: Mapped[date | None] = mapped_column(Date)

    market_cap: Mapped[int | None] = mapped_column(BigInteger)
    market_cap_currency: Mapped[str | None] = mapped_column(String(8))
    market_cap_source: Mapped[str | None] = mapped_column(String(64))
    market_cap_as_of: Mapped[date | None] = mapped_column(Date)
    market_cap_rank: Mapped[int | None] = mapped_column(Integer)
    market_cap_category: Mapped[str | None] = mapped_column(String(16))
    market_cap_category_method: Mapped[str | None] = mapped_column(String(96))
    twf_cap_tier: Mapped[str | None] = mapped_column(String(16))
    twf_cap_tier_method: Mapped[str | None] = mapped_column(String(96))

    context_benchmark: Mapped[str | None] = mapped_column(String(128))
    context_benchmark_symbol: Mapped[str | None] = mapped_column(String(64))
    benchmark_mapping_source: Mapped[str | None] = mapped_column(String(64))
    benchmark_mapping_basis: Mapped[str | None] = mapped_column(String(192))

    resolution_status: Mapped[str] = mapped_column(String(32))
    classification_completeness: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 5))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    present_in_latest_snapshot: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InstrumentMetadataRefreshRow(Base):
    __tablename__ = "instrument_metadata_refreshes"
    __table_args__ = (
        Index("ix_instrument_metadata_refresh_dataset_status", "dataset_run_id", "status"),
        Index("ix_instrument_metadata_refresh_completed", "import_completed_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    metadata_schema_version: Mapped[str | None] = mapped_column(String(16))
    dataset_run_id: Mapped[str | None] = mapped_column(String(64))
    dataset_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    import_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    import_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_file: Mapped[str] = mapped_column(String(512))
    source_summary_file: Mapped[str | None] = mapped_column(String(512))
    total_rows: Mapped[int] = mapped_column(Integer)
    imported_rows: Mapped[int] = mapped_column(Integer)
    inserted_rows: Mapped[int] = mapped_column(Integer)
    updated_rows: Mapped[int] = mapped_column(Integer)
    unchanged_rows: Mapped[int] = mapped_column(Integer)
    removed_or_missing_rows: Mapped[int] = mapped_column(Integer)
    unresolved_rows: Mapped[int] = mapped_column(Integer)
    sector_coverage: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    industry_coverage: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    market_cap_coverage: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    validation_status: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_summary: Mapped[str | None] = mapped_column(String(512))
