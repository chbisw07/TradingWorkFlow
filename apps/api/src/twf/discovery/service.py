"""Direct-call synthetic contract proofs, intentionally absent from app composition/API."""

from decimal import Decimal
from uuid import UUID

from twf.discovery.domain import (
    CandidateInput,
    DiscoveryCandidate,
    DiscoveryEpisode,
    DiscoveryEvidence,
    DiscoveryIntent,
    DiscoveryRelevance,
    DiscoverySnapshot,
    FreshnessState,
    OpportunityWindow,
    RevisionRef,
    ScanMatch,
    ScanRun,
    SourceMode,
    freshness,
)
from twf.discovery.domain import (
    DiscoveryLifecycleState as State,
)
from twf.discovery.lifecycle import TransitionAssessment
from twf.discovery.memory import InMemoryDiscoveryHistory
from twf.discovery.providers import (
    CandidateIntelligenceProvider,
    CandidateSource,
    DomainErrorCode,
    MarketIntelligenceProvider,
    OperationContext,
    ProviderAccess,
    ProviderError,
    ProviderFailure,
    ScanProvider,
    UniverseProvider,
)
from twf.discovery.synthetic import fixture_id
from twf.integrations.contracts import Contract, ErrorCode

FIXTURE_POLICY = RevisionRef(id="synthetic-discovery-proof", version="1")
FIXTURE_TTL_SECONDS = 300


class EnrichmentResult(Contract):
    evidence: tuple[DiscoveryEvidence, ...]
    failures: tuple[ProviderError, ...]
    unavailable: tuple[str, ...]
    partial: tuple[str, ...]


def scan_input(match: ScanMatch) -> CandidateInput:
    return CandidateInput(
        input_id=fixture_id(str(match.scan_match_id) + "input"),
        owner_id=match.owner_id,
        instrument=match.instrument,
        evidence=match.evidence,
        provenance=match.provenance,
        scan_match_id=match.scan_match_id,
        scan_lineage=match.lineage,
    )


