"""OE-2 manual preview envelopes; separate from frozen OE-1 order persistence."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class ManualOrderPreviewRecord(Base):
    __tablename__ = "manual_order_previews"
    __table_args__ = (
        Index("ix_manual_order_previews_owner_expiry", "owner_id", "expires_at"),
        UniqueConstraint("order_id", name="uq_manual_order_previews_order_id"),
        CheckConstraint(
            "(consumed_at IS NULL AND order_id IS NULL AND validation IS NULL) OR "
            "(consumed_at IS NOT NULL AND order_id IS NOT NULL AND validation IS NOT NULL)",
            name="consumed_has_order",
        ),
    )

    preview_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    selection_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    terms: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("twf_orders.twf_order_id"))
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
