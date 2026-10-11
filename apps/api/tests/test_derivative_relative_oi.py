"""Provider-free O4 OI cohort, filter, and conservative interpretation rules."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from test_derivative_relative_volume import chain_with_volumes
from test_option_chain import EXPIRY, Source, snapshot

from twf.scanner_v2.derivatives import (
    DerivativeFilter,
    evaluate,
    oi_interpretation,
    relative_oi_metrics,
)

NOW = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)


def with_oi(oi: list[int | None], changes: list[int | None]) -> Any:
    chain = chain_with_volumes([100] * len(oi), oi=oi)
    rows = list(chain.rows)
    for index, change in enumerate(changes):
        row_index, side = divmod(index, 2)
        row = rows[row_index]
        name = "ce" if side == 0 else "pe"
        leg = getattr(row, name)
        assert leg is not None
        leg = leg.model_copy(
            update={
                "market": leg.market.model_copy(
                    update={
                        "change_in_open_interest": Decimal(change) if change is not None else None
                    }
                )
            }
        )
        rows[row_index] = row.model_copy(update={name: leg})
    return chain.model_copy(update={"rows": tuple(rows)})


def metric(chain: Any, index: int, key: str) -> Any:
    row = chain.rows[index // 2]
    leg = row.ce if index % 2 == 0 else row.pe
    assert leg is not None
    return relative_oi_metrics(chain)[leg.contract.canonical_id][key]


def test_oi_percentile_median_ties_missing_and_zero() -> None:
    chain = with_oi([10, 20, 30, 40, 50], [1, 2, 3, 4, 5])
    assert [metric(chain, i, "oi_percentile") for i in range(5)] == [20, 40, 60, 80, 100]
    assert metric(chain, 2, "oi_chain_median") == 30
    assert float(metric(chain, 3, "oi_vs_chain_median")) == pytest.approx(4 / 3)
    tied = with_oi([10, 20, 20, 20, 50], [1] * 5)
    assert [metric(tied, i, "oi_percentile") for i in (1, 2, 3)] == [80, 80, 80]
    missing = with_oi([0, None, 0, 0, 50, 100], [0] * 6)
    assert metric(missing, 1, "oi_percentile") is None
    assert metric(missing, 0, "oi_percentile") == 60
    assert metric(missing, 0, "relative_oi_cohort_size") == 5
    assert metric(missing, 5, "oi_vs_chain_median") is None
    even = with_oi([10, 20, 30, 40, 50, 60], [1] * 6)
    assert metric(even, 0, "oi_chain_median") == 35
    assert float(metric(even, 5, "oi_vs_chain_median")) == pytest.approx(60 / 35)
    small = with_oi([10, 20, 30, 40], [1] * 4)
    assert metric(small, 0, "oi_percentile") is None


def test_change_percent_safety_and_absolute_magnitude_percentile() -> None:
    chain = with_oi([120, 80, 0, 20, 50], [20, -20, 0, 20, None])
    assert metric(chain, 0, "oi_change_percent") == 20
    assert metric(chain, 1, "oi_change_percent") == -20
    assert metric(chain, 2, "oi_change_percent") is None
    assert metric(chain, 3, "oi_change_percent") is None
    assert metric(chain, 4, "oi_change_percent") is None
    assert metric(chain, 0, "oi_change_percentile") is None  # four valid changes
    chain = with_oi([120, 80, 0, 20, 50], [20, -20, 0, 20, -5])
    assert metric(chain, 0, "oi_change_percentile") == 100
    assert metric(chain, 1, "oi_change_percentile") == 100
    assert metric(chain, 2, "oi_change_percentile") == 20


def test_oi_cohorts_are_isolated_and_filters_are_explicit() -> None:
    nifty = with_oi([10, 20, 30, 40, 50], [1] * 5)
    bank = chain_with_volumes([1] * 5, symbol="HDFCBANK", oi=[100, 200, 300, 400, 500])
    assert metric(nifty, 0, "oi_percentile") == metric(bank, 0, "oi_percentile")
    assert metric(nifty, 0, "oi_chain_median") == 30
    assert metric(bank, 0, "oi_chain_median") == 300
    assert set(relative_oi_metrics(nifty)).isdisjoint(relative_oi_metrics(bank))
    next_expiry = chain_with_volumes(
        [1] * 5, expiry=EXPIRY + timedelta(days=7), oi=[500, 400, 300, 200, 100]
    )
    assert metric(next_expiry, 0, "oi_percentile") == 100
    assert metric(next_expiry, 0, "oi_chain_median") == 300
    assert set(relative_oi_metrics(nifty)).isdisjoint(relative_oi_metrics(next_expiry))
    for field, value, low, high in (
        ("oi_percentile", 80, 79.9, 95),
        ("oi_vs_chain_median", 2, 1.9, 2.1),
        ("oi_change_percent", 10, 9.9, 10),
        ("oi_change_percentile", 80, 79.9, 95),
    ):
        filt = (DerivativeFilter(field=field, operator=">=", value=value),)
        assert evaluate(filt, {field: low}, quote_available=True)["outcome"] == "NON_MATCH"
        assert evaluate(filt, {field: high}, quote_available=True)["outcome"] == "MATCH"
        assert evaluate(filt, {field: None}, quote_available=True)["outcome"] == "NOT_EVALUATED"
    negative = (DerivativeFilter(field="oi_change_percent", operator="<=", value=-10),)
    assert (
        evaluate(negative, {"oi_change_percent": -10}, quote_available=True)["outcome"] == "MATCH"
    )


def interpretation(
    side: str,
    ltp: int,
    oi: int,
    old_spot: int = 100,
    iv: int | None = None,
    old_iv: int | None = None,
) -> dict[str, Any]:
    chain = snapshot(Source(), around_atm=0)
    chain = chain.model_copy(
        update={
            "spot": Decimal("102.5"),
            "provenance": chain.provenance.model_copy(update={"received_at": NOW}),
        }
    )
    leg = chain.rows[0].ce if side == "CE" else chain.rows[0].pe
    assert leg is not None
    leg = leg.model_copy(
        update={
            "market": leg.market.model_copy(
                update={
                    "ltp": Decimal(ltp),
                    "open_interest": Decimal(oi),
                    "implied_volatility": Decimal(iv) if iv is not None else None,
                }
            )
        }
    )
    prior = {
        "market": {
            "ltp": "100",
            "open_interest": "100",
            "implied_volatility": str(old_iv) if old_iv is not None else None,
        },
        "spot": str(old_spot),
        "provenance": {
            "provider": "dhan",
            "received_at": (NOW - timedelta(minutes=15)).isoformat(),
            "cached": False,
        },
    }
    return oi_interpretation(chain, leg, prior)


@pytest.mark.parametrize(
    "side,ltp,oi,old_spot,label",
    [
        ("CE", 120, 120, 100, "Call long buildup"),
        ("CE", 80, 120, 105, "Call short buildup"),
        ("PE", 120, 120, 105, "Put long buildup"),
        ("PE", 80, 120, 100, "Put short buildup"),
        ("CE", 120, 80, 100, "Short covering"),
        ("CE", 80, 80, 105, "Long unwinding"),
    ],
)
def test_inferred_patterns_have_archived_window(
    side: str, ltp: int, oi: int, old_spot: int, label: str
) -> None:
    result = interpretation(side, ltp, oi, old_spot)
    assert result["label"] == label
    assert result["inferred"] is True
    assert result["confidence"] in {"LOW", "MEDIUM", "HIGH"}
    assert result["window_seconds"] == 900
    assert result["premium_change_percent"] == (ltp - 100)
    assert result["oi_window_change_percent"] == (oi - 100)
    assert result["underlying_change_percent"] is not None
    assert result["freshness"] == "SOURCE_TIME_UNAVAILABLE"


def test_fresh_option_timestamps_can_support_high_evidence_quality() -> None:
    chain = snapshot(Source(), around_atm=0)
    chain = chain.model_copy(
        update={
            "spot": Decimal("102.5"),
            "provenance": chain.provenance.model_copy(
                update={"received_at": NOW, "freshness": "FRESH", "cached": False}
            ),
        }
    )
    leg = chain.rows[0].ce
    assert leg is not None
    leg = leg.model_copy(
        update={
            "market": leg.market.model_copy(
                update={
                    "ltp": Decimal("120"),
                    "open_interest": Decimal("120"),
                    "source_time": NOW,
                }
            )
        }
    )
    prior = {
        "market": {
            "ltp": "100",
            "open_interest": "100",
            "source_time": (NOW - timedelta(minutes=15)).isoformat(),
        },
        "spot": "100",
        "provenance": {
            "provider": "dhan",
            "received_at": (NOW - timedelta(minutes=15)).isoformat(),
            "cached": False,
        },
    }
    result = oi_interpretation(chain, leg, prior)
    assert result["label"] == "Call long buildup"
    assert result["confidence"] == "HIGH"
    assert result["freshness"] == "FRESH"
    assert result["window_seconds"] == 900


def test_conflict_missing_and_stale_do_not_make_strong_claims() -> None:
    conflicting = interpretation("CE", 120, 120, 105, iv=18, old_iv=20)
    assert conflicting["confidence"] == "LOW"
    assert interpretation("CE", 100, 120)["label"] == "Mixed / Unclear"
    chain = snapshot(Source(), around_atm=0)
    leg = chain.rows[0].ce
    assert leg is not None
    assert oi_interpretation(chain, leg, None)["label"] == "Insufficient evidence"
    stale = chain.model_copy(
        update={"provenance": chain.provenance.model_copy(update={"freshness": "STALE"})}
    )
    prior = {
        "market": {"ltp": "9", "open_interest": "40"},
        "spot": "100",
        "provenance": {
            "provider": "dhan",
            "received_at": (stale.provenance.received_at - timedelta(minutes=5)).isoformat(),
        },
    }
    assert oi_interpretation(stale, leg, prior)["confidence"] == "INSUFFICIENT"
