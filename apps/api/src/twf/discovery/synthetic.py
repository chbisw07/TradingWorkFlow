"""Finite fabricated fixtures behind S&D ports. No prices, networks, broker or LLM imports."""

from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from twf.discovery.domain import (
    CandidateInput,
    DiscoveryEvidence,
    EvidenceCategory,
    EvidencePolarity,
    InstrumentIdentity,
    Measure,
    ProducerIdentity,
    Provenance,
    RevisionRef,
    ScanMatch,
    ScanRun,
    SourceMode,
    SourceReference,
    UnderlyingIdentity,
)
from twf.discovery.providers import (
    DomainErrorCode,
    OperationContext,
    ProviderAccess,
    ProviderBatch,
    ProviderHealth,
    ProviderManifest,
)
from twf.integrations.contracts import DeploymentMode, ErrorCode, Health


def fixture_id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, "twf-sd-synthetic-v1:" + value)


def fixture_instruments() -> tuple[InstrumentIdentity, ...]:
    return tuple(
        InstrumentIdentity(
            instrument_id=fixture_id("listing-" + symbol),
            underlying=UnderlyingIdentity(
                underlying_id=fixture_id("subject-" + symbol),
                source=SourceReference(namespace="twf-fixture", native_id=symbol, revision="1"),
                mapping=RevisionRef(id="synthetic-mapping", version="1"),
            ),
            native=SourceReference(
                namespace="twf-fixture", native_id="SIM:" + symbol, revision="1"
            ),
            symbol="SYNTHETIC-" + symbol,
            exchange="SIM",
            segment="FIXTURE",
        )
        for symbol in ("HAL", "BEL", "HINDALCO", "KAYNES")
    )


class SyntheticProvider:
    mode = DeploymentMode.SYNTHETIC

    def __init__(
        self,
        capability: str,
        *,
        available: bool = True,
        failure: ErrorCode | DomainErrorCode | None = None,
    ) -> None:
        self.manifest = ProviderManifest(
            identity=ProducerIdentity(
                service_id="synthetic-" + capability.replace(".", "-"),
                provider="twf-fixture",
                service_version="1",
                contract_version=capability + ".v1",
            ),
            capabilities=(capability,),
            source_modes=(SourceMode.SYNTHETIC,),
            max_items=4,
            supported_metrics=("fixture.ordinal",),
            supported_operators=("GTE",),
            supported_timeframes=("fixture-step",),
        )
        self.available = available
        self.failure = failure

    def check(self, context: OperationContext) -> None:
        code = self.failure or (None if self.available else ErrorCode.SERVICE_UNAVAILABLE)
        if code is not None:
            raise ProviderAccess.failure(self, context, code)

    async def health(self, context: OperationContext) -> ProviderHealth:
        return ProviderHealth(
            identity=self.manifest.identity,
            request_id=context.correlation.request_id,
            health=Health.AVAILABLE if self.available else Health.UNAVAILABLE,
            as_of=context.as_of,
            source_mode=SourceMode.SYNTHETIC,
        )

    def provenance(self, instrument: InstrumentIdentity, at: datetime) -> Provenance:
        return Provenance(
            producer=self.manifest.identity,
            source=SourceReference(
                namespace="twf-fixture", native_id=str(instrument.instrument_id), revision="1"
            ),
            mode=SourceMode.SYNTHETIC,
            observation_key=fixture_id(str(instrument.instrument_id) + at.isoformat()).hex,
            transformation=RevisionRef(id="synthetic-normalization", version="1"),
            dependence_group="fabricated-fixture-series",
        )

    def evidence(
        self,
        context: OperationContext,
        instrument: InstrumentIdentity,
        category: EvidenceCategory,
        measure: Measure,
        *,
        related_evidence_ids: tuple[UUID, ...] = (),
        extra_measures: tuple[Measure, ...] = (),
    ) -> DiscoveryEvidence:
        return DiscoveryEvidence(
            evidence_id=fixture_id(
                str(context.owner_id)
                + self.manifest.identity.service_id
                + str(instrument.instrument_id)
                + context.as_of.isoformat()
            ),
            owner_id=context.owner_id,
            subject_id=instrument.instrument_id,
            category=category,
            polarity=EvidencePolarity.NEUTRAL,
            observation_basis="fixture-step",
            observed_at=context.as_of,
            source_data_time=context.as_of,
            received_at=context.as_of,
            available_at=context.as_of,
            provenance=self.provenance(instrument, context.as_of),
            measures=(measure, *extra_measures),
            related_evidence_ids=related_evidence_ids,
        )

    def batch[T](
        self, context: OperationContext, items: tuple[T, ...], result_type: type[ProviderBatch[T]]
    ) -> ProviderBatch[T]:
        return result_type(
            identity=self.manifest.identity,
            owner_id=context.owner_id,
            request_id=context.correlation.request_id,
            as_of=context.as_of,
            source_mode=SourceMode.SYNTHETIC,
            completeness="COMPLETE",
            items=items,
        )


class SyntheticUniverseProvider(SyntheticProvider):
    def __init__(self) -> None:
        super().__init__("sd.universe")

    async def resolve(self, context: OperationContext) -> ProviderBatch[InstrumentIdentity]:
        self.check(context)
        return self.batch(context, fixture_instruments(), ProviderBatch[InstrumentIdentity])


