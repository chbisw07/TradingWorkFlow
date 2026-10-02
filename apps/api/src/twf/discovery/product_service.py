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
from twf.discovery.internal_scanner.conditions import measure as series_measure
from twf.discovery.internal_scanner.market_series import (
    Bar,
    DataUnavailable,
    FixtureMarketSeriesSource,
    MarketSeries,
)
from twf.discovery.internal_scanner.profiles import IDENTITY as INTERNAL_IDENTITY
from twf.discovery.internal_scanner.profiles import build_profile
from twf.discovery.internal_scanner.scanner import InternalScannerV0, ScannerDataFailure
from twf.discovery.market_data import (
    DhanMarketDataProvider,
    FixtureMarketDataProvider,
    MarketDataErrorCode,
    MarketDataFailure,
    MarketDataProvider,
)
from twf.discovery.market_intelligence import (
    IntelligenceKind,
    IntelligenceState,
    MarketIntelligenceBatch,
    MarketIntelligenceProvider,
)
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


INDEX_SYMBOLS = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"})


@dataclass(frozen=True)
class SyntheticInstrumentFixture:
    base_price: Decimal
    daily_trend: Decimal
    relative_volume: Decimal
    final_move: Decimal | None = None
    cycle_amplitude: Decimal = Decimal("0.08")


SYNTHETIC_FIXTURES: dict[str, SyntheticInstrumentFixture] = {
    # Distinct deterministic archetypes for operator validation, never market claims.
    "RELIANCE": SyntheticInstrumentFixture(
        Decimal("2846.40"),
        Decimal("0.18"),
        Decimal("1.95"),
        Decimal("8.00"),
        Decimal("0.20"),
    ),
    "MCX": SyntheticInstrumentFixture(
        Decimal("3146.80"),
        Decimal("0.34"),
        Decimal("2.60"),
        None,
        Decimal("0.30"),
    ),
    "HDFCBANK": SyntheticInstrumentFixture(
        Decimal("1684.25"),
        Decimal("-0.03"),
        Decimal("0.82"),
        None,
        Decimal("0.35"),
    ),
    "INFY": SyntheticInstrumentFixture(
        Decimal("1568.60"),
        Decimal("0.22"),
        Decimal("1.30"),
        Decimal("-2.80"),
        Decimal("0.25"),
    ),
    "BSE": SyntheticInstrumentFixture(
        Decimal("2488.15"),
        Decimal("-0.30"),
        Decimal("1.85"),
        None,
        Decimal("0.25"),
    ),
    "NIFTY": SyntheticInstrumentFixture(
        Decimal("24520.30"),
        Decimal("0.10"),
        Decimal("1.25"),
        None,
        Decimal("0.60"),
    ),
    "BANKNIFTY": SyntheticInstrumentFixture(
        Decimal("51780.10"),
        Decimal("-0.12"),
        Decimal("2.05"),
        Decimal("-18.00"),
        Decimal("0.45"),
    ),
    "TCS": SyntheticInstrumentFixture(
        Decimal("3984.50"),
        Decimal("0.04"),
        Decimal("1.20"),
        None,
        Decimal("0.40"),
    ),
}


