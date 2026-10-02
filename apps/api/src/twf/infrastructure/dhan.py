"""Owner-scoped Dhan market-data authority and encrypted material."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class DhanMarketDataSecret(Base):
    __tablename__ = "dhan_market_data_secrets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    ciphertext: Mapped[str] = mapped_column(Text)
    algorithm: Mapped[str] = mapped_column(String(32), default="fernet-v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class DhanMarketDataConnection(Base):
    __tablename__ = "dhan_market_data_connections"

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    secret_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dhan_market_data_secrets.id"), nullable=True
    )
    generation: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(24))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str | None] = mapped_column(String(40))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
