"""Immutable native catalog versions and account-scoped publication pointer."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class CatalogSnapshot(Base):
    __tablename__ = "catalog_snapshots"
    __table_args__ = (UniqueConstraint("broker_account_id", "fingerprint"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    broker_account_id: Mapped[UUID] = mapped_column(ForeignKey("broker_accounts.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(48))
    fingerprint: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(Integer)


class CatalogPointer(Base):
    __tablename__ = "catalog_pointers"
    broker_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("broker_accounts.id"), primary_key=True
    )
    snapshot_id: Mapped[UUID | None] = mapped_column(ForeignKey("catalog_snapshots.id"))
    refresh_id: Mapped[UUID | None]
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(32))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)


class CatalogInstrument(Base):
    __tablename__ = "catalog_instruments"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "native_id", name="uq_catalog_native_id"),
        UniqueConstraint("snapshot_id", "exchange", "symbol", name="uq_catalog_exchange_symbol"),
        Index("ix_catalog_search", "snapshot_id", "exchange", "segment", "symbol"),
        Index(
            "ix_catalog_derivative", "snapshot_id", "segment", "expiry", "strike", "derivative_kind"
        ),
        Index("ix_catalog_name", "snapshot_id", "name"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("catalog_snapshots.id"))
    native_id: Mapped[str] = mapped_column(String(64))
    exchange_id: Mapped[str | None] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(128))
    name: Mapped[str | None] = mapped_column(String(256))
    exchange: Mapped[str] = mapped_column(String(32))
    segment: Mapped[str] = mapped_column(String(32))
    instrument_type: Mapped[str] = mapped_column(String(32))
    expiry: Mapped[date | None] = mapped_column(Date)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    derivative_kind: Mapped[str | None] = mapped_column(String(3))
    lot_size: Mapped[int] = mapped_column(Integer)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    canonical_id: Mapped[UUID | None]
    fingerprint: Mapped[str] = mapped_column(String(64))
