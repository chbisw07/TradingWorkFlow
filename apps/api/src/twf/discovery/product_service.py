"""Integrated Sprint-2 Scan & Discover use cases with explicit bounded degradation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import Float, and_, case, func, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from twf.discovery.domain import (
    CandidateLineage,
    CandidateToleranceEnvelope,
    Comparison,
    Criterion,
    DiscoveryEpisode,
    DiscoveryEvidence,
    DiscoveryIntent,
    DiscoveryLifecycleState,
    DiscoveryObservationKind,
    DiscoveryRelevance,
    DiscoverySnapshot,
    EvaluationCoverage,
    EvidenceCategory,
    EvidencePolarity,
    FreshnessState,
    HorizonBasis,
    HorizonSpec,
    InstrumentIdentity,
    Measure,
    OpportunityWindow,
    ProducerIdentity,
    Provenance,
    RelevanceThresholds,
    RevisionRef,
    ScanComparabilityDescriptor,
    ScanMatch,
    ScanProfileReference,
    ScanRun,
    SourceMode,
    SourceReference,
    ToleranceRule,
    UnderlyingIdentity,
    digest,
)
from twf.discovery.evidence_chart import archive_payload, build_chart, unavailable_chart
from twf.discovery.internal_scanner.conditions import compare as series_compare
from twf.discovery.internal_scanner.conditions import measure as series_measure
from twf.discovery.internal_scanner.market_series import (
    Bar,
    FixtureMarketSeriesSource,
    MarketSeries,
)
from twf.discovery.internal_scanner.profiles import IDENTITY as INTERNAL_IDENTITY
from twf.discovery.internal_scanner.profiles import build_profile
from twf.discovery.internal_scanner.scanner import InternalScannerV0
from twf.discovery.product import (
    AdmissionReason,
    AdmissionSummary,
    CandidateDetail,
    CandidateSummary,
    ContextAvailability,
    ContextDimension,
    ContextPolicy,
    DiscoverySettings,
    EvidenceChart,
    EvidenceChartMode,
    EvidenceChartState,
    EvidenceVerification,
    HistoricalScanDetail,
    HorizonChoice,
    IntentChoice,
    LifecycleAction,
    LLMExplanation,
    MarketContextSnapshot,
    MatchAdmissionDecision,
    PaginatedCandidates,
    ProductScanRequest,
    ProfileLineage,
    ProviderChoice,
    ProviderStatus,
    RealEvidenceLineage,
    RelevanceContribution,
    RelevanceExplanation,
    RunTemporalCandidate,
    RunTemporalView,
    RunViewMode,
    ScanMatchView,
    ScanResult,
    ScanSummary,
    SnapshotView,
    TemporalHistoryPage,
    TemporalSummary,
    ToleranceAssessment,
    ToleranceDimensionAssessment,
)
from twf.discovery.providers import OperationContext
from twf.discovery.temporal import RunAdmission, TemporalConflict, TemporalStore
from twf.discovery.tradingview.evidence import (
    EvidenceOutcome,
    SymbolEvidence,
    TradingViewEvidenceGateway,
)
from twf.infrastructure.discovery import (
    DiscoveryActiveSlotRecord,
    DiscoveryEpisodeRecord,
    DiscoveryExplanationRecord,
    DiscoveryObservationRecord,
    DiscoverySettingsRecord,
    DiscoverySnapshotRecord,
    DiscoveryTransitionRecord,
    MarketContextRecord,
    ScanEvidenceSeriesRecord,
    ScanMatchRecord,
    ScanRunRecord,
)
from twf.integrations.contracts import RequestContext

POLICY = RevisionRef(id="deterministic-relevance-v2", version="2")
TEMPORAL_POLICY = RevisionRef(id="scan-driven-temporal", version="1")
TRANSFORMATION = RevisionRef(id="sprint2-product-normalization", version="1")
REAL_TRADINGVIEW = ProducerIdentity(
    service_id="tradingview-real-evidence",
    provider="tradingview",
    service_version="1",
    contract_version="sd.evidence.v1",
)
TRADINGVIEW_SYNTHETIC = ProducerIdentity(
    service_id="tradingview-synthetic-validation",
    provider="tradingview",
    service_version="1",
    contract_version="sd.scan.v1",
)
TERMINAL = {
    DiscoveryLifecycleState.EXPIRED.value,
    DiscoveryLifecycleState.REJECTED.value,
}


class ProductFailure(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code
        super().__init__(code)


def stable(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, "twf-sprint2-product:" + value)


def now_utc() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    """SQLite returns naive values for timezone columns; persisted values are UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def horizon_seconds(value: HorizonChoice) -> int:
    return {
        HorizonChoice.INTRADAY: 6 * 3600,
        HorizonChoice.ONE_DAY: 86400,
        HorizonChoice.FIVE_DAYS: 5 * 86400,
        HorizonChoice.FIFTEEN_DAYS: 15 * 86400,
    }[value]


def intent_direction(choice: IntentChoice) -> Literal["LONG", "SHORT"]:
    return (
        "SHORT"
        if choice in {IntentChoice.INTRADAY_SHORT, IntentChoice.POSITIONAL_SHORT}
        else "LONG"
    )


def fixture_polarity(fixture: SyntheticInstrumentFixture) -> EvidencePolarity:
    if fixture.daily_trend > 0:
        return EvidencePolarity.POSITIVE
    if fixture.daily_trend < 0:
        return EvidencePolarity.NEGATIVE
    return EvidencePolarity.NEUTRAL


INDEX_SYMBOLS = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"})


@dataclass(frozen=True)
class SyntheticInstrumentFixture:
    base_price: Decimal
    daily_trend: Decimal
    relative_volume: Decimal
    technical_evidence: bool
    tradingview_match: bool
    final_move: Decimal | None = None
    cycle_amplitude: Decimal = Decimal("0.08")


SYNTHETIC_FIXTURES: dict[str, SyntheticInstrumentFixture] = {
    # Distinct deterministic archetypes for operator validation, never market claims.
    "RELIANCE": SyntheticInstrumentFixture(
        Decimal("2846.40"),
        Decimal("0.18"),
        Decimal("1.95"),
        True,
        True,
        Decimal("8.00"),
        Decimal("0.20"),
    ),
    "MCX": SyntheticInstrumentFixture(
        Decimal("3146.80"),
        Decimal("0.34"),
        Decimal("2.60"),
        True,
        True,
        None,
        Decimal("0.30"),
    ),
    "HDFCBANK": SyntheticInstrumentFixture(
        Decimal("1684.25"),
        Decimal("-0.03"),
        Decimal("0.82"),
        False,
        False,
        None,
        Decimal("0.35"),
    ),
    "INFY": SyntheticInstrumentFixture(
        Decimal("1568.60"),
        Decimal("0.22"),
        Decimal("1.30"),
        True,
        True,
        Decimal("-2.80"),
        Decimal("0.25"),
    ),
    "BSE": SyntheticInstrumentFixture(
        Decimal("2488.15"),
        Decimal("-0.30"),
        Decimal("1.85"),
        True,
        True,
        None,
        Decimal("0.25"),
    ),
    "NIFTY": SyntheticInstrumentFixture(
        Decimal("24520.30"),
        Decimal("0.10"),
        Decimal("1.25"),
        True,
        True,
        None,
        Decimal("0.60"),
    ),
    "BANKNIFTY": SyntheticInstrumentFixture(
        Decimal("51780.10"),
        Decimal("-0.12"),
        Decimal("2.05"),
        True,
        True,
        Decimal("-18.00"),
        Decimal("0.45"),
    ),
    "TCS": SyntheticInstrumentFixture(
        Decimal("3984.50"),
        Decimal("0.04"),
        Decimal("1.20"),
        False,
        True,
        None,
        Decimal("0.40"),
    ),
}


def synthetic_fixture(symbol: str, progression: int = 0) -> SyntheticInstrumentFixture:
    if symbol.startswith("NO"):
        return SyntheticInstrumentFixture(
            Decimal("120.00"), Decimal("-0.10"), Decimal("0.70"), False, False
        )
    fixture = SYNTHETIC_FIXTURES.get(symbol)
    if fixture is None:
        seed = sum(ord(char) for char in symbol)
        fixture = SyntheticInstrumentFixture(
            base_price=Decimal(100 + seed % 900),
            daily_trend=Decimal("0.18") + Decimal(seed % 11) / Decimal(100),
            relative_volume=Decimal("1.55") + Decimal(seed % 45) / Decimal(100),
            technical_evidence=seed % 3 == 0,
            tradingview_match=True,
        )
    if progression <= 0:
        return fixture
    return replace(
        fixture,
        relative_volume=min(
            Decimal("3.50"), fixture.relative_volume + Decimal("0.15") * progression
        ),
        final_move=(
            fixture.final_move
            + (Decimal("0.50") if fixture.final_move > 0 else Decimal("-0.50")) * progression
            if fixture.final_move is not None
            else None
        ),
    )


def identity(symbol: str) -> InstrumentIdentity:
    segment = "INDEX" if symbol in INDEX_SYMBOLS else "EQ"
    return InstrumentIdentity(
        instrument_id=stable(f"instrument:NSE:{symbol}"),
        underlying=UnderlyingIdentity(
            underlying_id=stable("underlying:" + symbol),
            source=SourceReference(namespace="twf-product", native_id=symbol, revision="1"),
            mapping=RevisionRef(id="product-symbol-mapping", version="2"),
        ),
        native=SourceReference(namespace="NSE", native_id="NSE:" + symbol, revision="1"),
        symbol=symbol,
        exchange="NSE",
        segment=segment,
    )


def intent(
    owner_id: UUID, choice: IntentChoice, horizon: HorizonChoice, at: datetime
) -> DiscoveryIntent:
    short = choice in {IntentChoice.INTRADAY_SHORT, IntentChoice.POSITIONAL_SHORT}
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "SHORT" if short else "LONG"
    objective = {
        IntentChoice.BREAKOUT: "breakout",
        IntentChoice.MOMENTUM: "momentum",
        IntentChoice.PULLBACK: "pullback",
    }.get(choice, "attention")
    return DiscoveryIntent(
        intent_id=stable(f"intent:{owner_id}:{choice}:{horizon}"),
        owner_id=owner_id,
        revision=1,
        created_at=at,
        direction=direction,
        objective=objective,
        setup_family=choice.value.lower(),
        horizon=HorizonSpec(
            preset=horizon.value,
            basis=HorizonBasis.ELAPSED,
            minimum=horizon_seconds(horizon),
            maximum=horizon_seconds(horizon),
            unit="seconds",
            cadence_seconds=300 if horizon == HorizonChoice.INTRADAY else 86400,
        ),
    )


def provenance(
    producer: ProducerIdentity, instrument: InstrumentIdentity, at: datetime, key: str
) -> Provenance:
    return Provenance(
        producer=producer,
        source=instrument.native,
        mode=SourceMode.SYNTHETIC,
        observation_key=stable(key + at.isoformat()).hex,
        transformation=TRANSFORMATION,
        dependence_group=producer.service_id,
    )


def market_series(
    instrument: InstrumentIdentity, at: datetime, progression: int = 0
) -> MarketSeries:
    fixture = synthetic_fixture(instrument.symbol, progression)
    seed = sum(ord(char) for char in instrument.symbol)
    bars: list[Bar] = []
    baseline_volume = Decimal(900 + seed % 700)
    for index in range(260):
        cycle = Decimal(((index + seed) % 7) - 3) * fixture.cycle_amplitude
        close_value = fixture.base_price + fixture.daily_trend * index + cycle
        if index == 259 and fixture.final_move is not None:
            close_value = Decimal(str(bars[-1].close)) + fixture.final_move
        close = float(close_value.quantize(Decimal("0.01")))
        volume = float(baseline_volume)
        if index == 259:
            volume = float((baseline_volume * fixture.relative_volume).quantize(Decimal("0.01")))
        timestamp = at - timedelta(days=259 - index)
        bars.append(
            Bar(
                timestamp=timestamp,
                available_at=timestamp,
                open=close - 0.12,
                high=close + 0.35,
                low=close - 0.35,
                close=close,
                volume=volume,
            )
        )
    return MarketSeries(
        instrument=instrument,
        interval="1d",
        price_unit="INR",
        adjustment=RevisionRef(id="synthetic-unadjusted", version="1"),
        session_basis=RevisionRef(id="nse-validation-calendar", version="1"),
        provenance=provenance(INTERNAL_IDENTITY, instrument, at, "series:" + instrument.symbol),
        bars=tuple(bars),
    )


