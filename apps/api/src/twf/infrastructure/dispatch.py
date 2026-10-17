"""OE-4 durable admission policy, dispatch linkage, and operator aliases."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class QueueDispatchPolicy(Base):
    __tablename__ = "twf_queue_dispatch_policies"
    __table_args__ = (CheckConstraint("current_dispatch_mode IN ('MANUAL','AUTO')", name="mode"),)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    broker_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("broker_accounts.id"), primary_key=True
    )
    current_dispatch_mode: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QueuePolicyEvent(Base):
    __tablename__ = "twf_queue_policy_events"
    __table_args__ = (
        UniqueConstraint("owner_id", "broker_account_id", "version", name="uq_twf_policy_version"),
    )
    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    broker_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("broker_accounts.id"), nullable=False
    )
    previous_mode: Mapped[str] = mapped_column(String(8), nullable=False)
    new_mode: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DispatchAttempt(Base):
    __tablename__ = "twf_dispatch_attempts"
    dispatch_attempt_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    queue_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("twf_queue_entries.queue_entry_id"), nullable=False, unique=True
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    broker_intent_id: Mapped[UUID] = mapped_column(
        ForeignKey("broker_order_intents.id"), unique=True, nullable=False
    )
    authority: Mapped[str] = mapped_column(String(8), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(32))


class PublicIDCounter(Base):
    __tablename__ = "twf_public_id_counters"
    bucket: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderPublicID(Base):
    __tablename__ = "twf_order_public_ids"
    twf_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("twf_orders.twf_order_id"), primary_key=True
    )
    public_order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
