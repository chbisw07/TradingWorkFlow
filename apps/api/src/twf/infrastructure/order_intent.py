"""Immutable preview terms and a durable, single-claim manual submission ledger."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class OrderIntent(Base):
    __tablename__ = "broker_order_intents"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("broker_accounts.id"), index=True)
    account_name: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(32))
    session_hash: Mapped[str] = mapped_column(String(64))
    generation: Mapped[int] = mapped_column(Integer)
    broker_identity: Mapped[str] = mapped_column(String(64))
    instrument_json: Mapped[str] = mapped_column(Text)
    order_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    execution_authority: Mapped[str] = mapped_column(String(32))
    tag: Mapped[str] = mapped_column(String(20), unique=True)
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    broker_order_id: Mapped[str | None] = mapped_column(String(160))
    provider_status: Mapped[str | None] = mapped_column(String(160))
    failure: Mapped[str | None] = mapped_column(String(240))
