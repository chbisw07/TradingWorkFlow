"""Integrated Sprint-2 Scan & Discover use cases with explicit bounded degradation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, select, update
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
    DiscoveryRelevance,
    DiscoverySnapshot,
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
    ScanDefinition,
    ScanMatch,
    ScanProfileReference,
    ScanRun,
    SourceMode,
    SourceReference,
    ToleranceRule,
    UnderlyingIdentity,
)
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
    CandidateDetail,
    CandidateSummary,
    ContextAvailability,
    ContextDimension,
    DiscoverySettings,
    HorizonChoice,
    IntentChoice,
    LifecycleAction,
    LLMExplanation,
    MarketContextSnapshot,
    PaginatedCandidates,
    ProductScanRequest,
    ProviderChoice,
    ProviderStatus,
    RelevanceContribution,
    RelevanceExplanation,
    ScanMatchView,
    ScanResult,
    ScanSummary,
    SnapshotView,
    ToleranceAssessment,
    ToleranceDimensionAssessment,
)
from twf.discovery.providers import OperationContext
from twf.infrastructure.discovery import (
    DiscoveryEpisodeRecord,
    DiscoveryExplanationRecord,
    DiscoverySettingsRecord,
    DiscoverySnapshotRecord,
    DiscoveryTransitionRecord,
    MarketContextRecord,
    ScanMatchRecord,
    ScanRunRecord,
)
from twf.integrations.contracts import RequestContext

POLICY = RevisionRef(id="deterministic-relevance-v1", version="1")
TRANSFORMATION = RevisionRef(id="sprint2-product-normalization", version="1")
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


INDEX_SYMBOLS = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"})


@dataclass(frozen=True)
class SyntheticInstrumentFixture:
    base_price: Decimal
    daily_trend: Decimal
    relative_volume: Decimal
    technical_evidence: bool
    tradingview_match: bool
    final_move: Decimal | None = None


SYNTHETIC_FIXTURES: dict[str, SyntheticInstrumentFixture] = {
    "RELIANCE": SyntheticInstrumentFixture(
        Decimal("2846.40"), Decimal("0.42"), Decimal("1.90"), False, True, Decimal("-0.30")
    ),
    "MCX": SyntheticInstrumentFixture(
        Decimal("3146.80"), Decimal("0.74"), Decimal("2.60"), True, True
    ),
    "HDFCBANK": SyntheticInstrumentFixture(
        Decimal("1684.25"), Decimal("-0.16"), Decimal("0.82"), False, False
    ),
    "INFY": SyntheticInstrumentFixture(
        Decimal("1568.60"), Decimal("0.24"), Decimal("1.65"), False, True
    ),
    "BSE": SyntheticInstrumentFixture(
        Decimal("2488.15"), Decimal("-0.05"), Decimal("1.10"), False, False
    ),
    "NIFTY": SyntheticInstrumentFixture(
        Decimal("24520.30"), Decimal("0.55"), Decimal("1.72"), True, True
    ),
    "BANKNIFTY": SyntheticInstrumentFixture(
        Decimal("51780.10"), Decimal("-0.08"), Decimal("0.96"), False, False
    ),
    "TCS": SyntheticInstrumentFixture(
        Decimal("3984.50"), Decimal("0.31"), Decimal("1.78"), True, True
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
        technical_evidence=fixture.technical_evidence or fixture.tradingview_match,
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
        cycle = Decimal(((index + seed) % 7) - 3) * Decimal("0.08")
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
    def __init__(self, session: Session, owner_id: UUID, request_id: str | None) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id or uuid4().hex

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
                polarity=(
                    EvidencePolarity.POSITIVE
                    if fixture.daily_trend > 0
                    else EvidencePolarity.NEUTRAL
                ),
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
        return (
            ProviderStatus(
                id=ProviderChoice.INTERNAL,
                label="Internal Scanner V0",
                enabled=True,
                mode="LOCAL_SYNTHETIC",
                health="AVAILABLE",
                capabilities=("deterministic-scan", "five-profiles", "offline-validation"),
                last_success_at=aware(internal.completed_at) if internal else None,
            ),
            ProviderStatus(
                id=ProviderChoice.TRADINGVIEW_SYNTHETIC,
                label="TradingView exact-batch validation",
                enabled=True,
                mode="SYNTHETIC_VALIDATION",
                health="AVAILABLE",
                capabilities=("exact-universe", "synthetic-ci", "provider-lineage"),
                last_success_at=aware(tradingview.completed_at) if tradingview else None,
                last_error="Live exact-row proof remains deferred after provider rate limiting.",
            ),
        )

    async def run_scan(self, payload: ProductScanRequest) -> ScanResult:
        started = now_utc()
        instruments = tuple(identity(symbol) for symbol in payload.universe)
        context = OperationContext(
            owner_id=self.owner_id,
            correlation=RequestContext(request_id=self.request_id),
            as_of=started,
        )
        run_id = uuid4()
        progression = self.fixture_progression(payload.provider)
        profile = ScanProfileReference(
            profile_id=stable(f"profile:{self.owner_id}:{payload.profile}"),
            owner_id=self.owner_id,
            applied_revision=1,
        )
        if payload.provider == ProviderChoice.INTERNAL:
            definition = build_profile(
                payload.profile,
                context,
                stable("definition:" + payload.profile),
                interval="1d",
            )
            run = ScanRun(
                run_id=run_id,
                owner_id=self.owner_id,
                request_id=self.request_id,
                profile=profile,
                definition=definition,
                as_of=started,
            )
            series = tuple(market_series(item, started, progression) for item in instruments)
            source = FixtureMarketSeriesSource(series)
            result = await InternalScannerV0(source).scan(context, run, instruments)
            matches = tuple(
                self.with_supporting_fixture_evidence(item, started, progression, started)
                for item in result.items
            )
        else:
            definition = ScanDefinition(
                definition_id=stable("definition:tradingview-exact-validation"),
                revision=1,
                criteria=(
                    Criterion(
                        metric="close",
                        operator=Comparison.GT,
                        threshold=Decimal("0"),
                        unit="price",
                    ),
                ),
                timeframe="provider-current",
                source_mode=SourceMode.SYNTHETIC,
                required_capabilities=("sd.scan",),
            )
            run = ScanRun(
                run_id=run_id,
                owner_id=self.owner_id,
                request_id=self.request_id,
                profile=profile,
                definition=definition,
                as_of=started,
            )
            matches = tuple(
                self.synthetic_tradingview_match(run, item, started, progression)
                for item in instruments
                if synthetic_fixture(item.symbol, progression).tradingview_match
            )
        context_snapshot, context_evidence = self.market_context(
            started, payload.context_mode, instruments, run_id
        )
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
        for match in matches:
            self.session.add(
                ScanMatchRecord(
                    id=match.scan_match_id,
                    user_id=self.owner_id,
                    run_id=run_id,
                    instrument_id=match.instrument.instrument_id,
                    payload=match.model_dump(mode="json"),
                )
            )
            extra = tuple(
                item
                for item in context_evidence
                if item.subject_id == match.instrument.instrument_id
            )
            candidates.append(
                self.capture_candidate(
                    match,
                    payload.intent,
                    payload.horizon,
                    (*match.evidence, *extra),
                    started,
                    context_snapshot,
                    payload.include_llm,
                )
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
            context_availability=context_snapshot.availability,
            degraded=tuple(context_snapshot.limitations),
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
        self.commit()
        return ScanResult(
            summary=summary,
            matches=tuple(self.match_view(item) for item in matches),
            candidates=tuple(candidates),
            market_context=context_snapshot,
        )

    def synthetic_tradingview_match(
        self,
        run: ScanRun,
        instrument: InstrumentIdentity,
        at: datetime,
        progression: int,
    ) -> ScanMatch:
        source = provenance(
            TRADINGVIEW_SYNTHETIC, instrument, at, "tradingview:" + instrument.symbol
        )
        fixture = synthetic_fixture(instrument.symbol, progression)
        series = market_series(instrument, at, progression)
        evidence = (
            DiscoveryEvidence(
                evidence_id=stable(f"tv-scan:{run.run_id}:{instrument.instrument_id}"),
                owner_id=self.owner_id,
                subject_id=instrument.instrument_id,
                category=EvidenceCategory.PROVIDER_SCAN,
                polarity=EvidencePolarity.POSITIVE,
                observation_basis="provider-current",
                observed_at=at,
                source_data_time=None,
                received_at=at,
                available_at=at,
                provenance=source,
                measures=(
                    Measure(
                        name="close",
                        value=Decimal(str(series.bars[-1].close)),
                        unit="INR",
                    ),
                    Measure(
                        name="momentum.10",
                        value=Decimal(str(series_measure("roc.10", series.bars))).quantize(
                            Decimal("0.01")
                        ),
                        unit="percent",
                    ),
                    Measure(
                        name="relative_volume.20",
                        value=fixture.relative_volume,
                        unit="ratio",
                    ),
                    Measure(name="matched", value=True, unit="boolean"),
                ),
                reason="synthetic-validation-no-live-provider-call",
            ),
            *self.supporting_fixture_evidence(
                run.run_id,
                instrument,
                at,
                TRADINGVIEW_SYNTHETIC,
                progression,
                None,
            ),
        )
        return ScanMatch(
            scan_match_id=stable(f"tv-match:{run.run_id}:{instrument.instrument_id}"),
            run_id=run.run_id,
            owner_id=self.owner_id,
            instrument=instrument,
            definition_id=run.definition.definition_id,
            definition_revision=run.definition.revision,
            profile=run.profile,
            configuration_fingerprint=run.configuration_fingerprint,
            evidence=evidence,
            provenance=source,
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
    ) -> tuple[DiscoveryRelevance, RelevanceExplanation]:
        categories = {item.category for item in evidence if item.availability == "PRESENT"}
        factors = (
            ("provider-scan", EvidenceCategory.PROVIDER_SCAN, Decimal("0.45")),
            ("price", EvidenceCategory.INSTRUMENT_PRICE, Decimal("0.20")),
            ("market-context", EvidenceCategory.MARKET_CONTEXT, Decimal("0.20")),
            ("technical", EvidenceCategory.TECHNICAL, Decimal("0.15")),
        )
        contributions: list[RelevanceContribution] = []
        missing: list[str] = []
        score = Decimal(0)
        for name, category, weight in factors:
            value = Decimal(1) if category in categories else Decimal(0)
            contribution = value * weight
            score += contribution
            if not value:
                missing.append(name)
            contributions.append(
                RelevanceContribution(
                    factor=name,
                    value=value,
                    weight=weight,
                    contribution=contribution,
                    reason=("Evidence present" if value else "Evidence unavailable"),
                )
            )
        stale = any(item.source_data_time is None for item in evidence)
        freshness_penalty = Decimal("0.05") if stale else Decimal(0)
        horizon_adjustment = (
            Decimal("0.03")
            if horizon in {HorizonChoice.FIVE_DAYS, HorizonChoice.FIFTEEN_DAYS}
            and EvidenceCategory.MARKET_CONTEXT in categories
            else Decimal(0)
        )
        score = max(Decimal(0), min(Decimal(1), score - freshness_penalty + horizon_adjustment))
        coverage = Decimal(len(categories & {item[1] for item in factors})) / Decimal(len(factors))
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
            missing=tuple(missing),
            freshness_penalty=freshness_penalty,
            horizon_adjustment=horizon_adjustment,
        )
        return relevance, explanation

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

    def capture_candidate(
        self,
        match: ScanMatch,
        intent_choice: IntentChoice,
        horizon_choice: HorizonChoice,
        evidence: tuple[DiscoveryEvidence, ...],
        at: datetime,
        context: MarketContextSnapshot,
        include_llm: bool,
    ) -> CandidateSummary:
        existing = self.session.scalar(
            select(DiscoveryEpisodeRecord)
            .where(
                DiscoveryEpisodeRecord.user_id == self.owner_id,
                DiscoveryEpisodeRecord.instrument_id == match.instrument.instrument_id,
                DiscoveryEpisodeRecord.intent_key == intent_choice.value,
                DiscoveryEpisodeRecord.horizon_key == horizon_choice.value,
                DiscoveryEpisodeRecord.state.not_in(TERMINAL),
            )
            .order_by(DiscoveryEpisodeRecord.opened_at.desc())
        )
        previous: DiscoveryEpisodeRecord | None = None
        if existing is not None:
            stored = existing.payload["episode"]
            if at >= datetime.fromisoformat(stored["window"]["ends_at"]):
                existing.state = DiscoveryLifecycleState.EXPIRED.value
                existing.revision += 1
                existing.updated_at = at
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
                        DiscoveryEpisodeRecord.state.in_(TERMINAL),
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
                policy_series=POLICY,
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
                opened_at=at,
                updated_at=at,
                payload={"episode": episode.model_dump(mode="json")},
            )
            self.session.add(record)
            self.session.flush()
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
        if prior_rows:
            previous_snapshot = DiscoverySnapshot.model_validate(prior_rows[-1].payload["snapshot"])
            known = {item.evidence_id for item in previous_snapshot.evidence}
            evidence = (
                *previous_snapshot.evidence,
                *(item for item in evidence if item.evidence_id not in known),
            )
        relevance, explanation = self.relevance(evidence, horizon_choice, self.settings())
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
            source_data_time=min(cast(datetime, item) for item in source_times)
            if all(source_times)
            else None,
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
        lifecycle = (
            DiscoveryLifecycleState.CURRENT if sequence >= 2 else DiscoveryLifecycleState.NEW
        )
        if prior_rows and tolerance.state == "BREACHED":
            prior_tolerance = ToleranceAssessment.model_validate(
                prior_rows[-1].payload["tolerance"]
            )
            if prior_tolerance.state == "BREACHED":
                lifecycle = DiscoveryLifecycleState.DEFUNCT
        if (
            context.availability in {ContextAvailability.STALE, ContextAvailability.UNAVAILABLE}
            and sequence >= 2
        ):
            lifecycle = DiscoveryLifecycleState.STALE
        snapshot_payload = {
            "snapshot": snapshot.model_dump(mode="json"),
            "lifecycle": lifecycle.value,
            "relevance_explanation": explanation.model_dump(mode="json"),
            "tolerance": tolerance.model_dump(mode="json"),
            "context_id": str(context.context_id),
        }
        self.session.add(
            DiscoverySnapshotRecord(
                id=snapshot.snapshot_id,
                episode_id=record.id,
                user_id=self.owner_id,
                sequence=sequence,
                observed_at=snapshot.observed_at,
                payload=snapshot_payload,
            )
        )
        old_state = record.state
        record.snapshot_count = sequence
        record.state = (
            lifecycle.value
            if lifecycle != DiscoveryLifecycleState.STALE
            else DiscoveryLifecycleState.CURRENT.value
        )
        record.revision += 1 if sequence > 1 else 0
        record.updated_at = at
        episode_payload = {
            **episode.model_dump(mode="json"),
            "head_snapshot_id": str(snapshot.snapshot_id),
            "evaluated_at": at.isoformat(),
            "revision": record.revision,
            "lifecycle": record.state,
        }
        record.payload = {"episode": episode_payload}
        if old_state != record.state:
            self.session.add(
                DiscoveryTransitionRecord(
                    episode_id=record.id,
                    user_id=self.owner_id,
                    revision=record.revision,
                    occurred_at=at,
                    payload={
                        "from_state": old_state,
                        "to_state": record.state,
                        "reason": (
                            "tolerance-confirmed"
                            if lifecycle == DiscoveryLifecycleState.DEFUNCT
                            else (
                                "comparable-observation" if sequence >= 2 else "first-observation"
                            )
                        ),
                        "rule": "deterministic-lifecycle-v1",
                        "snapshot_id": str(snapshot.snapshot_id),
                    },
                )
            )
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
            return "20-day high exceeded with volume"
        if name == "roc.10":
            return f"10-day momentum {numeric:+.1f}%"
        if name == "rsi.14":
            return f"RSI {numeric:.0f} within profile range"
        if name == "close_sma20_gap":
            return f"Close versus 20-day average {numeric:+.1f}%"
        if name == "close_sma50_gap":
            return f"Close above 50-day average {numeric:+.1f}%"
        if name == "sma50_sma200_gap":
            return f"50-day trend above 200-day trend by {numeric:.1f}%"
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
        source_times = [item.source_data_time for item in match.evidence]
        source_data_time = (
            max(cast(datetime, item) for item in source_times)
            if source_times and all(source_times)
            else None
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
        snapshot = DiscoverySnapshot.model_validate(payload["snapshot"])
        explanation = RelevanceExplanation.model_validate(payload["relevance_explanation"])
        tolerance = ToleranceAssessment.model_validate(payload["tolerance"])
        sources = tuple(sorted({item.provenance.producer.provider for item in snapshot.evidence}))
        return CandidateSummary(
            candidate_id=episode.candidate_id,
            episode_id=episode.id,
            revision=episode.revision,
            instrument=snapshot.instrument,
            intent=IntentChoice(episode.intent_key),
            horizon=HorizonChoice(episode.horizon_key),
            relevance=snapshot.relevance,
            relevance_explanation=explanation,
            tolerance=tolerance,
            lifecycle=DiscoveryLifecycleState(
                DiscoveryLifecycleState.STALE.value
                if episode.state == DiscoveryLifecycleState.CURRENT.value
                and payload["lifecycle"] == DiscoveryLifecycleState.STALE.value
                else episode.state
            ),
            freshness=(
                FreshnessState.UNKNOWN
                if snapshot.source_data_time is None
                else FreshnessState.FRESH
            ),
            snapshot_count=episode.snapshot_count,
            provider_sources=sources,
            updated_at=aware(episode.updated_at),
        )

    def candidates(self, limit: int, offset: int) -> PaginatedCandidates:
        query = select(DiscoveryEpisodeRecord).where(
            DiscoveryEpisodeRecord.user_id == self.owner_id
        )
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = tuple(
            self.session.scalars(
                query.order_by(DiscoveryEpisodeRecord.updated_at.desc()).offset(offset).limit(limit)
            )
        )
        return PaginatedCandidates(
            items=tuple(self.summary(row) for row in rows),
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
        return CandidateDetail(
            **head.model_dump(),
            snapshots=tuple(views),
            transitions=transitions,
            explanations=explanations,
            context=context,
            previous_episode_id=episode.previous_episode_id,
        )

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
            target = DiscoveryLifecycleState.CURRENT
        else:
            raise ProductFailure(422, "INVALID_TRANSITION")
        episode.state = target.value
        episode.revision += 1
        episode.updated_at = now_utc()
        stored = episode.payload["episode"]
        stored["lifecycle"] = target.value
        stored["revision"] = episode.revision
        stored["evaluated_at"] = episode.updated_at.isoformat()
        if target == DiscoveryLifecycleState.REJECTED:
            stored["rejection_reason"] = "USER_DISMISSED"
        episode.payload = {"episode": stored}
        self.session.add(
            DiscoveryTransitionRecord(
                episode_id=episode.id,
                user_id=self.owner_id,
                revision=episode.revision,
                occurred_at=episode.updated_at,
                payload={
                    "from_state": old,
                    "to_state": target.value,
                    "reason": reason,
                    "rule": "owner-lifecycle-action-v1",
                },
            )
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
