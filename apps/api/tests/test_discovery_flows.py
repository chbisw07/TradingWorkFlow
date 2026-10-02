import asyncio
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import pytest
from discovery_support import (
    EPISODE,
    OTHER,
    OWNER,
    context,
    intent,
    proof,
    replace,
    scan_run,
    window,
)

from twf.discovery.domain import (
    CandidateInput,
    DiscoveryEvidence,
    FreshnessState,
    InstrumentIdentity,
    RejectionReason,
)
from twf.discovery.domain import (
    DiscoveryLifecycleState as State,
)
from twf.discovery.lifecycle import TransitionAssessment
from twf.discovery.memory import HistoryConflict
from twf.discovery.providers import OperationContext, ProviderBatch
from twf.discovery.service import FIXTURE_POLICY, SyntheticFoundationProof, scan_input
from twf.discovery.synthetic import (
    SyntheticCandidateIntelligenceProvider,
    SyntheticCandidateSource,
    SyntheticMarketIntelligenceProvider,
    SyntheticScanProvider,
    SyntheticUniverseProvider,
    fixture_id,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Synthetic orchestration attempted network use")

    monkeypatch.setattr(socket.socket, "connect", denied)


def source_input(seconds: int = 0) -> CandidateInput:
    return asyncio.run(SyntheticCandidateSource().nominate(context(seconds))).items[0]


def current() -> SyntheticFoundationProof:
    service = proof()
    for seconds in (0, 60):
        service.discover(context(seconds), source_input(seconds), intent(), window(), EPISODE)
    return service


def assessment(service: SyntheticFoundationProof, **changes: Any) -> TransitionAssessment:
    head = service.history.snapshots(OWNER, EPISODE)[-1]
    return TransitionAssessment.model_validate(
        {
            "policy": FIXTURE_POLICY,
            "freshness": FreshnessState.FRESH,
            "comparable_observations": service.history.comparable_observations(OWNER, EPISODE),
            "eligible": True,
            "reason": "test-policy-assessment",
            "evidence_ids": tuple(e.evidence_id for e in head.evidence),
            **changes,
        }
    )


def test_scan_only_then_two_observation_discovery_and_repeatability() -> None:
    async def run() -> tuple[str, ...]:
        service = proof()
        scanner, universe = SyntheticScanProvider(), SyntheticUniverseProvider()
        matches = await service.scan_only(context(), scan_run(), universe, scanner)
        with pytest.raises(LookupError):
            service.history.episode(OWNER, EPISODE)
        first = service.discover(context(), scan_input(matches[0]), intent(), window(), EPISODE)
        assert first.lifecycle == State.NEW
        s1 = service.history.snapshots(OWNER, EPISODE)[0]
        original = s1.model_dump_json()
        later = await service.scan_only(context(60), scan_run(context(60)), universe, scanner)
        second = service.discover(context(60), scan_input(later[0]), intent(), window(), EPISODE)
        assert second.lifecycle == State.CURRENT and second.episode_id == first.episode_id
        assert (
            second.candidate_id == first.candidate_id
            and second.head_snapshot_id != first.head_snapshot_id
        )
        assert service.history.snapshots(OWNER, EPISODE)[0].model_dump_json() == original
        assert s1.evidence[0].provenance.producer == scanner.manifest.identity
        return tuple(s.model_dump_json() for s in service.history.snapshots(OWNER, EPISODE))

    assert asyncio.run(run()) == asyncio.run(run())


def test_discovery_without_scan_and_duplicate_poll_not_evolution() -> None:
    service = proof()
    items = asyncio.run(service.candidate_inputs(context(), SyntheticCandidateSource()))
    first = service.discover(context(), items[0], intent(), window(), EPISODE)
    again = service.discover(context(1), items[0], intent(), window(), EPISODE)
    assert first.lifecycle == again.lifecycle == State.NEW
    assert service.history.comparable_observations(OWNER, EPISODE) == 1
    assert items[0].scan_match_id is None
    with pytest.raises(ValueError):
        head = service.history.episode(OWNER, EPISODE)
        service.history.transition(
            OWNER,
            EPISODE,
            head.revision,
            State.CURRENT,
            context(2).as_of,
            assessment(service, comparable_observations=2),
        )


def test_multiple_intents_and_listing_identity_are_not_merged() -> None:
    service = proof()
    item = source_input()
    first = service.discover(context(), item, intent(), window(), EPISODE)
    short = replace(intent(), intent_id=fixture_id("short-intent"), direction="SHORT")
    second = service.discover(context(), item, short, window(), fixture_id("short-episode"))
    assert first.instrument == second.instrument and first.episode_id != second.episode_id
    with pytest.raises(HistoryConflict):
        service.discover(context(), item, intent(), window(), fixture_id("duplicate-episode"))


def test_freshness_expiry_projection_does_not_mutate_durable_history() -> None:
    service = current()
    before = service.history.episode(OWNER, EPISODE)
    stale = service.history.candidate(OWNER, EPISODE, context(361).as_of, 300)
    expired = service.history.candidate(OWNER, EPISODE, window().ends_at, 300)
    assert stale.lifecycle == State.STALE and expired.lifecycle == State.EXPIRED
    assert service.history.episode(OWNER, EPISODE) == before
    assert before.lifecycle == State.CURRENT
    with pytest.raises(ValueError):
        service.history.transition(
            OWNER,
            EPISODE,
            before.revision,
            State.CURRENT,
            window().ends_at,
            assessment(service, recovery_verified=True),
        )


def test_defunct_recovery_and_expiry_rejection_are_explicit_events() -> None:
    service = current()
    head = service.history.episode(OWNER, EPISODE)
    defunct = service.history.transition(
        OWNER,
        EPISODE,
        head.revision,
        State.DEFUNCT,
        context(61).as_of,
        assessment(service, material_breach=True),
    )
    assert (
        service.history.candidate(OWNER, EPISODE, context(400).as_of, 300).lifecycle
        == State.DEFUNCT
    )
    recovered = service.history.transition(
        OWNER,
        EPISODE,
        defunct.revision,
        State.CURRENT,
        context(62).as_of,
        assessment(service, recovery_verified=True),
    )
    expired = service.history.transition(
        OWNER, EPISODE, recovered.revision, State.EXPIRED, window().ends_at, assessment(service)
    )
    rejected = service.history.transition(
        OWNER,
        EPISODE,
        expired.revision,
        State.REJECTED,
        window().ends_at,
        assessment(service),
        RejectionReason.EXPIRED,
    )
    assert rejected.rejection_reason == RejectionReason.EXPIRED
    assert len(service.history.events(OWNER, EPISODE)) == 5  # includes NEW -> CURRENT
    assert len(service.history.snapshots(OWNER, EPISODE)) == 2


@pytest.mark.parametrize(
    "target,changes,reason",
    [
        (State.NEW, {}, None),
        (State.STALE, {}, None),
        (State.DEFUNCT, {"material_breach": False}, None),
        (State.DEFUNCT, {"material_breach": True, "freshness": FreshnessState.STALE}, None),
        (State.EXPIRED, {}, None),
        (State.REJECTED, {}, None),
        (State.REJECTED, {"actor_id": OTHER}, RejectionReason.USER_DISMISSED),
        (State.REJECTED, {}, RejectionReason.DEFUNCT_CONFIRMED),
        (State.REJECTED, {}, RejectionReason.INSUFFICIENT_EVIDENCE),
        (State.REJECTED, {}, RejectionReason.IDENTITY_INVALID),
        (State.REJECTED, {}, RejectionReason.EXPIRED),
    ],
)
def test_illegal_transition_leaves_head_and_events_unchanged(
    target: State, changes: dict[str, Any], reason: RejectionReason | None
) -> None:
    service = current()
    head = service.history.episode(OWNER, EPISODE)
    events = service.history.events(OWNER, EPISODE)
    with pytest.raises(ValueError):
        service.history.transition(
            OWNER,
            EPISODE,
            head.revision,
            target,
            context(61).as_of,
            assessment(service, **changes),
            reason,
        )
    assert service.history.episode(OWNER, EPISODE) == head
    assert service.history.events(OWNER, EPISODE) == events


def test_terminal_episode_never_reopens_and_new_episode_links_history() -> None:
    service = current()
    head = service.history.episode(OWNER, EPISODE)
    rejected = service.history.transition(
        OWNER,
        EPISODE,
        head.revision,
        State.REJECTED,
        context(61).as_of,
        assessment(service, actor_id=OWNER),
        RejectionReason.USER_DISMISSED,
    )
    original = service.history.snapshots(OWNER, EPISODE)
    with pytest.raises(ValueError):
        service.history.transition(
            OWNER,
            EPISODE,
            rejected.revision,
            State.CURRENT,
            context(62).as_of,
            assessment(service, recovery_verified=True),
        )
    with pytest.raises(HistoryConflict):
        service.discover(context(62), source_input(62), intent(), window(), fixture_id("unlinked"))
    with pytest.raises(HistoryConflict):
        service.discover(
            context(120),
            source_input(120),
            intent(),
            window(),
            fixture_id("too-early"),
            previous_episode_id=EPISODE,
        )
    new = service.discover(
        context(121),
        source_input(121),
        intent(),
        window(),
        fixture_id("recurrence"),
        previous_episode_id=EPISODE,
    )
    assert new.episode_id != EPISODE and new.lifecycle == State.NEW
    assert service.history.snapshots(OWNER, EPISODE) == original
    assert service.history.episode(OWNER, EPISODE) == rejected


def test_ownership_revision_identity_and_window_guards() -> None:
    service = current()
    head = service.history.episode(OWNER, EPISODE)
    with pytest.raises(LookupError):
        service.history.snapshots(OTHER, EPISODE)
    with pytest.raises(HistoryConflict):
        service.history.transition(
            OWNER,
            EPISODE,
            head.revision - 1,
            State.REJECTED,
            context(61).as_of,
            assessment(service, actor_id=OWNER),
            RejectionReason.USER_DISMISSED,
        )
    with pytest.raises(ValueError):
        service.discover(
            context(120),
            source_input(120),
            intent(),
            replace(window(), ends_at=window().ends_at + timedelta(days=1)),
            EPISODE,
        )
    with pytest.raises(ValueError):
        service.discover(
            context(owner=OTHER), source_input(), intent(), window(), fixture_id("forged-owner")
        )
    stale = replace(head, lifecycle=State.STALE)
    assert stale.lifecycle == State.STALE


def test_concurrent_append_compare_and_swap_has_one_winner() -> None:
    service = current()
    old = service.history.snapshots(OWNER, EPISODE)[-1]
    head = service.history.episode(OWNER, EPISODE)
    proposed = replace(
        old,
        snapshot_id=fixture_id("next-snapshot"),
        sequence=3,
        previous_snapshot_id=old.snapshot_id,
    )

    def append() -> bool:
        try:
            service.history.append(OWNER, proposed, head.revision)
            return True
        except HistoryConflict:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: append(), range(4)))
    assert outcomes.count(True) == 1
    assert len(service.history.snapshots(OWNER, EPISODE)) == 3


