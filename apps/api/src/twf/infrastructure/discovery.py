"""Durable owner-scoped Sprint-2 Scan & Discover records."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class DiscoverySettingsRecord(Base):
    __tablename__ = "discovery_settings"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScanRunRecord(Base):
    __tablename__ = "discovery_scan_runs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    match_count: Mapped[int] = mapped_column(Integer)
    candidate_count: Mapped[int] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ScanMatchRecord(Base):
    __tablename__ = "discovery_scan_matches"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_scan_runs.id", ondelete="CASCADE"), index=True
    )
    instrument_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class MarketContextRecord(Base):
    __tablename__ = "discovery_market_context"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_scan_runs.id", ondelete="CASCADE"), index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DiscoveryEpisodeRecord(Base):
    __tablename__ = "discovery_episodes"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_discovery_episodes_candidate_identity"),
        Index(
            "ix_discovery_episode_active_key",
            "user_id",
            "instrument_id",
            "intent_key",
            "horizon_key",
            "state",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    instrument_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    intent_key: Mapped[str] = mapped_column(String(48), index=True)
    horizon_key: Mapped[str] = mapped_column(String(24), index=True)
    state: Mapped[str] = mapped_column(String(24), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    snapshot_count: Mapped[int] = mapped_column(Integer)
    previous_episode_id: Mapped[UUID | None] = mapped_column(Uuid)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DiscoverySnapshotRecord(Base):
    __tablename__ = "discovery_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "episode_id",
            "sequence",
            name="uq_discovery_snapshots_episode_sequence",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    episode_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_episodes.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DiscoveryTransitionRecord(Base):
    __tablename__ = "discovery_transitions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    episode_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_episodes.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DiscoveryExplanationRecord(Base):
    __tablename__ = "discovery_llm_explanations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_snapshots.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
