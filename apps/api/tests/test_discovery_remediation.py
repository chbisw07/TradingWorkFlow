"""Regressions for the independent S21-01/02/03 acceptance findings."""

import asyncio
import socket
from typing import Any, cast

import pytest
from discovery_support import (
    EPISODE,
    OWNER,
    FixtureGrants,
    context,
    intent,
    proof,
    replace,
    scan_run,
    window,
)
from pydantic import ValidationError

from twf.discovery.domain import (
    CandidateInput,
    DiscoverySnapshot,
    InstrumentIdentity,
    ScanMatch,
    ScanRun,
    SourceMode,
)
from twf.discovery.domain import DiscoveryLifecycleState as State
from twf.discovery.memory import HistoryConflict
from twf.discovery.providers import (
    DomainErrorCode,
    OperationContext,
    ProviderAccess,
    ProviderBatch,
    ProviderFailure,
)
from twf.discovery.service import scan_input
from twf.discovery.synthetic import (
    SyntheticCandidateIntelligenceProvider,
    SyntheticCandidateSource,
    SyntheticMarketIntelligenceProvider,
    SyntheticScanProvider,
    SyntheticUniverseProvider,
    fixture_id,
)
from twf.integrations.contracts import DeploymentMode, ErrorCode


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Remediation tests must stay offline")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def source_input(seconds: int = 0) -> CandidateInput:
    return asyncio.run(SyntheticCandidateSource().nominate(context(seconds))).items[0]


@pytest.mark.parametrize(
    "capability",
    [
        "sd.universe",
        "sd.scan",
        "sd.candidate-source",
        "sd.market-context",
        "sd.candidate-intelligence",
    ],
)
@pytest.mark.parametrize("shape", ["string", "other-operation"])
def test_expected_operation_schema_rejects_wrong_items(capability: str, shape: str) -> None:
    async def run() -> None:
        ctx = context()
        universe = SyntheticUniverseProvider()
        instruments = (await universe.resolve(ctx)).items
        source = SyntheticCandidateSource()
        inputs = (await source.nominate(ctx)).items
        providers: dict[str, Any] = {
            "sd.universe": universe,
            "sd.scan": SyntheticScanProvider(),
            "sd.candidate-source": source,
            "sd.market-context": SyntheticMarketIntelligenceProvider(),
            "sd.candidate-intelligence": SyntheticCandidateIntelligenceProvider(),
        }
        provider = providers[capability]
        values: dict[str, Any] = {
            "identity": provider.manifest.identity,
            "owner_id": OWNER,
            "request_id": ctx.correlation.request_id,
            "as_of": ctx.as_of,
            "source_mode": SourceMode.SYNTHETIC,
            "completeness": "COMPLETE",
            "items": ("bad-item",)
            if shape == "string"
            else (inputs if capability == "sd.universe" else instruments),
        }
        # Generic erasure/wrong specialization must not choose its own validation schema.
        bad = ProviderBatch[Any](**values)

        async def operation() -> ProviderBatch[Any]:
            return bad

        with pytest.raises(ProviderFailure) as exc:
            await ProviderAccess(FixtureGrants()).call(
                provider, ctx, capability, capability + ".v1", operation
            )
        assert exc.value.error.code == ErrorCode.INVALID_RESPONSE
        assert exc.value.error.operation == capability
        assert exc.value.error.provider_id == provider.manifest.identity.service_id
        assert exc.value.error.request_id == ctx.correlation.request_id

    asyncio.run(run())


def test_wrong_scan_type_never_reaches_downstream_attribute_access() -> None:
    class WrongScanner(SyntheticScanProvider):
        async def scan(
            self, ctx: OperationContext, run: ScanRun, instruments: tuple[InstrumentIdentity, ...]
        ) -> ProviderBatch[ScanMatch]:
            valid = await super().scan(ctx, run, instruments)
            wrong = ProviderBatch[InstrumentIdentity](
                **{**valid.model_dump(), "items": instruments}
            )
            return cast(ProviderBatch[ScanMatch], wrong)

    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(
            proof().scan_only(context(), scan_run(), SyntheticUniverseProvider(), WrongScanner())
        )
    assert exc.value.error.code == ErrorCode.INVALID_RESPONSE
    assert exc.value.error.operation == "sd.scan"