def test_optional_enrichment_missing_failure_and_success_do_not_change_discovery() -> None:
    service = current()
    inputs = (source_input(60),)

    async def run() -> None:
        head = service.history.episode(OWNER, EPISODE)
        missing = await service.enrich(context(60), inputs, None, None)
        assert missing.unavailable == ("sd.market-context", "sd.candidate-intelligence")
        market, intelligence = (
            SyntheticMarketIntelligenceProvider(),
            SyntheticCandidateIntelligenceProvider(),
        )
        success = await service.enrich(context(60), inputs, market, intelligence)
        assert len(success.evidence) == 2 and not success.failures
        market.available = False
        partial = await service.enrich(context(60), inputs, market, intelligence)
        assert len(partial.evidence) == 1 and len(partial.failures) == 1
        assert service.history.episode(OWNER, EPISODE) == head
        assert partial.evidence[0].provenance.producer == intelligence.manifest.identity

    asyncio.run(run())


@pytest.mark.parametrize("change", ["producer", "unit", "transformation"])
def test_incomparable_observation_cannot_extend_history(change: str) -> None:
    service = current()
    original = service.history.snapshots(OWNER, EPISODE)
    item = source_input(120)
    if change == "producer":
        item = replace(
            item,
            provenance=replace(
                item.provenance, producer=replace(item.provenance.producer, service_version="2")
            ),
        )
    elif change == "transformation":
        item = replace(
            item,
            provenance=replace(
                item.provenance, transformation=replace(item.provenance.transformation, version="2")
            ),
        )
    else:
        evidence = item.evidence[0]
        item = replace(
            item,
            evidence=(
                replace(evidence, measures=(replace(evidence.measures[0], unit="different-unit"),)),
            ),
        )
    with pytest.raises(HistoryConflict, match="Incomparable"):
        service.discover(context(120), item, intent(), window(), EPISODE)
    assert service.history.snapshots(OWNER, EPISODE) == original


