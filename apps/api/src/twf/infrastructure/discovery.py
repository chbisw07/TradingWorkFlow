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


class ScanEvidenceSeriesRecord(Base):
    __tablename__ = "discovery_scan_evidence_series"
    __table_args__ = (
        UniqueConstraint("user_id", "run_id", "match_id", name="uq_discovery_chart_identity"),
    )
    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_scan_matches.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_scan_runs.id", ondelete="CASCADE"), index=True
    )
    instrument_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


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
    comparison_scope_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("discovery_comparison_scopes.id"), index=True, nullable=True
    )
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


class DiscoveryComparisonScopeRecord(Base):
    __tablename__ = "discovery_comparison_scopes"
    __table_args__ = (
        UniqueConstraint("user_id", "digest", name="uq_discovery_scope_owner_digest"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    descriptor: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DiscoveryTemporalLaneRecord(Base):
    __tablename__ = "discovery_temporal_lanes"
    scope_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_comparison_scopes.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    next_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    finalized_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    last_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoveryScanAdmissionRecord(Base):
    __tablename__ = "discovery_scan_admissions"
    __table_args__ = (
        UniqueConstraint("scope_id", "sequence", name="uq_discovery_admission_scope_sequence"),
        UniqueConstraint("user_id", "request_key", name="uq_discovery_admission_request"),
        Index("ix_discovery_admission_owner_status", "user_id", "status"),
    )
    run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    scope_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_comparison_scopes.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DiscoveryObservationRecord(Base):
    __tablename__ = "discovery_observations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "scope_id",
            "instrument_id",
            "run_id",
            name="uq_discovery_observation_idempotency",
        ),
        Index(
            "ix_discovery_observation_episode_sequence",
            "user_id",
            "episode_id",
            "run_sequence",
        ),
        Index(
            "ix_discovery_observation_run",
            "user_id",
            "run_id",
            "instrument_id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    scope_id: Mapped[UUID] = mapped_column(ForeignKey("discovery_comparison_scopes.id"), index=True)
    episode_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("discovery_episodes.id", ondelete="CASCADE"), index=True, nullable=True
    )
    candidate_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    run_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    run_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_data_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_sample_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DiscoveryActiveSlotRecord(Base):
    __tablename__ = "discovery_active_slots"
    __table_args__ = (UniqueConstraint("episode_id", name="uq_discovery_active_slot_episode"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    scope_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_comparison_scopes.id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    episode_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_episodes.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class DiscoveryProjectionCheckpointRecord(Base):
    __tablename__ = "discovery_projection_checkpoints"
    episode_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_episodes.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    through_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    prefix_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
