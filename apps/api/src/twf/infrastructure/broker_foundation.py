"""Durable personal broker-account foundation; no provider transport or raw secrets."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class BrokerProviderConfiguration(Base):
    __tablename__ = "broker_provider_configurations"
    __table_args__ = (
        CheckConstraint(
            "configuration_revision >= 1", name="provider_configuration_revision_positive"
        ),
    )

    provider_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    configuration_revision: Mapped[int] = mapped_column(Integer, default=1)
    secret_reference: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BrokerAccountRecord(Base):
    __tablename__ = "broker_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "environment",
            "provider_account_id",
            name="uq_broker_accounts_provider_environment_external",
        ),
        UniqueConstraint(
            "owner_user_id", "provider_id", "label", name="uq_broker_accounts_owner_provider_label"
        ),
        CheckConstraint("configuration_revision >= 1", name="configuration_revision_positive"),
        CheckConstraint("connection_generation >= 0", name="connection_generation_nonnegative"),
        CheckConstraint("mode = 'LIVE'", name="mode_live"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("broker_provider_configurations.provider_id"), index=True
    )
    environment: Mapped[str] = mapped_column(String(16))
    provider_account_id: Mapped[str | None] = mapped_column(String(128))
    mode: Mapped[str] = mapped_column(String(16), default="LIVE")
    label: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    configuration_revision: Mapped[int] = mapped_column(Integer, default=1)
    connection_generation: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BrokerConnectionRecord(Base):
    __tablename__ = "broker_connections"
    __table_args__ = (
        CheckConstraint("applied_configuration_revision >= 0", name="applied_revision_nonnegative"),
    )

    broker_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("broker_accounts.id"), primary_key=True
    )
    authentication_state: Mapped[str] = mapped_column(String(24), default="NOT_CONFIGURED")
    read_health: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    applied_configuration_revision: Mapped[int] = mapped_column(Integer, default=0)
    secret_reference: Mapped[str | None] = mapped_column(String(128))
    secret_version: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BrokerAuditEvent(Base):
    __tablename__ = "broker_audit_events"
    __table_args__ = (
        CheckConstraint("configuration_revision >= 0", name="configuration_revision_nonnegative"),
        CheckConstraint("connection_generation >= 0", name="connection_generation_nonnegative"),
        Index("ix_broker_audit_events_account_created", "broker_account_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    broker_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("broker_accounts.id"))
    provider_id: Mapped[str] = mapped_column(String(48))
    event_type: Mapped[str] = mapped_column(String(48))
    configuration_revision: Mapped[int] = mapped_column(Integer)
    connection_generation: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(24), default="SUCCEEDED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
