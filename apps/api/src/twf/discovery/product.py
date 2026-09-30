"""Typed Sprint-2 product contracts. These expose discovery, never trading authority."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from twf.discovery.domain import (
    CandidateToleranceEnvelope,
    DiscoveryEvidence,
    DiscoveryLifecycleState,
    DiscoveryRelevance,
    FreshnessState,
    InstrumentIdentity,
    RelevanceBand,
)
from twf.integrations.contracts import Contract, Identifier


class ProviderChoice(StrEnum):
    INTERNAL = "internal"
    TRADINGVIEW_SYNTHETIC = "tradingview-synthetic"


class IntentChoice(StrEnum):
    INTRADAY_LONG = "INTRADAY_LONG"
    INTRADAY_SHORT = "INTRADAY_SHORT"
    POSITIONAL_LONG = "POSITIONAL_LONG"
    POSITIONAL_SHORT = "POSITIONAL_SHORT"
    BREAKOUT = "BREAKOUT"
    MOMENTUM = "MOMENTUM"
    PULLBACK = "PULLBACK"


class HorizonChoice(StrEnum):
    INTRADAY = "intraday"
    ONE_DAY = "1d"
    FIVE_DAYS = "5d"
    FIFTEEN_DAYS = "15d"


class ContextAvailability(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"


class ContextDimension(Contract):
    name: Identifier
    availability: Literal["PRESENT", "MISSING", "UNAVAILABLE", "STALE"]
    value: str | Decimal | None = None
    source: Identifier
    reason: Identifier | None = None

    @model_validator(mode="after")
    def truthful(self) -> "ContextDimension":
        if self.availability == "PRESENT" and self.value is None:
            raise ValueError("Present context requires a value")
        if self.availability != "PRESENT" and self.value is not None:
            raise ValueError("Unavailable context cannot invent a value")
        if self.availability != "PRESENT" and self.reason is None:
            raise ValueError("Unavailable context requires a reason")
        return self


class MarketContextSnapshot(Contract):
    context_id: UUID
    owner_id: UUID
    observed_at: AwareDatetime
    source_data_time: AwareDatetime | None = None
    market: Identifier
    session: Literal["PRE_OPEN", "OPEN", "CLOSED", "UNKNOWN"]
    availability: ContextAvailability
    dimensions: tuple[ContextDimension, ...] = Field(min_length=1, max_length=16)
    producer: Identifier
    producer_version: Identifier
    evidence_ids: tuple[UUID, ...] = Field(default=(), max_length=64)
    limitations: tuple[Identifier, ...] = Field(default=(), max_length=16)


class RelevanceContribution(Contract):
    factor: Identifier
    value: Decimal = Field(ge=-1, le=1, allow_inf_nan=False)
    weight: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    contribution: Decimal = Field(ge=-1, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=240)


class RelevanceExplanation(Contract):
    policy: Literal["deterministic-relevance-v1"] = "deterministic-relevance-v1"
    score: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    band: RelevanceBand | None = None
    coverage: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    contributions: tuple[RelevanceContribution, ...] = Field(max_length=16)
    conflicts: tuple[str, ...] = Field(default=(), max_length=16)
    missing: tuple[str, ...] = Field(default=(), max_length=16)
    freshness_penalty: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    horizon_adjustment: Decimal = Field(ge=-1, le=1, allow_inf_nan=False)


class ToleranceDimensionAssessment(Contract):
    dimension: Literal["price", "structure", "momentum", "volume", "market", "sector", "time_decay"]
    status: Literal["WITHIN", "DEGRADED", "BREACHED", "UNKNOWN"]
    observed: Decimal | None = Field(default=None, allow_inf_nan=False)
    threshold: Decimal | None = Field(default=None, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=240)


class ToleranceAssessment(Contract):
    envelope: CandidateToleranceEnvelope
    horizon: HorizonChoice
    state: Literal["WITHIN", "DEGRADED", "BREACHED", "UNKNOWN"]
    dimensions: tuple[ToleranceDimensionAssessment, ...] = Field(min_length=2, max_length=7)


class LLMExplanation(Contract):
    explanation_id: UUID
    owner_id: UUID
    candidate_id: UUID
    snapshot_id: UUID
    provider: Identifier
    model: Identifier
    model_version: Identifier
    prompt_version: Identifier
    generated_at: AwareDatetime
    grounding: Literal["GROUNDED", "PARTIALLY_GROUNDED", "CONTEXT_ONLY"]
    evidence_ids: tuple[UUID, ...] = Field(max_length=64)
    narrative: str = Field(min_length=1, max_length=2000)
    limitations: tuple[str, ...] = Field(default=(), max_length=16)


Symbol = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9._-]*$")]


class ProductScanRequest(Contract):
    universe: tuple[Symbol, ...] = Field(min_length=1, max_length=20)
    provider: ProviderChoice = ProviderChoice.INTERNAL
    profile: Literal[
        "TREND_CONTINUATION",
        "BREAKOUT_WITH_VOLUME",
        "PULLBACK_IN_UPTREND",
        "MOMENTUM",
        "RELATIVE_VOLUME",
    ] = "RELATIVE_VOLUME"
    horizon: HorizonChoice = HorizonChoice.FIVE_DAYS
    intent: IntentChoice = IntentChoice.MOMENTUM
    include_llm: bool = False
    context_mode: Literal["healthy", "partial", "unavailable", "stale"] = "partial"

    @field_validator("universe")
    @classmethod
    def unique_universe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip().upper() for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("Universe symbols must be unique")
        return normalized


class ProviderStatus(Contract):
    id: ProviderChoice
    label: str
    enabled: bool
    mode: Literal["LOCAL_SYNTHETIC", "REMOTE", "SYNTHETIC_VALIDATION"]
    health: Literal["AVAILABLE", "DEGRADED", "AUTH_REQUIRED", "RATE_LIMITED"]
    capabilities: tuple[str, ...]
    last_success_at: AwareDatetime | None = None
    last_error: str | None = None


class ScanSummary(Contract):
    run_id: UUID
    provider: ProviderChoice
    status: Literal["COMPLETE", "FAILED"]
    started_at: AwareDatetime
    completed_at: AwareDatetime
    profile: str
    horizon: HorizonChoice
    intent: IntentChoice
    universe_size: int
    match_count: int
    candidate_count: int
    context_availability: ContextAvailability
    degraded: tuple[str, ...] = ()


class ScanMatchView(Contract):
    match_id: UUID
    symbol: str
    exchange: str
    provider: str
    why_matched: tuple[str, ...]
    key_metrics: dict[str, str]
    source_mode: str
    lineage: str


class ScanResult(Contract):
    summary: ScanSummary
    matches: tuple[ScanMatchView, ...]
    candidates: tuple["CandidateSummary", ...]
    market_context: MarketContextSnapshot


class CandidateSummary(Contract):
    candidate_id: UUID
    episode_id: UUID
    revision: int = Field(ge=1)
    instrument: InstrumentIdentity
    intent: IntentChoice
    horizon: HorizonChoice
    relevance: DiscoveryRelevance
    relevance_explanation: RelevanceExplanation
    tolerance: ToleranceAssessment
    lifecycle: DiscoveryLifecycleState
    freshness: FreshnessState
    snapshot_count: int
    provider_sources: tuple[str, ...]
    updated_at: AwareDatetime


class SnapshotView(Contract):
    snapshot_id: UUID
    sequence: int
    observed_at: AwareDatetime
    source_data_time: AwareDatetime | None
    lifecycle: DiscoveryLifecycleState
    relevance: DiscoveryRelevance
    relevance_explanation: RelevanceExplanation
    tolerance: ToleranceAssessment
    evidence: tuple[DiscoveryEvidence, ...]
    provider_sources: tuple[str, ...]


class CandidateDetail(CandidateSummary):
    snapshots: tuple[SnapshotView, ...]
    transitions: tuple[dict[str, object], ...]
    explanations: tuple[LLMExplanation, ...]
    context: MarketContextSnapshot | None = None
    previous_episode_id: UUID | None = None


class DiscoverySettings(Contract):
    revision: int = Field(ge=0)
    llm_enabled: bool = False
    llm_provider: Literal["synthetic", "openai", "anthropic", "google"] = "synthetic"
    default_provider: ProviderChoice = ProviderChoice.INTERNAL
    default_profile: str = "RELATIVE_VOLUME"
    default_horizon: HorizonChoice = HorizonChoice.FIVE_DAYS
    low_max: Decimal = Field(default=Decimal("0.60"), ge=0, le=1)
    medium_max: Decimal = Field(default=Decimal("0.90"), ge=0, le=1)
    freshness_seconds: int = Field(default=900, ge=60, le=86400)
    retention_days: int = Field(default=90, ge=7, le=3650)
    max_history_items: int = Field(default=50, ge=5, le=200)

    @model_validator(mode="after")
    def ordered(self) -> "DiscoverySettings":
        if not self.low_max < self.medium_max < 1:
            raise ValueError("Relevance thresholds must be ordered")
        return self


class DiscoverySettingsUpdate(DiscoverySettings):
    pass


class LifecycleAction(StrEnum):
    DISMISS = "DISMISS"
    MARK_DEFUNCT = "MARK_DEFUNCT"
    RECOVER = "RECOVER"


class LifecycleRequest(Contract):
    action: LifecycleAction
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=160)


class PaginatedCandidates(Contract):
    items: tuple[CandidateSummary, ...]
    total: int
    limit: int
    offset: int
    as_of: datetime