class SyntheticScanProvider(SyntheticProvider):
    def __init__(self) -> None:
        super().__init__("sd.scan")

    async def scan(
        self, context: OperationContext, run: ScanRun, instruments: tuple[InstrumentIdentity, ...]
    ) -> ProviderBatch[ScanMatch]:
        self.check(context)
        if (
            run.owner_id != context.owner_id
            or run.as_of != context.as_of
            or run.request_id != context.correlation.request_id
        ):
            raise ProviderAccess.failure(self, context, DomainErrorCode.INVALID_REQUEST)
        definition = run.definition
        if (
            definition.source_mode != SourceMode.SYNTHETIC
            or definition.timeframe != "fixture-step"
            or definition.combination != "ALL"
            or len(definition.criteria) != 1
            or set(definition.required_capabilities) != {"sd.scan"}
        ):
            raise ProviderAccess.failure(self, context, ErrorCode.UNSUPPORTED_CAPABILITY)
        criterion = definition.criteria[0]
        if (
            criterion.metric != "fixture.ordinal"
            or criterion.operator != "GTE"
            or criterion.unit != "fixture-index"
        ):
            raise ProviderAccess.failure(self, context, ErrorCode.UNSUPPORTED_CAPABILITY)
        catalog = {i.instrument_id: (index, i) for index, i in enumerate(fixture_instruments(), 1)}
        if len(instruments) > self.manifest.max_items or len(
            {i.instrument_id for i in instruments}
        ) != len(instruments):
            raise ProviderAccess.failure(self, context, DomainErrorCode.INVALID_REQUEST)
        matches = []
        for instrument in instruments:
            known = catalog.get(instrument.instrument_id)
            if known is None or known[1] != instrument:
                raise ProviderAccess.failure(self, context, DomainErrorCode.INVALID_REQUEST)
            index = known[0]
            if index < criterion.threshold:
                continue
            evidence = self.evidence(
                context,
                instrument,
                EvidenceCategory.PROVIDER_SCAN,
                Measure(name="fixture.ordinal", value=Decimal(index), unit="fixture-index"),
            )
            matches.append(
                ScanMatch(
                    scan_match_id=fixture_id(str(run.run_id) + str(instrument.instrument_id)),
                    run_id=run.run_id,
                    owner_id=context.owner_id,
                    instrument=instrument,
                    definition_id=definition.definition_id,
                    definition_revision=definition.revision,
                    profile=run.profile,
                    configuration_fingerprint=run.configuration_fingerprint,
                    evidence=(evidence,),
                    provenance=evidence.provenance,
                )
            )
        return self.batch(context, tuple(matches), ProviderBatch[ScanMatch])


class SyntheticCandidateSource(SyntheticProvider):
    def __init__(self) -> None:
        super().__init__("sd.candidate-source")

    async def nominate(self, context: OperationContext) -> ProviderBatch[CandidateInput]:
        self.check(context)
        subject = fixture_instruments()[0]
        evidence = self.evidence(
            context,
            subject,
            EvidenceCategory.INSTRUMENT_PRICE,
            Measure(name="fixture.signal", value=Decimal("7"), unit="fabricated-points"),
        )
        return self.batch(
            context,
            (
                CandidateInput(
                    input_id=fixture_id(str(evidence.evidence_id) + "input"),
                    owner_id=context.owner_id,
                    instrument=subject,
                    evidence=(evidence,),
                    provenance=evidence.provenance,
                ),
            ),
            ProviderBatch[CandidateInput],
        )


class SyntheticMarketIntelligenceProvider(SyntheticProvider):
    def __init__(self) -> None:
        super().__init__("sd.market-context")

    async def observe(
        self, context: OperationContext, instruments: tuple[InstrumentIdentity, ...]
    ) -> ProviderBatch[DiscoveryEvidence]:
        self.check(context)
        return self.batch(
            context,
            tuple(
                self.evidence(
                    context,
                    i,
                    EvidenceCategory.MARKET_CONTEXT,
                    Measure(name="fixture.regime", value="neutral-synthetic", unit="category"),
                    extra_measures=(
                        Measure(
                            name="fixture.volatility", value="normal-synthetic", unit="category"
                        ),
                        Measure(
                            name="fixture.sector-strength",
                            value=Decimal(2),
                            unit="fabricated-points",
                        ),
                    ),
                )
                for i in instruments
            ),
            ProviderBatch[DiscoveryEvidence],
        )


class SyntheticCandidateIntelligenceProvider(SyntheticProvider):
    def __init__(self) -> None:
        super().__init__("sd.candidate-intelligence")

    async def annotate(
        self, context: OperationContext, inputs: tuple[CandidateInput, ...]
    ) -> ProviderBatch[DiscoveryEvidence]:
        self.check(context)
        if any(i.owner_id != context.owner_id for i in inputs):
            raise ProviderAccess.failure(self, context, ErrorCode.AUTHORIZATION_FAILED)
        return self.batch(
            context,
            tuple(
                self.evidence(
                    context,
                    i.instrument,
                    EvidenceCategory.TECHNICAL,
                    Measure(
                        name="fixture.annotation",
                        value="deterministic-fixture-only",
                        unit="category",
                    ),
                    related_evidence_ids=tuple(e.evidence_id for e in i.evidence),
                )
                for i in inputs
            ),
            ProviderBatch[DiscoveryEvidence],
        )
