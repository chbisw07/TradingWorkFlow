"""MCP connection metadata, encrypted generation-bound material and OAuth attempts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class MCPConnection(Base):
    __tablename__ = "mcp_connections"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String(64))
    config_fingerprint: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean)
    auth_invalidation_pending: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    generation: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32))
    health: Mapped[str] = mapped_column(String(16))
    health_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_kind: Mapped[str | None] = mapped_column(String(40))
    consecutive_failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cleanup_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    secret_id: Mapped[UUID | None] = mapped_column(Uuid)
    tools_json: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MCPSecret(Base):
    __tablename__ = "mcp_secrets"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("mcp_connections.id"), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    ciphertext: Mapped[str] = mapped_column(Text)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Retain encrypted material until remote revocation and physical cleanup succeed.
    revoke_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MCPOAuthAttempt(Base):
    __tablename__ = "mcp_oauth_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("mcp_connections.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    generation: Mapped[int] = mapped_column(Integer)
    verifier_ciphertext: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class MCPOperation(Base):
    """Durable admission; expiry is NOT evidence that its worker stopped sending."""

    __tablename__ = "mcp_operations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("mcp_connections.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    generation: Mapped[int] = mapped_column(Integer)
    session_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), default="AUTHENTICATED")
    tool_name: Mapped[str | None] = mapped_column(String(128))
    health_outcome: Mapped[str | None] = mapped_column(String(40))
    worker_id: Mapped[UUID] = mapped_column(Uuid)
    state: Mapped[str] = mapped_column(String(24))
    cleanup_state: Mapped[str] = mapped_column(String(24))
    outcome: Mapped[str | None] = mapped_column(String(40))
    provider_outcome: Mapped[str | None] = mapped_column(String(40))
    reconciliation_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