def test_caller_cannot_claim_stale_evidence_is_fresh() -> None:
    service = current()
    head = service.history.episode(OWNER, EPISODE)
    with pytest.raises(HistoryConflict, match="Stale/unknown"):
        service.history.transition(
            OWNER,
            EPISODE,
            head.revision,
            State.DEFUNCT,
            context(361).as_of,
            assessment(service, material_breach=True),
        )
    assert service.history.episode(OWNER, EPISODE) == head


def test_unknown_source_time_never_manufactures_evolution_or_score() -> None:
    service = proof()
    for seconds in (0, 60):
        item = source_input(seconds)
        item = replace(item, evidence=(replace(item.evidence[0], source_data_time=None),))
        candidate = service.discover(context(seconds), item, intent(), window(), EPISODE)
        assert candidate.lifecycle == State.NEW
        assert candidate.freshness == FreshnessState.UNKNOWN
        assert candidate.relevance.value is None
    assert service.history.comparable_observations(OWNER, EPISODE) == 0


def test_partial_optional_provider_is_explicit_and_cannot_rewrite_candidate() -> None:
    class PartialMarket(SyntheticMarketIntelligenceProvider):
        async def observe(
            self, ctx: OperationContext, instruments: tuple[InstrumentIdentity, ...]
        ) -> ProviderBatch[DiscoveryEvidence]:
            result = await super().observe(ctx, instruments)
            return replace(result, completeness="PARTIAL", limitations=("fixture-partial",))

    service = current()
    head = service.history.episode(OWNER, EPISODE)
    result = asyncio.run(service.enrich(context(60), (source_input(60),), PartialMarket(), None))
    assert result.partial == (PartialMarket().manifest.identity.service_id,)
    assert result.unavailable == ("sd.candidate-intelligence",)
    assert service.history.episode(OWNER, EPISODE) == head
