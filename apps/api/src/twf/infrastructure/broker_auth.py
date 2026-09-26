"""BW-2.2 correlation and secret lifecycle metadata. No credential values."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class BrokerAuthConfiguration(Base):
    __tablename__ = "broker_auth_configurations"
    broker_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("broker_accounts.id"), primary_key=True
    )
    api_key: Mapped[str] = mapped_column(String(128))
    secret_reference: Mapped[str] = mapped_column(String(128))
    secret_generation: Mapped[int] = mapped_column(Integer)
    credential_revision: Mapped[int] = mapped_column(Integer)
    bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_auth_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BrokerAuthAttempt(Base):
    __tablename__ = "broker_auth_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    broker_account_id: Mapped[UUID] = mapped_column(ForeignKey("broker_accounts.id"), index=True)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(ForeignKey("auth_sessions.token_hash"))
    provider_id: Mapped[str] = mapped_column(String(48))
    environment: Mapped[str] = mapped_column(String(16))
    generation: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finalize_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    pending_reference: Mapped[str | None] = mapped_column(String(128))
    verified_subject: Mapped[str | None] = mapped_column(String(128))


class BrokerSecretLifecycle(Base):
    __tablename__ = "broker_secret_lifecycle"
    reference: Mapped[str] = mapped_column(String(128), primary_key=True)
    broker_account_id: Mapped[UUID] = mapped_column(ForeignKey("broker_accounts.id"), index=True)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    provider_id: Mapped[str] = mapped_column(String(48))
    environment: Mapped[str] = mapped_column(String(16))
    generation: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(24))
    context: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_attempts: Mapped[int] = mapped_column(Integer, default=0)
