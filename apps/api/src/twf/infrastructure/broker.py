"""Only configuration, encrypted secrets and single-use login attempts are durable."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class BrokerSecret(Base):
    __tablename__ = "broker_secrets"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Standard Fernet token contains the authenticated version, timestamp and IV.
    ciphertext: Mapped[str] = mapped_column(Text)
    algorithm: Mapped[str] = mapped_column(
        String(32), default="fernet-v1", server_default="fernet-v1"
    )
    # Constant fallback permits additive SQLite migration without rebuilding the
    # referenced table. ORM writes always supply UTC timestamps.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=text("'1970-01-01 00:00:00'"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("'1970-01-01 00:00:00'"),
    )


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider", "identity"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    identity: Mapped[str | None] = mapped_column(String(64))
    secret_id: Mapped[UUID] = mapped_column(ForeignKey("broker_secrets.id"))
    state: Mapped[str] = mapped_column(String(24))
    health: Mapped[str] = mapped_column(String(16), default="unknown")
    generation: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BrokerAttempt(Base):
    __tablename__ = "broker_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("broker_accounts.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    generation: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
