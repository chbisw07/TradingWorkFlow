"""Immutable S&D value objects. No persistence, provider SDK or execution authority."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from twf.integrations.contracts import Contract, Identifier


def utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


Instant = Annotated[AwareDatetime, AfterValidator(utc)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Text = Annotated[str, Field(min_length=1, max_length=256)]
Number = Annotated[Decimal, Field(allow_inf_nan=False)]
Score = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class RevisionRef(Contract):
    id: Identifier
    version: Identifier


class ProducerIdentity(Contract):
    service_id: Identifier
    provider: Identifier
    service_version: Identifier
    contract_version: Identifier


class SourceMode(StrEnum):
    LIVE_SNAPSHOT = "LIVE_SNAPSHOT"
    DELAYED = "DELAYED"
    EOD = "EOD"
    SYNTHETIC = "SYNTHETIC"


class SourceReference(Contract):
    namespace: Identifier
    native_id: Text
    revision: Identifier


class UnderlyingIdentity(Contract):
    underlying_id: UUID
    source: SourceReference
    mapping: RevisionRef
    ambiguous: bool = False


class InstrumentIdentity(Contract):
    instrument_id: UUID
    underlying: UnderlyingIdentity
    native: SourceReference
    symbol: Text
    exchange: Identifier
    segment: Identifier
    instrument_type: Identifier | None = None
    provider_symbol: Text | None = None
    expiry: Instant | None = None
    strike: Number | None = None
    right: Literal["CALL", "PUT"] | None = None


class HorizonBasis(StrEnum):
    ELAPSED = "ELAPSED"
    TRADING_SESSIONS = "TRADING_SESSIONS"
    CALENDAR = "CALENDAR"
    EVENT_RELATIVE = "EVENT_RELATIVE"


class HorizonSpec(Contract):
    schema_version: Literal[1] = 1
    preset: Identifier | None = None
    basis: HorizonBasis
    minimum: PositiveInt
    maximum: PositiveInt
    unit: Literal["seconds", "sessions", "days", "weeks"]
    calendar: RevisionRef | None = None
    timezone: str = "UTC"
    event_ref: SourceReference | None = None
    cadence_seconds: PositiveInt

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("Horizon range is reversed")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown horizon timezone") from exc
        if self.basis == HorizonBasis.ELAPSED and self.unit != "seconds":
            raise ValueError("Elapsed horizons use seconds")
        if self.basis == HorizonBasis.TRADING_SESSIONS:
            if self.unit != "sessions" or self.calendar is None:
                raise ValueError("Session horizons require a pinned calendar")
        elif self.unit == "sessions":
            raise ValueError("Session units need a trading-session basis")
        if self.basis == HorizonBasis.CALENDAR and self.unit not in ("days", "weeks"):
            raise ValueError("Calendar horizons use days or weeks")
        if (self.basis == HorizonBasis.EVENT_RELATIVE) != (self.event_ref is not None):
            raise ValueError("Event horizons require an explicit event anchor only")
        return self


# The accepted architecture calls this HorizonSpec; the implementation brief also uses TimeHorizon.
TimeHorizon = HorizonSpec


class OpportunityWindow(Contract):
    starts_at: Instant
    ends_at: Instant
    calendar: RevisionRef | None = None

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("Opportunity window must have positive duration")
        return self


class DiscoveryIntent(Contract):
    intent_id: UUID
    owner_id: UUID
    revision: PositiveInt
    created_at: Instant
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    objective: Identifier
    setup_family: Identifier
    horizon: HorizonSpec

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "direction": self.direction,
                "objective": self.objective,
                "setup_family": self.setup_family,
                "horizon": self.horizon.model_dump(mode="json", exclude={"preset"}),
            }
        )


class GroundingStatus(StrEnum):
    GROUNDED = "GROUNDED"
    PARTIALLY_GROUNDED = "PARTIALLY_GROUNDED"
    CONTEXT_ONLY = "CONTEXT_ONLY"


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class EvidenceCategory(StrEnum):
    INSTRUMENT_PRICE = "INSTRUMENT_PRICE"
    TECHNICAL = "TECHNICAL"
    VOLUME_LIQUIDITY = "VOLUME_LIQUIDITY"
    MARKET_CONTEXT = "MARKET_CONTEXT"
    SECTOR_INDUSTRY = "SECTOR_INDUSTRY"
    EVENT_NEWS = "EVENT_NEWS"
    PROVIDER_SCAN = "PROVIDER_SCAN"
    LLM_INTERPRETATION = "LLM_INTERPRETATION"
    CONFLICTING = "CONFLICTING"
    MISSING_UNAVAILABLE = "MISSING_UNAVAILABLE"


class EvidencePolarity(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class Measure(Contract):
    name: Identifier
    value: Number | Annotated[str, Field(max_length=256)] | bool
    unit: Identifier


class Provenance(Contract):
    producer: ProducerIdentity
    source: SourceReference
    mode: SourceMode
    observation_key: Identifier
    transformation: RevisionRef
    dependence_group: Identifier


class DiscoveryEvidence(Contract):
    evidence_id: UUID
    owner_id: UUID
    subject_id: UUID
    category: EvidenceCategory
    polarity: EvidencePolarity
    observation_basis: Identifier
    observed_at: Instant
    source_data_time: Instant | None = None
    source_published_at: Instant | None = None
    available_at: Instant | None = None
    received_at: Instant
    provenance: Provenance
    availability: Literal["PRESENT", "MISSING", "UNAVAILABLE"] = "PRESENT"
    measures: tuple[Measure, ...] = Field(default=(), max_length=32)
    reason: Identifier | None = None
    grounding: GroundingStatus | None = None
    related_evidence_ids: tuple[UUID, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.observed_at > self.received_at:
            raise ValueError("Observation cannot follow receipt")
        for value in (self.source_data_time, self.source_published_at, self.available_at):
            if value is not None and value > self.received_at:
                raise ValueError("Source time cannot follow receipt")
        if self.availability != "PRESENT" and (self.measures or self.reason is None):
            raise ValueError("Missing evidence needs a reason, never invented measurements")
        if self.availability == "PRESENT" and not self.measures:
            raise ValueError("Present evidence requires typed measurements")
        if self.category == EvidenceCategory.LLM_INTERPRETATION and self.grounding is None:
            raise ValueError("LLM evidence requires explicit grounding")
        return self


def freshness(evidence: DiscoveryEvidence, as_of: datetime, ttl_seconds: int) -> FreshnessState:
    if as_of.tzinfo is None or ttl_seconds <= 0:
        raise ValueError("Freshness requires an aware clock and positive TTL")
    source_time = evidence.source_data_time
    if evidence.availability != "PRESENT" or source_time is None or source_time > as_of:
        return FreshnessState.UNKNOWN
    if evidence.received_at > as_of:
        return FreshnessState.UNKNOWN
    return (
        FreshnessState.FRESH
        if (as_of - source_time).total_seconds() <= ttl_seconds
        else FreshnessState.STALE
    )


class RelevanceBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RelevanceThresholds(Contract):
    low_max: Score = Decimal("0.60")
    medium_max: Score = Decimal("0.90")

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if not self.low_max < self.medium_max < 1:
            raise ValueError("Relevance thresholds must be ordered below one")
        if any(x != x.quantize(Decimal(".01")) for x in (self.low_max, self.medium_max)):
            raise ValueError("Thresholds use displayed two-place precision")
        return self


class DiscoveryRelevance(Contract):
    """Policy fit, never probability of profit. No scoring algorithm lives here."""

    value: Score | None
    policy: RevisionRef
    thresholds: RelevanceThresholds = RelevanceThresholds()
    required_inputs_satisfied: bool
    coverage: Score
    reasons: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def required_inputs(self) -> Self:
        if not self.required_inputs_satisfied and self.value is not None:
            raise ValueError("Missing required inputs must remain unscored")
        return self

    @property
    def displayed_value(self) -> Decimal | None:
        return (
            None
            if self.value is None
            else self.value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        )

    @property
    def band(self) -> RelevanceBand | None:
        value = self.displayed_value
        if value is None:
            return None
        if value <= self.thresholds.low_max:
            return RelevanceBand.LOW
        if value <= self.thresholds.medium_max:
            return RelevanceBand.MEDIUM
        return RelevanceBand.HIGH


class Comparison(StrEnum):
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    GTE = "GTE"
    GT = "GT"


class Criterion(Contract):
    metric: Identifier
    operator: Comparison
    threshold: Number
    unit: Identifier


class ScanDefinition(Contract):
    definition_id: UUID
    revision: PositiveInt
    criteria: tuple[Criterion, ...] = Field(min_length=1, max_length=16)
    combination: Literal["ALL", "ANY"] = "ALL"
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "NEUTRAL"
    timeframe: Identifier
    source_mode: SourceMode
    required_capabilities: tuple[Identifier, ...] = Field(min_length=1, max_length=16)


class ScanProfileReference(Contract):
    profile_id: UUID
    owner_id: UUID
    applied_revision: PositiveInt
    schema_version: Literal[1] = 1


class ScanRun(Contract):
    run_id: UUID
    owner_id: UUID
    request_id: Identifier
    profile: ScanProfileReference
    definition: ScanDefinition
    as_of: Instant

    @model_validator(mode="after")
    def owned(self) -> Self:
        if self.owner_id != self.profile.owner_id:
            raise ValueError("Profile owner mismatch")
        return self

    @property
    def configuration_fingerprint(self) -> str:
        return digest(
            {
                "definition": self.definition.model_dump(mode="json"),
                "profile": self.profile.model_dump(mode="json"),
            }
        )


class ScanLineage(Contract):
    run_id: UUID
    match_id: UUID
    definition_id: UUID
    definition_revision: PositiveInt
    profile: ScanProfileReference
    configuration_fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

    @property
    def comparison_key(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"run_id", "match_id"}))


class CandidateLineage(Contract):
    input_id: UUID
    owner_id: UUID
    producer: ProducerIdentity
    source: SourceReference
    scan: ScanLineage | None = None

    @model_validator(mode="after")
    def owned(self) -> Self:
        if self.scan is not None and self.scan.profile.owner_id != self.owner_id:
            raise ValueError("Lineage profile owner mismatch")
        return self


class ScanMatch(Contract):
    scan_match_id: UUID
    run_id: UUID
    owner_id: UUID
    instrument: InstrumentIdentity
    definition_id: UUID
    definition_revision: PositiveInt
    profile: ScanProfileReference
    configuration_fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    evidence: tuple[DiscoveryEvidence, ...] = Field(min_length=1, max_length=64)
    provenance: Provenance

    @model_validator(mode="after")
    def owned(self) -> Self:
        if any(
            e.owner_id != self.owner_id or e.subject_id != self.instrument.instrument_id
            for e in self.evidence
        ):
            raise ValueError("Match evidence scope mismatch")
        if self.profile.owner_id != self.owner_id:
            raise ValueError("Match profile owner mismatch")
        return self

    @property
    def lineage(self) -> ScanLineage:
        return ScanLineage(
            run_id=self.run_id,
            match_id=self.scan_match_id,
            definition_id=self.definition_id,
            definition_revision=self.definition_revision,
            profile=self.profile,
            configuration_fingerprint=self.configuration_fingerprint,
        )


class CandidateInput(Contract):
    input_id: UUID
    owner_id: UUID
    instrument: InstrumentIdentity
    evidence: tuple[DiscoveryEvidence, ...] = Field(min_length=1, max_length=64)
    provenance: Provenance
    scan_match_id: UUID | None = None
    scan_lineage: ScanLineage | None = None

    @model_validator(mode="after")
    def owned(self) -> Self:
        if any(
            e.owner_id != self.owner_id or e.subject_id != self.instrument.instrument_id
            for e in self.evidence
        ):
            raise ValueError("Candidate input evidence scope mismatch")
        if (self.scan_lineage is None) != (self.scan_match_id is None):
            raise ValueError("Scan input requires complete lineage")
        if self.scan_lineage is not None and (
            self.scan_lineage.match_id != self.scan_match_id
            or self.scan_lineage.profile.owner_id != self.owner_id
        ):
            raise ValueError("Candidate scan lineage mismatch")
        return self

    @property
    def lineage(self) -> CandidateLineage:
        return CandidateLineage(
            input_id=self.input_id,
            owner_id=self.owner_id,
            producer=self.provenance.producer,
            source=self.provenance.source,
            scan=self.scan_lineage,
        )


class ToleranceRule(Contract):
    dimension: Literal["price", "structure", "momentum", "volume", "market", "sector", "time_decay"]
    criterion: Criterion
    reference_basis: Identifier
    reference_snapshot_id: UUID | None = None
    required_categories: tuple[EvidenceCategory, ...] = Field(min_length=1)
    confirmation_observations: PositiveInt
    recovery_rule: RevisionRef


class CandidateToleranceEnvelope(Contract):
    policy: RevisionRef
    rules: tuple[ToleranceRule, ...] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({rule.dimension for rule in self.rules}) != len(self.rules):
            raise ValueError("Tolerance dimensions must be unique")
        return self


class DiscoveryLifecycleState(StrEnum):
    NEW = "NEW"
    CURRENT = "CURRENT"
    STALE = "STALE"
    DEFUNCT = "DEFUNCT"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class DiscoveryObservationKind(StrEnum):
    """Mechanical result for one instrument in one admitted scan."""

    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    NOT_EVALUATED = "NOT_EVALUATED"


class EvaluationCoverage(StrEnum):
    EVALUATED = "EVALUATED"
    NOT_REQUESTED = "NOT_REQUESTED"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    MISSING_DATA = "MISSING_DATA"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    SKIPPED = "SKIPPED"
    INCOMPLETE = "INCOMPLETE"


class ObservationComparison(StrEnum):
    COMPARABLE = "COMPARABLE"
    INCOMPARABLE = "INCOMPARABLE"


class SourceNovelty(StrEnum):
    NOVEL = "NOVEL"
    DUPLICATE = "DUPLICATE"
    UNKNOWN = "UNKNOWN"
    REGRESSED = "REGRESSED"


class ScanComparabilityDescriptor(Contract):
    """Versioned semantic identity; operational/provider credentials are excluded."""

    schema_version: Literal[1] = 1
    criteria_fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    profile_semantic_class: Identifier
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    intent: Identifier
    horizon: HorizonSpec
    observation_basis: Identifier
    provider_equivalence_class: Identifier
    data_mode: SourceMode
    admission_policy: Identifier
    lifecycle_policy: RevisionRef

    @property
    def fingerprint(self) -> str:
        return digest(self.model_dump(mode="json"))


class DiscoveryObservation(Contract):
    """Immutable temporal input. Lifecycle-after is an auditable cached reduction."""

    observation_id: UUID
    owner_id: UUID
    comparison_scope_id: UUID
    episode_id: UUID | None = None
    candidate_id: UUID | None = None
    run_id: UUID
    run_sequence: PositiveInt
    instrument_id: UUID
    kind: DiscoveryObservationKind
    comparison: ObservationComparison
    coverage: EvaluationCoverage
    novelty: SourceNovelty
    source_sample_key: str | None = Field(default=None, max_length=128)
    observed_at: Instant
    source_data_time: Instant | None = None
    recorded_at: Instant
    scan_match_id: UUID | None = None
    snapshot_id: UUID | None = None
    relevance_score: Score | None = None
    relevance_band: RelevanceBand | None = None
    relevance_policy: RevisionRef | None = None
    lifecycle_after: DiscoveryLifecycleState | None = None
    reason: Identifier
    evidence_ids: tuple[UUID, ...] = Field(default=(), max_length=128)
    context_id: UUID | None = None

    @model_validator(mode="after")
    def truthful(self) -> Self:
        if self.recorded_at < self.observed_at:
            raise ValueError("Observation cannot be recorded before it was observed")
        if self.kind == DiscoveryObservationKind.PRESENT:
            if self.coverage != EvaluationCoverage.EVALUATED or self.scan_match_id is None:
                raise ValueError("PRESENT requires evaluated coverage and a ScanMatch")
        elif self.scan_match_id is not None:
            raise ValueError("Only PRESENT may reference a ScanMatch")
        if self.kind == DiscoveryObservationKind.ABSENT:
            if self.coverage != EvaluationCoverage.EVALUATED:
                raise ValueError("ABSENT requires definitive evaluated coverage")
            if self.relevance_score is not None or self.relevance_band is not None:
                raise ValueError("ABSENT relevance is always null")
        if self.kind == DiscoveryObservationKind.NOT_EVALUATED:
            if self.coverage == EvaluationCoverage.EVALUATED:
                raise ValueError("NOT_EVALUATED cannot claim evaluated coverage")
            if self.relevance_score is not None or self.relevance_band is not None:
                raise ValueError("NOT_EVALUATED relevance is always null")
        if (self.episode_id is None) != (self.candidate_id is None):
            raise ValueError("Candidate and episode references are both present or both absent")
        if self.source_data_time is not None and self.source_data_time > self.recorded_at:
            raise ValueError("Future source observation")
        return self


class RejectionReason(StrEnum):
    DEFUNCT_CONFIRMED = "DEFUNCT_CONFIRMED"
    EXPIRED = "EXPIRED"
    USER_DISMISSED = "USER_DISMISSED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    IDENTITY_INVALID = "IDENTITY_INVALID"


class DiscoveryEpisode(Contract):
    episode_id: UUID
    candidate_id: UUID
    owner_id: UUID
    instrument: InstrumentIdentity
    intent: DiscoveryIntent
    observation_basis: Identifier
    policy_series: RevisionRef
    window: OpportunityWindow
    opened_at: Instant
    evaluated_at: Instant
    revision: PositiveInt = 1
    lifecycle: DiscoveryLifecycleState = DiscoveryLifecycleState.NEW
    head_snapshot_id: UUID | None = None
    previous_episode_id: UUID | None = None
    rejection_reason: RejectionReason | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.intent.owner_id != self.owner_id:
            raise ValueError("Intent owner mismatch")
        if (self.lifecycle == DiscoveryLifecycleState.REJECTED) != (
            self.rejection_reason is not None
        ):
            raise ValueError("Only rejected episodes require a rejection reason")
        if not self.window.starts_at <= self.opened_at < self.window.ends_at:
            raise ValueError("Episode must open inside its fixed window")
        if self.evaluated_at < self.opened_at:
            raise ValueError("Evaluation cannot precede opening")
        if self.window.calendar != self.intent.horizon.calendar:
            raise ValueError("Window must pin the intent calendar")
        return self

    @property
    def active_key(self) -> tuple[UUID, UUID, str, str, RevisionRef]:
        return (
            self.owner_id,
            self.instrument.instrument_id,
            self.observation_basis,
            self.intent.fingerprint,
            self.policy_series,
        )


class DiscoverySnapshot(Contract):
    snapshot_id: UUID
    episode_id: UUID
    owner_id: UUID
    sequence: PositiveInt
    previous_snapshot_id: UUID | None
    instrument: InstrumentIdentity
    intent_fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    observation_basis: Identifier
    observed_at: Instant
    source_data_time: Instant | None
    evaluated_at: Instant
    recorded_at: Instant
    evidence: tuple[DiscoveryEvidence, ...] = Field(min_length=1, max_length=128)
    provenance: Provenance
    relevance: DiscoveryRelevance
    lineage: CandidateLineage

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            self.lineage.owner_id != self.owner_id
            or self.lineage.producer != self.provenance.producer
            or self.lineage.source != self.provenance.source
        ):
            raise ValueError("Snapshot input lineage mismatch")
        source_times = tuple(e.source_data_time for e in self.evidence)
        expected_source = (
            min(t for t in source_times if t is not None)
            if all(t is not None for t in source_times)
            else None
        )
        if self.source_data_time != expected_source or self.observed_at != max(
            e.observed_at for e in self.evidence
        ):
            raise ValueError("Snapshot time summary must match captured evidence")
        if not self.observed_at <= self.evaluated_at <= self.recorded_at:
            raise ValueError("Snapshot time order is invalid")
        if self.source_data_time is not None and self.source_data_time > self.evaluated_at:
            raise ValueError("Future source observation")
        if (self.sequence == 1) != (self.previous_snapshot_id is None):
            raise ValueError("Snapshot sequence and predecessor disagree")
        if len({e.evidence_id for e in self.evidence}) != len(self.evidence):
            raise ValueError("Duplicate evidence identity")
        for item in self.evidence:
            if item.owner_id != self.owner_id or item.subject_id != self.instrument.instrument_id:
                raise ValueError("Snapshot evidence scope mismatch")
            if item.received_at > self.evaluated_at:
                raise ValueError("Evidence was unavailable at evaluation cutoff")
        return self

    @property
    def content_hash(self) -> str:
        return digest(self.model_dump(mode="json"))


class DiscoveryCandidate(Contract):
    candidate_id: UUID
    owner_id: UUID
    episode_id: UUID
    revision: PositiveInt
    instrument: InstrumentIdentity
    intent: DiscoveryIntent
    head_snapshot_id: UUID
    lifecycle: DiscoveryLifecycleState
    freshness: FreshnessState
    relevance: DiscoveryRelevance
    window: OpportunityWindow
    evaluated_at: Instant
    projected_at: Instant