def synthetic_fixture(symbol: str, progression: int = 0) -> SyntheticInstrumentFixture:
    if symbol.startswith("NO"):
        return SyntheticInstrumentFixture(Decimal("120.00"), Decimal("-0.10"), Decimal("0.70"))
    fixture = SYNTHETIC_FIXTURES.get(symbol)
    if fixture is None:
        seed = sum(ord(char) for char in symbol)
        fixture = SyntheticInstrumentFixture(
            base_price=Decimal(100 + seed % 900),
            daily_trend=Decimal("0.18") + Decimal(seed % 11) / Decimal(100),
            relative_volume=Decimal("1.55") + Decimal(seed % 45) / Decimal(100),
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
        market_data: MarketDataProvider | None = None,
        market_intelligence: MarketIntelligenceProvider | None = None,
        *,
        market_data_state: str | None = None,
        market_data_error: str | None = None,
    ) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id or uuid4().hex
        self.market_data = market_data
        self.market_intelligence = market_intelligence
        self.market_data_state = market_data_state or (
            "READY" if market_data is not None else "NOT_CONFIGURED"
        )
        self.market_data_error = market_data_error

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

    def providers(self) -> tuple[ProviderStatus, ...]:
        last = {
            row.provider: row
            for row in self.session.scalars(
                select(ScanRunRecord)
                .where(ScanRunRecord.user_id == self.owner_id)
                .order_by(ScanRunRecord.completed_at.asc())
            )
        }
        synthetic = last.get(ProviderChoice.SYNTHETIC.value) or last.get(
            ProviderChoice.INTERNAL.value
        )
        real = last.get(ProviderChoice.REAL.value)
        dhan_ready = self.market_data is not None and self.market_data_state == "READY"
        dhan_health = {
            "READY": "AVAILABLE",
            "CONFIGURED": "DEGRADED",
            "AUTH_FAILED": "AUTH_REQUIRED",
            "RATE_LIMITED": "RATE_LIMITED",
            "PROVIDER_ERROR": "UNAVAILABLE",
            "DISABLED": "AUTH_REQUIRED",
            "NOT_CONFIGURED": "AUTH_REQUIRED",
        }.get(self.market_data_state, "UNAVAILABLE")
        dhan_detail = {
            "CONFIGURED": "Credentials saved; test the connection before running a real scan.",
            "AUTH_FAILED": "Dhan rejected the saved credentials. Replace or update them.",
            "RATE_LIMITED": "Dhan rate limited the last connection test. Retry later.",
            "PROVIDER_ERROR": "Dhan could not complete the last connection test.",
            "DISABLED": "Dhan market-data access is disabled for this user.",
            "NOT_CONFIGURED": "Configure Dhan client ID and a current access token.",
        }.get(self.market_data_state)
        try:
            mi_ready, mi_state, mi_success = (
                self.market_intelligence.readiness()
                if self.market_intelligence is not None
                else (False, IntelligenceState.AUTH_REQUIRED, None)
            )
        except Exception:
            mi_ready, mi_state, mi_success = False, IntelligenceState.PROVIDER_ERROR, None
        mi_health = {
            IntelligenceState.AVAILABLE: "AVAILABLE",
            IntelligenceState.PARTIAL: "DEGRADED",
            IntelligenceState.STALE: "DEGRADED",
            IntelligenceState.AUTH_REQUIRED: "AUTH_REQUIRED",
            IntelligenceState.RATE_LIMITED: "RATE_LIMITED",
            IntelligenceState.UNAVAILABLE: "UNAVAILABLE",
            IntelligenceState.PROVIDER_ERROR: "DEGRADED",
        }[mi_state]
        scanner_last = max(
            (item for item in (real, synthetic) if item is not None),
            key=lambda item: aware(item.completed_at),
            default=None,
        )
        scanner_mode = (
            "SYNTHETIC"
            if scanner_last is None or scanner_last.provider != ProviderChoice.REAL.value
            else "LOCAL"
        )
        return (
            ProviderStatus(
                id="dhan",
                label="Dhan market data",
                enabled=dhan_ready,
                mode="REMOTE",
                health=cast(Any, dhan_health),
                role="MARKET_DATA",
                capabilities=(
                    "canonical-instrument-resolution",
                    "batch-quotes",
                    "daily-ohlcv",
                    "intraday-ohlcv",
                ),
                limitations=(
                    "access-tokens-expire-after-24-hours",
                    "bounded-internal-evidence-retention",
                ),
                last_success_at=aware(real.completed_at) if real else None,
                last_error=(
                    None
                    if dhan_ready
                    else (dhan_detail or self.market_data_error or "Dhan is not ready.")
                ),
            ),
            ProviderStatus(
                id="internal-scanner-v0",
                label="Internal Scanner V0",
                enabled=True,
                mode=cast(Any, scanner_mode),
                health="AVAILABLE",
                role="SCANNER",
                capabilities=("deterministic-scan", "five-profiles", "provider-neutral-series"),
                last_success_at=(
                    aware(scanner_last.completed_at) if scanner_last is not None else None
                ),
            ),
            ProviderStatus(
                id="tapetide",
                label="TapTide market intelligence",
                enabled=mi_ready,
                mode="REMOTE",
                health=cast(Any, mi_health),
                role="MARKET_INTELLIGENCE",
                capabilities=(
                    "market-pulse",
                    "india-vix",
                    "fii-dii",
                    "fpi-sector-flows",
                    "index-performance",
                    "market-news",
                    "corporate-events",
                ),
                limitations=("optional-enrichment", "does-not-authorize-candidate-admission"),
                last_success_at=mi_success,
                last_error=None
                if mi_ready
                else "Optional market intelligence is not connected; technical scans continue.",
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
            ProviderChoice.SYNTHETIC: "twf-native-synthetic-v1",
            ProviderChoice.REAL: "dhan-authoritative-market-data-v1",
        }[payload.provider.active]
        return ScanComparabilityDescriptor(
            criteria_fingerprint=criteria_fingerprint,
            profile_semantic_class=f"{payload.profile.lower()}.v1",
            direction=definition.direction,
            intent=payload.intent.value.lower(),
            horizon=selected_intent.horizon,
            observation_basis=(
                f"{definition.timeframe}.dhan-authoritative-v1"
                if payload.provider.active == ProviderChoice.REAL
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

    def with_series_evidence(
        self,
        match: ScanMatch,
        series: MarketSeries,
        at: datetime,
    ) -> ScanMatch:
        """Add normalized supporting facts from the exact scanner input series."""

        bars = series.bars
        close = Decimal(str(bars[-1].close))
        momentum = Decimal(str(series_measure("roc.10", bars))).quantize(Decimal("0.01"))
        rsi = Decimal(str(series_measure("rsi.14", bars))).quantize(Decimal("0.1"))
        relative_volume = Decimal(str(series_measure("relative_volume.20", bars))).quantize(
            Decimal("0.01")
        )
        polarity = (
            EvidencePolarity.POSITIVE
            if momentum > 0
            else (EvidencePolarity.NEGATIVE if momentum < 0 else EvidencePolarity.NEUTRAL)
        )

        def evidence_item(
            key: str,
            category: EvidenceCategory,
            observation_basis: str,
            measures: tuple[Measure, ...],
        ) -> DiscoveryEvidence:
            return DiscoveryEvidence(
                evidence_id=stable(f"series-{key}:{match.run_id}:{match.instrument.instrument_id}"),
                owner_id=self.owner_id,
                subject_id=match.instrument.instrument_id,
                category=category,
                polarity=polarity,
                observation_basis=observation_basis,
                observed_at=bars[-1].timestamp,
                source_data_time=bars[-1].timestamp,
                received_at=series.received_at or at,
                available_at=bars[-1].available_at,
                provenance=series.provenance,
                measures=measures,
                reason="normalized-market-series",
            )

        supporting = (
            evidence_item(
                "price",
                EvidenceCategory.INSTRUMENT_PRICE,
                f"{series.interval}.authoritative-close",
                (
                    Measure(name="close", value=close, unit=series.price_unit),
                    Measure(name="momentum.10", value=momentum, unit="percent"),
                ),
            ),
            evidence_item(
                "volume",
                EvidenceCategory.VOLUME_LIQUIDITY,
                f"{series.interval}.authoritative-volume",
                (
                    Measure(name="relative_volume.20", value=relative_volume, unit="ratio"),
                    Measure(
                        name="volume",
                        value=Decimal(str(bars[-1].volume or 0)),
                        unit="volume",
                    ),
                ),
            ),
            evidence_item(
                "technical",
                EvidenceCategory.TECHNICAL,
                f"{series.interval}.authoritative-indicators",
                (
                    Measure(name="rsi.14", value=rsi, unit="index"),
                    Measure(name="momentum.10", value=momentum, unit="percent"),
                ),
            ),
        )
        return match.model_copy(update={"evidence": (*match.evidence, *supporting)})

    async def run_scan(self, payload: ProductScanRequest) -> ScanResult:
        started = now_utc()
        active_provider = payload.provider.active
        payload = payload.model_copy(update={"provider": active_provider})
        if active_provider == ProviderChoice.REAL and (
            self.market_data is None or self.market_data_state != "READY"
        ):
            raise ProductFailure(409, "DHAN_NOT_READY")
        context = OperationContext(
            owner_id=self.owner_id,
            correlation=RequestContext(request_id=self.request_id),
            as_of=started,
        )
        interval = (
            "1d"
            if active_provider == ProviderChoice.SYNTHETIC
            else {
                HorizonChoice.INTRADAY: "15m",
                HorizonChoice.ONE_DAY: "1h",
                HorizonChoice.FIVE_DAYS: "1d",
                HorizonChoice.FIFTEEN_DAYS: "1d",
            }[payload.horizon]
        )
        source_mode = (
            SourceMode.SYNTHETIC
            if active_provider == ProviderChoice.SYNTHETIC
            else (SourceMode.EOD if interval == "1d" else SourceMode.LIVE_SNAPSHOT)
        )
        profile = ScanProfileReference(
            profile_id=stable(f"profile:{self.owner_id}:{payload.profile}"),
            owner_id=self.owner_id,
            applied_revision=1,
        )
        definition = build_profile(
            payload.profile,
            context,
            stable("definition:" + payload.profile),
            interval=interval,
            direction=intent_direction(payload.intent),
            source_mode=source_mode,
        )
        descriptor = self.comparison_descriptor(payload, definition, started)
        request_payload = payload.model_dump(mode="json", exclude={"idempotency_key"})
        request_digest = digest(request_payload)
        temporal = TemporalStore(self.session, self.owner_id)
        proposed_run_id = uuid4()
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
        progression = self.fixture_progression(active_provider)
        requested_identities = tuple(identity(symbol) for symbol in payload.universe)
        failures: dict[UUID, MarketDataErrorCode] = {}
        instruments: list[InstrumentIdentity] = []
        series_by_id: dict[UUID, MarketSeries] = {}

        try:
            if active_provider == ProviderChoice.SYNTHETIC:
                fixture_series = tuple(
                    market_series(item, started, progression) for item in requested_identities
                )
                source: MarketDataProvider = FixtureMarketDataProvider(fixture_series)
                instruments = list(
                    await source.resolve_instruments(
                        tuple(item.symbol for item in requested_identities)
                    )
                )
                for item in instruments:
                    series_by_id[item.instrument_id] = await source.get_ohlcv(
                        item, interval, as_of=started, count=320
                    )
            else:
                real_source = self.market_data
                if real_source is None or (
                    isinstance(real_source, DhanMarketDataProvider)
                    and not real_source.settings.configured
                ):
                    for item in requested_identities:
                        failures[item.instrument_id] = MarketDataErrorCode.AUTH_REQUIRED
                    instruments = list(requested_identities)
                else:
                    systemic: MarketDataErrorCode | None = None
                    for fallback in requested_identities:
                        if systemic is not None:
                            instruments.append(fallback)
                            failures[fallback.instrument_id] = systemic
                            continue
                        try:
                            resolved = (await real_source.resolve_instruments((fallback.symbol,)))[
                                0
                            ]
                            instruments.append(resolved)
                        except MarketDataFailure as exc:
                            instruments.append(fallback)
                            failures[fallback.instrument_id] = exc.code
                            if exc.code in {
                                MarketDataErrorCode.AUTH_REQUIRED,
                                MarketDataErrorCode.RATE_LIMITED,
                                MarketDataErrorCode.TIMEOUT,
                                MarketDataErrorCode.PROVIDER_ERROR,
                            }:
                                systemic = exc.code
                    for item in instruments:
                        if item.instrument_id in failures:
                            continue
                        try:
                            series_by_id[item.instrument_id] = await real_source.get_ohlcv(
                                item, interval, as_of=started, count=320
                            )
                        except MarketDataFailure as exc:
                            failures[item.instrument_id] = exc.code
        except BaseException as exc:
            temporal.fail_run(run_id, type(exc).__name__)
            raise

        successful = tuple(item for item in instruments if item.instrument_id in series_by_id)
        try:
            if successful:
                provider_result = await InternalScannerV0(
                    FixtureMarketSeriesSource(
                        tuple(series_by_id[item.instrument_id] for item in successful)
                    )
                ).scan(context, run, successful)
                matches = tuple(
                    self.with_series_evidence(
                        item, series_by_id[item.instrument.instrument_id], started
                    )
                    for item in provider_result.items
                )
            else:
                matches = ()
        except ScannerDataFailure:
            for item in successful:
                failures[item.instrument_id] = MarketDataErrorCode.INVALID_RESPONSE
            matches = ()

        intelligence: MarketIntelligenceBatch | None = None
        if active_provider == ProviderChoice.REAL and self.market_intelligence is not None:
            try:
                intelligence = await self.market_intelligence.observe(tuple(instruments))
            except Exception:
                intelligence = MarketIntelligenceBatch(
                    provider="tapetide",
                    state=IntelligenceState.PROVIDER_ERROR,
                    claims=(),
                    received_at=now_utc(),
                    failures=("provider-error",),
                )
        context_snapshot, context_evidence = self.market_context(
            started,
            payload.context_mode,
            tuple(instruments),
            run_id,
            intelligence=intelligence,
            real_mode=active_provider == ProviderChoice.REAL,
        )
        context_policy = self.effective_context_policy(payload)
        completed = now_utc()
        run_record = ScanRunRecord(
            id=run_id,
            user_id=self.owner_id,
            provider=active_provider.value,
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
            matched_series = series_by_id[match.instrument.instrument_id]
            chart_payload = archive_payload(matched_series, definition)
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
            if (
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
                temporal.append_observation(
                    admission=admission,
                    instrument=match.instrument,
                    kind=DiscoveryObservationKind.PRESENT,
                    coverage=EvaluationCoverage.EVALUATED,
                    reason="matched-not-admitted",
                    observed_at=max(item.observed_at for item in match.evidence),
                    source_data_time=min(source_times) if source_times else None,
                    source_sample_key=self.source_sample_key(match),
                    episode=None,
                    scan_match_id=match.scan_match_id,
                    evidence_ids=tuple(item.evidence_id for item in match.evidence),
                    context_id=context_snapshot.context_id,
                    provider=match.provenance.producer.provider,
                )

        successful_ids = set(series_by_id).difference(failures)
        for instrument_item in instruments:
            if instrument_item.instrument_id in match_instruments:
                continue
            provider_failure = failures.get(instrument_item.instrument_id)
            episode = temporal.episode_for_observation(
                admission.scope_id, instrument_item.instrument_id, admission.sequence
            )
            if provider_failure is None and episode is not None:
                self.close_elapsed_episode(episode, admission, started)
            temporal.append_observation(
                admission=admission,
                instrument=instrument_item,
                kind=(
                    DiscoveryObservationKind.NOT_EVALUATED
                    if provider_failure is not None
                    else DiscoveryObservationKind.ABSENT
                ),
                coverage=(
                    EvaluationCoverage.PROVIDER_UNAVAILABLE
                    if provider_failure is not None
                    else EvaluationCoverage.EVALUATED
                ),
                reason=(
                    f"market-data-{provider_failure.value.lower()}"
                    if provider_failure is not None
                    else "not-rediscovered"
                ),
                observed_at=started,
                source_data_time=(
                    series_by_id[instrument_item.instrument_id].bars[-1].timestamp
                    if instrument_item.instrument_id in series_by_id
                    else None
                ),
                source_sample_key=(
                    digest(
                        {
                            "instrument": str(instrument_item.instrument_id),
                            "cutoff": started.isoformat(),
                            "scope": str(admission.scope_id),
                        }
                    )
                    if provider_failure is None
                    else None
                ),
                episode=episode,
                context_id=context_snapshot.context_id,
                provider=("dhan" if active_provider == ProviderChoice.REAL else "twf-fixture"),
            )

        active_slots = tuple(
            self.session.scalars(
                select(DiscoveryActiveSlotRecord).where(
                    DiscoveryActiveSlotRecord.user_id == self.owner_id,
                    DiscoveryActiveSlotRecord.scope_id == admission.scope_id,
                )
            )
        )
        requested_ids = {item.instrument_id for item in instruments}
        for slot in active_slots:
            if slot.instrument_id in requested_ids:
                continue
            excluded_episode = self.session.get(DiscoveryEpisodeRecord, slot.episode_id)
            if excluded_episode is None or excluded_episode.user_id != self.owner_id:
                continue
            excluded_instrument = InstrumentIdentity.model_validate(
                excluded_episode.payload["episode"]["instrument"]
            )
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
                provider=("dhan" if active_provider == ProviderChoice.REAL else "twf-fixture"),
            )

        admission_summary = AdmissionSummary(
            match_count=len(matches),
            admitted_count=len(candidates),
            excluded_count=len(matches) - len(candidates),
            decisions=tuple(decisions),
        )
        evidence_lineage = None
        if active_provider == ProviderChoice.REAL:
            returned = tuple(
                item.symbol for item in instruments if item.instrument_id in successful_ids
            )
            missing = tuple(item.symbol for item in instruments if item.instrument_id in failures)
            states = set(failures.values())
            capability_state = (
                "available"
                if not failures
                else ("partial" if returned else next(iter(states)).value.lower())
            )
            received = max(
                (
                    item.received_at
                    for item in series_by_id.values()
                    if item.received_at is not None
                ),
                default=completed,
            )
            evidence_lineage = RealEvidenceLineage(
                evidence_provider="dhan",
                data_mode="AUTHORITATIVE_MARKET_DATA",
                requested_symbols=payload.universe,
                returned_symbols=returned,
                missing_symbols=missing,
                chunk_count=len(series_by_id),
                received_at=received,
                capability_state=capability_state,
                limitations=tuple(
                    dict.fromkeys(
                        [
                            *(
                                f"{symbol.lower()}-{failures[item.instrument_id].value.lower()}"
                                for symbol, item in zip(payload.universe, instruments, strict=True)
                                if item.instrument_id in failures
                            ),
                            *(
                                "live-bar-excluded"
                                for item in series_by_id.values()
                                if item.live_bar_excluded
                            ),
                        ]
                    )
                )[:16],
            )

        mi_limitations = (
            ()
            if intelligence is None or intelligence.state == IntelligenceState.AVAILABLE
            else (f"tapetide-{intelligence.state.value.lower()}",)
        )
        summary = ScanSummary(
            run_id=run_id,
            provider=active_provider,
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
                        *mi_limitations,
                        *(f"dhan-{code.value.lower()}" for code in failures.values()),
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
                "evaluated": [str(item) for item in successful_ids],
                "present": [str(item.instrument.instrument_id) for item in matches],
                "not_evaluated": [
                    *(str(item) for item in failures),
                    *(
                        str(slot.instrument_id)
                        for slot in active_slots
                        if slot.instrument_id not in requested_ids
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
        *,
        intelligence: MarketIntelligenceBatch | None = None,
        real_mode: bool = False,
    ) -> tuple[MarketContextSnapshot, tuple[DiscoveryEvidence, ...]]:
        if real_mode:
            batch = intelligence or MarketIntelligenceBatch(
                provider="tapetide",
                state=IntelligenceState.AUTH_REQUIRED,
                claims=(),
                received_at=at,
                failures=("not-connected",),
            )
            expected = (
                IntelligenceKind.MARKET_PULSE,
                IntelligenceKind.MARKET_VOLATILITY,
                IntelligenceKind.MARKET_FLOW,
                IntelligenceKind.SECTOR_FLOW,
                IntelligenceKind.INDEX_STRENGTH,
                IntelligenceKind.NEWS_SENTIMENT,
                IntelligenceKind.CORPORATE_EVENT,
            )
            by_kind = {claim.kind: claim for claim in batch.claims}
            real_dimensions = tuple(
                ContextDimension(
                    name=kind.value.lower().replace("_", "-"),
                    availability="PRESENT" if kind in by_kind else "UNAVAILABLE",
                    value="available" if kind in by_kind else None,
                    source="tapetide",
                    reason=None if kind in by_kind else f"tapetide-{batch.state.value.lower()}",
                )
                for kind in expected
            )
            present_count = len(by_kind)
            availability = (
                ContextAvailability.COMPLETE
                if present_count == len(expected)
                else (
                    ContextAvailability.PARTIAL
                    if present_count
                    else (
                        ContextAvailability.STALE
                        if batch.state == IntelligenceState.STALE
                        else ContextAvailability.UNAVAILABLE
                    )
                )
            )
            producer = ProducerIdentity(
                service_id="tapetide-market-intelligence",
                provider="tapetide",
                service_version="1",
                contract_version="sd.market-context.v1",
            )
            real_evidence: list[DiscoveryEvidence] = []
            category = {
                IntelligenceKind.SECTOR_FLOW: EvidenceCategory.SECTOR_INDUSTRY,
                IntelligenceKind.INDEX_STRENGTH: EvidenceCategory.SECTOR_INDUSTRY,
                IntelligenceKind.NEWS_SENTIMENT: EvidenceCategory.EVENT_NEWS,
                IntelligenceKind.CORPORATE_EVENT: EvidenceCategory.EVENT_NEWS,
            }
            for instrument in instruments:
                for claim in batch.claims:
                    prov = Provenance(
                        producer=producer,
                        source=SourceReference(
                            namespace="tapetide",
                            native_id=claim.provider_tool,
                            revision="normalized-mi-v1",
                        ),
                        mode=SourceMode.LIVE_SNAPSHOT,
                        observation_key=digest(
                            {
                                "tool": claim.provider_tool,
                                "subject": claim.subject,
                                "source_time": (
                                    claim.source_time.isoformat()
                                    if claim.source_time is not None
                                    else None
                                ),
                                "received_at": claim.received_at.isoformat(),
                            }
                        ),
                        transformation=RevisionRef(id="tapetide-claim-normalization", version="1"),
                        dependence_group="tapetide-market-intelligence",
                    )
                    real_evidence.append(
                        DiscoveryEvidence(
                            evidence_id=stable(
                                f"mi:{run_id}:{instrument.instrument_id}:{claim.kind.value}"
                            ),
                            owner_id=self.owner_id,
                            subject_id=instrument.instrument_id,
                            category=category.get(claim.kind, EvidenceCategory.MARKET_CONTEXT),
                            polarity=EvidencePolarity.NEUTRAL,
                            observation_basis=claim.kind.value.lower(),
                            observed_at=claim.source_time or claim.received_at,
                            source_data_time=claim.source_time,
                            received_at=claim.received_at,
                            available_at=claim.received_at,
                            provenance=prov,
                            measures=(
                                Measure(
                                    name="normalized-fact-count",
                                    value=Decimal(len(claim.values)),
                                    unit="count",
                                ),
                                Measure(
                                    name="context-kind",
                                    value=claim.kind.value,
                                    unit="category",
                                ),
                            ),
                            reason="optional-market-intelligence-context",
                        )
                    )
            source_times = tuple(
                claim.source_time for claim in batch.claims if claim.source_time is not None
            )
            snapshot_at = batch.received_at
            snapshot = MarketContextSnapshot(
                context_id=stable(f"context-snapshot:{run_id}"),
                owner_id=self.owner_id,
                observed_at=snapshot_at,
                source_data_time=max(source_times) if source_times else None,
                market="india-equities",
                session="UNKNOWN",
                availability=availability,
                dimensions=real_dimensions,
                producer="tapetide" if batch.claims else "none",
                producer_version="normalized-mi-v1",
                evidence_ids=tuple(item.evidence_id for item in real_evidence),
                limitations=tuple(
                    dict.fromkeys(
                        (
                            *batch.failures,
                            *(
                                ()
                                if batch.state == IntelligenceState.AVAILABLE
                                else (f"tapetide-{batch.state.value.lower()}",)
                            ),
                        )
                    )
                )[:16],
            )
            return snapshot, tuple(real_evidence)

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
            "Authoritative market evidence conflicts with the discovery predicate."
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
        authoritative_provider = match.provenance.source.namespace
        if authoritative_provider == "dhan":
            verification = EvidenceVerification.CONFIRMED
        elif authoritative_provider == "tradingview":
            # Historical records retain their original verification vocabulary.
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
            provider=(
                authoritative_provider
                if authoritative_provider in {"dhan", "tradingview"}
                else match.provenance.producer.provider
            ),
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

        # TradingView remains historical provenance only. It is never called by active runtime.
        if summary.provider == ProviderChoice.REAL_TRADINGVIEW:
            return unavailable_chart(
                mode=mode,
                state=(
                    EvidenceChartState.RETENTION_RESTRICTED
                    if mode == EvidenceChartMode.AS_SCANNED
                    else EvidenceChartState.CURRENT_UNAVAILABLE
                ),
                message=(
                    "Historical TradingView source bars were not retained; persisted numerical "
                    "evidence and provenance remain available."
                    if mode == EvidenceChartMode.AS_SCANNED
                    else "TradingView is decommissioned. Current evidence uses Dhan on new scans."
                ),
                match=match,
                summary=summary,
                source_class="PROVIDER_RESTRICTED",
                historical_chart_reconstructable=False,
                scan_bars_retained=False,
            )

        current: MarketSeries | None = None
        if mode == EvidenceChartMode.CURRENT:
            if summary.provider.active == ProviderChoice.REAL:
                if self.market_data is None:
                    return unavailable_chart(
                        mode=mode,
                        state=EvidenceChartState.AUTH_REQUIRED,
                        message="Current chart requires configured Dhan market-data credentials.",
                        match=match,
                        summary=summary,
                        source_class="PROVIDER_RESTRICTED",
                        historical_chart_reconstructable=True,
                        scan_bars_retained=True,
                    )
                try:
                    archived_series = MarketSeries.model_validate(archive.payload["series"])
                    current = await self.market_data.get_ohlcv(
                        match.instrument,
                        archived_series.interval,
                        as_of=now_utc(),
                        count=320,
                    )
                except MarketDataFailure as exc:
                    state = {
                        MarketDataErrorCode.AUTH_REQUIRED: EvidenceChartState.AUTH_REQUIRED,
                        MarketDataErrorCode.RATE_LIMITED: EvidenceChartState.RATE_LIMITED,
                        MarketDataErrorCode.INSTRUMENT_NOT_FOUND: EvidenceChartState.EXACT_MISSING,
                        MarketDataErrorCode.AMBIGUOUS_INSTRUMENT: EvidenceChartState.EXACT_MISSING,
                    }.get(exc.code, EvidenceChartState.CURRENT_UNAVAILABLE)
                    return unavailable_chart(
                        mode=mode,
                        state=state,
                        message={
                            EvidenceChartState.AUTH_REQUIRED: (
                                "Current chart requires configured Dhan market-data credentials."
                            ),
                            EvidenceChartState.RATE_LIMITED: (
                                "Dhan rate limited the current chart request. Retry later."
                            ),
                            EvidenceChartState.EXACT_MISSING: (
                                "Dhan could not resolve this exact provider-native instrument."
                            ),
                            EvidenceChartState.CURRENT_UNAVAILABLE: (
                                "Current Dhan OHLCV is unavailable for this instrument."
                            ),
                        }[state],
                        match=match,
                        summary=summary,
                        source_class="PROVIDER_RESTRICTED",
                        historical_chart_reconstructable=True,
                        scan_bars_retained=True,
                    )
                except (KeyError, TypeError, ValueError):
                    return unavailable_chart(
                        mode=mode,
                        state=EvidenceChartState.RECONSTRUCTION_FAILED,
                        message="Archived evidence metadata failed integrity checks.",
                        match=match,
                        summary=summary,
                        source_class="LEGACY_UNKNOWN",
                        scan_bars_retained=True,
                    )
            else:
                current = market_series(
                    match.instrument,
                    now_utc(),
                    self.fixture_progression(ProviderChoice.SYNTHETIC),
                )
        try:
            return build_chart(
                mode=mode,
                match=match,
                summary=summary,
                archived_payload=archive.payload,
                current_series=current,
            )
        except (KeyError, TypeError, ValueError, DataUnavailable):
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