@pytest.mark.parametrize("mutation", ["item-mode", "evidence-mode", "producer", "missing-source"])
def test_provenance_errors_are_typed(mutation: str) -> None:
    async def run() -> None:
        provider = SyntheticCandidateSource()
        batch = await provider.nominate(context())
        item = batch.items[0]
        code: ErrorCode | DomainErrorCode = DomainErrorCode.PROVENANCE_MISMATCH
        if mutation == "item-mode":
            item = replace(item, provenance=replace(item.provenance, mode=SourceMode.LIVE_SNAPSHOT))
        elif mutation == "evidence-mode":
            item = replace(
                item,
                evidence=(
                    replace(
                        item.evidence[0],
                        provenance=replace(
                            item.evidence[0].provenance, mode=SourceMode.LIVE_SNAPSHOT
                        ),
                    ),
                ),
            )
        elif mutation == "producer":
            item = replace(
                item,
                provenance=replace(
                    item.provenance,
                    producer=replace(item.provenance.producer, service_id="wrong-producer"),
                ),
            )
        values = {**batch.model_dump(), "items": (item.model_dump(),)}
        if mutation == "missing-source":
            del values["items"][0]["provenance"]["source"]
            code = ErrorCode.INVALID_RESPONSE
        malformed = ProviderBatch[Any](**values)

        async def operation() -> ProviderBatch[Any]:
            return malformed

        with pytest.raises(ProviderFailure) as exc:
            await ProviderAccess(FixtureGrants()).call(
                provider, context(), "sd.candidate-source", "sd.candidate-source.v1", operation
            )
        assert exc.value.error.code == code

    asyncio.run(run())


@pytest.mark.parametrize("mode", [SourceMode.SYNTHETIC, SourceMode.EOD])
def test_upstream_producer_is_not_forced_to_equal_adapter(mode: SourceMode) -> None:
    async def run() -> None:
        provider = SyntheticCandidateSource()
        provider.mode = DeploymentMode.LOCAL
        provider.manifest = replace(provider.manifest, source_modes=(mode,))
        batch = await provider.nominate(context())
        item = batch.items[0]
        upstream = replace(
            item.evidence[0].provenance,
            producer=replace(item.provenance.producer, service_id="upstream-reader"),
            mode=SourceMode.DELAYED if mode == SourceMode.EOD else mode,
        )
        item = replace(
            item,
            provenance=replace(item.provenance, mode=mode),
            evidence=(replace(item.evidence[0], provenance=upstream),),
        )
        batch = replace(batch, source_mode=mode, items=(item,))

        async def operation() -> ProviderBatch[CandidateInput]:
            return batch

        accepted = await ProviderAccess(FixtureGrants()).call(
            provider, context(), "sd.candidate-source", "sd.candidate-source.v1", operation
        )
        assert accepted.items[0].evidence[0].provenance == upstream

    asyncio.run(run())


@pytest.mark.parametrize("mutation", ["producer", "normalization", "source", "mode"])
def test_nested_evidence_incompatibility_does_not_change_history(mutation: str) -> None:
    service = proof()
    service.discover(context(), source_input(), intent(), window(), EPISODE)
    original = service.history.snapshots(OWNER, EPISODE)
    item = source_input(60)
    evidence = item.evidence[0]
    provenance = evidence.provenance
    updates: dict[str, Any] = {
        "producer": {"producer": replace(provenance.producer, service_version="2")},
        "normalization": {"transformation": replace(provenance.transformation, version="2")},
        "source": {"source": replace(provenance.source, native_id="other-feed")},
        "mode": {"mode": SourceMode.EOD},
    }
    item = replace(
        item, evidence=(replace(evidence, provenance=replace(provenance, **updates[mutation])),)
    )
    with pytest.raises(ValueError):
        service.discover(context(60), item, intent(), window(), EPISODE)
    assert service.history.snapshots(OWNER, EPISODE) == original
    assert service.history.comparable_observations(OWNER, EPISODE) == 1
    assert service.history.episode(OWNER, EPISODE).lifecycle == State.NEW


def test_capture_only_replay_is_retained_but_not_a_second_observation() -> None:
    service = proof()
    item = source_input()
    service.discover(context(), item, intent(), window(), EPISODE)
    original = service.history.snapshots(OWNER, EPISODE)[0].model_dump_json()
    rewrapped = replace(
        item,
        input_id=fixture_id("new-capture"),
        provenance=replace(item.provenance, observation_key="new-envelope-only"),
    )
    candidate = service.discover(context(60), rewrapped, intent(), window(), EPISODE)
    snapshots = service.history.snapshots(OWNER, EPISODE)
    assert len(snapshots) == 2 and snapshots[0].model_dump_json() == original
    assert snapshots[0].evidence == snapshots[1].evidence
    assert candidate.lifecycle == State.NEW
    assert service.history.comparable_observations(OWNER, EPISODE) == 1
    with pytest.raises(ValidationError, match="time summary"):
        replace(snapshots[1], source_data_time=context(60).as_of, observed_at=context(60).as_of)
    later = service.discover(context(120), source_input(120), intent(), window(), EPISODE)
    assert later.lifecycle == State.CURRENT
    assert service.history.comparable_observations(OWNER, EPISODE) == 2


