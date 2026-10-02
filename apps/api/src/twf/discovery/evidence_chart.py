"""Bounded, profile-aware reconstruction of immutable scan evidence charts."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from math import isclose
from typing import Any, Literal

from twf.discovery.domain import (
    Comparison,
    EvidenceCategory,
    ScanDefinition,
    ScanMatch,
    SourceMode,
)
from twf.discovery.internal_scanner.conditions import compare, measure
from twf.discovery.internal_scanner.indicators import average_volume, sma
from twf.discovery.internal_scanner.market_series import Bar, DataUnavailable, MarketSeries
from twf.discovery.product import (
    EvidenceChart,
    EvidenceChartBar,
    EvidenceChartMetric,
    EvidenceChartMode,
    EvidenceChartPoint,
    EvidenceChartPredicate,
    EvidenceChartRetention,
    EvidenceChartSeries,
    EvidenceChartState,
    EvidenceChartThreshold,
    ProviderChoice,
    ScanSummary,
)

DISPLAY_BARS = 72
METRIC_LABELS = {
    "breakdown.20": "Price below prior 20-day low",
    "breakout.20": "Price above prior 20-day high",
    "close_sma20_gap": "Distance from 20-day average",
    "close_sma50_gap": "Distance from 50-day average",
    "relative_volume.20": "Relative volume",
    "roc.1": "1-day momentum",
    "roc.10": "10-day momentum",
    "rsi.14": "RSI (14)",
    "sma50_sma200_gap": "50-day vs 200-day trend",
}


def archive_payload(series: MarketSeries, definition: ScanDefinition) -> dict[str, Any]:
    """Persist the exact bounded scanner input once per match."""
    synthetic = series.provenance.mode == SourceMode.SYNTHETIC
    return {
        "schema_version": 2,
        "series": series.model_dump(mode="json"),
        "definition": definition.model_dump(mode="json"),
        "retention": {
            "source_class": ("SYNTHETIC_RETAINED" if synthetic else "LICENSED_RETAINED"),
            "historical_chart_reconstructable": True,
            "scan_bars_retained": True,
            "current_chart_available": True,
            "limitation": (
                "Deterministic validation bars are retained."
                if synthetic
                else (
                    "A bounded normalized Dhan series is retained as the immutable "
                    "as-scanned evidence snapshot."
                )
            ),
        },
    }


def _decimal(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _evidence_predicates(match: ScanMatch) -> tuple[EvidenceChartPredicate, ...]:
    output: list[EvidenceChartPredicate] = []
    for item in match.evidence:
        if item.category != EvidenceCategory.PROVIDER_SCAN:
            continue
        values = {entry.name: entry for entry in item.measures}
        metric = next(
            (
                entry
                for entry in item.measures
                if entry.name
                not in {"threshold", "operator", "matched", "price-unit", "input-digest"}
            ),
            None,
        )
        if metric is None or not {"threshold", "operator", "matched"} <= values.keys():
            continue
        output.append(
            EvidenceChartPredicate(
                metric=metric.name,
                label=METRIC_LABELS.get(metric.name, metric.name.replace("_", " ")),
                observed=_decimal(metric.value),
                operator=Comparison(str(values["operator"].value)),
                threshold=_decimal(values["threshold"].value),
                unit=metric.unit,
                matched=bool(values["matched"].value),
            )
        )
    return tuple(output)


def _current_predicates(
    definition: ScanDefinition, bars: Sequence[Bar]
) -> tuple[EvidenceChartPredicate, ...]:
    return tuple(
        EvidenceChartPredicate(
            metric=item.metric,
            label=METRIC_LABELS.get(item.metric, item.metric.replace("_", " ")),
            observed=_decimal(value := measure(item.metric, bars)),
            operator=item.operator,
            threshold=item.threshold,
            unit=item.unit,
            matched=compare(value, item),
        )
        for item in definition.criteria
    )


def _validate_reconciliation(
    predicates: Sequence[EvidenceChartPredicate], definition: ScanDefinition, bars: Sequence[Bar]
) -> None:
    expected = {(item.metric, item.operator.value, item.threshold): item for item in predicates}
    for criterion in definition.criteria:
        key = (criterion.metric, criterion.operator.value, criterion.threshold)
        stored = expected.get(key)
        if stored is None:
            raise ValueError("Persisted predicate set does not match the pinned definition")
        calculated = measure(criterion.metric, bars)
        if not isclose(calculated, float(stored.observed), rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("Archived series does not reconcile with persisted evidence")
        if compare(calculated, criterion) != stored.matched:
            raise ValueError("Persisted predicate outcome does not reconcile")


def _point_series(
    key: str,
    label: str,
    panel: Literal["PRICE", "VOLUME", "OSCILLATOR"],
    all_bars: Sequence[Bar],
    start: int,
    calculator: Any,
) -> EvidenceChartSeries:
    points: list[EvidenceChartPoint] = []
    for index in range(start, len(all_bars)):
        try:
            value = calculator(all_bars[: index + 1])
        except (DataUnavailable, ValueError):
            continue
        points.append(
            EvidenceChartPoint(timestamp=all_bars[index].timestamp, value=_decimal(value))
        )
    return EvidenceChartSeries(key=key, label=label, panel=panel, points=tuple(points))


def _series_for(
    definition: ScanDefinition, all_bars: Sequence[Bar], start: int
) -> tuple[EvidenceChartSeries, ...]:
    metrics = {item.metric for item in definition.criteria}
    output: list[EvidenceChartSeries] = []
    periods: set[int] = set()
    if "close_sma20_gap" in metrics:
        periods.add(20)
    if "close_sma50_gap" in metrics or "sma50_sma200_gap" in metrics:
        periods.add(50)
    if "sma50_sma200_gap" in metrics:
        periods.add(200)
    for period in sorted(periods):
        output.append(
            _point_series(
                f"sma-{period}",
                f"SMA {period}",
                "PRICE",
                all_bars,
                start,
                lambda bars, selected=period: sma([bar.close for bar in bars], selected),
            )
        )
    if "close_sma20_gap" in metrics:
        limits = [
            abs(float(item.threshold))
            for item in definition.criteria
            if item.metric == "close_sma20_gap"
        ]
        zone = max(limits, default=1.0) / 100
        for key, label, multiplier in (
            ("pullback-upper", "Pullback zone upper", 1 + zone),
            ("pullback-lower", "Pullback zone lower", 1 - zone),
        ):
            output.append(
                _point_series(
                    key,
                    label,
                    "PRICE",
                    all_bars,
                    start,
                    lambda bars, factor=multiplier: sma([bar.close for bar in bars], 20) * factor,
                )
            )
    if "relative_volume.20" in metrics:
        output.append(
            _point_series(
                "average-volume-20",
                "20-day average volume",
                "VOLUME",
                all_bars,
                start,
                lambda bars: average_volume(bars, 20),
            )
        )
    for metric in ("roc.1", "roc.10", "rsi.14"):
        if metric in metrics:
            output.append(
                _point_series(
                    metric,
                    METRIC_LABELS[metric],
                    "OSCILLATOR",
                    all_bars,
                    start,
                    lambda bars, selected=metric: measure(selected, bars),
                )
            )
    return tuple(output)


def _thresholds(
    definition: ScanDefinition, bars: Sequence[Bar]
) -> tuple[EvidenceChartThreshold, ...]:
    output: list[EvidenceChartThreshold] = []
    for item in definition.criteria:
        if item.metric == "breakout.20":
            output.append(
                EvidenceChartThreshold(
                    key="breakout-20",
                    label="Prior 20-day high",
                    panel="PRICE",
                    value=_decimal(measure("rolling_high.20", bars)),
                )
            )
        elif item.metric == "breakdown.20":
            output.append(
                EvidenceChartThreshold(
                    key="breakdown-20",
                    label="Prior 20-day low",
                    panel="PRICE",
                    value=_decimal(measure("rolling_low.20", bars)),
                )
            )
        elif item.metric in {"roc.1", "roc.10", "rsi.14"}:
            output.append(
                EvidenceChartThreshold(
                    key=f"{item.metric}-{item.operator.value}-{item.threshold}",
                    label=f"Required {item.operator.value} {item.threshold}",
                    panel="OSCILLATOR",
                    value=item.threshold,
                )
            )
    return tuple(output)


def _metrics(
    predicates: Sequence[EvidenceChartPredicate], bars: Sequence[Bar]
) -> tuple[EvidenceChartMetric, ...]:
    output = [
        EvidenceChartMetric(
            key="close", label="Scan price", value=_decimal(bars[-1].close), unit="INR"
        )
    ]
    if bars[-1].volume is not None:
        output.append(
            EvidenceChartMetric(
                key="volume",
                label="Scan volume",
                value=_decimal(bars[-1].volume or 0),
                unit="volume",
            )
        )
    seen = {"close", "volume"}
    for item in predicates:
        if item.metric in seen:
            continue
        output.append(
            EvidenceChartMetric(
                key=item.metric,
                label=item.label,
                value=item.observed,
                unit=item.unit,
            )
        )
        seen.add(item.metric)
    if any(item.metric == "relative_volume.20" for item in predicates):
        output.append(
            EvidenceChartMetric(
                key="average_volume.20",
                label="20-day average volume",
                value=_decimal(average_volume(bars, 20)),
                unit="volume",
            )
        )
    return tuple(output[:16])


def unavailable_chart(
    *,
    mode: EvidenceChartMode,
    state: EvidenceChartState,
    message: str,
    match: ScanMatch,
    summary: ScanSummary,
    source_class: Literal["PROVIDER_RESTRICTED", "LEGACY_UNKNOWN"],
    historical_chart_reconstructable: bool = False,
    scan_bars_retained: bool = False,
    archive_bar_count: int = 0,
) -> EvidenceChart:
    return EvidenceChart(
        mode=mode,
        state=state,
        message=message,
        run_id=summary.run_id,
        match_id=match.scan_match_id,
        instrument=match.instrument,
        scan_time=summary.started_at,
        source_data_time=None,
        profile=summary.profile,
        profile_revision=match.profile.applied_revision,
        definition_revision=match.definition_revision,
        intent=summary.intent,
        horizon=summary.horizon,
        provider=(
            "tradingview"
            if summary.provider == ProviderChoice.REAL_TRADINGVIEW
            else (
                "dhan"
                if summary.provider.active == ProviderChoice.REAL
                else match.provenance.producer.provider
            )
        ),
        data_mode=match.provenance.mode.value,
        timeframe="1d",
        price_unit="INR",
        bar_finality="PROVIDER_UNSPECIFIED",
        bars=(),
        series=(),
        thresholds=(),
        predicates=_evidence_predicates(match),
        metrics=(),
        retention=EvidenceChartRetention(
            source_class=source_class,
            historical_chart_reconstructable=historical_chart_reconstructable,
            scan_bars_retained=scan_bars_retained,
            current_chart_available=False,
            archive_bar_count=archive_bar_count,
            displayed_bar_count=0,
            limitation=message,
        ),
        provenance=(
            "Persisted normalized scan evidence remains available; source bars are unavailable."
        ),
    )


def build_chart(
    *,
    mode: EvidenceChartMode,
    match: ScanMatch,
    summary: ScanSummary,
    archived_payload: dict[str, Any],
    current_series: MarketSeries | None = None,
) -> EvidenceChart:
    archived_raw = archived_payload.get("series")
    archived_series = (
        MarketSeries.model_validate(archived_raw) if archived_raw is not None else None
    )
    definition = ScanDefinition.model_validate(archived_payload["definition"])
    series = archived_series if mode == EvidenceChartMode.AS_SCANNED else current_series
    if series is None:
        return unavailable_chart(
            mode=mode,
            state=EvidenceChartState.CURRENT_UNAVAILABLE,
            message=(
                "Current chart unavailable for this provider; retained as-scanned "
                "evidence remains usable."
            ),
            match=match,
            summary=summary,
            source_class="PROVIDER_RESTRICTED",
            scan_bars_retained=False,
        )
    cutoff = (
        summary.started_at if mode == EvidenceChartMode.AS_SCANNED else series.bars[-1].timestamp
    )
    all_bars = (
        series.bars
        if mode == EvidenceChartMode.CURRENT and series.provenance.mode != SourceMode.SYNTHETIC
        else series.at(cutoff)
    )
    predicates = (
        _evidence_predicates(match)
        if mode == EvidenceChartMode.AS_SCANNED
        else _current_predicates(definition, all_bars)
    )
    if mode == EvidenceChartMode.AS_SCANNED:
        _validate_reconciliation(predicates, definition, all_bars)
    display = all_bars[-DISPLAY_BARS:]
    start = len(all_bars) - len(display)
    retention = archived_payload["retention"]
    finality: Literal["COMPLETED", "PROVIDER_UNSPECIFIED"] = (
        "COMPLETED"
        if all(item.finality == "COMPLETED" for item in display)
        else "PROVIDER_UNSPECIFIED"
    )
    return EvidenceChart(
        mode=mode,
        state=EvidenceChartState.AVAILABLE,
        run_id=summary.run_id,
        match_id=match.scan_match_id,
        instrument=match.instrument,
        scan_time=summary.started_at
        if mode == EvidenceChartMode.AS_SCANNED
        else display[-1].timestamp,
        source_data_time=display[-1].timestamp,
        profile=summary.profile,
        profile_revision=match.profile.applied_revision,
        definition_revision=match.definition_revision,
        intent=summary.intent,
        horizon=summary.horizon,
        provider=series.provenance.producer.provider,
        data_mode=series.provenance.mode.value,
        timeframe=series.interval,
        price_unit=series.price_unit,
        bar_finality=finality,
        bars=tuple(
            EvidenceChartBar(
                timestamp=item.timestamp,
                open=_decimal(item.open),
                high=_decimal(item.high),
                low=_decimal(item.low),
                close=_decimal(item.close),
                volume=None if item.volume is None else _decimal(item.volume),
                finality=finality,
            )
            for item in display
        ),
        series=_series_for(definition, all_bars, start),
        thresholds=_thresholds(definition, all_bars),
        predicates=predicates,
        metrics=_metrics(predicates, all_bars),
        retention=EvidenceChartRetention(
            **{
                **retention,
                "archive_bar_count": len(archived_series.bars) if archived_series else 0,
                "displayed_bar_count": len(display),
                "current_chart_available": (
                    current_series is not None
                    or summary.provider.active == ProviderChoice.SYNTHETIC
                ),
            }
        ),
        provenance=(
            f"{series.provenance.producer.provider} / "
            f"{series.provenance.producer.service_version} · {series.provenance.transformation.id} "
            f"{series.provenance.transformation.version}"
        ),
    )
