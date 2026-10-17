"""OE-3 Queue admission and append-only operational history.

The Queue references an Order; it never copies the authoritative trade request.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class TWFQueueEntryRecord(Base):
    __tablename__ = "twf_queue_entries"
    __table_args__ = (
        UniqueConstraint("public_queue_id", name="uq_twf_queue_public_id"),
        ForeignKeyConstraint(
            ["twf_order_id", "owner_id"],
            ["twf_orders.twf_order_id", "twf_orders.owner_id"],
            ondelete="RESTRICT",
            name="fk_twf_queue_entries_order_owner",
        ),
        ForeignKeyConstraint(
            ["twf_order_id", "owner_id", "queue_entry_id"],
            ["twf_orders.twf_order_id", "twf_orders.owner_id", "twf_orders.queue_entry_id"],
            ondelete="RESTRICT",
            name="fk_twf_queue_entries_order_binding",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("twf_order_id", name="uq_twf_queue_entries_order"),
        UniqueConstraint(
            "queue_entry_id", "twf_order_id", "owner_id", name="uq_twf_queue_entries_identity"
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "queue_state IN ('READY', 'HELD', 'DISPATCHING', 'DISPATCHED', 'FAILED', "
            "'RECONCILIATION_REQUIRED', 'CANCELLED')",
            name="active_state",
        ),
        CheckConstraint("effective_dispatch_mode IN ('MANUAL', 'AUTO')", name="dispatch_mode"),
        Index("ix_twf_queue_entries_owner_fifo", "owner_id", "admitted_at", "queue_entry_id"),
    )

    queue_entry_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    twf_order_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    effective_dispatch_mode: Mapped[str] = mapped_column(
        String(8), nullable=False, default="MANUAL", server_default="MANUAL"
    )
    broker_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("broker_accounts.id"))
    policy_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    source_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="MANUAL", server_default="MANUAL"
    )
    source_reference: Mapped[str | None] = mapped_column(String(256))
    public_queue_id: Mapped[str | None] = mapped_column(String(64))
    queue_state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    reason_message: Mapped[str | None] = mapped_column(String(512))


class TWFQueueEventRecord(Base):
    __tablename__ = "twf_queue_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["queue_entry_id", "twf_order_id", "owner_id"],
            [
                "twf_queue_entries.queue_entry_id",
                "twf_queue_entries.twf_order_id",
                "twf_queue_entries.owner_id",
            ],
            ondelete="RESTRICT",
            name="fk_twf_queue_events_entry_order_owner",
        ),
        Index(
            "ix_twf_queue_events_owner_entry_seq",
            "owner_id",
            "queue_entry_id",
            "sequence",
            unique=True,
        ),
    )

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    queue_entry_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    twf_order_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    queue_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    reason_message: Mapped[str | None] = mapped_column(String(512))
    details: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