class SyntheticFoundationProof:
    """Fixture-only evaluator: fixed relevance, no real indicator/ranking/calibration engine."""

    def __init__(self, access: ProviderAccess, history: InMemoryDiscoveryHistory) -> None:
        self.access = access
        self.history = history

    async def scan_only(
        self,
        context: OperationContext,
        run: ScanRun,
        universe: UniverseProvider,
        scanner: ScanProvider,
    ) -> tuple[ScanMatch, ...]:
        if context.owner_id != run.owner_id or context.as_of != run.as_of:
            raise ValueError("Scan run context mismatch")
        subjects = await self.access.call(
            universe, context, "sd.universe", "sd.universe.v1", lambda: universe.resolve(context)
        )
        if subjects.completeness != "COMPLETE":
            raise self.access.failure(universe, context, ErrorCode.INVALID_RESPONSE, "sd.universe")
        result = await self.access.call(
            scanner,
            context,
            "sd.scan",
            "sd.scan.v1",
            lambda: scanner.scan(context, run, subjects.items),
        )
        if result.completeness != "COMPLETE":
            raise self.access.failure(scanner, context, ErrorCode.INVALID_RESPONSE, "sd.scan")
        known = {i.instrument_id: i for i in subjects.items}
        for match in result.items:
            if (
                match.owner_id != context.owner_id
                or match.run_id != run.run_id
                or match.definition_id != run.definition.definition_id
                or match.definition_revision != run.definition.revision
                or match.profile != run.profile
                or match.configuration_fingerprint != run.configuration_fingerprint
                or known.get(match.instrument.instrument_id) != match.instrument
                or match.provenance.producer != result.identity
            ):
                raise self.access.failure(
                    scanner, context, DomainErrorCode.PROVENANCE_MISMATCH, "sd.scan"
                )
        return result.items

    async def candidate_inputs(
        self, context: OperationContext, source: CandidateSource
    ) -> tuple[CandidateInput, ...]:
        result = await self.access.call(
            source,
            context,
            "sd.candidate-source",
            "sd.candidate-source.v1",
            lambda: source.nominate(context),
        )
        if result.completeness != "COMPLETE":
            raise self.access.failure(
                source, context, ErrorCode.INVALID_RESPONSE, "sd.candidate-source"
            )
        for item in result.items:
            if item.owner_id != context.owner_id or item.provenance.producer != result.identity:
                raise self.access.failure(
                    source, context, DomainErrorCode.PROVENANCE_MISMATCH, "sd.candidate-source"
                )
        return result.items

    async def enrich(
        self,
        context: OperationContext,
        inputs: tuple[CandidateInput, ...],
        market: MarketIntelligenceProvider | None,
        intelligence: CandidateIntelligenceProvider | None,
    ) -> EnrichmentResult:
        if any(i.owner_id != context.owner_id for i in inputs):
            raise ValueError("Enrichment ownership mismatch")
        evidence: list[DiscoveryEvidence] = []
        failures: list[ProviderError] = []
        unavailable: list[str] = []
        partial: list[str] = []
        subjects = {i.instrument.instrument_id for i in inputs}
        if market is None:
            unavailable.append("sd.market-context")
        else:
            try:
                result = await self.access.call(
                    market,
                    context,
                    "sd.market-context",
                    "sd.market-context.v1",
                    lambda: market.observe(context, tuple(i.instrument for i in inputs)),
                )
                if any(e.subject_id not in subjects for e in result.items):
                    raise self.access.failure(
                        market, context, DomainErrorCode.PROVENANCE_MISMATCH, "sd.market-context"
                    )
                if result.completeness == "PARTIAL":
                    partial.append(result.identity.service_id)
                evidence.extend(result.items)
            except ProviderFailure as exc:
                failures.append(exc.error)
        if intelligence is None:
            unavailable.append("sd.candidate-intelligence")
        else:
            try:
                result = await self.access.call(
                    intelligence,
                    context,
                    "sd.candidate-intelligence",
                    "sd.candidate-intelligence.v1",
                    lambda: intelligence.annotate(context, inputs),
                )
                if any(e.subject_id not in subjects for e in result.items):
                    raise self.access.failure(
                        intelligence,
                        context,
                        DomainErrorCode.PROVENANCE_MISMATCH,
                        "sd.candidate-intelligence",
                    )
                if result.completeness == "PARTIAL":
                    partial.append(result.identity.service_id)
                evidence.extend(result.items)
            except ProviderFailure as exc:
                failures.append(exc.error)
        # Optional annotations are returned separately. They cannot change the fixture score/state.
        return EnrichmentResult(
            evidence=tuple(evidence),
            failures=tuple(failures),
            unavailable=tuple(unavailable),
            partial=tuple(partial),
        )

    def discover(
        self,
        context: OperationContext,
        item: CandidateInput,
        intent: DiscoveryIntent,
        window: OpportunityWindow,
        episode_id: UUID,
        *,
        previous_episode_id: UUID | None = None,
    ) -> DiscoveryCandidate:
        if item.owner_id != context.owner_id or intent.owner_id != context.owner_id:
            raise ValueError("Discovery ownership mismatch")
        if item.provenance.mode != SourceMode.SYNTHETIC or any(
            e.provenance.mode != SourceMode.SYNTHETIC for e in item.evidence
        ):
            raise ValueError("Only explicitly synthetic inputs are admitted to the proof evaluator")
        if item.instrument.underlying.ambiguous:
            raise ValueError("Fixture nomination requires an unambiguous source identity")
        try:
            episode = self.history.episode(context.owner_id, episode_id)
        except LookupError:
            episode = None
        if episode is not None and (
            episode.instrument != item.instrument
            or episode.intent != intent
            or episode.window != window
        ):
            raise ValueError("Refresh cannot retarget an episode or move its window")
        old = () if episode is None else self.history.snapshots(context.owner_id, episode_id)
        fresh = all(
            freshness(e, context.as_of, FIXTURE_TTL_SECONDS) == FreshnessState.FRESH
            for e in item.evidence
        )
        snapshot = DiscoverySnapshot(
            snapshot_id=fixture_id(str(episode_id) + str(len(old) + 1) + context.as_of.isoformat()),
            episode_id=episode_id,
            owner_id=context.owner_id,
            sequence=len(old) + 1,
            previous_snapshot_id=old[-1].snapshot_id if old else None,
            instrument=item.instrument,
            intent_fingerprint=intent.fingerprint,
            observation_basis="fixture-step",
            observed_at=max(e.observed_at for e in item.evidence),
            source_data_time=(
                min(e.source_data_time for e in item.evidence if e.source_data_time is not None)
                if all(e.source_data_time is not None for e in item.evidence)
                else None
            ),
            evaluated_at=context.as_of,
            recorded_at=context.as_of,
            evidence=item.evidence,
            provenance=item.provenance,
            lineage=item.lineage,
            relevance=DiscoveryRelevance(
                value=Decimal(".75") if fresh else None,
                policy=FIXTURE_POLICY,
                required_inputs_satisfied=fresh,
                coverage=Decimal(1) if fresh else Decimal(0),
                reasons=("synthetic-fixed-fit",),
            ),
        )
        if episode is None:
            episode = self.history.open(
                DiscoveryEpisode(
                    episode_id=episode_id,
                    candidate_id=fixture_id(str(episode_id) + "candidate"),
                    owner_id=context.owner_id,
                    instrument=item.instrument,
                    intent=intent,
                    observation_basis="fixture-step",
                    policy_series=FIXTURE_POLICY,
                    window=window,
                    opened_at=context.as_of,
                    evaluated_at=context.as_of,
                    previous_episode_id=previous_episode_id,
                ),
                snapshot,
            )
        else:
            episode = self.history.append(context.owner_id, snapshot, episode.revision)
        count = self.history.comparable_observations(context.owner_id, episode_id)
        if episode.lifecycle == State.NEW and count >= 2 and fresh:
            episode = self.history.transition(
                context.owner_id,
                episode_id,
                episode.revision,
                State.CURRENT,
                context.as_of,
                TransitionAssessment(
                    policy=FIXTURE_POLICY,
                    freshness=FreshnessState.FRESH,
                    comparable_observations=count,
                    eligible=True,
                    reason="synthetic-comparison",
                    evidence_ids=tuple(e.evidence_id for e in item.evidence),
                ),
            )
        return self.history.candidate(
            context.owner_id, episode_id, context.as_of, FIXTURE_TTL_SECONDS
        )
