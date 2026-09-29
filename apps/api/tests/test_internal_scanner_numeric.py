"""S22-01: non-finite calculations must never become ordinary scan decisions."""

import asyncio
from collections.abc import Callable
from decimal import Decimal
from typing import Literal

import pytest
from discovery_support import FixtureGrants, context, replace
from internal_scanner_support import run_for, series

from twf.discovery.domain import Comparison, Criterion, ScanDefinition
from twf.discovery.internal_scanner import indicators as ind
from twf.discovery.internal_scanner.conditions import METRICS, compare, measure
from twf.discovery.internal_scanner.market_series import (
    DataReason,
    DataUnavailable,
    FixtureMarketSeriesSource,
    MarketSeries,
)
from twf.discovery.internal_scanner.profiles import IDENTITY, build_profile
from twf.discovery.internal_scanner.scanner import InternalScannerV0, ScannerDataFailure
from twf.discovery.providers import ProviderAccess, ProviderFailure
from twf.discovery.synthetic import fixture_id, fixture_instruments
from twf.integrations.contracts import ErrorCode

NONFINITE = (float("nan"), float("inf"), float("-inf"))


def criterion(metric: str, op: Comparison, threshold: str = "1") -> Criterion:
    return Criterion(metric=metric, operator=op, threshold=Decimal(threshold), unit=METRICS[metric])


def definition(*criteria: Criterion, combination: Literal["ALL", "ANY"] = "ALL") -> ScanDefinition:
    base = build_profile("RELATIVE_VOLUME", context(), fixture_id("numeric-review"), interval="1m")
    return replace(base, criteria=criteria, combination=combination)


def overflow_series(metric: str) -> MarketSeries:
    data = series([10] * 21, volumes=[1e-310] * 20 + [100])
    if metric == "roc.10":
        # The denominator ten bars ago is positive/finite and valid OHLC.
        tiny = replace(data.bars[-11], open=1e-310, high=1e-310, low=1e-310, close=1e-310)
        data = replace(data, bars=(*data.bars[:-11], tiny, *data.bars[-10:]))
    return data


@pytest.mark.parametrize("value", NONFINITE)
@pytest.mark.parametrize("op", list(Comparison))
def test_direct_comparison_rejects_nonfinite(value: float, op: Comparison) -> None:
    with pytest.raises(DataUnavailable) as exc:
        compare(value, criterion("close", op))
    assert exc.value.reason == DataReason.MALFORMED_SERIES


@pytest.mark.parametrize("value", NONFINITE)
@pytest.mark.parametrize("operand", range(4))
@pytest.mark.parametrize("cross", [ind.cross_above, ind.cross_below])
def test_every_crossover_operand_is_finite_before_comparison(
    value: float, operand: int, cross: Callable[[float, float, float, float], bool]
) -> None:
    values = [10.0] * 4
    values[operand] = value
    with pytest.raises(DataUnavailable) as exc:
        cross(*values)
    assert exc.value.reason == DataReason.MALFORMED_SERIES


@pytest.mark.parametrize("value", NONFINITE)
def test_breakout_validates_derived_resistance_before_boolean_conversion(
    value: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ind, "rolling_high", lambda bars, period: value)
    with pytest.raises(DataUnavailable) as exc:
        measure("breakout.20", series([10] * 21).bars)
    assert exc.value.reason == DataReason.MALFORMED_SERIES


