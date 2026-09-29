from collections.abc import Callable

import pytest
from discovery_support import replace
from internal_scanner_support import series
from pydantic import ValidationError

from twf.discovery.domain import Criterion
from twf.discovery.internal_scanner import indicators as ind
from twf.discovery.internal_scanner.conditions import compare, measure, supported
from twf.discovery.internal_scanner.market_series import DataReason, DataUnavailable


def test_hand_calculated_sma_and_sma_seeded_ema() -> None:
    # SMA(3) of the last [3,4,8] = 5. EMA seed [1,2,3]=2, then 3, then 5.5.
    assert ind.sma([1, 2, 3, 4, 8], 3) == 5
    assert ind.ema([1, 2, 3], 3) == 2
    assert ind.ema([1, 2, 3, 4, 8], 3) == 5.5


def test_wilder_rsi_independent_seed_and_smoothing() -> None:
    # Changes +1,-1,+2 seed gain=1/loss=1/3; next -1 -> gain=2/3, loss=5/9.
    assert ind.rsi([1, 2, 1, 3], 3) == pytest.approx(75)
    assert ind.rsi([1, 2, 1, 3, 2], 3) == pytest.approx(100 * 6 / 11)


@pytest.mark.parametrize(
    "values,expected", [([1, 2, 3, 4], 100), ([4, 3, 2, 1], 0), ([2, 2, 2, 2], 50)]
)
def test_rsi_edges(values: list[float], expected: float) -> None:
    assert ind.rsi(values, 3) == expected


def test_atr_true_range_gap_seed_and_wilder_smoothing() -> None:
    bars = series([10, 12, 11, 15]).bars
    bars = (
        replace(bars[0], high=11, low=9),
        replace(bars[1], high=13, low=11),
        replace(bars[2], high=12, low=10),
        replace(bars[3], high=16, low=14),
    )
    # TR from previous closes: 3,2,5. Seed(2)=2.5; next Wilder value=(2.5+5)/2.
    assert ind.atr(bars[:3], 2) == 2.5
    assert ind.atr(bars, 2) == 3.75


def test_relative_volume_excludes_current_bar() -> None:
    bars = series([10] * 4, volumes=[10, 20, 30, 120]).bars
    assert ind.average_volume(bars, 3) == 20
    assert ind.relative_volume(bars, 3) == 6


@pytest.mark.parametrize(
    "volumes,reason",
    [
        ([0, 0, 10], DataReason.ZERO_BASELINE),
        ([10, None, 10], DataReason.MISSING_VOLUME),
        ([10, 20, None], DataReason.MISSING_VOLUME),
    ],
)
def test_relative_volume_undefined(volumes: list[float | None], reason: DataReason) -> None:
    with pytest.raises(DataUnavailable) as exc:
        ind.relative_volume(series([10] * 3, volumes=volumes).bars, 2)
    assert exc.value.reason == reason


@pytest.mark.parametrize(
    "values,roc,momentum", [([10, 11, 12], 20, 2), ([10, 9, 8], -20, -2), ([10, 10, 10], 0, 0)]
)
def test_roc_and_momentum(values: list[float], roc: float, momentum: float) -> None:
    assert ind.roc(values, 2) == pytest.approx(roc)
    assert ind.momentum(values, 2) == momentum


def test_rolling_prior_range_excludes_current_high_low() -> None:
    bars = series([10, 12, 11, 20]).bars
    assert ind.rolling_high(bars, 3) == 12.1
    assert ind.rolling_low(bars, 3) == 9.9
    assert ind.roc([1, 2, 3], 1) == 50


@pytest.mark.parametrize("fn", [ind.sma, ind.ema, ind.rsi, ind.roc, ind.momentum])
def test_warmup_numeric(fn: Callable[[list[float], int], float]) -> None:
    with pytest.raises(DataUnavailable) as exc:
        fn([10], 3)
    assert exc.value.reason == DataReason.INSUFFICIENT_HISTORY


