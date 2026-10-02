"""Typed Sprint-2 product contracts. These expose discovery, never trading authority."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from twf.discovery.domain import (
    CandidateToleranceEnvelope,
    Comparison,
    DiscoveryEvidence,
    DiscoveryLifecycleState,
    DiscoveryObservationKind,
    DiscoveryRelevance,
    FreshnessState,
    InstrumentIdentity,
    RelevanceBand,
    SourceNovelty,
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


class ContextPolicy(StrEnum):
    REQUIRE_COMPLETE = "REQUIRE_COMPLETE"
    ALLOW_PARTIAL = "ALLOW_PARTIAL"
    OPTIONAL = "OPTIONAL"


class AdmissionReason(StrEnum):
    ADMITTED = "ADMITTED"
    EXCLUDED_DIRECTION = "EXCLUDED_DIRECTION"
    EXCLUDED_CONTEXT_POLICY = "EXCLUDED_CONTEXT_POLICY"


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
    policy: Literal["deterministic-relevance-v1", "deterministic-relevance-v2"] = (
        "deterministic-relevance-v2"
    )
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
    context_policy: ContextPolicy | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("universe")
    @classmethod
    def unique_universe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip().upper() for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("Universe symbols must be unique")
        return normalized

    @model_validator(mode="after")
    def compatible_selection(self) -> "ProductScanRequest":
        intraday = {IntentChoice.INTRADAY_LONG, IntentChoice.INTRADAY_SHORT}
        positional = {IntentChoice.POSITIONAL_LONG, IntentChoice.POSITIONAL_SHORT}
        if self.intent in intraday and self.horizon not in {
            HorizonChoice.INTRADAY,
            HorizonChoice.ONE_DAY,
        }:
            raise ValueError("Intraday intent requires an intraday or 1-day horizon")
        if self.intent in positional and self.horizon not in {
            HorizonChoice.FIVE_DAYS,
            HorizonChoice.FIFTEEN_DAYS,
        }:
            raise ValueError("Positional intent requires a multi-day horizon")
        if self.profile == "PULLBACK_IN_UPTREND" and self.intent in {
            IntentChoice.INTRADAY_SHORT,
            IntentChoice.POSITIONAL_SHORT,
        }:
            raise ValueError("Pullback in uptrend supports long-side intent only")
        return self


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
    universe: tuple[Symbol, ...] = ()
    match_count: int
    candidate_count: int
    context_mode: Literal["healthy", "partial", "unavailable", "stale"] = "partial"
    context_policy: ContextPolicy = ContextPolicy.ALLOW_PARTIAL
    context_availability: ContextAvailability
    degraded: tuple[str, ...] = ()
    archived_at: AwareDatetime | None = None


class ScanMatchView(Contract):
    match_id: UUID
    symbol: str
    exchange: str
    segment: str
    provider: str
    why_matched: tuple[str, ...]
    raw_reasons: tuple[str, ...]
    key_metrics: dict[str, str]
    source_mode: str
    source_data_time: AwareDatetime | None = None
    lineage: str


class EvidenceChartMode(StrEnum):
    AS_SCANNED = "as_scanned"
    CURRENT = "current"


class EvidenceChartState(StrEnum):
    AVAILABLE = "AVAILABLE"
    LEGACY_UNAVAILABLE = "LEGACY_UNAVAILABLE"
    CURRENT_UNAVAILABLE = "CURRENT_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RETENTION_RESTRICTED = "RETENTION_RESTRICTED"
    RECONSTRUCTION_FAILED = "RECONSTRUCTION_FAILED"


class EvidenceChartBar(Contract):
    timestamp: AwareDatetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal | None = Field(default=None, ge=0)
    finality: Literal["COMPLETED", "PROVIDER_UNSPECIFIED"]


class EvidenceChartPoint(Contract):
    timestamp: AwareDatetime
    value: Decimal = Field(allow_inf_nan=False)


class EvidenceChartSeries(Contract):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    panel: Literal["PRICE", "VOLUME", "OSCILLATOR"]
    points: tuple[EvidenceChartPoint, ...] = Field(max_length=120)


class EvidenceChartThreshold(Contract):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    panel: Literal["PRICE", "VOLUME", "OSCILLATOR"]
    value: Decimal = Field(allow_inf_nan=False)
    kind: Literal["LINE", "UPPER", "LOWER"] = "LINE"


class EvidenceChartPredicate(Contract):
    metric: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    observed: Decimal = Field(allow_inf_nan=False)
    operator: Comparison
    threshold: Decimal = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=32)
    matched: bool


class EvidenceChartMetric(Contract):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    value: Decimal = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=32)


class EvidenceChartRetention(Contract):
    source_class: Literal[
        "SYNTHETIC_RETAINED",
        "LICENSED_RETAINED",
        "PROVIDER_RESTRICTED",
        "LEGACY_UNKNOWN",
    ]
    historical_chart_reconstructable: bool
    scan_bars_retained: bool
    current_chart_available: bool
    archive_bar_count: int = Field(ge=0, le=1024)
    displayed_bar_count: int = Field(ge=0, le=120)
    limitation: str = Field(min_length=1, max_length=320)


class EvidenceChart(Contract):
    mode: EvidenceChartMode
    state: EvidenceChartState
    message: str | None = Field(default=None, max_length=320)
    run_id: UUID
    match_id: UUID
    instrument: InstrumentIdentity
    scan_time: AwareDatetime
    source_data_time: AwareDatetime | None = None
    profile: str
    profile_revision: int = Field(ge=1)
    definition_revision: int = Field(ge=1)
    intent: IntentChoice
    horizon: HorizonChoice
    provider: str
    data_mode: str
    timeframe: str
    price_unit: str
    bar_finality: Literal["COMPLETED", "PROVIDER_UNSPECIFIED"]
    bars: tuple[EvidenceChartBar, ...] = Field(max_length=120)
    series: tuple[EvidenceChartSeries, ...] = Field(max_length=12)
    thresholds: tuple[EvidenceChartThreshold, ...] = Field(max_length=12)
    predicates: tuple[EvidenceChartPredicate, ...] = Field(max_length=16)
    metrics: tuple[EvidenceChartMetric, ...] = Field(max_length=16)
    retention: EvidenceChartRetention
    provenance: str = Field(min_length=1, max_length=320)


class MatchAdmissionDecision(Contract):
    match_id: UUID
    symbol: str
    status: Literal["ADMITTED", "EXCLUDED"]
    reason: AdmissionReason


class AdmissionSummary(Contract):
    match_count: int = Field(ge=0)
    admitted_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    decisions: tuple[MatchAdmissionDecision, ...]

    @model_validator(mode="after")
    def reconciles(self) -> "AdmissionSummary":
        if self.match_count != self.admitted_count + self.excluded_count:
            raise ValueError("Match admission counts must reconcile")
        if self.match_count != len(self.decisions):
            raise ValueError("Every match requires an admission decision")
        return self


class ScanResult(Contract):
    summary: ScanSummary
    matches: tuple[ScanMatchView, ...]
    candidates: tuple["CandidateSummary", ...]
    market_context: MarketContextSnapshot
    admission: AdmissionSummary


class HistoricalScanDetail(Contract):
    summary: ScanSummary
    matches: tuple[ScanMatchView, ...]
    market_context: MarketContextSnapshot | None = None


class WindowStatus(StrEnum):
    OPEN = "OPEN"
    ENDED = "ENDED"
    UNKNOWN = "UNKNOWN"


class TemporalObservationView(Contract):
    observation_id: UUID
    run_id: UUID
    run_sequence: int = Field(ge=1)
    observed_at: AwareDatetime
    source_data_time: AwareDatetime | None = None
    kind: DiscoveryObservationKind
    coverage: str
    novelty: SourceNovelty
    relevance_score: Decimal | None = Field(default=None, ge=0, le=1)
    relevance_band: RelevanceBand | None = None
    relevance_model: str | None = None
    lifecycle_after: DiscoveryLifecycleState | None = None
    reason: str
    comparison_scope_version: int = Field(ge=1)
    provider: str | None = None
    is_hot: bool


class TemporalSummary(Contract):
    latest_observation_kind: DiscoveryObservationKind
    last_observed_at: AwareDatetime
    latest_comparable_run_id: UUID
    latest_attempted_run_id: UUID
    latest_present_run_id: UUID | None = None
    last_known_relevance: Decimal | None = Field(default=None, ge=0, le=1)
    relevance_delta: Decimal | None = Field(default=None, ge=-1, le=1)
    relevance_model: str | None = None
    hot_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    window_status: WindowStatus
    observation_age_seconds: int = Field(ge=0)
    recent_observations: tuple[TemporalObservationView, ...] = ()


class TemporalHistoryPage(Contract):
    items: tuple[TemporalObservationView, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    hot_size: int = Field(ge=5, le=100)
    as_of: AwareDatetime


class RunViewMode(StrEnum):
    AS_SCANNED = "as_scanned"
    CURRENT_STATE = "current_state"


class RunTemporalCandidate(Contract):
    instrument: InstrumentIdentity
    observation: TemporalObservationView
    candidate: "CandidateSummary | None" = None


class RunTemporalView(Contract):
    run_id: UUID
    mode: RunViewMode
    summary: ScanSummary
    items: tuple[RunTemporalCandidate, ...]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)


ProfileLineage = Literal[
    "CURRENT_SNAPSHOT",
    "ORIGINATING_SCAN",
    "LATEST_SCAN",
    "PERSISTED_SNAPSHOT",
    "CANDIDATE_METADATA",
    "LEGACY_UNAVAILABLE",
]


class CandidateSummary(Contract):
    candidate_id: UUID
    episode_id: UUID
    revision: int = Field(ge=1)
    instrument: InstrumentIdentity
    intent: IntentChoice
    horizon: HorizonChoice
    profile: str | None
    profile_lineage: ProfileLineage
    legacy_profile: bool
    relevance: DiscoveryRelevance
    relevance_explanation: RelevanceExplanation
    tolerance: ToleranceAssessment
    lifecycle: DiscoveryLifecycleState
    lifecycle_reason: str
    freshness: FreshnessState
    snapshot_count: int
    provider_sources: tuple[str, ...]
    originating_scan_run_id: UUID | None = None
    latest_scan_run_id: UUID | None = None
    updated_at: AwareDatetime
    temporal: TemporalSummary | None = None


class SnapshotView(Contract):
    snapshot_id: UUID
    sequence: int
    observed_at: AwareDatetime
    source_data_time: AwareDatetime | None
    lifecycle: DiscoveryLifecycleState
    lifecycle_reason: str
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
    observations: tuple[TemporalObservationView, ...] = ()


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
    hot_observation_count: int = Field(default=20, ge=5, le=100)

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
