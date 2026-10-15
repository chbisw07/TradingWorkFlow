"""OE-3 Queue admission and append-only operational history.

The Queue references an Order; it never copies the authoritative trade request.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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
        ForeignKeyConstraint(
            ["twf_order_id", "owner_id"],
            ["twf_orders.twf_order_id", "twf_orders.owner_id"],
            ondelete="RESTRICT",
            name="fk_twf_queue_entries_order_owner",
        ),
        UniqueConstraint("twf_order_id", name="uq_twf_queue_entries_order"),
        UniqueConstraint(
            "queue_entry_id", "twf_order_id", "owner_id", name="uq_twf_queue_entries_identity"
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("queue_state IN ('READY', 'HELD')", name="active_state"),
        Index("ix_twf_queue_entries_owner_fifo", "owner_id", "admitted_at", "queue_entry_id"),
    )

    queue_entry_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    twf_order_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
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
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
