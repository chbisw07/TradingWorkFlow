"""Current TWF Order snapshot and append-only audit rows; unrelated to Broker V2 intents."""

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


class TWFOrderRecord(Base):
    __tablename__ = "twf_orders"
    __table_args__ = (
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "state NOT IN ('DRAFT', 'READY') OR queue_entry_id IS NULL",
            name="pre_queue_unbound",
        ),
        CheckConstraint(
            "state NOT IN ('QUEUED', 'SUBMITTING', 'BROKER_ACCEPTED', "
            "'PARTIALLY_FILLED', 'FILLED') OR queue_entry_id IS NOT NULL",
            name="admitted_state_bound",
        ),
        UniqueConstraint("twf_order_id", "owner_id", name="uq_twf_orders_id_owner"),
        UniqueConstraint(
            "twf_order_id", "owner_id", "queue_entry_id", name="uq_twf_orders_queue_binding"
        ),
        ForeignKeyConstraint(
            ["queue_entry_id", "twf_order_id", "owner_id"],
            [
                "twf_queue_entries.queue_entry_id",
                "twf_queue_entries.twf_order_id",
                "twf_queue_entries.owner_id",
            ],
            name="fk_twf_orders_queue_binding",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_twf_orders_owner_created", "owner_id", "created_at"),
    )

    twf_order_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state_reason_code: Mapped[str | None] = mapped_column(String(64))
    state_reason: Mapped[str | None] = mapped_column(String(512))
    queue_entry_id: Mapped[UUID | None] = mapped_column(Uuid)


class TWFOrderEventRecord(Base):
    __tablename__ = "twf_order_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["twf_order_id", "owner_id"],
            ["twf_orders.twf_order_id", "twf_orders.owner_id"],
            ondelete="RESTRICT",
            name="fk_twf_order_events_order_owner",
        ),
        Index(
            "ix_twf_order_events_owner_order_seq",
            "owner_id",
            "twf_order_id",
            "sequence",
            unique=True,
        ),
    )

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    twf_order_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str | None] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    authority: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(512))
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# Direct metadata.create_all users need the referenced Queue table registered.
import twf.infrastructure.twf_queue  # noqa: E402,F401
import twf.queue.public_ids  # noqa: E402,F401 -- transactional alias, no lifecycle authority