def test_reissued_evidence_id_and_key_with_same_source_time_is_not_evolution() -> None:
    service = proof()
    item = source_input()
    service.discover(context(), item, intent(), window(), EPISODE)
    evidence = replace(
        item.evidence[0],
        evidence_id=fixture_id("reissued"),
        provenance=replace(item.evidence[0].provenance, observation_key="reissued-key"),
    )
    item = replace(item, evidence=(evidence,))
    candidate = service.discover(context(60), item, intent(), window(), EPISODE)
    assert candidate.lifecycle == State.NEW
    assert service.history.comparable_observations(OWNER, EPISODE) == 1


def test_additional_independent_source_is_retained_without_false_promotion() -> None:
    service = proof()
    item = source_input()
    service.discover(context(), item, intent(), window(), EPISODE)
    extra = source_input(60).evidence[0]
    extra = replace(
        extra,
        provenance=replace(
            extra.provenance,
            producer=replace(extra.provenance.producer, service_id="independent-fixture"),
        ),
    )
    candidate = service.discover(
        context(60), replace(item, evidence=(*item.evidence, extra)), intent(), window(), EPISODE
    )
    assert candidate.lifecycle == State.NEW
    assert len(service.history.snapshots(OWNER, EPISODE)[-1].evidence) == 2
    assert service.history.comparable_observations(OWNER, EPISODE) == 1
    assert (
        service.discover(context(120), source_input(120), intent(), window(), EPISODE).lifecycle
        == State.CURRENT
    )


def test_scan_lineage_survives_s1_s2_and_is_deeply_immutable() -> None:
    async def run() -> None:
        service = proof()
        originals: list[tuple[ScanRun, ScanMatch, CandidateInput]] = []
        for seconds in (0, 60):
            run = scan_run(context(seconds))
            matches = await service.scan_only(
                context(seconds), run, SyntheticUniverseProvider(), SyntheticScanProvider()
            )
            item = scan_input(matches[0])
            originals.append((run, matches[0], item))
            candidate = service.discover(context(seconds), item, intent(), window(), EPISODE)
        assert candidate.lifecycle == State.CURRENT
        for snapshot, (run, match, item) in zip(
            service.history.snapshots(OWNER, EPISODE), originals, strict=True
        ):
            lineage = snapshot.lineage
            assert lineage.input_id == item.input_id
            assert (
                lineage.producer == match.provenance.producer
                and lineage.source == match.provenance.source
            )
            assert lineage.scan is not None
            assert (
                lineage.scan.run_id == run.run_id and lineage.scan.match_id == match.scan_match_id
            )
            assert lineage.scan.definition_id == run.definition.definition_id
            assert lineage.scan.definition_revision == run.definition.revision
            assert lineage.scan.profile == run.profile
            assert lineage.scan.configuration_fingerprint == run.configuration_fingerprint
            assert DiscoverySnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
            with pytest.raises(ValidationError):
                lineage.scan.profile.applied_revision = 99

    asyncio.run(run())


@pytest.mark.parametrize("changed", ["definition", "profile", "criteria"])
def test_scan_configuration_change_has_distinct_lineage_and_cannot_continue(changed: str) -> None:
    async def run() -> None:
        service = proof()
        first_run = scan_run()
        next_run = scan_run(context(60))
        if changed == "definition":
            next_run = replace(
                next_run,
                definition=replace(
                    next_run.definition,
                    definition_id=fixture_id("different-definition"),
                    revision=2,
                ),
            )
        elif changed == "profile":
            next_run = replace(
                next_run,
                profile=replace(
                    next_run.profile, profile_id=fixture_id("different-profile"), applied_revision=2
                ),
            )
        else:
            next_run = replace(
                next_run,
                definition=replace(
                    next_run.definition,
                    criteria=(replace(next_run.definition.criteria[0], threshold=2),),
                ),
            )
        scanner, universe = SyntheticScanProvider(), SyntheticUniverseProvider()
        first = (await service.scan_only(context(), first_run, universe, scanner))[0]
        matches = await service.scan_only(context(60), next_run, universe, scanner)
        second = next(m for m in matches if m.instrument == first.instrument)
        service.discover(context(), scan_input(first), intent(), window(), EPISODE)
        before = service.history.snapshots(OWNER, EPISODE)
        assert first.lineage.comparison_key != second.lineage.comparison_key
        with pytest.raises(HistoryConflict, match="Incomparable"):
            service.discover(context(60), scan_input(second), intent(), window(), EPISODE)
        assert service.history.snapshots(OWNER, EPISODE) == before
        independent = proof()
        independent.discover(context(60), scan_input(second), intent(), window(), EPISODE)
        assert independent.history.snapshots(OWNER, EPISODE)[0].lineage != before[0].lineage

    asyncio.run(run())


def test_non_scan_input_lineage_is_retained() -> None:
    service = proof()
    item = source_input()
    service.discover(context(), item, intent(), window(), EPISODE)
    lineage = service.history.snapshots(OWNER, EPISODE)[0].lineage
    assert lineage.input_id == item.input_id and lineage.scan is None
    assert lineage.owner_id == OWNER
    assert lineage.source == item.provenance.source and lineage.producer == item.provenance.producer
