"""Native deterministic ScanProvider over injected offline series; fail-fast batches."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field

from twf.discovery.domain import (
    DiscoveryEvidence,
    EvidenceCategory,
    EvidencePolarity,
    Instant,
    InstrumentIdentity,
    Measure,
    Provenance,
    RevisionRef,
    ScanMatch,
    ScanRun,
    SourceMode,
    digest,
)
from twf.discovery.internal_scanner.conditions import (
    METRICS,
    OPERATORS,
    compare,
    measure,
    supported,
)
from twf.discovery.internal_scanner.market_series import (
    INTERVAL_SECONDS,
    MAX_INSTRUMENTS,
    DataReason,
    DataUnavailable,
    MarketSeries,
    MarketSeriesSource,
)
from twf.discovery.internal_scanner.profiles import IDENTITY, PROFILE_NAMES
from twf.discovery.providers import (
    DomainErrorCode,
    OperationContext,
    ProviderAccess,
    ProviderBatch,
    ProviderFailure,
    ProviderHealth,
    ProviderManifest,
)
from twf.integrations.contracts import Contract, DeploymentMode, ErrorCode, Health


def identity(text: str) -> UUID:
    return uuid5(NAMESPACE_URL, "twf-internal-scanner-v0:" + text)


class ScannerDataFailure(ProviderFailure):
    """Safe per-subject cause for direct calls; common guard retains canonical error code."""

    def __init__(self, failure: ProviderFailure, instrument_id: UUID, reason: DataReason) -> None:
        self.instrument_id = instrument_id
        self.reason = reason
        super().__init__(failure.error)


class SeriesCapture(Contract):
    instrument: InstrumentIdentity
    provenance: Provenance
    adjustment: RevisionRef
    session_basis: RevisionRef
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    completed_bars: int
    source_data_time: Instant


class ScanExecution(Contract):
    run: ScanRun
    universe: tuple[InstrumentIdentity, ...]
    universe_fingerprint: str
    started_at: Instant
    completed_at: Instant
    captures: tuple[SeriesCapture, ...]
    result: ProviderBatch[ScanMatch]

    @property
    def result_count(self) -> int:
        return len(self.result.items)


def clock() -> datetime:
    return datetime.now(UTC)


class InternalScannerV0:
    mode = DeploymentMode.LOCAL
    supported_profiles = PROFILE_NAMES
    manifest = ProviderManifest(
        identity=IDENTITY,
        capabilities=("sd.scan",),
        source_modes=(SourceMode.SYNTHETIC,),
        max_items=MAX_INSTRUMENTS,
        supported_metrics=tuple(METRICS),
        supported_operators=OPERATORS,
        supported_timeframes=tuple(INTERVAL_SECONDS),
    )

    def __init__(self, source: MarketSeriesSource, *, now: Callable[[], datetime] = clock) -> None:
        self.source = source
        self.now = now

    async def health(self, context: OperationContext) -> ProviderHealth:
        # This is local implementation availability, not a dataset-coverage claim.
        return ProviderHealth(
            identity=IDENTITY,
            request_id=context.correlation.request_id,
            health=Health.AVAILABLE,
            as_of=context.as_of,
            source_mode=SourceMode.SYNTHETIC,
        )

    def validate(
        self, context: OperationContext, run: ScanRun, instruments: tuple[InstrumentIdentity, ...]
    ) -> None:
        if (
            run.owner_id != context.owner_id
            or run.request_id != context.correlation.request_id
            or run.as_of != context.as_of
            or len(instruments) > MAX_INSTRUMENTS
            or len({i.instrument_id for i in instruments}) != len(instruments)
        ):
            raise ProviderAccess.failure(self, context, DomainErrorCode.INVALID_REQUEST)
        definition = run.definition
        if (
            definition.timeframe not in INTERVAL_SECONDS
            or definition.source_mode != SourceMode.SYNTHETIC
            or set(definition.required_capabilities) != {"sd.scan"}
            or any(not supported(c) for c in definition.criteria)
        ):
            raise ProviderAccess.failure(self, context, ErrorCode.UNSUPPORTED_CAPABILITY)

    async def scan(
        self, context: OperationContext, run: ScanRun, instruments: tuple[InstrumentIdentity, ...]
    ) -> ProviderBatch[ScanMatch]:
        return (await self.scan_with_report(context, run, instruments)).result

    async def scan_with_report(
        self, context: OperationContext, run: ScanRun, instruments: tuple[InstrumentIdentity, ...]
    ) -> ScanExecution:
        self.validate(context, run, instruments)
        started = self.now()
        matches: list[ScanMatch] = []
        captures: list[SeriesCapture] = []
        for instrument in sorted(instruments, key=lambda i: i.instrument_id.hex):
            await asyncio.sleep(0)  # Cancellation/deadline checkpoint between bounded CPU work.
            try:
                raw = await self.source.read(context, instrument, run.definition.timeframe)
                series = MarketSeries.model_validate(raw.model_dump())
                if series.instrument != instrument or series.interval != run.definition.timeframe:
                    raise DataUnavailable(DataReason.MALFORMED_SERIES)
                bars = series.at(context.as_of)
                if not bars:
                    raise DataUnavailable(DataReason.INSUFFICIENT_HISTORY)
                values = tuple(measure(c.metric, bars) for c in run.definition.criteria)
                flags = tuple(
                    compare(v, c) for v, c in zip(values, run.definition.criteria, strict=True)
                )
                input_digest = digest(
                    {
                        "instrument": instrument.model_dump(mode="json"),
                        "interval": series.interval,
                        "price_unit": series.price_unit,
                        "adjustment": series.adjustment.model_dump(mode="json"),
                        "session": series.session_basis.model_dump(mode="json"),
                        "source": series.provenance.model_dump(mode="json"),
                        "bars": [b.model_dump(mode="json") for b in bars],
                    }
                )
                captures.append(
                    SeriesCapture(
                        instrument=instrument,
                        provenance=series.provenance,
                        adjustment=series.adjustment,
                        session_basis=series.session_basis,
                        input_digest=input_digest,
                        completed_bars=len(bars),
                        source_data_time=bars[-1].timestamp,
                    )
                )
                matched = all(flags) if run.definition.combination == "ALL" else any(flags)
                if not matched:
                    continue
                basis_version = digest(
                    {
                        "algorithm": "internal-v0.1",
                        "interval": series.interval,
                        "adjustment": series.adjustment.model_dump(mode="json"),
                        "session": series.session_basis.model_dump(mode="json"),
                        "price_unit": series.price_unit,
                    }
                )
                provenance = Provenance(
                    producer=IDENTITY,
                    source=series.provenance.source,
                    mode=SourceMode.SYNTHETIC,
                    observation_key=input_digest,
                    transformation=RevisionRef(id="internal-v0", version=basis_version),
                    dependence_group=series.provenance.dependence_group,
                )
                evidence: list[DiscoveryEvidence] = []
                for index, (criterion, value, flag) in enumerate(
                    zip(run.definition.criteria, values, flags, strict=True)
                ):
                    evidence.append(
                        DiscoveryEvidence(
                            evidence_id=identity(
                                str(context.owner_id)
                                + str(instrument.instrument_id)
                                + input_digest
                                + run.configuration_fingerprint
                                + str(index)
                                + context.as_of.isoformat()
                            ),
                            owner_id=context.owner_id,
                            subject_id=instrument.instrument_id,
                            category=EvidenceCategory.PROVIDER_SCAN,
                            polarity=EvidencePolarity.NEUTRAL,
                            observation_basis=f"{series.interval}.{index}.{criterion.metric}",
                            observed_at=bars[-1].timestamp,
                            source_data_time=bars[-1].timestamp,
                            available_at=max(b.available_at for b in bars),
                            received_at=context.as_of,
                            provenance=provenance,
                            measures=(
                                Measure(
                                    name=criterion.metric,
                                    value=Decimal(str(value)),
                                    unit=criterion.unit,
                                ),
                                Measure(
                                    name="threshold", value=criterion.threshold, unit=criterion.unit
                                ),
                                Measure(
                                    name="operator", value=criterion.operator.value, unit="category"
                                ),
                                Measure(name="matched", value=flag, unit="boolean"),
                                Measure(
                                    name="price-unit", value=series.price_unit, unit="category"
                                ),
                            ),
                        )
                    )
                # Preserve the actual input producer in addition to the calculating adapter.
                evidence.append(
                    DiscoveryEvidence(
                        evidence_id=identity(
                            str(context.owner_id)
                            + input_digest
                            + "input"
                            + context.as_of.isoformat()
                        ),
                        owner_id=context.owner_id,
                        subject_id=instrument.instrument_id,
                        category=EvidenceCategory.INSTRUMENT_PRICE,
                        polarity=EvidencePolarity.NEUTRAL,
                        observation_basis=series.interval + ".input",
                        observed_at=bars[-1].timestamp,
                        source_data_time=bars[-1].timestamp,
                        available_at=max(b.available_at for b in bars),
                        received_at=context.as_of,
                        provenance=Provenance.model_validate(
                            {**series.provenance.model_dump(), "observation_key": input_digest}
                        ),
                        measures=(
                            Measure(
                                name="close",
                                value=Decimal(str(bars[-1].close)),
                                unit=series.price_unit,
                            ),
                            Measure(name="input-digest", value=input_digest, unit="digest"),
                        ),
                    )
                )
                matches.append(
                    ScanMatch(
                        scan_match_id=identity(
                            str(run.run_id)
                            + str(instrument.instrument_id)
                            + run.configuration_fingerprint
                            + input_digest
                        ),
                        run_id=run.run_id,
                        owner_id=context.owner_id,
                        instrument=instrument,
                        definition_id=run.definition.definition_id,
                        definition_revision=run.definition.revision,
                        profile=run.profile,
                        configuration_fingerprint=run.configuration_fingerprint,
                        evidence=tuple(evidence),
                        provenance=provenance,
                    )
                )
            except DataUnavailable as exc:
                raise ScannerDataFailure(
                    ProviderAccess.failure(self, context, ErrorCode.INVALID_RESPONSE),
                    instrument.instrument_id,
                    exc.reason,
                ) from None
            except Exception:
                raise ScannerDataFailure(
                    ProviderAccess.failure(self, context, ErrorCode.INVALID_RESPONSE),
                    instrument.instrument_id,
                    DataReason.MALFORMED_SERIES,
                ) from None
        result = ProviderBatch[ScanMatch](
            identity=IDENTITY,
            owner_id=context.owner_id,
            request_id=context.correlation.request_id,
            as_of=context.as_of,
            source_mode=SourceMode.SYNTHETIC,
            completeness="COMPLETE",
            items=tuple(matches),
        )
        return ScanExecution(
            run=run,
            universe=instruments,
            universe_fingerprint=digest(sorted(i.model_dump_json() for i in instruments)),
            started_at=started,
            completed_at=self.now(),
            captures=tuple(captures),
            result=result,
        )