class ScanDiscoverService:
    def __init__(
        self,
        session: Session,
        owner_id: UUID,
        request_id: str | None,
        real_evidence: TradingViewEvidenceGateway | None = None,
    ) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id or uuid4().hex
        self.real_evidence = real_evidence

    def settings(self) -> DiscoverySettings:
        row = self.session.get(DiscoverySettingsRecord, self.owner_id)
        if row is None:
            return DiscoverySettings(revision=0)
        return DiscoverySettings.model_validate({"revision": row.revision, **row.values})

    def save_settings(self, value: DiscoverySettings) -> DiscoverySettings:
        self.session.rollback()
        payload = value.model_dump(mode="json", exclude={"revision"})
        current = self.session.get(DiscoverySettingsRecord, self.owner_id)
        self.session.rollback()
        if current is None:
            if value.revision != 0:
                raise ProductFailure(409, "REVISION_CONFLICT")
            self.session.add(
                DiscoverySettingsRecord(
                    user_id=self.owner_id,
                    revision=1,
                    values=payload,
                    updated_at=now_utc(),
                )
            )
        else:
            result = self.session.execute(
                update(DiscoverySettingsRecord)
                .where(
                    DiscoverySettingsRecord.user_id == self.owner_id,
                    DiscoverySettingsRecord.revision == value.revision,
                )
                .values(revision=value.revision + 1, values=payload, updated_at=now_utc())
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                self.session.rollback()
                raise ProductFailure(409, "REVISION_CONFLICT")
        self.commit()
        return self.settings()

    def fixture_progression(self, provider: ProviderChoice) -> int:
        count = self.session.scalar(
            select(func.count())
            .select_from(ScanRunRecord)
            .where(
                ScanRunRecord.user_id == self.owner_id,
                ScanRunRecord.provider == provider.value,
            )
        )
        return min(int(count or 0), 3)

    def supporting_fixture_evidence(
        self,
        run_id: UUID,
        instrument: InstrumentIdentity,
        at: datetime,
        producer: ProducerIdentity,
        progression: int,
        source_data_time: datetime | None,
    ) -> tuple[DiscoveryEvidence, ...]:
        fixture = synthetic_fixture(instrument.symbol, progression)
        series = market_series(instrument, at, progression)
        closes = series.bars
        close = Decimal(str(closes[-1].close))
        momentum = Decimal(str(series_measure("roc.10", closes))).quantize(Decimal("0.01"))
        rsi = Decimal(str(series_measure("rsi.14", closes))).quantize(Decimal("0.1"))
        relative_volume = Decimal(str(series_measure("relative_volume.20", closes))).quantize(
            Decimal("0.01")
        )
        prov = provenance(producer, instrument, at, "support:" + instrument.symbol)

        def item(
            category: EvidenceCategory,
            key: str,
            measures: tuple[Measure, ...],
        ) -> DiscoveryEvidence:
            return DiscoveryEvidence(
                evidence_id=stable(f"support:{run_id}:{instrument.instrument_id}:{key}"),
                owner_id=self.owner_id,
                subject_id=instrument.instrument_id,
                category=category,
                polarity=fixture_polarity(fixture),
                observation_basis="deterministic-daily-fixture",
                observed_at=at,
                source_data_time=source_data_time,
                received_at=at,
                available_at=at,
                provenance=prov,
                measures=measures,
                reason="deterministic-synthetic-validation-evidence",
            )

        evidence = [
            item(
                EvidenceCategory.INSTRUMENT_PRICE,
                "price",
                (
                    Measure(name="close", value=close, unit="INR"),
                    Measure(name="momentum.10", value=momentum, unit="percent"),
                ),
            ),
            item(
                EvidenceCategory.VOLUME_LIQUIDITY,
                "volume",
                (Measure(name="relative_volume.20", value=relative_volume, unit="ratio"),),
            ),
        ]
        if fixture.technical_evidence:
            evidence.append(
                item(
                    EvidenceCategory.TECHNICAL,
                    "technical",
                    (
                        Measure(name="rsi.14", value=rsi, unit="index"),
                        Measure(name="momentum.10", value=momentum, unit="percent"),
                    ),
                )
            )
        return tuple(evidence)

    def with_supporting_fixture_evidence(
        self,
        match: ScanMatch,
        at: datetime,
        progression: int,
        source_data_time: datetime | None,
    ) -> ScanMatch:
        supporting = self.supporting_fixture_evidence(
            match.run_id,
            match.instrument,
            at,
            match.provenance.producer,
            progression,
            source_data_time,
        )
        return match.model_copy(update={"evidence": (*match.evidence, *supporting)})

    def providers(self) -> tuple[ProviderStatus, ...]:
        last = {
            row.provider: row
            for row in self.session.scalars(
                select(ScanRunRecord)
                .where(ScanRunRecord.user_id == self.owner_id)
                .order_by(ScanRunRecord.completed_at.asc())
            )
        }
        internal = last.get(ProviderChoice.INTERNAL.value)
        tradingview = last.get(ProviderChoice.TRADINGVIEW_SYNTHETIC.value)
        real = last.get(ProviderChoice.REAL_TRADINGVIEW.value)
        real_enabled, real_health, real_success = (
            self.real_evidence.readiness()
            if self.real_evidence is not None
            else (False, "AUTH_REQUIRED", None)
        )
        return (
            ProviderStatus(
                id=ProviderChoice.INTERNAL,
                label="Internal Scanner V0",
                enabled=True,
                mode="LOCAL_SYNTHETIC",
                health="AVAILABLE",
                role="DISCOVERY",
                capabilities=("deterministic-scan", "five-profiles", "offline-validation"),
                last_success_at=aware(internal.completed_at) if internal else None,
            ),
            ProviderStatus(
                id=ProviderChoice.REAL_TRADINGVIEW,
                label="TradingView market evidence",
                enabled=real_enabled,
                mode="REMOTE",
                health=cast(Any, real_health),
                role="EVIDENCE",
                capabilities=(
                    "exact-symbol-batch",
                    "ohlcv",
                    "current-evidence-chart",
                    "source-bar-timestamps",
                ),
                limitations=(
                    "broad-screener-unreliable",
                    "bar-finality-unavailable",
                    "realtime-delay-status-unresolved",
                    "retention-rights-unknown",
                ),
                last_success_at=real_success or (aware(real.completed_at) if real else None),
                last_error=None
                if real_enabled
                else "Connect and authorize TradingView to use real evidence.",
            ),
            ProviderStatus(
                id=ProviderChoice.TRADINGVIEW_SYNTHETIC,
                label="TradingView exact-batch validation",
                enabled=True,
                mode="SYNTHETIC_VALIDATION",
                health="AVAILABLE",
                role="VALIDATION",
                capabilities=("exact-universe", "synthetic-ci", "provider-lineage"),
                last_success_at=aware(tradingview.completed_at) if tradingview else None,
                last_error=None,
            ),
        )

    @staticmethod
    def effective_context_policy(payload: ProductScanRequest) -> ContextPolicy:
        if payload.context_policy is not None:
            return payload.context_policy
        return ContextPolicy.ALLOW_PARTIAL

    def comparison_descriptor(
        self,
        payload: ProductScanRequest,
        definition: Any,
        at: datetime,
    ) -> ScanComparabilityDescriptor:
        selected_intent = intent(self.owner_id, payload.intent, payload.horizon, at)
        criteria_fingerprint = digest(
            {
                "criteria": [item.model_dump(mode="json") for item in definition.criteria],
                "combination": definition.combination,
                "timeframe": definition.timeframe,
                "required_capabilities": definition.required_capabilities,
            }
        )
        provider_class = {
            ProviderChoice.INTERNAL: "twf-native-synthetic-v1",
            ProviderChoice.REAL_TRADINGVIEW: "internal-discovery-tradingview-real-evidence-v1",
            ProviderChoice.TRADINGVIEW_SYNTHETIC: "tradingview-synthetic-v1",
        }[payload.provider]
        return ScanComparabilityDescriptor(
            criteria_fingerprint=criteria_fingerprint,
            profile_semantic_class=f"{payload.profile.lower()}.v1",
            direction=definition.direction,
            intent=payload.intent.value.lower(),
            horizon=selected_intent.horizon,
            observation_basis=(
                f"{definition.timeframe}.real-evidence-v1"
                if payload.provider == ProviderChoice.REAL_TRADINGVIEW
                else f"{definition.timeframe}.synthetic-unadjusted-v1"
            ),
            provider_equivalence_class=provider_class,
            data_mode=definition.source_mode,
            admission_policy=("context-" + self.effective_context_policy(payload).value.lower()),
            lifecycle_policy=TEMPORAL_POLICY,
        )

    @staticmethod
    def source_sample_key(match: ScanMatch) -> str:
        return digest(
            {
                "instrument": str(match.instrument.instrument_id),
                "basis": sorted(item.observation_basis for item in match.evidence),
                "source_times": sorted(
                    item.source_data_time.isoformat()
                    for item in match.evidence
                    if item.source_data_time is not None
                ),
                "source_keys": sorted(item.provenance.observation_key for item in match.evidence),
            }
        )

    def as_tradingview_match(self, match: ScanMatch, at: datetime) -> ScanMatch:
        """Retain profile predicates while changing only provider provenance/mode."""
        source = provenance(
            TRADINGVIEW_SYNTHETIC,
            match.instrument,
            at,
            "tradingview:" + match.instrument.symbol,
        )
        evidence = tuple(
            item.model_copy(
                update={
                    "evidence_id": stable(f"tv-evidence:{match.run_id}:{item.evidence_id}"),
                    "source_data_time": None,
                    "provenance": source,
                    "reason": item.reason or "synthetic-validation-no-live-provider-call",
                }
            )
            for item in match.evidence
        )
        return match.model_copy(
            update={
                "scan_match_id": stable(
                    f"tv-match:{match.run_id}:{match.instrument.instrument_id}"
                ),
                "evidence": evidence,
                "provenance": source,
            }
        )

    def normalize_real_match(
        self, provisional: ScanMatch, item: SymbolEvidence, definition: Any
    ) -> tuple[ScanMatch, EvidenceVerification]:
        """Replace provisional fixture evidence with provider-native normalized evidence."""
        source_time = item.bars[-1].source_time if item.bars else None
        # TradingView does not expose finality. A following bar proves that the prior
        # interval has ended, so verification conservatively excludes the newest bar.
        verification_source_time = item.bars[-2].source_time if len(item.bars) > 1 else None
        key = digest(
            {
                "run": str(provisional.run_id),
                "instrument": str(provisional.instrument.instrument_id),
                "outcome": item.outcome.value,
                "source_time": source_time.isoformat() if source_time else None,
                "received_at": item.received_at.isoformat(),
            }
        )
        real_provenance = Provenance(
            producer=REAL_TRADINGVIEW,
            source=SourceReference(
                namespace="tradingview",
                native_id=f"{item.instrument.exchange}:{item.instrument.symbol}",
                revision="exact-batch-ohlcv-v1",
            ),
            mode=SourceMode.LIVE_SNAPSHOT,
            observation_key=key,
            transformation=RevisionRef(id="tradingview-real-evidence-normalization", version="1"),
            dependence_group="tradingview-exact-and-ohlcv",
        )
        evidence: list[DiscoveryEvidence] = []
        verification = EvidenceVerification.UNAVAILABLE
        if item.quote is not None:
            quote_measures = [
                Measure(name="close", value=item.quote.close, unit="price"),
                Measure(
                    name="exact-batch-chunk", value=Decimal(item.quote.chunk_index), unit="index"
                ),
            ]
            if item.quote.volume is not None:
                quote_measures.append(
                    Measure(name="volume", value=item.quote.volume, unit="volume")
                )
            evidence.append(
                DiscoveryEvidence(
                    evidence_id=stable(
                        f"real-quote:{provisional.run_id}:{item.instrument.instrument_id}"
                    ),
                    owner_id=self.owner_id,
                    subject_id=item.instrument.instrument_id,
                    category=EvidenceCategory.INSTRUMENT_PRICE,
                    polarity=EvidencePolarity.NEUTRAL,
                    observation_basis="tradingview-exact-batch",
                    observed_at=item.received_at,
                    received_at=item.received_at,
                    source_data_time=None,
                    provenance=real_provenance,
                    measures=tuple(quote_measures),
                    reason="source-timestamp-unavailable",
                )
            )
        if item.outcome == EvidenceOutcome.AVAILABLE and item.bars:
            series = MarketSeries(
                instrument=item.instrument,
                interval=item.interval,
                price_unit="INR",
                adjustment=RevisionRef(id="provider-unspecified", version="1"),
                session_basis=RevisionRef(id="tradingview-provider-calendar", version="1"),
                provenance=real_provenance,
                bars=tuple(
                    Bar(
                        timestamp=bar.source_time,
                        available_at=max(bar.source_time, item.received_at),
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=None if bar.volume is None else float(bar.volume),
                    )
                    for bar in item.bars
                ),
            )
            flags: list[bool] = []
            technical_measures: list[Measure] = []
            try:
                verification_bars = series.bars[:-1]
                for index, criterion in enumerate(definition.criteria):
                    observed = Decimal(str(series_measure(criterion.metric, verification_bars)))
                    matched = series_compare(float(observed), criterion)
                    flags.append(matched)
                    technical_measures.append(
                        Measure(name=criterion.metric, value=observed, unit=criterion.unit)
                    )
                    evidence.append(
                        DiscoveryEvidence(
                            evidence_id=stable(
                                f"real-rule:{provisional.run_id}:{item.instrument.instrument_id}:{index}"
                            ),
                            owner_id=self.owner_id,
                            subject_id=item.instrument.instrument_id,
                            category=EvidenceCategory.PROVIDER_SCAN,
                            polarity=(
                                EvidencePolarity.POSITIVE if matched else EvidencePolarity.NEGATIVE
                            ),
                            observation_basis=f"{item.interval}-provider-unspecified-finality",
                            observed_at=item.received_at,
                            source_data_time=verification_source_time,
                            received_at=item.received_at,
                            provenance=real_provenance,
                            measures=(
                                Measure(name=criterion.metric, value=observed, unit=criterion.unit),
                                Measure(
                                    name="threshold", value=criterion.threshold, unit=criterion.unit
                                ),
                                Measure(
                                    name="operator",
                                    value=criterion.operator.value,
                                    unit="comparison",
                                ),
                                Measure(name="matched", value=matched, unit="boolean"),
                            ),
                            reason="real-ohlcv-recomputed",
                        )
                    )
            except (ValueError, TypeError):
                flags = []
            if flags:
                passed = sum(flags)
                verification = (
                    EvidenceVerification.CONFIRMED
                    if passed == len(flags)
                    else (
                        EvidenceVerification.PARTIALLY_CONFIRMED
                        if passed
                        else EvidenceVerification.CONTRADICTED
                    )
                )
                evidence.append(
                    DiscoveryEvidence(
                        evidence_id=stable(
                            f"real-technical:{provisional.run_id}:{item.instrument.instrument_id}"
                        ),
                        owner_id=self.owner_id,
                        subject_id=item.instrument.instrument_id,
                        category=EvidenceCategory.TECHNICAL,
                        polarity=(
                            EvidencePolarity.POSITIVE
                            if verification == EvidenceVerification.CONFIRMED
                            else EvidencePolarity.NEUTRAL
                        ),
                        observation_basis=f"{item.interval}-real-indicators",
                        observed_at=item.received_at,
                        source_data_time=verification_source_time,
                        received_at=item.received_at,
                        provenance=real_provenance,
                        measures=tuple(technical_measures),
                        reason=f"verification-{verification.value.lower()}",
                    )
                )
                if verification == EvidenceVerification.CONTRADICTED:
                    evidence.append(
                        DiscoveryEvidence(
                            evidence_id=stable(
                                f"real-conflict:{provisional.run_id}:{item.instrument.instrument_id}"
                            ),
                            owner_id=self.owner_id,
                            subject_id=item.instrument.instrument_id,
                            category=EvidenceCategory.CONFLICTING,
                            polarity=EvidencePolarity.NEGATIVE,
                            observation_basis="internal-match-versus-real-ohlcv",
                            observed_at=item.received_at,
                            source_data_time=verification_source_time,
                            received_at=item.received_at,
                            provenance=real_provenance,
                            measures=(
                                Measure(
                                    name="verification",
                                    value=EvidenceVerification.CONTRADICTED.value,
                                    unit="state",
                                ),
                            ),
                            reason="real-evidence-contradicted-provisional-match",
                        )
                    )
            else:
                verification = EvidenceVerification.UNVERIFIED
        elif item.quote is not None:
            verification = EvidenceVerification.UNVERIFIED
        if not evidence:
            evidence.append(
                DiscoveryEvidence(
                    evidence_id=stable(
                        f"real-unavailable:{provisional.run_id}:{item.instrument.instrument_id}"
                    ),
                    owner_id=self.owner_id,
                    subject_id=item.instrument.instrument_id,
                    category=EvidenceCategory.MISSING_UNAVAILABLE,
                    polarity=EvidencePolarity.UNKNOWN,
                    observation_basis="tradingview-real-evidence",
                    observed_at=item.received_at,
                    received_at=item.received_at,
                    provenance=real_provenance,
                    availability="UNAVAILABLE",
                    reason=item.outcome.value.lower().replace("_", "-"),
                )
            )
        return (
            provisional.model_copy(
                update={
                    "scan_match_id": stable(
                        f"real-match:{provisional.run_id}:{item.instrument.instrument_id}"
                    ),
                    "instrument": item.instrument,
                    "evidence": tuple(evidence),
                    "provenance": real_provenance,
                }
            ),
            verification,
        )

    async def run_scan(self, payload: ProductScanRequest) -> ScanResult:
        started = now_utc()
        instruments = tuple(identity(symbol) for symbol in payload.universe)
        context = OperationContext(
            owner_id=self.owner_id,
            correlation=RequestContext(request_id=self.request_id),
            as_of=started,
        )
        proposed_run_id = uuid4()
        profile = ScanProfileReference(
            profile_id=stable(f"profile:{self.owner_id}:{payload.profile}"),
            owner_id=self.owner_id,
            applied_revision=1,
        )
        definition = build_profile(
            payload.profile,
            context,
            stable("definition:" + payload.profile),
            interval="1d",
            direction=intent_direction(payload.intent),
        )
        descriptor = self.comparison_descriptor(payload, definition, started)
        request_payload = payload.model_dump(mode="json", exclude={"idempotency_key"})
        request_digest = digest(request_payload)
        temporal = TemporalStore(self.session, self.owner_id)
        try:
            admission = temporal.admit_run(
                descriptor,
                run_id=proposed_run_id,
                request_key=payload.idempotency_key or self.request_id,
                request_digest=request_digest,
                as_of=started,
                payload={
                    "request": request_payload,
                    "descriptor": descriptor.model_dump(mode="json"),
                },
            )
        except TemporalConflict as exc:
            raise ProductFailure(409, str(exc)) from exc
        if admission.replay:
            cached = temporal.cached_response(admission.run_id)
            if cached is not None:
                return ScanResult.model_validate(cached)
            raise ProductFailure(409, "SCAN_IN_PROGRESS")

        run_id = admission.run_id
        run = ScanRun(
            run_id=run_id,
            owner_id=self.owner_id,
            request_id=self.request_id,
            profile=profile,
            definition=definition,
            as_of=started,
        )
        progression = self.fixture_progression(payload.provider)
        try:
            # Provider I/O begins only after admission was durably committed.
            series = tuple(market_series(item, started, progression) for item in instruments)
            provider_result = await InternalScannerV0(FixtureMarketSeriesSource(series)).scan(
                context, run, instruments
            )
        except BaseException as exc:
            temporal.fail_run(run_id, type(exc).__name__)
            raise
        normalized_matches = tuple(
            self.with_supporting_fixture_evidence(item, started, progression, started)
            for item in provider_result.items
        )
        verification_by_match: dict[UUID, EvidenceVerification] = {}
        enrichment = None
        if payload.provider == ProviderChoice.INTERNAL:
            matches = normalized_matches
        elif payload.provider == ProviderChoice.TRADINGVIEW_SYNTHETIC:
            matches = tuple(
                self.as_tradingview_match(item, started)
                for item in normalized_matches
                if synthetic_fixture(item.instrument.symbol, progression).tradingview_match
            )
        else:
            if self.real_evidence is None:
                real_items = tuple(
                    SymbolEvidence(
                        instrument=item.instrument,
                        outcome=EvidenceOutcome.AUTH_REQUIRED,
                        interval="1d",
                        received_at=now_utc(),
                        limitation="auth-required",
                    )
                    for item in normalized_matches
                )
            else:
                enrichment = await self.real_evidence.enrich(
                    tuple(item.instrument for item in normalized_matches), payload.horizon.value
                )
                real_items = enrichment.symbols
            real_matches: list[ScanMatch] = []
            by_instrument = {item.instrument.instrument_id: item for item in real_items}
            for provisional in normalized_matches:
                real_item = by_instrument[provisional.instrument.instrument_id]
                normalized, verification = self.normalize_real_match(
                    provisional, real_item, definition
                )
                real_matches.append(normalized)
                verification_by_match[normalized.scan_match_id] = verification
            matches = tuple(real_matches)
        context_snapshot, context_evidence = self.market_context(
            started, payload.context_mode, instruments, run_id
        )
        context_policy = self.effective_context_policy(payload)
        completed = now_utc()
        run_record = ScanRunRecord(
            id=run_id,
            user_id=self.owner_id,
            provider=payload.provider.value,
            status="COMPLETE",
            started_at=started,
            completed_at=completed,
            match_count=len(matches),
            candidate_count=0,
            payload={},
        )
        self.session.add(run_record)
        self.session.flush()
        candidates: list[CandidateSummary] = []
        decisions: list[MatchAdmissionDecision] = []
        match_instruments: set[UUID] = set()
        for match in matches:
            match_instruments.add(match.instrument.instrument_id)
            self.session.add(
                ScanMatchRecord(
                    id=match.scan_match_id,
                    user_id=self.owner_id,
                    run_id=run_id,
                    instrument_id=match.instrument.instrument_id,
                    payload=match.model_dump(mode="json"),
                )
            )
            self.session.flush()
            matched_series = next(
                item
                for item in series
                if item.instrument.instrument_id == match.instrument.instrument_id
            )
            chart_payload = archive_payload(matched_series, definition)
            if payload.provider == ProviderChoice.REAL_TRADINGVIEW:
                chart_payload = {
                    "schema_version": 2,
                    "definition": definition.model_dump(mode="json"),
                    "verification": verification_by_match[match.scan_match_id].value,
                    "retention": {
                        "source_class": "PROVIDER_RESTRICTED",
                        "historical_chart_reconstructable": False,
                        "scan_bars_retained": False,
                        "current_chart_available": True,
                        "limitation": (
                            "TradingView retention rights are unknown. TWF retains normalized "
                            "numerical evidence and source timestamps, not provider OHLCV bars."
                        ),
                    },
                    "provider_lineage": {
                        "connection_id": str(enrichment.connection_id) if enrichment else None,
                        "generation": enrichment.generation if enrichment else None,
                        "requested_symbols": list(enrichment.requested_symbols)
                        if enrichment
                        else [],
                        "returned_symbols": list(enrichment.returned_symbols) if enrichment else [],
                        "missing_symbols": list(enrichment.missing_symbols) if enrichment else [],
                        "chunk_count": enrichment.chunk_count if enrichment else 0,
                    },
                }
            self.session.add(
                ScanEvidenceSeriesRecord(
                    match_id=match.scan_match_id,
                    user_id=self.owner_id,
                    run_id=run_id,
                    instrument_id=match.instrument.instrument_id,
                    captured_at=started,
                    payload=chart_payload,
                )
            )
            extra = tuple(
                item
                for item in context_evidence
                if item.subject_id == match.instrument.instrument_id
            )
            reason = AdmissionReason.ADMITTED
            match_verification = verification_by_match.get(match.scan_match_id)
            if match_verification == EvidenceVerification.CONTRADICTED:
                reason = AdmissionReason.EXCLUDED_CONTRADICTED
            elif match_verification in {
                EvidenceVerification.UNVERIFIED,
                EvidenceVerification.UNAVAILABLE,
            }:
                reason = AdmissionReason.EXCLUDED_UNVERIFIED
            elif (
                context_policy == ContextPolicy.REQUIRE_COMPLETE
                and context_snapshot.availability != ContextAvailability.COMPLETE
            ):
                reason = AdmissionReason.EXCLUDED_CONTEXT_POLICY
            elif not self.match_supports_intent(match, payload.intent):
                reason = AdmissionReason.EXCLUDED_DIRECTION
            admitted = reason == AdmissionReason.ADMITTED
            decisions.append(
                MatchAdmissionDecision(
                    match_id=match.scan_match_id,
                    symbol=match.instrument.symbol,
                    status="ADMITTED" if admitted else "EXCLUDED",
                    reason=reason,
                )
            )
            if admitted:
                candidates.append(
                    self.capture_candidate(
                        match,
                        payload.intent,
                        payload.horizon,
                        payload.profile,
                        (*match.evidence, *extra),
                        completed,
                        context_snapshot,
                        context_policy,
                        payload.include_llm,
                        admission,
                    )
                )
            else:
                source_times = tuple(
                    item.source_data_time
                    for item in match.evidence
                    if item.source_data_time is not None
                )
                provider_unavailable = reason == AdmissionReason.EXCLUDED_UNVERIFIED
                temporal.append_observation(
                    admission=admission,
                    instrument=match.instrument,
                    kind=(
                        DiscoveryObservationKind.NOT_EVALUATED
                        if provider_unavailable
                        else DiscoveryObservationKind.PRESENT
                    ),
                    coverage=(
                        EvaluationCoverage.PROVIDER_UNAVAILABLE
                        if provider_unavailable
                        else EvaluationCoverage.EVALUATED
                    ),
                    reason=(
                        "real-provider-not-evaluated"
                        if provider_unavailable
                        else "matched-not-admitted"
                    ),
                    observed_at=max(item.observed_at for item in match.evidence),
                    source_data_time=min(source_times) if source_times else None,
                    source_sample_key=self.source_sample_key(match),
                    episode=None,
                    scan_match_id=None if provider_unavailable else match.scan_match_id,
                    evidence_ids=tuple(item.evidence_id for item in match.evidence),
                    context_id=context_snapshot.context_id,
                    provider=match.provenance.producer.provider,
                )

        for instrument_item in instruments:
            if instrument_item.instrument_id in match_instruments:
                continue
            episode = temporal.episode_for_observation(
                admission.scope_id, instrument_item.instrument_id, admission.sequence
            )
            if episode is not None:
                self.close_elapsed_episode(episode, admission, started)
            temporal.append_observation(
                admission=admission,
                instrument=instrument_item,
                kind=DiscoveryObservationKind.ABSENT,
                coverage=EvaluationCoverage.EVALUATED,
                reason="not-rediscovered",
                observed_at=started,
                source_data_time=started,
                source_sample_key=digest(
                    {
                        "instrument": str(instrument_item.instrument_id),
                        "cutoff": started.isoformat(),
                        "scope": str(admission.scope_id),
                    }
                ),
                episode=episode,
                context_id=context_snapshot.context_id,
                provider=(
                    "twf-native" if payload.provider == ProviderChoice.INTERNAL else "tradingview"
                ),
            )

        evaluated_ids = {item.instrument_id for item in instruments}
        active_slots = tuple(
            self.session.scalars(
                select(DiscoveryActiveSlotRecord).where(
                    DiscoveryActiveSlotRecord.user_id == self.owner_id,
                    DiscoveryActiveSlotRecord.scope_id == admission.scope_id,
                )
            )
        )
        for slot in active_slots:
            if slot.instrument_id in evaluated_ids:
                continue
            excluded_episode = self.session.get(DiscoveryEpisodeRecord, slot.episode_id)
            if excluded_episode is None or excluded_episode.user_id != self.owner_id:
                continue
            excluded_instrument = InstrumentIdentity.model_validate(
                excluded_episode.payload["episode"]["instrument"]
            )
            self.close_elapsed_episode(excluded_episode, admission, started)
            temporal.append_observation(
                admission=admission,
                instrument=excluded_instrument,
                kind=DiscoveryObservationKind.NOT_EVALUATED,
                coverage=EvaluationCoverage.NOT_REQUESTED,
                reason="instrument-outside-run-universe",
                observed_at=started,
                source_data_time=None,
                source_sample_key=None,
                episode=excluded_episode,
                context_id=context_snapshot.context_id,
                provider=(
                    "twf-native" if payload.provider == ProviderChoice.INTERNAL else "tradingview"
                ),
            )

        admission_summary = AdmissionSummary(
            match_count=len(matches),
            admitted_count=len(candidates),
            excluded_count=len(matches) - len(candidates),
            decisions=tuple(decisions),
        )
        evidence_lineage = None
        if payload.provider == ProviderChoice.REAL_TRADINGVIEW:
            outcomes = {item.outcome for item in real_items}
            capability_state = (
                "AVAILABLE"
                if outcomes == {EvidenceOutcome.AVAILABLE}
                else (
                    "PARTIAL"
                    if EvidenceOutcome.AVAILABLE in outcomes
                    else (next(iter(outcomes)).value if len(outcomes) == 1 else "UNAVAILABLE")
                )
            )
            requested_symbols = tuple(
                f"{item.instrument.exchange}:{item.instrument.symbol}"
                for item in normalized_matches
            )
            evidence_lineage = RealEvidenceLineage(
                connection_id=enrichment.connection_id if enrichment else None,
                generation=enrichment.generation if enrichment else None,
                requested_symbols=(
                    enrichment.requested_symbols if enrichment else requested_symbols
                ),
                returned_symbols=enrichment.returned_symbols if enrichment else (),
                missing_symbols=enrichment.missing_symbols if enrichment else requested_symbols,
                chunk_count=enrichment.chunk_count if enrichment else 0,
                received_at=enrichment.received_at if enrichment else completed,
                capability_state=capability_state.lower().replace("_", "-"),
                limitations=(
                    "bar-finality-unavailable",
                    "realtime-delay-status-unresolved",
                    "retention-rights-unknown",
                    "broad-screener-not-used",
                ),
            )

        summary = ScanSummary(
            run_id=run_id,
            provider=payload.provider,
            status="COMPLETE",
            started_at=started,
            completed_at=completed,
            profile=payload.profile,
            horizon=payload.horizon,
            intent=payload.intent,
            universe_size=len(instruments),
            universe=payload.universe,
            match_count=len(matches),
            candidate_count=len(candidates),
            context_mode=payload.context_mode,
            context_policy=context_policy,
            context_availability=context_snapshot.availability,
            evidence_lineage=evidence_lineage,
            degraded=tuple(
                dict.fromkeys(
                    (
                        *context_snapshot.limitations,
                        *(
                            (
                                "tradingview-bar-finality-unavailable",
                                "tradingview-realtime-delay-status-unresolved",
                                "tradingview-retention-rights-unknown",
                                "tradingview-broad-screener-not-used",
                            )
                            if payload.provider == ProviderChoice.REAL_TRADINGVIEW
                            else ()
                        ),
                    )
                )
            ),
        )
        run_record.candidate_count = len(candidates)
        run_record.payload = summary.model_dump(mode="json")
        self.session.add(
            MarketContextRecord(
                id=context_snapshot.context_id,
                user_id=self.owner_id,
                run_id=run_id,
                observed_at=started,
                payload=context_snapshot.model_dump(mode="json"),
            )
        )
        temporal.seal_run(
            admission,
            {
                "summary": summary.model_dump(mode="json"),
                "evaluated": [str(item.instrument_id) for item in instruments],
                "present": [
                    str(item.instrument.instrument_id)
                    for item in matches
                    if verification_by_match.get(item.scan_match_id)
                    not in {EvidenceVerification.UNVERIFIED, EvidenceVerification.UNAVAILABLE}
                ],
                "not_evaluated": [
                    *(
                        str(item.instrument.instrument_id)
                        for item in matches
                        if verification_by_match.get(item.scan_match_id)
                        in {EvidenceVerification.UNVERIFIED, EvidenceVerification.UNAVAILABLE}
                    ),
                    *(
                        str(slot.instrument_id)
                        for slot in active_slots
                        if slot.instrument_id not in evaluated_ids
                    ),
                ],
            },
        )
        temporal.finalize_run(admission)
        response = ScanResult(
            summary=summary,
            matches=tuple(self.match_view(item) for item in matches),
            candidates=tuple(candidates),
            market_context=context_snapshot,
            admission=admission_summary,
        )
        temporal.store_response(run_id, response.model_dump(mode="json"))
        try:
            self.commit()
        except ProductFailure:
            temporal.fail_run(run_id, "FINALIZATION_CONFLICT")
            raise
        return response

    @staticmethod
    def match_supports_intent(match: ScanMatch, choice: IntentChoice) -> bool:
        expected = (
            EvidencePolarity.NEGATIVE
            if intent_direction(choice) == "SHORT"
            else EvidencePolarity.POSITIVE
        )
        return any(
            item.availability == "PRESENT"
            and item.category == EvidenceCategory.PROVIDER_SCAN
            and item.polarity == expected
            for item in match.evidence
        )

    def market_context(
        self,
        at: datetime,
        mode: str,
        instruments: tuple[InstrumentIdentity, ...],
        run_id: UUID,
    ) -> tuple[MarketContextSnapshot, tuple[DiscoveryEvidence, ...]]:
        availability = {
            "healthy": ContextAvailability.COMPLETE,
            "partial": ContextAvailability.PARTIAL,
            "unavailable": ContextAvailability.UNAVAILABLE,
            "stale": ContextAvailability.STALE,
        }[mode]
        source_time = (
            at
            if mode in {"healthy", "partial"}
            else (at - timedelta(days=2) if mode == "stale" else None)
        )
        present = mode not in {"unavailable"}
        dimensions = [
            ContextDimension(
                name="broad-regime",
                availability="STALE"
                if mode == "stale"
                else ("PRESENT" if present else "UNAVAILABLE"),
                value="constructive" if present and mode != "stale" else None,
                source="internal-context-v1",
                reason="context-stale"
                if mode == "stale"
                else ("source-unavailable" if not present else None),
            ),
            ContextDimension(
                name="nifty-direction",
                availability="PRESENT"
                if present and mode != "stale"
                else ("STALE" if mode == "stale" else "UNAVAILABLE"),
                value="positive" if present and mode != "stale" else None,
                source="internal-context-v1",
                reason="context-stale"
                if mode == "stale"
                else ("source-unavailable" if not present else None),
            ),
            ContextDimension(
                name="banknifty-direction",
                availability="PRESENT" if mode == "healthy" else "MISSING",
                value="neutral" if mode == "healthy" else None,
                source="internal-context-v1",
                reason=None if mode == "healthy" else "benchmark-unavailable",
            ),
            ContextDimension(
                name="breadth",
                availability="PRESENT"
                if present and mode != "stale"
                else ("STALE" if mode == "stale" else "UNAVAILABLE"),
                value=Decimal("0.64") if present and mode != "stale" else None,
                source="internal-context-v1",
                reason="context-stale"
                if mode == "stale"
                else ("source-unavailable" if not present else None),
            ),
            ContextDimension(
                name="volatility",
                availability="PRESENT"
                if present and mode != "stale"
                else ("STALE" if mode == "stale" else "UNAVAILABLE"),
                value="normal" if present and mode != "stale" else None,
                source="internal-context-v1",
                reason="context-stale"
                if mode == "stale"
                else ("source-unavailable" if not present else None),
            ),
            ContextDimension(
                name="sector-strength",
                availability="MISSING" if mode != "healthy" else "PRESENT",
                value="mixed" if mode == "healthy" else None,
                source="internal-context-v1",
                reason=None if mode == "healthy" else "sector-source-unavailable",
            ),
        ]
        limitations = () if mode == "healthy" else (f"market-context-{mode}",)
        evidence: list[DiscoveryEvidence] = []
        producer = ProducerIdentity(
            service_id="internal-market-context-v1",
            provider="twf-native",
            service_version="1",
            contract_version="sd.market-context.v1",
        )
        for instrument in instruments:
            prov = provenance(producer, instrument, at, "context:" + instrument.symbol)
            if present and mode != "stale":
                evidence.append(
                    DiscoveryEvidence(
                        evidence_id=stable(f"context:{run_id}:{instrument.instrument_id}"),
                        owner_id=self.owner_id,
                        subject_id=instrument.instrument_id,
                        category=EvidenceCategory.MARKET_CONTEXT,
                        polarity=EvidencePolarity.POSITIVE,
                        observation_basis="india-market-session",
                        observed_at=at,
                        source_data_time=source_time,
                        received_at=at,
                        available_at=at,
                        provenance=prov,
                        measures=(
                            Measure(name="breadth", value=Decimal("0.64"), unit="ratio"),
                            Measure(name="regime", value="constructive", unit="category"),
                        ),
                    )
                )
            else:
                evidence.append(
                    DiscoveryEvidence(
                        evidence_id=stable(f"context:{run_id}:{instrument.instrument_id}"),
                        owner_id=self.owner_id,
                        subject_id=instrument.instrument_id,
                        category=EvidenceCategory.MISSING_UNAVAILABLE,
                        polarity=EvidencePolarity.UNKNOWN,
                        observation_basis="india-market-session",
                        observed_at=source_time or at,
                        source_data_time=source_time,
                        received_at=at,
                        provenance=prov,
                        availability="UNAVAILABLE" if mode == "unavailable" else "MISSING",
                        reason="market-context-unavailable"
                        if mode == "unavailable"
                        else "market-context-stale",
                    )
                )
        snapshot = MarketContextSnapshot(
            context_id=stable(f"context-snapshot:{run_id}"),
            owner_id=self.owner_id,
            observed_at=at,
            source_data_time=source_time,
            market="india-equities",
            session="OPEN",
            availability=availability,
            dimensions=tuple(dimensions),
            producer="internal-market-context-v1",
            producer_version="1",
            evidence_ids=tuple(item.evidence_id for item in evidence),
            limitations=limitations,
        )
        return snapshot, tuple(evidence)

    def relevance(
        self,
        evidence: tuple[DiscoveryEvidence, ...],
        horizon: HorizonChoice,
        settings: DiscoverySettings,
        context: MarketContextSnapshot,
        context_policy: ContextPolicy,
    ) -> tuple[DiscoveryRelevance, RelevanceExplanation]:
        categories = {item.category for item in evidence if item.availability == "PRESENT"}
        context_quality = {
            ContextAvailability.COMPLETE: Decimal(1),
            ContextAvailability.PARTIAL: Decimal("0.50"),
            ContextAvailability.STALE: Decimal(0),
            ContextAvailability.UNAVAILABLE: Decimal(0),
        }[context.availability]
        provider_items = tuple(
            item
            for item in evidence
            if item.category == EvidenceCategory.PROVIDER_SCAN and item.availability == "PRESENT"
        )
        provider_quality = self.provider_evidence_quality(provider_items)
        factors: tuple[tuple[str, EvidenceCategory, Decimal, Decimal | None], ...]
        if context_policy == ContextPolicy.OPTIONAL:
            factors = (
                (
                    "provider-scan",
                    EvidenceCategory.PROVIDER_SCAN,
                    Decimal("0.5625"),
                    provider_quality,
                ),
                ("price", EvidenceCategory.INSTRUMENT_PRICE, Decimal("0.25"), None),
                ("technical", EvidenceCategory.TECHNICAL, Decimal("0.1875"), None),
            )
        else:
            factors = (
                (
                    "provider-scan",
                    EvidenceCategory.PROVIDER_SCAN,
                    Decimal("0.45"),
                    provider_quality,
                ),
                ("price", EvidenceCategory.INSTRUMENT_PRICE, Decimal("0.20"), None),
                (
                    "market-context",
                    EvidenceCategory.MARKET_CONTEXT,
                    Decimal("0.20"),
                    context_quality,
                ),
                ("technical", EvidenceCategory.TECHNICAL, Decimal("0.15"), None),
            )
        contributions: list[RelevanceContribution] = []
        missing: list[str] = []
        score = Decimal(0)
        factor_values: list[Decimal] = []
        for name, category, weight, measured_value in factors:
            value = (
                measured_value
                if measured_value is not None
                else (Decimal(1) if category in categories else Decimal(0))
            )
            factor_values.append(value)
            contribution = value * weight
            score += contribution
            if value == 0:
                missing.append(name)
            contributions.append(
                RelevanceContribution(
                    factor=name,
                    value=value,
                    weight=weight,
                    contribution=contribution,
                    reason=(
                        "Partial evidence available"
                        if 0 < value < 1
                        else ("Evidence present" if value else "Evidence unavailable")
                    ),
                )
            )
        stale = any(
            item.source_data_time is None
            for item in evidence
            if item.category != EvidenceCategory.MARKET_CONTEXT
            and not (
                context_policy == ContextPolicy.OPTIONAL
                and item.reason in {"market-context-unavailable", "market-context-stale"}
            )
        )
        freshness_penalty = Decimal("0.05") if stale else Decimal(0)
        horizon_adjustment = (
            Decimal("0.03")
            if horizon in {HorizonChoice.FIVE_DAYS, HorizonChoice.FIFTEEN_DAYS}
            and (context_quality > 0 or context_policy == ContextPolicy.OPTIONAL)
            else Decimal(0)
        )
        score = max(
            Decimal(0),
            min(Decimal(1), score - freshness_penalty + horizon_adjustment),
        )
        conflicts = tuple(
            "Real TradingView evidence contradicted the provisional internal match."
            for item in evidence
            if item.category == EvidenceCategory.CONFLICTING
        )
        if conflicts:
            score = min(score, settings.low_max)
        coverage = sum(factor_values, Decimal(0)) / Decimal(len(factors))
        thresholds = RelevanceThresholds(low_max=settings.low_max, medium_max=settings.medium_max)
        relevance = DiscoveryRelevance(
            value=score,
            policy=POLICY,
            thresholds=thresholds,
            required_inputs_satisfied=EvidenceCategory.PROVIDER_SCAN in categories,
            coverage=coverage,
            reasons=tuple(item.factor for item in contributions if item.value),
        )
        explanation = RelevanceExplanation(
            score=score,
            band=relevance.band,
            coverage=coverage,
            contributions=tuple(contributions),
            conflicts=conflicts,
            missing=tuple(missing),
            freshness_penalty=freshness_penalty,
            horizon_adjustment=horizon_adjustment,
        )
        return relevance, explanation

    @staticmethod
    def provider_evidence_quality(evidence: tuple[DiscoveryEvidence, ...]) -> Decimal:
        """Measure matched-predicate strength without inventing missing evidence."""
        if not evidence:
            return Decimal(0)
        strengths: list[Decimal] = []
        for item in evidence:
            measures = {measure.name: measure.value for measure in item.measures}
            metric = next(
                (
                    measure.value
                    for measure in item.measures
                    if measure.name not in {"threshold", "operator", "matched", "price-unit"}
                ),
                None,
            )
            threshold = measures.get("threshold")
            operator = str(measures.get("operator", ""))
            try:
                observed = Decimal(str(metric))
                boundary = Decimal(str(threshold))
            except (InvalidOperation, TypeError, ValueError):
                strengths.append(Decimal(1))
                continue
            if operator in {"EQ", "NE"}:
                strengths.append(Decimal(1))
                continue
            scale = max(abs(boundary), abs(observed), Decimal(1))
            margin = observed - boundary if operator in {"GT", "GTE"} else boundary - observed
            normalized = max(Decimal(0), min(Decimal(1), margin / scale))
            strengths.append(Decimal("0.75") + Decimal("0.25") * normalized)
        return sum(strengths, Decimal(0)) / Decimal(len(strengths))

    def tolerance(
        self,
        evidence: tuple[DiscoveryEvidence, ...],
        horizon: HorizonChoice,
        context: MarketContextSnapshot,
        window: OpportunityWindow,
        at: datetime,
    ) -> ToleranceAssessment:
        volume_floor = {
            HorizonChoice.INTRADAY: Decimal("1.20"),
            HorizonChoice.ONE_DAY: Decimal("1.10"),
            HorizonChoice.FIVE_DAYS: Decimal("1.00"),
            HorizonChoice.FIFTEEN_DAYS: Decimal("0.90"),
        }[horizon]
        breadth_floor = {
            HorizonChoice.INTRADAY: Decimal("0.55"),
            HorizonChoice.ONE_DAY: Decimal("0.50"),
            HorizonChoice.FIVE_DAYS: Decimal("0.45"),
            HorizonChoice.FIFTEEN_DAYS: Decimal("0.40"),
        }[horizon]
        time_floor = Decimal("0.25")
        envelope = CandidateToleranceEnvelope(
            policy=RevisionRef(id="candidate-tolerance-v1", version="1"),
            rules=(
                ToleranceRule(
                    dimension="price",
                    criterion=Criterion(
                        metric="close",
                        operator=Comparison.GT,
                        threshold=Decimal(0),
                        unit="price-unit",
                    ),
                    reference_basis="latest-provider-observation",
                    required_categories=(EvidenceCategory.INSTRUMENT_PRICE,),
                    confirmation_observations=2,
                    recovery_rule=POLICY,
                ),
                ToleranceRule(
                    dimension="volume",
                    criterion=Criterion(
                        metric="relative_volume",
                        operator=Comparison.GTE,
                        threshold=volume_floor,
                        unit="ratio",
                    ),
                    reference_basis=f"{horizon.value}-horizon",
                    required_categories=(
                        EvidenceCategory.VOLUME_LIQUIDITY,
                        EvidenceCategory.PROVIDER_SCAN,
                    ),
                    confirmation_observations=2,
                    recovery_rule=POLICY,
                ),
                ToleranceRule(
                    dimension="market",
                    criterion=Criterion(
                        metric="breadth",
                        operator=Comparison.GTE,
                        threshold=breadth_floor,
                        unit="ratio",
                    ),
                    reference_basis=f"{horizon.value}-context",
                    required_categories=(EvidenceCategory.MARKET_CONTEXT,),
                    confirmation_observations=2,
                    recovery_rule=POLICY,
                ),
                ToleranceRule(
                    dimension="sector",
                    criterion=Criterion(
                        metric="sector_context_available",
                        operator=Comparison.EQ,
                        threshold=Decimal(1),
                        unit="availability-flag",
                    ),
                    reference_basis="current-sector-context",
                    required_categories=(EvidenceCategory.SECTOR_INDUSTRY,),
                    confirmation_observations=2,
                    recovery_rule=POLICY,
                ),
                ToleranceRule(
                    dimension="time_decay",
                    criterion=Criterion(
                        metric="window_remaining",
                        operator=Comparison.GTE,
                        threshold=time_floor,
                        unit="ratio",
                    ),
                    reference_basis=f"{horizon.value}-opportunity-window",
                    required_categories=(EvidenceCategory.PROVIDER_SCAN,),
                    confirmation_observations=1,
                    recovery_rule=POLICY,
                ),
            ),
        )

        numeric: dict[str, Decimal] = {}
        for item in evidence:
            for measure in item.measures:
                if isinstance(measure.value, bool) or not isinstance(
                    measure.value, (int, float, Decimal)
                ):
                    continue
                numeric[measure.name] = Decimal(str(measure.value))
        close = next((value for name, value in numeric.items() if name.endswith("close")), None)
        relative_volume = next(
            (value for name, value in numeric.items() if "relative_volume" in name), None
        )
        breadth_dimension = next(
            (item for item in context.dimensions if item.name == "breadth"), None
        )
        breadth = (
            Decimal(str(breadth_dimension.value))
            if breadth_dimension is not None
            and isinstance(breadth_dimension.value, (int, float, Decimal))
            and not isinstance(breadth_dimension.value, bool)
            else None
        )
        sector_dimension = next(
            (item for item in context.dimensions if item.name == "sector-strength"), None
        )
        duration = (window.ends_at - window.starts_at).total_seconds()
        remaining = Decimal(str(max(0.0, (window.ends_at - at).total_seconds()) / duration))

        dimensions = (
            ToleranceDimensionAssessment(
                dimension="price",
                status="UNKNOWN" if close is None else ("WITHIN" if close > 0 else "BREACHED"),
                observed=close,
                threshold=Decimal(0),
                reason="Current price is positive."
                if close is not None and close > 0
                else "Current price evidence is unavailable.",
            ),
            ToleranceDimensionAssessment(
                dimension="volume",
                status="UNKNOWN"
                if relative_volume is None
                else ("WITHIN" if relative_volume >= volume_floor else "BREACHED"),
                observed=relative_volume,
                threshold=volume_floor,
                reason=(
                    f"Relative volume is evaluated against the {horizon.value} floor."
                    if relative_volume is not None
                    else "Relative-volume evidence is unavailable."
                ),
            ),
            ToleranceDimensionAssessment(
                dimension="market",
                status="UNKNOWN"
                if breadth is None
                else ("WITHIN" if breadth >= breadth_floor else "DEGRADED"),
                observed=breadth,
                threshold=breadth_floor,
                reason=(
                    f"Breadth is evaluated against the {horizon.value} context floor."
                    if breadth is not None
                    else "Market breadth is missing, stale, or unavailable."
                ),
            ),
            ToleranceDimensionAssessment(
                dimension="sector",
                status="WITHIN"
                if sector_dimension is not None and sector_dimension.availability == "PRESENT"
                else "UNKNOWN",
                observed=None,
                threshold=None,
                reason="Sector context is present."
                if sector_dimension is not None and sector_dimension.availability == "PRESENT"
                else "Sector context is unavailable and is not inferred.",
            ),
            ToleranceDimensionAssessment(
                dimension="time_decay",
                status="WITHIN"
                if remaining >= time_floor
                else ("DEGRADED" if remaining > 0 else "BREACHED"),
                observed=remaining,
                threshold=time_floor,
                reason=(
                    f"Remaining time is evaluated within the {horizon.value} opportunity window."
                ),
            ),
        )
        statuses = {item.status for item in dimensions}
        state: Literal["WITHIN", "DEGRADED", "BREACHED", "UNKNOWN"]
        if sum(item.status == "BREACHED" for item in dimensions) >= 2:
            state = "BREACHED"
        elif "BREACHED" in statuses or "DEGRADED" in statuses:
            state = "DEGRADED"
        elif "WITHIN" in statuses:
            state = "WITHIN"
        else:
            state = "UNKNOWN"
        return ToleranceAssessment(
            envelope=envelope, horizon=horizon, state=state, dimensions=dimensions
        )

    def close_elapsed_episode(
        self,
        episode: DiscoveryEpisodeRecord,
        admission: RunAdmission,
        at: datetime,
    ) -> bool:
        stored = dict(episode.payload["episode"])
        if at < datetime.fromisoformat(str(stored["window"]["ends_at"])):
            return False
        old_state = episode.state
        episode.state = DiscoveryLifecycleState.EXPIRED.value
        episode.revision += 1
        episode.updated_at = at
        stored.update({"lifecycle": episode.state, "revision": episode.revision})
        episode.payload = {
            **episode.payload,
            "episode": stored,
            "lifecycle_reason": "window-closed-by-explicit-scan",
        }
        self.session.add(
            DiscoveryTransitionRecord(
                episode_id=episode.id,
                user_id=self.owner_id,
                revision=episode.revision,
                occurred_at=at,
                payload={
                    "event_type": "WINDOW_CLOSURE",
                    "from_state": old_state,
                    "to_state": episode.state,
                    "reason": "window-closed-by-explicit-scan",
                    "run_sequence": admission.sequence,
                    "rule": "scan-driven-temporal-v1",
                },
            )
        )
        if episode.comparison_scope_id is not None:
            TemporalStore(self.session, self.owner_id).release_active_slot(
                episode.comparison_scope_id, episode.instrument_id, episode.id
            )
        self.session.flush()
        return True

    def capture_candidate(
        self,
        match: ScanMatch,
        intent_choice: IntentChoice,
        horizon_choice: HorizonChoice,
        profile: str,
        evidence: tuple[DiscoveryEvidence, ...],
        at: datetime,
        context: MarketContextSnapshot,
        context_policy: ContextPolicy,
        include_llm: bool,
        admission: RunAdmission,
    ) -> CandidateSummary:
        temporal = TemporalStore(self.session, self.owner_id)
        existing = temporal.episode_for_observation(
            admission.scope_id, match.instrument.instrument_id, admission.sequence
        )
        if existing is not None and admission.sequence <= int(
            existing.payload.get("temporal", {}).get("projected_sequence", 0)
        ):
            relevance, _ = self.relevance(
                evidence,
                horizon_choice,
                self.settings(),
                context,
                context_policy,
            )
            late_source_times = tuple(
                item.source_data_time
                for item in match.evidence
                if item.source_data_time is not None
            )
            temporal.append_observation(
                admission=admission,
                instrument=match.instrument,
                kind=DiscoveryObservationKind.PRESENT,
                coverage=EvaluationCoverage.EVALUATED,
                reason="late-present-observation",
                observed_at=max(item.observed_at for item in match.evidence),
                source_data_time=min(late_source_times) if late_source_times else None,
                source_sample_key=self.source_sample_key(match),
                episode=existing,
                scan_match_id=match.scan_match_id,
                relevance_score=relevance.displayed_value,
                relevance_band=relevance.band,
                relevance_policy=relevance.policy,
                evidence_ids=tuple(item.evidence_id for item in match.evidence),
                context_id=context.context_id,
                provider=match.provenance.producer.provider,
            )
            return self.summary(existing)
        previous: DiscoveryEpisodeRecord | None = None
        if existing is not None and self.close_elapsed_episode(existing, admission, at):
            previous = existing
            existing = None
        if existing is None:
            if previous is None:
                previous = self.session.scalar(
                    select(DiscoveryEpisodeRecord)
                    .where(
                        DiscoveryEpisodeRecord.user_id == self.owner_id,
                        DiscoveryEpisodeRecord.instrument_id == match.instrument.instrument_id,
                        DiscoveryEpisodeRecord.intent_key == intent_choice.value,
                        DiscoveryEpisodeRecord.horizon_key == horizon_choice.value,
                    )
                    .order_by(DiscoveryEpisodeRecord.opened_at.desc())
                )
            episode_id, candidate_id = uuid4(), uuid4()
            selected_intent = intent(self.owner_id, intent_choice, horizon_choice, at)
            window = OpportunityWindow(
                starts_at=at, ends_at=at + timedelta(seconds=horizon_seconds(horizon_choice))
            )
            episode = DiscoveryEpisode(
                episode_id=episode_id,
                candidate_id=candidate_id,
                owner_id=self.owner_id,
                instrument=match.instrument,
                intent=selected_intent,
                observation_basis=horizon_choice.value,
                policy_series=TEMPORAL_POLICY,
                window=window,
                opened_at=at,
                evaluated_at=at,
                previous_episode_id=previous.id if previous else None,
            )
            record = DiscoveryEpisodeRecord(
                id=episode_id,
                candidate_id=candidate_id,
                user_id=self.owner_id,
                instrument_id=match.instrument.instrument_id,
                intent_key=intent_choice.value,
                horizon_key=horizon_choice.value,
                state=DiscoveryLifecycleState.NEW.value,
                revision=1,
                snapshot_count=0,
                previous_episode_id=previous.id if previous else None,
                comparison_scope_id=admission.scope_id,
                opened_at=at,
                updated_at=at,
                payload={
                    "episode": episode.model_dump(mode="json"),
                    "legacy_reconstruction": "NOT_REQUIRED",
                },
            )
            self.session.add(record)
            self.session.flush()
            temporal.claim_active_slot(admission.scope_id, record)
        else:
            record = existing
            episode = DiscoveryEpisode.model_validate(record.payload["episode"])

        prior_rows = tuple(
            self.session.scalars(
                select(DiscoverySnapshotRecord)
                .where(
                    DiscoverySnapshotRecord.user_id == self.owner_id,
                    DiscoverySnapshotRecord.episode_id == record.id,
                )
                .order_by(DiscoverySnapshotRecord.sequence.asc())
            )
        )
        sequence = len(prior_rows) + 1
        relevance, explanation = self.relevance(
            evidence,
            horizon_choice,
            self.settings(),
            context,
            context_policy,
        )
        source_times = [item.source_data_time for item in evidence]
        snapshot = DiscoverySnapshot(
            snapshot_id=uuid4(),
            episode_id=record.id,
            owner_id=self.owner_id,
            sequence=sequence,
            previous_snapshot_id=prior_rows[-1].id if prior_rows else None,
            instrument=match.instrument,
            intent_fingerprint=episode.intent.fingerprint,
            observation_basis=horizon_choice.value,
            observed_at=max(item.observed_at for item in evidence),
            source_data_time=(
                min(cast(datetime, item) for item in source_times) if all(source_times) else None
            ),
            evaluated_at=at,
            recorded_at=at,
            evidence=evidence,
            provenance=match.provenance,
            relevance=relevance,
            lineage=CandidateLineage(
                input_id=stable(f"candidate-input:{match.scan_match_id}"),
                owner_id=self.owner_id,
                producer=match.provenance.producer,
                source=match.provenance.source,
                scan=match.lineage,
            ),
        )
        tolerance = self.tolerance(evidence, horizon_choice, context, episode.window, at)
        lifecycle_override: DiscoveryLifecycleState | None = None
        lifecycle_reason = "first-observation" if sequence == 1 else "comparable-observation"
        if (
            context_policy != ContextPolicy.OPTIONAL
            and context.availability in {ContextAvailability.STALE, ContextAvailability.UNAVAILABLE}
            and sequence >= 2
        ):
            lifecycle_override = DiscoveryLifecycleState.STALE
            lifecycle_reason = (
                "market-context-stale"
                if context.availability == ContextAvailability.STALE
                else "market-context-unavailable"
            )
        elif prior_rows and tolerance.state == "BREACHED":
            prior_tolerance = ToleranceAssessment.model_validate(
                prior_rows[-1].payload["tolerance"]
            )
            if prior_tolerance.state == "BREACHED":
                lifecycle_override = DiscoveryLifecycleState.DEFUNCT
                lifecycle_reason = "tolerance-confirmed"
        elif record.state == DiscoveryLifecycleState.DEFUNCT.value and tolerance.state == "WITHIN":
            lifecycle_override = DiscoveryLifecycleState.CURRENT
            lifecycle_reason = "tolerance-recovery-verified"

        snapshot_payload = {
            "snapshot": snapshot.model_dump(mode="json"),
            "lifecycle": record.state,
            "lifecycle_reason": lifecycle_reason,
            "profile": profile,
            "context_policy": context_policy.value,
            "relevance_explanation": explanation.model_dump(mode="json"),
            "tolerance": tolerance.model_dump(mode="json"),
            "context_id": str(context.context_id),
        }
        snapshot_record = DiscoverySnapshotRecord(
            id=snapshot.snapshot_id,
            episode_id=record.id,
            user_id=self.owner_id,
            sequence=sequence,
            observed_at=snapshot.observed_at,
            payload=snapshot_payload,
        )
        self.session.add(snapshot_record)
        record.snapshot_count = sequence
        previous_lineage = record.payload.get("scan_lineage", {})
        episode_payload = {
            **episode.model_dump(mode="json"),
            "head_snapshot_id": str(snapshot.snapshot_id),
            "evaluated_at": at.isoformat(),
        }
        record.payload = {
            **record.payload,
            "episode": episode_payload,
            "scan_lineage": {
                "originating_scan_run_id": previous_lineage.get(
                    "originating_scan_run_id", str(match.run_id)
                ),
                "latest_scan_run_id": str(match.run_id),
                "profile": profile,
            },
            "lifecycle_reason": lifecycle_reason,
        }
        observation_row = temporal.append_observation(
            admission=admission,
            instrument=match.instrument,
            kind=DiscoveryObservationKind.PRESENT,
            coverage=EvaluationCoverage.EVALUATED,
            reason=lifecycle_reason,
            observed_at=snapshot.observed_at,
            source_data_time=(
                min(
                    item.source_data_time
                    for item in match.evidence
                    if item.source_data_time is not None
                )
                if any(item.source_data_time is not None for item in match.evidence)
                else None
            ),
            source_sample_key=self.source_sample_key(match),
            episode=record,
            scan_match_id=match.scan_match_id,
            snapshot_id=snapshot.snapshot_id,
            relevance_score=relevance.displayed_value,
            relevance_band=relevance.band,
            relevance_policy=relevance.policy,
            evidence_ids=tuple(item.evidence_id for item in evidence),
            context_id=context.context_id,
            provider=match.provenance.producer.provider,
            lifecycle_override=lifecycle_override,
        )
        observation = observation_row.payload["observation"]
        snapshot_payload = {
            **snapshot_payload,
            "lifecycle": observation.get("lifecycle_after") or record.state,
            "lifecycle_reason": observation["reason"],
        }
        snapshot_record.payload = snapshot_payload
        summary = self.summary(record, snapshot_payload)
        llm_settings = self.settings()
        if include_llm and llm_settings.llm_enabled and llm_settings.llm_provider == "synthetic":
            self.create_explanation(record, snapshot, evidence)
        return summary

    def create_explanation(
        self,
        episode: DiscoveryEpisodeRecord,
        snapshot: DiscoverySnapshot,
        evidence: tuple[DiscoveryEvidence, ...],
    ) -> LLMExplanation:
        categories = sorted({item.category.value for item in evidence})
        grounding: Literal["GROUNDED", "PARTIALLY_GROUNDED", "CONTEXT_ONLY"] = (
            "GROUNDED" if EvidenceCategory.PROVIDER_SCAN.value in categories else "CONTEXT_ONLY"
        )
        item = LLMExplanation(
            explanation_id=uuid4(),
            owner_id=self.owner_id,
            candidate_id=episode.candidate_id,
            snapshot_id=snapshot.snapshot_id,
            provider="synthetic",
            model="controlled-level0",
            model_version="1",
            prompt_version="candidate-explanation-v1",
            generated_at=now_utc(),
            grounding=grounding,
            evidence_ids=tuple(value.evidence_id for value in evidence),
            narrative=(
                f"{snapshot.instrument.symbol} matched deterministic scan evidence with "
                f"{len(categories)} evidence categories. Relevance remains policy-derived; "
                "this explanation has no lifecycle or trading authority."
            ),
            limitations=("synthetic-controlled-provider",),
        )
        self.session.add(
            DiscoveryExplanationRecord(
                id=item.explanation_id,
                candidate_id=episode.candidate_id,
                snapshot_id=snapshot.snapshot_id,
                user_id=self.owner_id,
                generated_at=item.generated_at,
                payload=item.model_dump(mode="json"),
            )
        )
        return item

    @staticmethod
    def match_reason(name: str, value: object) -> str | None:
        try:
            numeric = float(cast(Any, value))
        except (TypeError, ValueError):
            numeric = 0.0
        if name == "relative_volume.20":
            return f"Relative volume {numeric:.2f}×"
        if name == "breakout.20" and numeric == 1:
            return "Upside breakout confirmed above the 20-day high"
        if name == "breakdown.20" and numeric == 1:
            return "Downside breakdown confirmed below the 20-day low"
        if name == "roc.10":
            direction = "Positive" if numeric > 0 else "Negative"
            return f"{direction} 10-day momentum {numeric:+.1f}%"
        if name == "rsi.14":
            return f"RSI {numeric:.0f} satisfied the profile threshold"
        if name == "close_sma20_gap":
            position = "above" if numeric >= 0 else "below"
            return f"Close {abs(numeric):.1f}% {position} the 20-day average"
        if name == "close_sma50_gap":
            position = "above" if numeric >= 0 else "below"
            return f"Close {abs(numeric):.1f}% {position} the 50-day average"
        if name == "sma50_sma200_gap":
            position = "above" if numeric >= 0 else "below"
            return f"50-day trend {abs(numeric):.1f}% {position} the 200-day trend"
        if name == "roc.1" and numeric < 0:
            return f"One-day pullback {numeric:.1f}%"
        return None

    @classmethod
    def match_view(cls, match: ScanMatch) -> ScanMatchView:
        metrics: dict[str, object] = {}
        reasons: list[str] = []
        raw_reasons: list[str] = []
        for evidence in match.evidence:
            if evidence.category == EvidenceCategory.PROVIDER_SCAN:
                raw_reasons.append(evidence.observation_basis)
            for measure in evidence.measures:
                if measure.name not in {
                    "threshold",
                    "operator",
                    "input-digest",
                    "matched",
                    "price-unit",
                }:
                    metrics[measure.name] = str(measure.value)
                if evidence.category == EvidenceCategory.PROVIDER_SCAN:
                    reason = cls.match_reason(measure.name, measure.value)
                    if reason is not None and reason not in reasons:
                        reasons.append(reason)
        if not reasons:
            reasons.append("Selected provider conditions matched")
        source_times = [
            item.source_data_time for item in match.evidence if item.source_data_time is not None
        ]
        source_data_time = max(source_times) if source_times else None
        verification = EvidenceVerification.UNVERIFIED
        if match.provenance.producer == REAL_TRADINGVIEW:
            reasons_set = {item.reason for item in match.evidence}
            if "real-evidence-contradicted-provisional-match" in reasons_set:
                verification = EvidenceVerification.CONTRADICTED
            elif "verification-confirmed" in reasons_set:
                verification = EvidenceVerification.CONFIRMED
            elif "verification-partially_confirmed" in reasons_set:
                verification = EvidenceVerification.PARTIALLY_CONFIRMED
            elif any(item.availability == "PRESENT" for item in match.evidence):
                verification = EvidenceVerification.UNVERIFIED
            else:
                verification = EvidenceVerification.UNAVAILABLE
        present_categories = {
            item.category for item in match.evidence if item.availability == "PRESENT"
        }
        coverage = (
            "COMPLETE"
            if {EvidenceCategory.INSTRUMENT_PRICE, EvidenceCategory.TECHNICAL} <= present_categories
            else ("PARTIAL" if present_categories else "NONE")
        )
        return ScanMatchView(
            match_id=match.scan_match_id,
            symbol=match.instrument.symbol,
            exchange=match.instrument.exchange,
            segment=match.instrument.segment,
            provider=match.provenance.producer.provider,
            why_matched=tuple(reasons),
            raw_reasons=tuple(dict.fromkeys(raw_reasons)),
            key_metrics={key: str(value) for key, value in metrics.items()},
            source_mode=match.provenance.mode.value,
            source_data_time=source_data_time,
            lineage=match.lineage.comparison_key,
            verification=verification,
            evidence_coverage=cast(Any, coverage),
        )

    def summary(
        self, episode: DiscoveryEpisodeRecord, payload: dict[str, Any] | None = None
    ) -> CandidateSummary:
        if payload is None:
            row = self.session.scalar(
                select(DiscoverySnapshotRecord)
                .where(
                    DiscoverySnapshotRecord.user_id == self.owner_id,
                    DiscoverySnapshotRecord.episode_id == episode.id,
                )
                .order_by(DiscoverySnapshotRecord.sequence.desc())
            )
            if row is None:
                raise ProductFailure(404, "CANDIDATE_NOT_FOUND")
            payload = row.payload
        settings = self.settings()
        temporal_summary = TemporalStore(self.session, self.owner_id).summary(
            episode, settings.hot_observation_count
        )
        return self._candidate_summary(episode, payload, settings, temporal_summary)

    def _candidate_summary(
        self,
        episode: DiscoveryEpisodeRecord,
        payload: dict[str, Any],
        settings: DiscoverySettings,
        temporal_summary: TemporalSummary | None,
    ) -> CandidateSummary:
        snapshot = DiscoverySnapshot.model_validate(payload["snapshot"])
        explanation = RelevanceExplanation.model_validate(payload["relevance_explanation"])
        tolerance = ToleranceAssessment.model_validate(payload["tolerance"])
        sources = tuple(sorted({item.provenance.producer.provider for item in snapshot.evidence}))
        profile, profile_lineage, legacy_profile = self.candidate_profile(episode, payload)
        freshness_state = FreshnessState.UNKNOWN
        if snapshot.source_data_time is not None:
            age = (now_utc() - snapshot.source_data_time).total_seconds()
            freshness_state = (
                FreshnessState.FRESH if age <= settings.freshness_seconds else FreshnessState.STALE
            )
        return CandidateSummary(
            candidate_id=episode.candidate_id,
            episode_id=episode.id,
            revision=episode.revision,
            instrument=snapshot.instrument,
            intent=IntentChoice(episode.intent_key),
            horizon=HorizonChoice(episode.horizon_key),
            profile=profile,
            profile_lineage=profile_lineage,
            legacy_profile=legacy_profile,
            relevance=snapshot.relevance,
            relevance_explanation=explanation,
            tolerance=tolerance,
            lifecycle=DiscoveryLifecycleState(
                DiscoveryLifecycleState.STALE.value
                if episode.state == DiscoveryLifecycleState.CURRENT.value
                and payload["lifecycle"] == DiscoveryLifecycleState.STALE.value
                else episode.state
            ),
            lifecycle_reason=str(
                payload.get("lifecycle_reason")
                or episode.payload.get("lifecycle_reason")
                or "state-restored-from-persisted-record"
            ),
            freshness=freshness_state,
            snapshot_count=episode.snapshot_count,
            provider_sources=sources,
            originating_scan_run_id=episode.payload.get("scan_lineage", {}).get(
                "originating_scan_run_id"
            )
            or (snapshot.lineage.scan.run_id if snapshot.lineage.scan else None),
            latest_scan_run_id=episode.payload.get("scan_lineage", {}).get("latest_scan_run_id")
            or (snapshot.lineage.scan.run_id if snapshot.lineage.scan else None),
            updated_at=aware(episode.updated_at),
            temporal=temporal_summary,
        )

    def scan_profile(self, run_id: object) -> str | None:
        if not run_id:
            return None
        try:
            parsed = UUID(str(run_id))
        except ValueError:
            return None
        row = self.session.scalar(
            select(ScanRunRecord).where(
                ScanRunRecord.id == parsed,
                ScanRunRecord.user_id == self.owner_id,
            )
        )
        if row is None:
            return None
        value = row.payload.get("profile")
        return str(value) if value else None

    def candidate_profile(
        self, episode: DiscoveryEpisodeRecord, payload: dict[str, Any]
    ) -> tuple[str | None, ProfileLineage, bool]:
        direct = payload.get("profile")
        if direct:
            return str(direct), "CURRENT_SNAPSHOT", False

        lineage = episode.payload.get("scan_lineage", {})
        lineage_sources: tuple[tuple[str, ProfileLineage], ...] = (
            ("originating_scan_run_id", "ORIGINATING_SCAN"),
            ("latest_scan_run_id", "LATEST_SCAN"),
        )
        for key, source in lineage_sources:
            recovered = self.scan_profile(lineage.get(key))
            if recovered:
                return recovered, source, True

        snapshot_profiles = self.session.scalars(
            select(DiscoverySnapshotRecord.payload)
            .where(
                DiscoverySnapshotRecord.episode_id == episode.id,
                DiscoverySnapshotRecord.user_id == self.owner_id,
            )
            .order_by(DiscoverySnapshotRecord.sequence.desc())
        )
        for snapshot_payload in snapshot_profiles:
            recovered = snapshot_payload.get("profile")
            if recovered:
                return str(recovered), "PERSISTED_SNAPSHOT", True

        recovered = episode.payload.get("profile") or lineage.get("profile")
        if recovered:
            return str(recovered), "CANDIDATE_METADATA", True
        return None, "LEGACY_UNAVAILABLE", True

    @staticmethod
    def attention_key(candidate: CandidateSummary) -> tuple[object, ...]:
        lifecycle_priority = {
            DiscoveryLifecycleState.CURRENT: 0,
            DiscoveryLifecycleState.NEW: 1,
            DiscoveryLifecycleState.STALE: 2,
            DiscoveryLifecycleState.DEFUNCT: 3,
            DiscoveryLifecycleState.EXPIRED: 4,
            DiscoveryLifecycleState.REJECTED: 5,
        }
        freshness_priority = {
            FreshnessState.FRESH: 0,
            FreshnessState.UNKNOWN: 1,
            FreshnessState.STALE: 2,
        }
        current_relevance = (
            candidate.relevance.policy.id == POLICY.id
            and candidate.relevance.policy.version == POLICY.version
        )
        return (
            0 if current_relevance else 1,
            -float(candidate.relevance.value or 0),
            lifecycle_priority[candidate.lifecycle],
            freshness_priority[candidate.freshness],
            -aware(candidate.updated_at).timestamp(),
            candidate.instrument.symbol,
            str(candidate.candidate_id),
        )

    def candidates(self, limit: int, offset: int) -> PaginatedCandidates:
        settings = self.settings()
        snapshot_payload = DiscoverySnapshotRecord.payload["snapshot"]
        relevance = snapshot_payload["relevance"]
        score = sql_cast(relevance["value"].as_string(), Float)
        policy_id = relevance["policy"]["id"].as_string()
        policy_version = relevance["policy"]["version"].as_string()
        source_time = snapshot_payload["source_data_time"].as_string()
        symbol = snapshot_payload["instrument"]["symbol"].as_string()
        fresh_cutoff = (now_utc() - timedelta(seconds=settings.freshness_seconds)).isoformat()
        lifecycle_priority = case(
            (DiscoveryEpisodeRecord.state == DiscoveryLifecycleState.NEW.value, 0),
            (DiscoveryEpisodeRecord.state == DiscoveryLifecycleState.CURRENT.value, 1),
            (DiscoveryEpisodeRecord.state == DiscoveryLifecycleState.STALE.value, 2),
            (DiscoveryEpisodeRecord.state == DiscoveryLifecycleState.DEFUNCT.value, 3),
            (DiscoveryEpisodeRecord.state == DiscoveryLifecycleState.EXPIRED.value, 4),
            else_=5,
        )
        freshness_priority = case(
            (source_time.is_(None), 1),
            (source_time >= fresh_cutoff, 0),
            else_=2,
        )
        current_policy = case(
            (
                and_(policy_id == POLICY.id, policy_version == POLICY.version),
                0,
            ),
            else_=1,
        )
        score_missing = case((score.is_(None), 1), else_=0)
        query = (
            select(DiscoveryEpisodeRecord, DiscoverySnapshotRecord)
            .join(
                DiscoverySnapshotRecord,
                and_(
                    DiscoverySnapshotRecord.episode_id == DiscoveryEpisodeRecord.id,
                    DiscoverySnapshotRecord.sequence == DiscoveryEpisodeRecord.snapshot_count,
                    DiscoverySnapshotRecord.user_id == self.owner_id,
                ),
            )
            .where(DiscoveryEpisodeRecord.user_id == self.owner_id)
            .order_by(
                current_policy.asc(),
                score_missing.asc(),
                score.desc(),
                lifecycle_priority.asc(),
                freshness_priority.asc(),
                DiscoveryEpisodeRecord.updated_at.desc(),
                symbol.asc(),
                DiscoveryEpisodeRecord.candidate_id.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        page = tuple(self.session.execute(query))
        episodes = tuple(item[0] for item in page)
        temporal = TemporalStore(self.session, self.owner_id).summaries(
            episodes, settings.hot_observation_count
        )
        summaries = tuple(
            self._candidate_summary(episode, snapshot.payload, settings, temporal.get(episode.id))
            for episode, snapshot in page
        )
        total = int(
            self.session.scalar(
                select(func.count())
                .select_from(DiscoveryEpisodeRecord)
                .where(DiscoveryEpisodeRecord.user_id == self.owner_id)
            )
            or 0
        )
        return PaginatedCandidates(
            items=summaries,
            total=total,
            limit=limit,
            offset=offset,
            as_of=now_utc(),
        )

    def episode_by_candidate(self, candidate_id: UUID) -> DiscoveryEpisodeRecord:
        row = self.session.scalar(
            select(DiscoveryEpisodeRecord).where(
                DiscoveryEpisodeRecord.candidate_id == candidate_id,
                DiscoveryEpisodeRecord.user_id == self.owner_id,
            )
        )
        if row is None:
            raise ProductFailure(404, "CANDIDATE_NOT_FOUND")
        return row

    def detail(self, candidate_id: UUID, history_limit: int = 50) -> CandidateDetail:
        episode = self.episode_by_candidate(candidate_id)
        snapshots = tuple(
            self.session.scalars(
                select(DiscoverySnapshotRecord)
                .where(
                    DiscoverySnapshotRecord.episode_id == episode.id,
                    DiscoverySnapshotRecord.user_id == self.owner_id,
                )
                .order_by(DiscoverySnapshotRecord.sequence.desc())
                .limit(history_limit)
            )
        )[::-1]
        views: list[SnapshotView] = []
        for row in snapshots:
            snapshot = DiscoverySnapshot.model_validate(row.payload["snapshot"])
            sources = tuple(
                sorted({item.provenance.producer.provider for item in snapshot.evidence})
            )
            views.append(
                SnapshotView(
                    snapshot_id=row.id,
                    sequence=row.sequence,
                    observed_at=snapshot.observed_at,
                    source_data_time=snapshot.source_data_time,
                    lifecycle=DiscoveryLifecycleState(row.payload["lifecycle"]),
                    lifecycle_reason=str(
                        row.payload.get("lifecycle_reason", "persisted-snapshot-state")
                    ),
                    relevance=snapshot.relevance,
                    relevance_explanation=RelevanceExplanation.model_validate(
                        row.payload["relevance_explanation"]
                    ),
                    tolerance=ToleranceAssessment.model_validate(row.payload["tolerance"]),
                    evidence=snapshot.evidence,
                    provider_sources=sources,
                )
            )
        transitions = tuple(
            row.payload
            for row in self.session.scalars(
                select(DiscoveryTransitionRecord)
                .where(
                    DiscoveryTransitionRecord.episode_id == episode.id,
                    DiscoveryTransitionRecord.user_id == self.owner_id,
                )
                .order_by(DiscoveryTransitionRecord.revision.asc())
            )
        )
        explanations = tuple(
            LLMExplanation.model_validate(row.payload)
            for row in self.session.scalars(
                select(DiscoveryExplanationRecord)
                .where(
                    DiscoveryExplanationRecord.candidate_id == candidate_id,
                    DiscoveryExplanationRecord.user_id == self.owner_id,
                )
                .order_by(DiscoveryExplanationRecord.generated_at.asc())
            )
        )
        context = None
        if snapshots:
            context_id = UUID(snapshots[-1].payload["context_id"])
            context_row = self.session.get(MarketContextRecord, context_id)
            if context_row is not None and context_row.user_id == self.owner_id:
                context = MarketContextSnapshot.model_validate(context_row.payload)
        head = self.summary(episode, snapshots[-1].payload if snapshots else None)
        hot_size = self.settings().hot_observation_count
        observations = (
            TemporalStore(self.session, self.owner_id)
            .history_page(
                episode.id,
                limit=min(history_limit, hot_size),
                offset=0,
                hot_size=hot_size,
            )
            .items
        )
        return CandidateDetail(
            **head.model_dump(),
            snapshots=tuple(views),
            transitions=transitions,
            explanations=explanations,
            context=context,
            previous_episode_id=episode.previous_episode_id,
            observations=observations,
        )

    def temporal_history(self, candidate_id: UUID, limit: int, offset: int) -> TemporalHistoryPage:
        episode = self.episode_by_candidate(candidate_id)
        return TemporalStore(self.session, self.owner_id).history_page(
            episode.id,
            limit=limit,
            offset=offset,
            hot_size=self.settings().hot_observation_count,
        )

    def run_temporal(
        self, run_id: UUID, mode: RunViewMode, limit: int, offset: int
    ) -> RunTemporalView:
        run = self.session.scalar(
            select(ScanRunRecord).where(
                ScanRunRecord.id == run_id,
                ScanRunRecord.user_id == self.owner_id,
            )
        )
        if run is None:
            raise ProductFailure(404, "SCAN_NOT_FOUND")
        predicate = (
            DiscoveryObservationRecord.run_id == run_id,
            DiscoveryObservationRecord.user_id == self.owner_id,
        )
        total = int(
            self.session.scalar(
                select(func.count()).select_from(DiscoveryObservationRecord).where(*predicate)
            )
            or 0
        )
        rows = tuple(
            self.session.scalars(
                select(DiscoveryObservationRecord)
                .where(*predicate)
                .order_by(
                    DiscoveryObservationRecord.instrument_id.asc(),
                    DiscoveryObservationRecord.recorded_at.asc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )
        temporal = TemporalStore(self.session, self.owner_id)
        current_candidates: dict[UUID, CandidateSummary] = {}
        if mode == RunViewMode.CURRENT_STATE:
            candidate_ids = tuple(
                dict.fromkeys(row.candidate_id for row in rows if row.candidate_id is not None)
            )
            if candidate_ids:
                current_rows = tuple(
                    self.session.execute(
                        select(DiscoveryEpisodeRecord, DiscoverySnapshotRecord)
                        .join(
                            DiscoverySnapshotRecord,
                            and_(
                                DiscoverySnapshotRecord.episode_id == DiscoveryEpisodeRecord.id,
                                DiscoverySnapshotRecord.sequence
                                == DiscoveryEpisodeRecord.snapshot_count,
                                DiscoverySnapshotRecord.user_id == self.owner_id,
                            ),
                        )
                        .where(
                            DiscoveryEpisodeRecord.user_id == self.owner_id,
                            DiscoveryEpisodeRecord.candidate_id.in_(candidate_ids),
                        )
                    )
                )
                current_episodes = tuple(episode for episode, _snapshot in current_rows)
                settings = self.settings()
                current_temporal = temporal.summaries(
                    current_episodes, settings.hot_observation_count
                )
                current_candidates = {
                    episode.candidate_id: self._candidate_summary(
                        episode,
                        snapshot.payload,
                        settings,
                        current_temporal.get(episode.id),
                    )
                    for episode, snapshot in current_rows
                }
        items = tuple(
            RunTemporalCandidate(
                instrument=InstrumentIdentity.model_validate(row.payload["instrument"]),
                observation=temporal.view(row, True),
                candidate=(
                    current_candidates.get(row.candidate_id)
                    if row.candidate_id is not None
                    else None
                ),
            )
            for row in rows
        )
        return RunTemporalView(
            run_id=run_id,
            mode=mode,
            summary=ScanSummary.model_validate(run.payload),
            items=tuple(items),
            limit=limit,
            offset=offset,
            total=total,
        )

    def rebuild_candidate_projection(self, candidate_id: UUID) -> CandidateDetail:
        episode = self.episode_by_candidate(candidate_id)
        TemporalStore(self.session, self.owner_id).rebuild_projection(episode)
        self.commit()
        return self.detail(candidate_id)

    def history(
        self, limit: int, offset: int, include_archived: bool = False
    ) -> tuple[ScanSummary, ...]:
        query = select(ScanRunRecord).where(ScanRunRecord.user_id == self.owner_id)
        if not include_archived:
            query = query.where(ScanRunRecord.archived_at.is_(None))
        return tuple(
            ScanSummary.model_validate(row.payload)
            for row in self.session.scalars(
                query.order_by(ScanRunRecord.completed_at.desc()).offset(offset).limit(limit)
            )
        )

    def historical_detail(self, run_id: UUID) -> HistoricalScanDetail:
        run = self.session.scalar(
            select(ScanRunRecord).where(
                ScanRunRecord.id == run_id,
                ScanRunRecord.user_id == self.owner_id,
            )
        )
        if run is None:
            raise ProductFailure(404, "SCAN_NOT_FOUND")
        matches = tuple(
            self.match_view(ScanMatch.model_validate(row.payload))
            for row in self.session.scalars(
                select(ScanMatchRecord)
                .where(
                    ScanMatchRecord.run_id == run_id,
                    ScanMatchRecord.user_id == self.owner_id,
                )
                .order_by(ScanMatchRecord.id.asc())
            )
        )
        context_row = self.session.scalar(
            select(MarketContextRecord).where(
                MarketContextRecord.run_id == run_id,
                MarketContextRecord.user_id == self.owner_id,
            )
        )
        return HistoricalScanDetail(
            summary=ScanSummary.model_validate(run.payload),
            matches=matches,
            market_context=(
                None
                if context_row is None
                else MarketContextSnapshot.model_validate(context_row.payload)
            ),
        )

    async def evidence_chart(
        self, run_id: UUID, match_id: UUID, mode: EvidenceChartMode
    ) -> EvidenceChart:
        run_row = self.session.scalar(
            select(ScanRunRecord).where(
                ScanRunRecord.id == run_id,
                ScanRunRecord.user_id == self.owner_id,
            )
        )
        match_row = self.session.scalar(
            select(ScanMatchRecord).where(
                ScanMatchRecord.id == match_id,
                ScanMatchRecord.run_id == run_id,
                ScanMatchRecord.user_id == self.owner_id,
            )
        )
        if run_row is None or match_row is None:
            raise ProductFailure(404, "SCAN_MATCH_NOT_FOUND")
        summary = ScanSummary.model_validate(run_row.payload)
        match = ScanMatch.model_validate(match_row.payload)
        archive = self.session.scalar(
            select(ScanEvidenceSeriesRecord).where(
                ScanEvidenceSeriesRecord.match_id == match_id,
                ScanEvidenceSeriesRecord.run_id == run_id,
                ScanEvidenceSeriesRecord.user_id == self.owner_id,
            )
        )
        if archive is None:
            return unavailable_chart(
                mode=mode,
                state=EvidenceChartState.LEGACY_UNAVAILABLE,
                message="Evidence chart unavailable for this legacy scan.",
                match=match,
                summary=summary,
                source_class="LEGACY_UNKNOWN",
            )

        if summary.provider == ProviderChoice.REAL_TRADINGVIEW:
            if mode == EvidenceChartMode.AS_SCANNED:
                return unavailable_chart(
                    mode=mode,
                    state=EvidenceChartState.RETENTION_RESTRICTED,
                    message=(
                        "Historical TradingView bars are not retained because retention rights "
                        "are unknown. Persisted numerical scan evidence remains available."
                    ),
                    match=match,
                    summary=summary,
                    source_class="PROVIDER_RESTRICTED",
                    historical_chart_reconstructable=False,
                    scan_bars_retained=False,
                )
            if self.real_evidence is None:
                return unavailable_chart(
                    mode=mode,
                    state=EvidenceChartState.AUTH_REQUIRED,
                    message="Current chart requires an authorized TradingView connection.",
                    match=match,
                    summary=summary,
                    source_class="PROVIDER_RESTRICTED",
                )
            enrichment = await self.real_evidence.enrich((match.instrument,), summary.horizon.value)
            item = enrichment.symbols[0]
            if item.outcome != EvidenceOutcome.AVAILABLE or not item.bars:
                state = {
                    EvidenceOutcome.AUTH_REQUIRED: EvidenceChartState.AUTH_REQUIRED,
                    EvidenceOutcome.RATE_LIMITED: EvidenceChartState.RATE_LIMITED,
                    EvidenceOutcome.EXACT_MISSING: EvidenceChartState.EXACT_MISSING,
                }.get(item.outcome, EvidenceChartState.CURRENT_UNAVAILABLE)
                message = {
                    EvidenceChartState.AUTH_REQUIRED: (
                        "Current chart requires TradingView authorization."
                    ),
                    EvidenceChartState.RATE_LIMITED: (
                        "TradingView rate limited the current chart request. Retry later."
                    ),
                    EvidenceChartState.EXACT_MISSING: (
                        "TradingView did not return this exact broker-native symbol."
                    ),
                    EvidenceChartState.CURRENT_UNAVAILABLE: (
                        "Current TradingView OHLCV is unavailable for this symbol."
                    ),
                }[state]
                return unavailable_chart(
                    mode=mode,
                    state=state,
                    message=message,
                    match=match,
                    summary=summary,
                    source_class="PROVIDER_RESTRICTED",
                )
            current = MarketSeries(
                instrument=match.instrument,
                interval=item.interval,
                price_unit="INR",
                adjustment=RevisionRef(id="provider-unspecified", version="1"),
                session_basis=RevisionRef(id="tradingview-provider-calendar", version="1"),
                provenance=match.provenance,
                bars=tuple(
                    Bar(
                        timestamp=bar.source_time,
                        available_at=max(bar.source_time, item.received_at),
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=None if bar.volume is None else float(bar.volume),
                    )
                    for bar in item.bars
                ),
            )
            try:
                return build_chart(
                    mode=mode,
                    match=match,
                    summary=summary,
                    archived_payload=archive.payload,
                    current_series=current,
                )
            except (KeyError, TypeError, ValueError):
                return unavailable_chart(
                    mode=mode,
                    state=EvidenceChartState.RECONSTRUCTION_FAILED,
                    message="Current TradingView evidence failed integrity checks.",
                    match=match,
                    summary=summary,
                    source_class="PROVIDER_RESTRICTED",
                )

        if mode == EvidenceChartMode.CURRENT and summary.provider != ProviderChoice.INTERNAL:
            archived_bars = archive.payload.get("series", {}).get("bars", [])
            provider_status = next(item for item in self.providers() if item.id == summary.provider)
            unavailable_state = {
                "RATE_LIMITED": EvidenceChartState.RATE_LIMITED,
                "AUTH_REQUIRED": EvidenceChartState.AUTH_REQUIRED,
                "DEGRADED": EvidenceChartState.CURRENT_UNAVAILABLE,
            }.get(provider_status.health, EvidenceChartState.RETENTION_RESTRICTED)
            message = {
                EvidenceChartState.RATE_LIMITED: (
                    "Current chart unavailable: provider rate limited. "
                    "As-scanned evidence remains available."
                ),
                EvidenceChartState.AUTH_REQUIRED: (
                    "Current chart unavailable: provider authentication required."
                ),
                EvidenceChartState.CURRENT_UNAVAILABLE: (
                    "Current chart unavailable: provider health is degraded."
                ),
                EvidenceChartState.RETENTION_RESTRICTED: (
                    "Current chart unavailable: this validation provider has no licensed "
                    "live chart-data capability. As-scanned evidence remains available."
                ),
            }[unavailable_state]
            return unavailable_chart(
                mode=mode,
                state=unavailable_state,
                message=message,
                match=match,
                summary=summary,
                source_class="PROVIDER_RESTRICTED",
                historical_chart_reconstructable=True,
                scan_bars_retained=True,
                archive_bar_count=len(archived_bars),
            )
        synthetic_current: MarketSeries | None = None
        if mode == EvidenceChartMode.CURRENT:
            synthetic_current = market_series(
                match.instrument,
                now_utc(),
                self.fixture_progression(ProviderChoice.INTERNAL),
            )
        try:
            return build_chart(
                mode=mode,
                match=match,
                summary=summary,
                archived_payload=archive.payload,
                current_series=synthetic_current,
            )
        except (KeyError, TypeError, ValueError):
            return unavailable_chart(
                mode=mode,
                state=EvidenceChartState.RECONSTRUCTION_FAILED,
                message=(
                    "Evidence reconstruction failed integrity checks. Persisted numerical "
                    "evidence remains available."
                ),
                match=match,
                summary=summary,
                source_class="LEGACY_UNKNOWN",
                scan_bars_retained=True,
                archive_bar_count=len(archive.payload.get("series", {}).get("bars", [])),
            )

    def set_scan_archived(self, run_id: UUID, archived: bool) -> ScanSummary:
        row = self.session.scalar(
            select(ScanRunRecord).where(
                ScanRunRecord.id == run_id,
                ScanRunRecord.user_id == self.owner_id,
            )
        )
        if row is None:
            raise ProductFailure(404, "SCAN_NOT_FOUND")
        archived_at = now_utc() if archived else None
        row.archived_at = archived_at
        payload = dict(row.payload)
        payload["archived_at"] = None if archived_at is None else archived_at.isoformat()
        row.payload = payload
        self.commit()
        return ScanSummary.model_validate(row.payload)

    def latest_context(self) -> MarketContextSnapshot | None:
        row = self.session.scalar(
            select(MarketContextRecord)
            .where(MarketContextRecord.user_id == self.owner_id)
            .order_by(MarketContextRecord.observed_at.desc())
        )
        return None if row is None else MarketContextSnapshot.model_validate(row.payload)

    def lifecycle(
        self, candidate_id: UUID, action: LifecycleAction, revision: int, reason: str
    ) -> CandidateDetail:
        episode = self.episode_by_candidate(candidate_id)
        if episode.revision != revision:
            raise ProductFailure(409, "REVISION_CONFLICT")
        old = episode.state
        if action == LifecycleAction.DISMISS:
            target = DiscoveryLifecycleState.REJECTED
        elif action == LifecycleAction.MARK_DEFUNCT:
            target = DiscoveryLifecycleState.DEFUNCT
        elif action == LifecycleAction.RECOVER and old == DiscoveryLifecycleState.DEFUNCT.value:
            latest_snapshot = self.session.scalar(
                select(DiscoverySnapshotRecord)
                .where(
                    DiscoverySnapshotRecord.episode_id == episode.id,
                    DiscoverySnapshotRecord.user_id == self.owner_id,
                )
                .order_by(DiscoverySnapshotRecord.sequence.desc())
            )
            latest_observation = self.session.scalar(
                select(DiscoveryObservationRecord)
                .where(
                    DiscoveryObservationRecord.episode_id == episode.id,
                    DiscoveryObservationRecord.user_id == self.owner_id,
                )
                .order_by(DiscoveryObservationRecord.run_sequence.desc())
            )
            if (
                latest_snapshot is None
                or latest_observation is None
                or latest_observation.kind != DiscoveryObservationKind.PRESENT.value
                or ToleranceAssessment.model_validate(latest_snapshot.payload["tolerance"]).state
                != "WITHIN"
            ):
                raise ProductFailure(422, "RECOVERY_REQUIRES_FRESH_EVIDENCE")
            target = DiscoveryLifecycleState.CURRENT
        else:
            raise ProductFailure(422, "INVALID_TRANSITION")
        occurred_at = now_utc()
        episode.state = target.value
        episode.revision += 1
        episode.updated_at = occurred_at
        stored = dict(episode.payload["episode"])
        stored["lifecycle"] = target.value
        stored["revision"] = episode.revision
        stored["evaluated_at"] = occurred_at.isoformat()
        if target == DiscoveryLifecycleState.REJECTED:
            stored["rejection_reason"] = "USER_DISMISSED"
        projected_sequence = int(episode.payload.get("temporal", {}).get("projected_sequence", 0))
        episode.payload = {
            **episode.payload,
            "episode": stored,
            "lifecycle_reason": reason,
        }
        self.session.add(
            DiscoveryTransitionRecord(
                episode_id=episode.id,
                user_id=self.owner_id,
                revision=episode.revision,
                occurred_at=occurred_at,
                payload={
                    "event_type": "OWNER_ACTION",
                    "action": action.value,
                    "actor_owner_id": str(self.owner_id),
                    "after_sequence": projected_sequence,
                    "from_state": old,
                    "to_state": target.value,
                    "reason": reason,
                    "rule": "owner-lifecycle-action-v2",
                },
            )
        )
        if target == DiscoveryLifecycleState.REJECTED and episode.comparison_scope_id is not None:
            TemporalStore(self.session, self.owner_id).release_active_slot(
                episode.comparison_scope_id, episode.instrument_id, episode.id
            )
        self.commit()
        return self.detail(candidate_id)

    def explain(self, candidate_id: UUID) -> LLMExplanation:
        llm_settings = self.settings()
        if not llm_settings.llm_enabled:
            raise ProductFailure(409, "LLM_DISABLED")
        if llm_settings.llm_provider != "synthetic":
            raise ProductFailure(503, "LLM_UNAVAILABLE")
        episode = self.episode_by_candidate(candidate_id)
        row = self.session.scalar(
            select(DiscoverySnapshotRecord)
            .where(
                DiscoverySnapshotRecord.episode_id == episode.id,
                DiscoverySnapshotRecord.user_id == self.owner_id,
            )
            .order_by(DiscoverySnapshotRecord.sequence.desc())
        )
        if row is None:
            raise ProductFailure(404, "CANDIDATE_NOT_FOUND")
        snapshot = DiscoverySnapshot.model_validate(row.payload["snapshot"])
        item = self.create_explanation(episode, snapshot, snapshot.evidence)
        self.commit()
        return item

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ProductFailure(409, "CONCURRENT_UPDATE") from exc