@pytest.mark.parametrize("metric", ["relative_volume.20", "roc.10"])
@pytest.mark.parametrize("op", list(Comparison))
@pytest.mark.parametrize("guarded", [False, True])
def test_real_finite_input_overflow_has_operator_independent_failure(
    metric: str, op: Comparison, guarded: bool
) -> None:
    data = overflow_series(metric)
    native = InternalScannerV0(FixtureMarketSeriesSource((data,)))
    run = run_for(definition(criterion(metric, op)))

    async def execute() -> None:
        with pytest.raises(ProviderFailure) as exc:
            if guarded:
                await ProviderAccess(FixtureGrants()).call(
                    native,
                    context(),
                    "sd.scan",
                    "sd.scan.v1",
                    lambda: native.scan(context(), run, (data.instrument,)),
                )
            else:
                await native.scan(context(), run, (data.instrument,))
        error = exc.value.error
        assert error.code == ErrorCode.INVALID_RESPONSE
        assert error.provider_id == IDENTITY.service_id
        assert error.operation == "sd.scan"
        assert error.request_id == context().correlation.request_id
        assert str(exc.value) == "INVALID_RESPONSE"
        if not guarded:
            assert isinstance(exc.value, ScannerDataFailure)
            assert exc.value.reason == DataReason.MALFORMED_SERIES
            assert exc.value.instrument_id == data.instrument.instrument_id

    asyncio.run(execute())


@pytest.mark.parametrize("value", NONFINITE)
def test_profile_rejects_nonfinite_metric_result(
    value: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Inject an indicator result, not a bypassed schema-invalid market series.
    monkeypatch.setattr(ind, "relative_volume", lambda bars, period: value)
    data = series([10] * 21)
    native = InternalScannerV0(FixtureMarketSeriesSource((data,)))
    profile = build_profile("RELATIVE_VOLUME", context(), fixture_id("profile"), interval="1m")
    with pytest.raises(ScannerDataFailure) as exc:
        asyncio.run(native.scan(context(), run_for(profile), (data.instrument,)))
    assert exc.value.reason == DataReason.MALFORMED_SERIES


@pytest.mark.parametrize("combination", ["ALL", "ANY"])
@pytest.mark.parametrize("first_matches", [False, True])
def test_composition_cannot_hide_bad_second_condition(
    combination: Literal["ALL", "ANY"], first_matches: bool
) -> None:
    data = overflow_series("relative_volume.20")
    d = definition(
        criterion("close", Comparison.GT, "0" if first_matches else "20"),
        criterion("relative_volume.20", Comparison.LT),
        combination=combination,
    )
    native = InternalScannerV0(FixtureMarketSeriesSource((data,)))
    with pytest.raises(ScannerDataFailure) as exc:
        asyncio.run(native.scan(context(), run_for(d), (data.instrument,)))
    assert exc.value.reason == DataReason.MALFORMED_SERIES


def test_between_overflow_rejects_whole_batch_even_after_a_valid_match() -> None:
    first, second = sorted(fixture_instruments(), key=lambda i: i.instrument_id.hex)[:2]
    good = series([10] * 21, instrument=first)
    bad = replace(overflow_series("relative_volume.20"), instrument=second)
    # BETWEEN is the existing paired inclusive comparisons, not a new operator.
    d = definition(
        criterion("relative_volume.20", Comparison.GTE, "1"),
        criterion("relative_volume.20", Comparison.LTE, "2"),
    )
    native = InternalScannerV0(FixtureMarketSeriesSource((good, bad)))

    async def execute() -> None:
        with pytest.raises(ScannerDataFailure) as exc:
            await native.scan(context(), run_for(d), (first, second))
        assert exc.value.instrument_id == second.instrument_id
        assert exc.value.reason == DataReason.MALFORMED_SERIES
        valid = await native.scan(context(), run_for(d), (first,))
        assert len(valid.items) == 1 and valid.items[0].instrument == first

    asyncio.run(execute())


@pytest.mark.parametrize(
    "volume,matched", [(50, False), (100, True), (150, True), (200, True), (250, False)]
)
def test_finite_between_controls_keep_boundaries(volume: float, matched: bool) -> None:
    data = series([10] * 21, volumes=[100] * 20 + [volume])
    d = definition(
        criterion("relative_volume.20", Comparison.GTE, "1"),
        criterion("relative_volume.20", Comparison.LTE, "2"),
    )
    native = InternalScannerV0(FixtureMarketSeriesSource((data,)))
    result = asyncio.run(native.scan(context(), run_for(d), (data.instrument,)))
    assert bool(result.items) is matched
