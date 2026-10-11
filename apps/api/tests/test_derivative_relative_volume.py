"""Exact, provider-free O4 relative-volume cohort rules."""

from datetime import timedelta
from decimal import Decimal

import pytest
from test_option_chain import EXPIRY, Source, contract, snapshot

from twf.scanner_v2.derivatives import relative_volume_metrics


def chain_with_volumes(
    volumes: list[int | None],
    *,
    symbol: str = "NIFTY",
    expiry=EXPIRY,
    oi: list[int | None] | None = None,
):
    """Use the canonical O2 snapshot shape; set volumes on CE then PE legs."""
    base = snapshot(Source(), around_atm=2)
    keys = [(row_index, side) for row_index in range(5) for side in ("ce", "pe")]
    rows = list(base.rows)
    for index, (row_index, side) in enumerate(keys):
        row = rows[row_index]
        leg = getattr(row, side)
        assert leg is not None
        if index < len(volumes):
            updated = leg.model_copy(
                update={
                    "contract": contract(
                        int(row.strike), side.upper(), underlying=symbol, expiry=expiry
                    ),
                    "market": leg.market.model_copy(
                        update={
                            "volume": Decimal(volumes[index])
                            if volumes[index] is not None
                            else None,
                            "open_interest": Decimal(oi[index])
                            if oi is not None and oi[index] is not None
                            else (None if oi is not None else Decimal(1000)),
                        }
                    ),
                }
            )
        else:
            updated = None
        rows[row_index] = row.model_copy(update={side: updated})
    return base.model_copy(update={"underlying": symbol, "expiry": expiry, "rows": tuple(rows)})


def metric(chain, index: int, key: str):
    row = chain.rows[index // 2]
    leg = row.ce if index % 2 == 0 else row.pe
    assert leg is not None
    return relative_volume_metrics(chain)[leg.contract.canonical_id][key]


def test_percentile_basic_odd_median_and_combined_sides() -> None:
    chain = chain_with_volumes([10, 20, 30, 40, 50])
    assert [metric(chain, i, "volume_percentile") for i in range(5)] == [20, 40, 60, 80, 100]
    assert metric(chain, 2, "volume_chain_median") == 30
    assert metric(chain, 3, "volume_vs_chain_median") == pytest.approx(4 / 3)
    assert metric(chain, 0, "relative_volume_cohort_size") == 5


def test_ties_use_last_rank_and_missing_is_excluded() -> None:
    chain = chain_with_volumes([10, 20, 20, 20, 50])
    assert [metric(chain, i, "volume_percentile") for i in (1, 2, 3)] == [80, 80, 80]
    missing = chain_with_volumes([10, None, 30, 40, 50, 60])
    assert metric(missing, 1, "volume_percentile") is None
    assert metric(missing, 1, "volume_vs_chain_median") is None
    assert metric(missing, 5, "volume_percentile") == 100
    assert metric(missing, 5, "relative_volume_cohort_size") == 5


def test_even_median_ratio_zero_and_minimum_cohort() -> None:
    even = chain_with_volumes([10, 20, 30, 40, 50, 100])
    assert metric(even, 5, "volume_chain_median") == 35
    assert metric(even, 5, "volume_vs_chain_median") == pytest.approx(100 / 35)
    zeros = chain_with_volumes([0, 0, 0, 0, 100])
    assert metric(zeros, 0, "volume_percentile") == 80
    assert metric(zeros, 4, "volume_vs_chain_median") is None
    small = chain_with_volumes([10, 20, 30, 40])
    assert metric(small, 0, "volume_percentile") is None
    assert metric(small, 0, "volume_vs_chain_median") is None
    assert metric(small, 0, "volume_oi_percent") == 1


def test_volume_oi_percent_and_zero_null_oi() -> None:
    chain = chain_with_volumes([200, 10, 20, 30, 40], oi=[1000, 0, None, 100, 100])
    assert metric(chain, 0, "volume_oi_percent") == 20
    assert metric(chain, 1, "volume_oi_percent") is None
    assert metric(chain, 2, "volume_oi_percent") is None


def test_underlying_and_expiry_cohorts_are_separate() -> None:
    nifty = chain_with_volumes([1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000])
    stock = chain_with_volumes([1000, 2000, 3000, 4000, 5000], symbol="HDFCBANK")
    next_expiry = chain_with_volumes([50, 40, 30, 20, 10], expiry=EXPIRY + timedelta(days=7))
    assert metric(nifty, 0, "volume_percentile") == metric(stock, 0, "volume_percentile") == 20
    assert metric(next_expiry, 0, "volume_percentile") == 100
    assert metric(nifty, 0, "volume_chain_median") == 3_000_000
    assert metric(stock, 0, "volume_chain_median") == 3000
    assert metric(next_expiry, 0, "volume_chain_median") == 30
    assert set(relative_volume_metrics(nifty)).isdisjoint(relative_volume_metrics(stock))
    assert set(relative_volume_metrics(nifty)).isdisjoint(relative_volume_metrics(next_expiry))


def test_missing_relative_metric_only_blocks_when_its_filter_is_active() -> None:
    from twf.scanner_v2.derivatives import DerivativeFilter, evaluate

    chain = chain_with_volumes([10, 20, 30, 40])
    assert metric(chain, 0, "volume_percentile") is None
    active = (DerivativeFilter(field="volume_percentile", operator=">=", value=70),)
    result = evaluate(active, {"volume_percentile": None}, quote_available=True)
    assert result["outcome"] == "NOT_EVALUATED"
    assert result["diagnostics"][0]["passed"] is None
    assert result["missing_evidence"] == ["Volume Percentile"]
    raw_only = (DerivativeFilter(field="volume", operator=">=", value=10),)
    assert evaluate(raw_only, {"volume": 10}, quote_available=True)["outcome"] == "MATCH"
