import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal

import pytest
from discovery_support import EPISODE, NOW, OTHER, context, intent, proof, replace, window
from pydantic import ValidationError

from twf.discovery.domain import (
    CandidateToleranceEnvelope,
    Comparison,
    Criterion,
    DiscoveryEvidence,
    DiscoveryRelevance,
    EvidenceCategory,
    FreshnessState,
    GroundingStatus,
    HorizonBasis,
    HorizonSpec,
    RelevanceBand,
    RevisionRef,
    ToleranceRule,
    freshness,
)
from twf.discovery.service import FIXTURE_POLICY
from twf.discovery.synthetic import SyntheticCandidateSource


def evidence() -> DiscoveryEvidence:
    return asyncio.run(SyntheticCandidateSource().nominate(context())).items[0].evidence[0]


@pytest.mark.parametrize(
    "basis,unit,lo,hi,preset",
    [
        (HorizonBasis.ELAPSED, "seconds", 1800, 1800, "next-30-minutes"),
        (HorizonBasis.TRADING_SESSIONS, "sessions", 1, 1, "current-session"),
        (HorizonBasis.TRADING_SESSIONS, "sessions", 1, 3, "short-swing"),
        (HorizonBasis.TRADING_SESSIONS, "sessions", 1, 5, "swing"),
        (HorizonBasis.TRADING_SESSIONS, "sessions", 1, 15, "positional"),
        (HorizonBasis.CALENDAR, "weeks", 2, 6, "medium-term"),
        (HorizonBasis.ELAPSED, "seconds", 17, 233, None),
    ],
)
def test_horizon_presets_are_values_not_a_closed_enum(
    basis: HorizonBasis, unit: str, lo: int, hi: int, preset: str | None
) -> None:
    data: dict[str, Any] = dict(
        basis=basis, unit=unit, minimum=lo, maximum=hi, preset=preset, cadence_seconds=60
    )
    if basis == HorizonBasis.TRADING_SESSIONS:
        data.update(
            calendar=RevisionRef(id="fixture-calendar", version="1"), timezone="Asia/Kolkata"
        )
    value = HorizonSpec.model_validate(data)
    assert value.minimum == lo and value.maximum == hi
    assert HorizonSpec.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum": 0},
        {"minimum": 2000},
        {"maximum": True},
        {"unit": "sessions"},
        {"timezone": "Mars/Trading"},
        {"basis": "TRADING_SESSIONS", "unit": "sessions"},
        {"basis": "EVENT_RELATIVE"},
        {"unit": "days"},
        {"unexpected": "ignored?"},
    ],
)
def test_invalid_horizons_fail_closed(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        replace(intent().horizon, **changes)


def test_event_horizon_and_semantic_intent_fingerprint() -> None:
    base = intent()
    event = replace(
        base.horizon, basis=HorizonBasis.EVENT_RELATIVE, event_ref=evidence().provenance.source
    )
    assert event.event_ref is not None
    assert replace(base, revision=2).fingerprint == base.fingerprint
    assert (
        replace(base, horizon=replace(base.horizon, preset="renamed-label")).fingerprint
        == base.fingerprint
    )
    assert replace(base, direction="SHORT").fingerprint != base.fingerprint
    assert replace(base, horizon=event).fingerprint != base.fingerprint


@pytest.mark.parametrize(
    "value,display,band",
    [
        ("0", "0.00", RelevanceBand.LOW),
        (".60", "0.60", RelevanceBand.LOW),
        (".604", "0.60", RelevanceBand.LOW),
        (".605", "0.61", RelevanceBand.MEDIUM),
        (".61", "0.61", RelevanceBand.MEDIUM),
        (".90", "0.90", RelevanceBand.MEDIUM),
        (".904", "0.90", RelevanceBand.MEDIUM),
        (".905", "0.91", RelevanceBand.HIGH),
        ("1", "1.00", RelevanceBand.HIGH),
    ],
)
def test_quantized_relevance_boundary(value: str, display: str, band: RelevanceBand) -> None:
    score = DiscoveryRelevance(
        value=Decimal(value),
        policy=FIXTURE_POLICY,
        required_inputs_satisfied=True,
        coverage=Decimal(1),
    )
    assert score.displayed_value == Decimal(display)
    assert score.band == band


@pytest.mark.parametrize("value", ["-.01", "1.01", "NaN", "Infinity"])
def test_relevance_rejects_invalid_numbers(value: str) -> None:
    with pytest.raises(ValidationError):
        DiscoveryRelevance(
            value=Decimal(value),
            policy=FIXTURE_POLICY,
            required_inputs_satisfied=True,
            coverage=Decimal(1),
        )


def test_unscored_is_not_zero_and_thresholds_are_explicit() -> None:
    score = DiscoveryRelevance(
        value=None, policy=FIXTURE_POLICY, required_inputs_satisfied=False, coverage=Decimal(0)
    )
    assert score.band is None and score.displayed_value is None
    with pytest.raises(ValidationError):
        replace(score, value=Decimal(0))
    evaluated = replace(
        score,
        value=Decimal(".55"),
        required_inputs_satisfied=True,
        thresholds={"low_max": ".50", "medium_max": ".80"},
    )
    assert evaluated.band == RelevanceBand.MEDIUM
    with pytest.raises(ValidationError):
        replace(evaluated, thresholds={"low_max": ".80", "medium_max": ".50"})


@pytest.mark.parametrize("grounding", list(GroundingStatus))
def test_grounding_types_without_llm_inference(grounding: GroundingStatus) -> None:
    value = replace(evidence(), category=EvidenceCategory.LLM_INTERPRETATION, grounding=grounding)
    assert value.grounding == grounding
    with pytest.raises(ValidationError):
        replace(value, grounding=None)


def test_structured_missing_conflicting_and_immutable_evidence() -> None:
    item = evidence()
    missing = replace(item, availability="MISSING", measures=(), reason="source-unavailable")
    assert missing.measures == ()
    assert freshness(missing, NOW, 300) == FreshnessState.UNKNOWN
    with pytest.raises(ValidationError):
        replace(missing, measures=item.measures)
    conflict = replace(
        item, category=EvidenceCategory.CONFLICTING, related_evidence_ids=(item.evidence_id,)
    )
    assert conflict.related_evidence_ids == (item.evidence_id,)
    with pytest.raises(ValidationError):
        item.measures[0].value = Decimal(99)
    with pytest.raises(ValidationError):
        item.provenance.producer.provider = "relabelled"


@pytest.mark.parametrize(
    "age,expected",
    [
        (0, FreshnessState.FRESH),
        (300, FreshnessState.FRESH),
        (301, FreshnessState.STALE),
        (-1, FreshnessState.UNKNOWN),
    ],
)
def test_freshness_uses_source_time_not_receipt(age: int, expected: FreshnessState) -> None:
    assert freshness(evidence(), NOW + timedelta(seconds=age), 300) == expected
    assert freshness(replace(evidence(), source_data_time=None), NOW, 300) == FreshnessState.UNKNOWN


def test_snapshot_nested_immutability_and_information_cutoff() -> None:
    service = proof()
    item = asyncio.run(SyntheticCandidateSource().nominate(context())).items[0]
    service.discover(context(), item, intent(), window(), EPISODE)
    snapshot = service.history.snapshots(context().owner_id, EPISODE)[0]
    encoded, digest = snapshot.model_dump_json(), snapshot.content_hash
    with pytest.raises(ValidationError):
        snapshot.evidence[0].measures[0].value = Decimal(42)
    with pytest.raises(ValidationError):
        replace(snapshot, evidence=(replace(item.evidence[0], owner_id=OTHER),))
    with pytest.raises(ValidationError):
        replace(
            snapshot, evidence=(replace(item.evidence[0], received_at=NOW + timedelta(seconds=1)),)
        )
    with pytest.raises(ValidationError):
        replace(snapshot, observed_at=NOW.replace(tzinfo=None))
    assert snapshot.model_dump_json() == encoded and snapshot.content_hash == digest


def test_tolerance_is_typed_and_multidimensional_not_a_scoring_engine() -> None:
    dimensions: tuple[Literal["price", "structure"], ...] = ("price", "structure")
    rules = tuple(
        ToleranceRule(
            dimension=d,
            criterion=Criterion(
                metric="fixture." + d,
                operator=Comparison.GTE,
                threshold=Decimal(2),
                unit="fixture-points",
            ),
            reference_basis="opening-observation",
            required_categories=(EvidenceCategory.TECHNICAL,),
            confirmation_observations=2,
            recovery_rule=FIXTURE_POLICY,
        )
        for d in dimensions
    )
    value = CandidateToleranceEnvelope(policy=FIXTURE_POLICY, rules=rules)
    assert len(value.rules) == 2
    with pytest.raises(ValidationError):
        replace(value, rules=(rules[0], rules[0]))