@pytest.mark.parametrize(
    "metric",
    [
        "atr.14",
        "relative_volume.20",
        "average_volume.20",
        "rolling_high.20",
        "rolling_low.20",
        "rolling_high.252",
        "rolling_low.252",
        "cross_above_sma.20",
    ],
)
def test_warmup_bar_metrics(metric: str) -> None:
    with pytest.raises(DataUnavailable) as exc:
        measure(metric, series([10]).bars)
    assert exc.value.reason == DataReason.INSUFFICIENT_HISTORY


@pytest.mark.parametrize(
    "previous,current,above,below",
    [
        (0, 1, True, False),
        (1, 2, False, False),
        (-1, 1, True, False),
        (0, -1, False, True),
        (-1, -2, False, False),
        (1, -1, False, True),
        (0, 0, False, False),
    ],
)
def test_explicit_crossing_semantics(
    previous: float, current: float, above: bool, below: bool
) -> None:
    assert ind.cross_above(previous, 0, current, 0) == above
    assert ind.cross_below(previous, 0, current, 0) == below


def test_actual_price_sma_cross_not_merely_above() -> None:
    assert measure("cross_above_sma.20", series([10] * 20 + [11]).bars) == 1
    assert measure("cross_above_sma.20", series([10] * 19 + [11, 12]).bars) == 0
    assert measure("cross_below_sma.20", series([10] * 20 + [9]).bars) == 1
    assert measure("breakout.20", series([10] * 20 + [10.1]).bars) == 0
    assert measure("breakout.20", series([10] * 20 + [10.2]).bars) == 1


@pytest.mark.parametrize(
    "op,value,expected",
    [
        ("GT", 2, True),
        ("GT", 1, False),
        ("GTE", 1, True),
        ("LT", 0, True),
        ("LT", 1, False),
        ("LTE", 1, True),
        ("EQ", 1, True),
        ("EQ", 2, False),
        ("GT", 1 + 1e-10, False),
    ],
)
def test_comparison_operators_and_tolerance(op: str, value: float, expected: bool) -> None:
    criterion = Criterion.model_validate(
        dict(metric="close", operator=op, threshold=1, unit="price")
    )
    assert compare(value, criterion) == expected


@pytest.mark.parametrize(
    "fields",
    [
        {"metric": "exec.os"},
        {"unit": "wrong"},
        {"threshold": "1e99"},
        {"metric": "breakout.20", "unit": "boolean", "operator": "GT"},
    ],
)
def test_unsupported_condition_combinations(fields: dict[str, str]) -> None:
    criterion = Criterion.model_validate(
        dict(metric="close", operator="GT", threshold=1, unit="price") | fields
    )
    assert not supported(criterion)


@pytest.mark.parametrize(
    "fields", [{"operator": "BETWEEN"}, {"operator": "EXEC"}, {"threshold": "NaN"}]
)
def test_no_new_expression_language(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Criterion.model_validate(
            dict(metric="close", operator="GT", threshold=1, unit="price") | fields
        )


@pytest.mark.parametrize(
    "metric,expected",
    [
        ("close", 10),
        ("volume", 100),
        ("sma.20", 10),
        ("sma.50", 10),
        ("sma.200", 10),
        ("ema.20", 10),
        ("rsi.14", 50),
        ("atr.14", 0.2),
        ("roc.1", 0),
        ("roc.10", 0),
        ("momentum.10", 0),
        ("average_volume.20", 100),
        ("relative_volume.20", 1),
        ("rolling_high.20", 10.1),
        ("rolling_low.20", 9.9),
        ("rolling_high.252", 10.1),
        ("rolling_low.252", 9.9),
        ("close_sma20_gap", 0),
        ("close_sma50_gap", 0),
        ("sma50_sma200_gap", 0),
        ("breakout.20", 0),
        ("cross_above_sma.20", 0),
        ("cross_below_sma.20", 0),
    ],
)
def test_all_advertised_metrics_on_known_constant_series(metric: str, expected: float) -> None:
    assert measure(metric, series([10] * 260).bars) == pytest.approx(expected)
