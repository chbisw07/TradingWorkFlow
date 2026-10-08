"""Provider-neutral, deterministic Scanner V2 market-context analysis."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, Field

from twf.discovery.market_intelligence import (
    IntelligenceClaim,
    IntelligenceKind,
    IntelligenceState,
    MarketIntelligenceBatch,
    tapetide_limitation_codes,
)
from twf.integrations.contracts import Contract
from twf.scanner_v2.contracts import ContextFilter, ContextMode, Filter


class SetupDirection(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class ContextStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"


class ContextClassification(StrEnum):
    STRONGLY_SUPPORTIVE = "STRONGLY_SUPPORTIVE"
    SUPPORTIVE = "SUPPORTIVE"
    MIXED = "MIXED"
    ADVERSE = "ADVERSE"
    STRONGLY_ADVERSE = "STRONGLY_ADVERSE"
    UNAVAILABLE = "UNAVAILABLE"


class BroadRegime(StrEnum):
    STRONGLY_BULLISH = "STRONGLY_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    STRONGLY_BEARISH = "STRONGLY_BEARISH"
    UNKNOWN = "UNKNOWN"


class SectorStrength(StrEnum):
    STRONG = "STRONG"
    SUPPORTIVE = "SUPPORTIVE"
    NEUTRAL = "NEUTRAL"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"


class SectorRotation(StrEnum):
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DETERIORATING = "DETERIORATING"
    UNKNOWN = "UNKNOWN"


class VixState(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class FlowState(StrEnum):
    STRONGLY_POSITIVE = "STRONGLY_POSITIVE"
    POSITIVE = "POSITIVE"
    MIXED = "MIXED"
    NEGATIVE = "NEGATIVE"
    STRONGLY_NEGATIVE = "STRONGLY_NEGATIVE"
    UNKNOWN = "UNKNOWN"


class BreadthState(StrEnum):
    STRONG = "STRONG"
    POSITIVE = "POSITIVE"
    MIXED = "MIXED"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"


class EventRisk(StrEnum):
    POSITIVE_CATALYST = "POSITIVE_CATALYST"
    SUPPORTIVE = "SUPPORTIVE"
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"
    UNKNOWN = "UNKNOWN"


DIMENSIONS = ("broad_regime", "sector", "vix", "flows", "breadth", "event_news")
VIX_THRESHOLDS = {"low_below": 12.0, "normal_below": 18.0, "elevated_below": 25.0}
CONTEXT_WEIGHTS = {
    "broad_regime": 5,
    "sector": 5,
    "vix": 2,
    "flows": 4,
    "breadth": 3,
    "event_news": 1,
}
TECHNICAL_MATCH_BASELINE = 80


class ContextEvidence(Contract):
    dimension: str
    state: str
    detail: str
    provider: str | None = None
    provider_tool: str | None = None
    source_time: AwareDatetime | None = None
    received_at: AwareDatetime | None = None
    freshness: str


class MarketContextSnapshot(Contract):
    as_of: AwareDatetime
    provider: str | None
    status: ContextStatus
    source_health: str
    broad_regime: BroadRegime = BroadRegime.UNKNOWN
    benchmark_direction: BroadRegime = BroadRegime.UNKNOWN
    sector_strength: SectorStrength = SectorStrength.UNKNOWN
    sector_relative_strength: SectorStrength = SectorStrength.UNKNOWN
    sector_rotation: SectorRotation = SectorRotation.UNKNOWN
    vix_state: VixState = VixState.UNKNOWN
    fii_state: FlowState = FlowState.UNKNOWN
    dii_state: FlowState = FlowState.UNKNOWN
    net_institutional_state: FlowState = FlowState.UNKNOWN
    flow_velocity: str = "UNKNOWN"
    flow_streak: str = "UNKNOWN"
    breadth: BreadthState = BreadthState.UNKNOWN
    event_news_risk: EventRisk = EventRisk.UNKNOWN
    evidence: tuple[ContextEvidence, ...]
    missing_dimensions: tuple[str, ...]
    warnings: tuple[str, ...]
    coverage_count: int = Field(ge=0, le=6)
    dimension_count: int = 6


class ContextContribution(Contract):
    factor: str
    observed_state: str
    interpretation: str
    contribution: int
    explanation: str
    source: str | None
    freshness: str


class TechnicalEvidence(Contract):
    passed: int
    total: int
    diagnostics: tuple[dict[str, Any], ...]


class CandidateAnalysisPacket(Contract):
    run_id: str = Field(min_length=1)
    candidate_instrument_id: str | None
    candidate_symbol: str
    analyzed_at: AwareDatetime
    setup_direction: SetupDirection
    matched: bool
    technical_match: bool
    technical_evidence: TechnicalEvidence
    technical_score: int = Field(ge=0, le=100)
    context_mode: ContextMode
    context_status: ContextStatus
    context_coverage: str
    context_contributions: tuple[ContextContribution, ...]
    supporting_factors: tuple[str, ...]
    contradicting_factors: tuple[str, ...]
    neutral_factors: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    context_adjustment: int = Field(ge=-20, le=20)
    final_relevance: int = Field(ge=0, le=100)
    context_classification: ContextClassification
    short_reason: str = Field(max_length=180)
    provenance: tuple[ContextEvidence, ...]
    warnings: tuple[str, ...]
    context_filter_diagnostics: tuple[dict[str, Any], ...]


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("%", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _claim(batch: MarketIntelligenceBatch, kind: IntelligenceKind) -> IntelligenceClaim | None:
    return next((item for item in batch.claims if item.kind == kind), None)


def _evidence(
    dimension: str, state: StrEnum, detail: str, claim: IntelligenceClaim | None
) -> ContextEvidence:
    return ContextEvidence(
        dimension=dimension,
        state=state.value,
        detail=detail,
        provider=claim.provider if claim else None,
        provider_tool=claim.provider_tool if claim else None,
        source_time=claim.source_time if claim else None,
        received_at=claim.received_at if claim else None,
        freshness=claim.freshness if claim else "UNAVAILABLE",
    )


def _flow(value: object) -> FlowState:
    number = _number(value)
    if number is None:
        return FlowState.UNKNOWN
    if number > 0:
        return FlowState.POSITIVE
    if number < 0:
        return FlowState.NEGATIVE
    return FlowState.MIXED


def normalize_context(
    batch: MarketIntelligenceBatch | None, at: datetime | None = None
) -> MarketContextSnapshot:
    """Discard provider envelopes and retain only the six stable V1 dimensions."""

    now = at or datetime.now(UTC)
    if batch is None:
        batch = MarketIntelligenceBatch(
            provider="tapetide",
            state=IntelligenceState.UNAVAILABLE,
            claims=(),
            received_at=now,
            failures=("not-requested",),
        )
    volatility = _claim(batch, IntelligenceKind.MARKET_VOLATILITY) or _claim(
        batch, IntelligenceKind.MARKET_PULSE
    )
    vix_number = _number(
        volatility.values.get("level", volatility.values.get("india_vix")) if volatility else None
    )
    if vix_number is None:
        vix = VixState.UNKNOWN
    elif vix_number < VIX_THRESHOLDS["low_below"]:
        vix = VixState.LOW
    elif vix_number < VIX_THRESHOLDS["normal_below"]:
        vix = VixState.NORMAL
    elif vix_number < VIX_THRESHOLDS["elevated_below"]:
        vix = VixState.ELEVATED
    else:
        vix = VixState.HIGH

    flow_claim = _claim(batch, IntelligenceKind.MARKET_FLOW) or _claim(
        batch, IntelligenceKind.MARKET_PULSE
    )
    fii = _flow(flow_claim.values.get("fii_net_flow") if flow_claim else None)
    dii = _flow(flow_claim.values.get("dii_net_flow") if flow_claim else None)
    if FlowState.UNKNOWN in {fii, dii}:
        net = FlowState.UNKNOWN
    elif fii == dii:
        net = fii
    elif {fii, dii} == {FlowState.POSITIVE, FlowState.NEGATIVE}:
        net = FlowState.MIXED
    else:
        net = fii if fii != FlowState.MIXED else dii

    news = _claim(batch, IntelligenceKind.NEWS_SENTIMENT)
    sentiment = str(news.values.get("sentiment", "")).strip().casefold() if news else ""
    event = {
        "positive": EventRisk.POSITIVE_CATALYST,
        "bullish": EventRisk.POSITIVE_CATALYST,
        "supportive": EventRisk.SUPPORTIVE,
        "neutral": EventRisk.NEUTRAL,
        "negative": EventRisk.CAUTION,
        "bearish": EventRisk.CAUTION,
        "high_risk": EventRisk.HIGH_RISK,
    }.get(sentiment, EventRisk.UNKNOWN)

    # The current TapTide index output is sectoral, so it must not be promoted
    # to a broad benchmark regime. Candidate sector mapping and breadth are also
    # absent from accepted contracts and stay explicitly UNKNOWN.
    broad = BroadRegime.UNKNOWN
    sector = SectorStrength.UNKNOWN
    rotation = SectorRotation.UNKNOWN
    breadth = BreadthState.UNKNOWN
    evidence = (
        _evidence("broad_regime", broad, "No authoritative broad-benchmark regime evidence", None),
        _evidence("sector", sector, "Candidate-to-sector mapping is unavailable", None),
        _evidence(
            "vix",
            vix,
            f"India VIX {vix_number:g}" if vix_number is not None else "India VIX unavailable",
            volatility,
        ),
        _evidence(
            "flows",
            net,
            f"FII {fii.value}; DII {dii.value}; net {net.value}",
            flow_claim,
        ),
        _evidence("breadth", breadth, "Authoritative breadth evidence unavailable", None),
        _evidence(
            "event_news",
            event,
            "Provider-supplied news sentiment"
            if news and sentiment
            else "Reliable event sentiment unavailable",
            news,
        ),
    )
    missing = tuple(item.dimension for item in evidence if item.state == "UNKNOWN")
    coverage = len(DIMENSIONS) - len(missing)
    if batch.state == IntelligenceState.STALE:
        status = ContextStatus.STALE
    elif coverage == 0:
        status = ContextStatus.UNAVAILABLE
    elif coverage < len(DIMENSIONS) or batch.state != IntelligenceState.AVAILABLE:
        status = ContextStatus.PARTIAL
    else:
        status = ContextStatus.COMPLETE
    warnings = list(tapetide_limitation_codes(batch.failures))
    if flow_claim and net != FlowState.UNKNOWN:
        warnings.append("flow-history-and-streak-unavailable")
    return MarketContextSnapshot(
        as_of=batch.received_at,
        provider=batch.provider if batch.claims else None,
        status=status,
        source_health=batch.state.value,
        broad_regime=broad,
        benchmark_direction=broad,
        sector_strength=sector,
        sector_relative_strength=sector,
        sector_rotation=rotation,
        vix_state=vix,
        fii_state=fii,
        dii_state=dii,
        net_institutional_state=net,
        breadth=breadth,
        event_news_risk=event,
        evidence=evidence,
        missing_dimensions=missing,
        warnings=tuple(dict.fromkeys(warnings)),
        coverage_count=coverage,
    )


def infer_direction(filters: tuple[Filter, ...]) -> SetupDirection:
    bullish = False
    bearish = False
    for item in filters:
        if item.field in {"trend", "supertrend"} and item.operator == "equals":
            bullish |= item.value == "Up"
            bearish |= item.value == "Down"
        if item.field in {"price", "sma20", "sma50", "ema20"} and isinstance(item.value, str):
            bullish |= item.operator in {">", ">=", "crosses_above"}
            bearish |= item.operator in {"<", "<=", "crosses_below"}
    if bullish and not bearish:
        return SetupDirection.BULLISH
    if bearish and not bullish:
        return SetupDirection.BEARISH
    return SetupDirection.UNKNOWN


def _directional(
    state: str,
    positive: tuple[str, ...],
    negative: tuple[str, ...],
    weight: int,
    direction: SetupDirection,
) -> int:
    if direction not in {SetupDirection.BULLISH, SetupDirection.BEARISH}:
        return 0
    score = weight if state in positive else -weight if state in negative else 0
    return -score if direction == SetupDirection.BEARISH else score


def _contributions(
    snapshot: MarketContextSnapshot, direction: SetupDirection
) -> tuple[ContextContribution, ...]:
    states = {
        "broad_regime": snapshot.broad_regime.value,
        "sector": snapshot.sector_strength.value,
        "vix": snapshot.vix_state.value,
        "flows": snapshot.net_institutional_state.value,
        "breadth": snapshot.breadth.value,
        "event_news": snapshot.event_news_risk.value,
    }
    evidence = {item.dimension: item for item in snapshot.evidence}
    scores = {
        "broad_regime": _directional(
            states["broad_regime"],
            ("STRONGLY_BULLISH", "BULLISH"),
            ("STRONGLY_BEARISH", "BEARISH"),
            CONTEXT_WEIGHTS["broad_regime"],
            direction,
        ),
        "sector": _directional(
            states["sector"],
            ("STRONG", "SUPPORTIVE"),
            ("WEAK",),
            CONTEXT_WEIGHTS["sector"],
            direction,
        ),
        "vix": {"LOW": 1, "NORMAL": 1, "ELEVATED": -1, "HIGH": -2}.get(states["vix"], 0),
        "flows": _directional(
            states["flows"],
            ("STRONGLY_POSITIVE", "POSITIVE"),
            ("STRONGLY_NEGATIVE", "NEGATIVE"),
            CONTEXT_WEIGHTS["flows"],
            direction,
        ),
        "breadth": _directional(
            states["breadth"],
            ("STRONG", "POSITIVE"),
            ("WEAK",),
            CONTEXT_WEIGHTS["breadth"],
            direction,
        ),
        "event_news": {
            "POSITIVE_CATALYST": 1,
            "SUPPORTIVE": 1,
            "CAUTION": -1,
            "HIGH_RISK": -1,
        }.get(states["event_news"], 0),
    }
    output: list[ContextContribution] = []
    for factor in DIMENSIONS:
        item = evidence[factor]
        score = scores[factor]
        if item.state == "UNKNOWN":
            interpretation = "MISSING"
        elif score > 0:
            interpretation = "SUPPORTIVE"
        elif score < 0:
            interpretation = "ADVERSE"
        else:
            interpretation = "NEUTRAL"
        output.append(
            ContextContribution(
                factor=factor,
                observed_state=item.state,
                interpretation=interpretation,
                contribution=score,
                explanation=item.detail,
                source=item.provider,
                freshness=item.freshness,
            )
        )
    return tuple(output)


def relevance_score(technical_score: int, context_adjustment: int) -> int:
    """Return the bounded deterministic ranking score."""

    return max(0, min(100, technical_score + context_adjustment))


def _classification(score: int, available: bool) -> ContextClassification:
    if not available:
        return ContextClassification.UNAVAILABLE
    if score >= 12:
        return ContextClassification.STRONGLY_SUPPORTIVE
    if score >= 4:
        return ContextClassification.SUPPORTIVE
    if score <= -12:
        return ContextClassification.STRONGLY_ADVERSE
    if score <= -4:
        return ContextClassification.ADVERSE
    return ContextClassification.MIXED


def _context_filter_diagnostics(
    filters: tuple[ContextFilter, ...], snapshot: MarketContextSnapshot
) -> tuple[tuple[dict[str, Any], ...], bool]:
    diagnostics: list[dict[str, Any]] = []
    for item in filters:
        observed = str(getattr(snapshot, item.field).value)
        passed = observed != "UNKNOWN" and (
            observed == item.value if item.operator == "equals" else observed != item.value
        )
        diagnostics.append(
            {
                "filter": item.model_dump(mode="json"),
                "observed": observed,
                "threshold": item.value,
                "passed": passed,
                "reason": (
                    f"{item.field.replace('_', ' ')} {item.operator.replace('_', ' ')} {item.value}"
                ),
            }
        )
    return tuple(diagnostics), all(item["passed"] for item in diagnostics)


def analyze_candidate(
    symbol: str,
    row: dict[str, Any],
    snapshot: MarketContextSnapshot,
    mode: ContextMode,
    context_filters: tuple[ContextFilter, ...],
    direction: SetupDirection,
    at: datetime,
    run_id: str,
    candidate_instrument_id: str | None,
) -> CandidateAnalysisPacket:
    technical_match = row.get("outcome") == "MATCH"
    diagnostics = tuple(row.get("diagnostics", ()))
    passed = sum(item.get("passed") is True for item in diagnostics)
    total = len(diagnostics)
    technical_score = TECHNICAL_MATCH_BASELINE if technical_match else 0
    contributions = _contributions(snapshot, direction)
    adjustment = 0 if mode == ContextMode.OFF else sum(item.contribution for item in contributions)
    adjustment = max(-20, min(20, adjustment))
    filter_diagnostics, context_passed = _context_filter_diagnostics(context_filters, snapshot)
    matched = technical_match and not (
        mode == ContextMode.HARD_FILTER and context_filters and not context_passed
    )
    classification = _classification(
        adjustment, snapshot.coverage_count > 0 and mode != ContextMode.OFF
    )
    final_relevance = relevance_score(technical_score, adjustment) if technical_match else 0
    supporting = tuple(item.explanation for item in contributions if item.contribution > 0)
    contradicting = tuple(item.explanation for item in contributions if item.contribution < 0)
    neutral = tuple(
        item.explanation
        for item in contributions
        if item.contribution == 0 and item.interpretation != "MISSING"
    )
    coverage = f"{snapshot.coverage_count}/{snapshot.dimension_count}"
    if mode == ContextMode.OFF:
        context_text = "Context off"
    elif snapshot.coverage_count == 0:
        context_text = "Context unavailable"
    else:
        context_text = f"Context {adjustment:+d} {classification.value.replace('_', ' ').title()}"
    short_reason = f"{passed}/{total} technical · {context_text} · Final {final_relevance}"
    return CandidateAnalysisPacket(
        run_id=run_id,
        candidate_instrument_id=candidate_instrument_id,
        candidate_symbol=symbol,
        analyzed_at=at,
        setup_direction=direction,
        matched=matched,
        technical_match=technical_match,
        technical_evidence=TechnicalEvidence(passed=passed, total=total, diagnostics=diagnostics),
        technical_score=technical_score,
        context_mode=mode,
        context_status=snapshot.status,
        context_coverage=coverage,
        context_contributions=contributions,
        supporting_factors=supporting,
        contradicting_factors=contradicting,
        neutral_factors=neutral,
        missing_evidence=snapshot.missing_dimensions,
        context_adjustment=adjustment,
        final_relevance=final_relevance,
        context_classification=classification,
        short_reason=short_reason,
        provenance=snapshot.evidence,
        warnings=snapshot.warnings,
        context_filter_diagnostics=filter_diagnostics,
    )
