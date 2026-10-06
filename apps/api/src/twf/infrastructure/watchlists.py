"""Watchlist storage. Mutations serialize on the parent row, never over provider I/O."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class WatchlistRow(Base):
    __tablename__ = "watchlists"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240))
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    ordering: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WatchlistItemRow(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "instrument_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    watchlist_id: Mapped[UUID] = mapped_column(ForeignKey("watchlists.id"), index=True)
    instrument_id: Mapped[UUID] = mapped_column(Uuid)
    instrument: Mapped[dict[str, Any]] = mapped_column(JSON)
    source: Mapped[dict[str, Any]] = mapped_column(JSON)
    ordering: Mapped[int] = mapped_column(Integer)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WatchlistNoteRow(Base):
    __tablename__ = "watchlist_notes"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    watchlist_id: Mapped[UUID] = mapped_column(ForeignKey("watchlists.id"), index=True)
    text: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WatchlistActivityRow(Base):
    __tablename__ = "watchlist_activity"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    watchlist_id: Mapped[UUID] = mapped_column(ForeignKey("watchlists.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
