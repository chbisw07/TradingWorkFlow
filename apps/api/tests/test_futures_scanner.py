"""O5 exact-contract futures scanning over bounded Dhan quote evidence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_watchlists import HEADERS
from test_watchlists import client as client  # noqa: F401

from twf.discovery.market_data import QuoteSnapshot
from twf.scanner_v2.futures import (
    FuturesFilter,
    FuturesScanConfig,
    evaluate,
    interpretation,
    percentile,
)

BASE = "/api/v1/scanner/derivatives"
SYMBOLS = ("RELIANCE", "INFY", "HDFCBANK", "TCS", "SBIN")


def payload(**kwargs: Any) -> dict[str, Any]:
    return {
        "instrument_scope": "FUTURES",
        "universe": {"source": "CUSTOM", "symbols": list(SYMBOLS)},
        "filters": [{"field": "volume_percentile", "operator": ">=", "value": 60}],
        **kwargs,
    }


def install_futures(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    spot_source_lag_minutes: int = 0,
    missing_contract_symbol: str | None = None,
    ambiguous_symbol: str | None = None,
    stale_contract_symbol: str | None = None,
) -> dict[str, int]:
    from test_watchlists import provider as base_provider

    provider = base_provider()
    expiry = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    rows = []
    for index, symbol in enumerate(SYMBOLS, 1):
        rows.append(
            {
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "E",
                "SEM_SMST_SECURITY_ID": str(index),
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_TRADING_SYMBOL": symbol,
                "SEM_CUSTOM_SYMBOL": symbol,
                "SEM_EXCH_INSTRUMENT_TYPE": "",
                "SEM_SERIES": "EQ",
                "SM_SYMBOL_NAME": symbol,
            }
        )
        rows.append(
            {
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "D",
                "SEM_SMST_SECURITY_ID": str(100 + index),
                "SEM_INSTRUMENT_NAME": "FUTSTK",
                "SEM_TRADING_SYMBOL": f"{symbol}FUT",
                "SEM_CUSTOM_SYMBOL": f"{symbol}FUT",
                "SEM_EXCH_INSTRUMENT_TYPE": "",
                "SEM_SERIES": "",
                "SM_SYMBOL_NAME": symbol,
                "SEM_EXPIRY_DATE": expiry,
                "SEM_LOT_UNITS": "50",
                "SEM_TICK_SIZE": "0.05",
            }
        )
    if ambiguous_symbol:
        duplicate = next(
            row
            for row in rows
            if row["SEM_INSTRUMENT_NAME"] == "FUTSTK" and row["SM_SYMBOL_NAME"] == ambiguous_symbol
        ).copy()
        duplicate["SEM_SMST_SECURITY_ID"] = "901"
        rows.append(duplicate)
    provider._futures_master = tuple(rows)
    provider._futures_master_at = datetime.now(UTC)
    counts = {"quotes": 0, "master": 0}
    original_master = provider._load_futures_master

    async def master() -> tuple[dict[str, str], ...]:
        counts["master"] += 1
        return await original_master()

    async def quotes(instruments: tuple[Any, ...]) -> tuple[QuoteSnapshot, ...]:
        counts["quotes"] += 1
        assert len(instruments) == 10
        now = datetime.now(UTC)
        result = []
        for item in instruments:
            index = SYMBOLS.index(item.symbol.replace("FUT", "")) + 1
            future = item.instrument_type == "FUTSTK"
            result.append(
                QuoteSnapshot(
                    instrument=item,
                    last_price=Decimal(
                        101 + index + counts["quotes"] - 1 if future else 100 + index
                    ),
                    open=Decimal(100 + index),
                    previous_close=Decimal(100),
                    volume=Decimal(index * 100) if future else None,
                    open_interest=Decimal(index * 1000 + (counts["quotes"] - 1) * 100)
                    if future
                    else None,
                    provider_source_time=(
                        now - timedelta(minutes=spot_source_lag_minutes)
                        if not future
                        else now - timedelta(days=8)
                        if item.symbol == f"{stale_contract_symbol}FUT"
                        else now
                    ),
                    received_at=now,
                    provider="dhan",
                )
            )
        return tuple(result)

    monkeypatch.setattr(provider, "_load_futures_master", master)

    async def partial(
        instruments: tuple[Any, ...],
    ) -> tuple[tuple[QuoteSnapshot, ...], tuple[str, ...]]:
        batch = await quotes(instruments)
        missing = tuple(
            q.instrument.native.native_id
            for q in batch
            if q.instrument.symbol == f"{missing_contract_symbol}FUT"
        )
        return (
            tuple(q for q in batch if q.instrument.native.native_id not in missing),
            missing,
        )

    monkeypatch.setattr(provider, "get_quotes_partial", partial)
    monkeypatch.setattr(
        cast(Any, client.app).state.dhan_credentials,
        "capture",
        lambda *args, **kw: SimpleNamespace(
            provider=provider, status=SimpleNamespace(generation=3)
        ),
    )
    return counts


def test_futures_config_rejects_option_filters_and_invalid_bounds() -> None:
    with pytest.raises(ValidationError):
        FuturesScanConfig.model_validate(
            payload(filters=[{"field": "option_type", "operator": "equals", "value": "CE"}])
        )
    with pytest.raises(ValidationError):
        FuturesScanConfig.model_validate(
            payload(universe={"source": "CUSTOM", "symbols": [f"A{i}" for i in range(51)]})
        )
    assert percentile([Decimal(x) for x in (1, 2, 2, 4, 5)], Decimal(2)) == 60
    assert percentile([Decimal(1)] * 4, Decimal(1)) is None
    assert interpretation(Decimal("1"), Decimal("10"), Decimal("100"))["label"] == "Long buildup"
    assert interpretation(Decimal("-1"), Decimal("10"), Decimal("100"))["label"] == "Short buildup"
    assert interpretation(Decimal("1"), Decimal("-10"), Decimal("100"))["label"] == "Short covering"
    assert (
        interpretation(Decimal("-1"), Decimal("-10"), Decimal("100"))["label"] == "Long unwinding"
    )
    assert (
        evaluate(
            (FuturesFilter(field="basis_percent", operator=">", value=1),),
            {"basis_percent": None},
            True,
        )["outcome"]
        == "NOT_EVALUATED"
    )


def test_futures_run_archives_exact_contracts_and_one_quote_batch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    counts = install_futures(client, monkeypatch)
    response = client.post(BASE + "/futures/runs", json=payload(), headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert counts["quotes"] == 1
    assert counts["master"] == 1
    assert run["counts"] == {
        "requested": 5,
        "resolved": 5,
        "contracts_evaluated": 5,
        "not_evaluated": 0,
        "matches": 3,
    }
    assert [r["volume_percentile"] for r in run["rows"]] == [20, 40, 60, 80, 100]
    assert run["rows"][0]["contract"]["provider_native_id"] == "NSE_FNO:101"
    assert run["rows"][0]["contract"]["lot_size"] == 50
    assert run["rows"][0]["observed"]["basis_abs"] == 1
    assert run["rows"][0]["futures_interpretation"]["label"] == "Insufficient evidence"
    assert client.get(BASE + "/runs/" + run["id"]).json()["rows"] == run["rows"]
    assert client.get(BASE + "/futures/catalog").json()["max_underlyings"] == 50


def test_archived_exact_contract_comparison_is_inferred_and_immutable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch)
    first = client.post(BASE + "/futures/runs", json=payload(), headers=HEADERS)
    assert first.status_code == 200, first.text
    second = client.post(BASE + "/futures/runs", json=payload(), headers=HEADERS)
    assert second.status_code == 200, second.text
    prior, current = first.json(), second.json()
    assert prior["rows"][0]["observed"]["change_in_open_interest"] is None
    row = current["rows"][0]
    assert row["observed"]["change_in_open_interest"] == 100
    assert row["comparison_window"] is not None
    assert row["futures_interpretation"]["inferred"] is True
    assert row["futures_interpretation"]["label"] == "Long buildup"
    archived = client.get(BASE + "/runs/" + prior["id"]).json()
    assert archived["rows"][0] == prior["rows"][0]


def test_stale_spot_makes_basis_unavailable_and_active_basis_filter_not_evaluated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch, spot_source_lag_minutes=20)
    response = client.post(
        BASE + "/futures/runs",
        json=payload(filters=[{"field": "basis_percent", "operator": ">=", "value": 0}]),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["counts"]["matches"] == 0
    assert run["counts"]["not_evaluated"] == 5
    assert all(row["observed"]["basis_abs"] is None for row in run["rows"])
    assert all(row["outcome"] == "NOT_EVALUATED" for row in run["rows"])


def test_partial_quote_does_not_suppress_other_futures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    counts = install_futures(client, monkeypatch, missing_contract_symbol="INFY")
    response = client.post(
        BASE + "/futures/runs",
        json=payload(filters=[{"field": "volume", "operator": ">=", "value": 100}]),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert counts["quotes"] == 1
    assert run["counts"]["resolved"] == 5
    assert run["counts"]["not_evaluated"] == 1
    assert next(r for r in run["rows"] if r["underlying"] == "INFY")["outcome"] == "NOT_EVALUATED"
    assert next(r for r in run["rows"] if r["underlying"] == "TCS")["outcome"] == "MATCH"


def test_exact_expiry_requires_an_active_contract(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch)
    expiry = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    exact = client.post(
        BASE + "/futures/runs",
        json=payload(expiry_mode="EXACT", exact_expiry=expiry),
        headers=HEADERS,
    )
    assert exact.status_code == 200, exact.text
    assert exact.json()["counts"]["resolved"] == 5
    absent = client.post(
        BASE + "/futures/runs",
        json=payload(expiry_mode="EXACT", exact_expiry="2099-12-30"),
        headers=HEADERS,
    )
    assert absent.status_code == 200, absent.text
    assert absent.json()["counts"]["resolved"] == 0
    assert absent.json()["counts"]["not_evaluated"] == 5


def test_index_future_uses_exact_futidx_and_authoritative_index_spot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_watchlists import provider as base_provider

    provider = base_provider()
    expiry = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    provider._futures_master = (
        {
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_SEGMENT": "D",
            "SEM_SMST_SECURITY_ID": "301",
            "SEM_INSTRUMENT_NAME": "FUTIDX",
            "SEM_TRADING_SYMBOL": "NIFTYFUT",
            "SEM_CUSTOM_SYMBOL": "NIFTYFUT",
            "SEM_EXCH_INSTRUMENT_TYPE": "",
            "SEM_SERIES": "",
            "SM_SYMBOL_NAME": "NIFTY",
            "SEM_EXPIRY_DATE": expiry,
            "SEM_LOT_UNITS": "65",
            "SEM_TICK_SIZE": "0.05",
        },
        {
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_SEGMENT": "I",
            "SEM_SMST_SECURITY_ID": "13",
            "SEM_INSTRUMENT_NAME": "INDEX",
            "SEM_TRADING_SYMBOL": "NIFTY",
            "SEM_CUSTOM_SYMBOL": "NIFTY 50",
            "SEM_EXCH_INSTRUMENT_TYPE": "INDEX",
            "SEM_SERIES": "X",
            "SM_SYMBOL_NAME": "NIFTY 50",
        },
    )
    provider._futures_master_at = datetime.now(UTC)
    calls = {"quotes": 0}

    async def partial(
        instruments: tuple[Any, ...],
    ) -> tuple[tuple[QuoteSnapshot, ...], tuple[str, ...]]:
        calls["quotes"] += 1
        assert {i.native.native_id for i in instruments} == {"NSE_FNO:301", "IDX_I:13"}
        now = datetime.now(UTC)
        return (
            tuple(
                QuoteSnapshot(
                    instrument=item,
                    last_price=Decimal(25100 if item.instrument_type == "FUTIDX" else 25000),
                    open=Decimal(25000),
                    previous_close=Decimal(24900),
                    volume=Decimal(1000),
                    open_interest=Decimal(5000) if item.instrument_type == "FUTIDX" else None,
                    provider_source_time=now,
                    received_at=now,
                    provider="dhan",
                )
                for item in instruments
            ),
            (),
        )

    monkeypatch.setattr(provider, "get_quotes_partial", partial)
    monkeypatch.setattr(
        cast(Any, client.app).state.dhan_credentials,
        "capture",
        lambda *args, **kw: SimpleNamespace(
            provider=provider, status=SimpleNamespace(generation=3)
        ),
    )
    request = payload(
        universe={"source": "CUSTOM", "symbols": ["NIFTY", "RELIANCE"]},
        filters=[{"field": "basis_abs", "operator": ">=", "value": 0}],
    )
    response = client.post(BASE + "/futures/runs", json=request, headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert calls["quotes"] == 1
    assert run["counts"] == {
        "requested": 2,
        "resolved": 1,
        "contracts_evaluated": 1,
        "not_evaluated": 1,
        "matches": 1,
    }
    row = run["rows"][0]
    assert row["contract"]["instrument_type"] == "FUTIDX"
    assert row["contract"]["provider_native_id"] == "NSE_FNO:301"
    assert row["spot_quote"]["last_price"] == "25000"
    assert row["observed"]["basis_abs"] == 100
    assert row["observed"]["underlying_trend"] == "Up"
    assert (
        next(x for x in run["underlyings"] if x["symbol"] == "RELIANCE")["failure"]
        == "NO_MASTER_MATCH"
    )


def test_duplicate_same_expiry_contract_uses_stable_security_order(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch, ambiguous_symbol="INFY")
    response = client.post(
        BASE + "/futures/runs",
        json=payload(filters=[{"field": "volume", "operator": ">=", "value": 100}]),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["counts"]["resolved"] == 5
    assert run["counts"]["not_evaluated"] == 0
    infy = next(row for row in run["rows"] if row["underlying"] == "INFY")
    assert infy["contract"]["provider_native_id"] == "NSE_FNO:102"


def test_futures_saved_scan_is_configuration_only_and_history_is_owner_scoped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch)
    config = FuturesScanConfig.model_validate(payload()).model_dump(mode="json")
    saved = client.post(
        BASE + "/futures/saved",
        json={"config": config, "archived": False},
        headers=HEADERS,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["config"]["instrument_scope"] == "FUTURES"
    assert "rows" not in saved.json() and "quote" not in str(saved.json())
    listed = client.get(BASE + "/saved").json()
    assert len(listed) == 1 and listed[0]["id"] == saved.json()["id"]
    assert client.get(BASE + "/runs").json() == []
    executed = client.post(BASE + "/futures/runs", json=config, headers=HEADERS)
    assert executed.status_code == 200, executed.text
    history = client.get(BASE + "/runs").json()
    assert len(history) == 1 and history[0]["id"] == executed.json()["id"]
    assert "rows" not in history[0]
    assert client.get(BASE + "/runs/" + history[0]["id"]).json()["rows"] == executed.json()["rows"]


def test_active_futures_evidence_reasons_are_typed_and_optional_fields_do_not_block() -> None:
    from twf.scanner_v2.futures import evidence_reasons

    now = datetime(2026, 10, 16, 6, 30, tzinfo=UTC)
    future = SimpleNamespace(
        provider_source_time=now,
        received_at=now,
        volume=Decimal(100),
        open_interest=Decimal(500),
    )
    spot = SimpleNamespace(
        provider_source_time=now,
        received_at=now,
        previous_close=Decimal(100),
        last_price=Decimal(101),
    )
    values: dict[str, Any] = {
        "volume": Decimal(100),
        "open_interest": Decimal(500),
        "volume_percentile": None,
        "oi_percentile": None,
        "underlying_trend": "Up",
        "basis_abs": None,
        "change_in_open_interest": None,
    }

    def codes(field: str, **changes: Any) -> list[str]:
        options: dict[str, Any] = {
            "future": future,
            "spot": spot,
            "quote_error": None,
            "volume_cohort": 2,
            "oi_cohort": 2,
            "comparison_window": None,
            "basis_reason": "Source timestamps differ by six minutes",
        }
        options.update(changes)
        return [
            item["code"]
            for item in evidence_reasons(
                (
                    FuturesFilter(field=field, operator=">=", value=1)
                    if field != "underlying_trend"
                    else FuturesFilter(field=field, operator="equals", value="Up"),
                ),
                values,
                **options,
            )
        ]

    assert codes("volume_percentile") == ["VOLUME_HISTORY_INSUFFICIENT"]
    assert codes("oi_percentile") == ["OI_HISTORY_INSUFFICIENT"]
    assert codes("volume") == []  # Missing optional spot/basis does not block.
    assert codes("volume", future=None, quote_error="RATE_LIMITED") == ["PROVIDER_UNAVAILABLE"]
    assert codes("volume", future=None) == ["FUTURES_QUOTE_UNAVAILABLE"]
    assert codes("volume", future=SimpleNamespace(**{**vars(future), "volume": None})) == [
        "VOLUME_UNAVAILABLE"
    ]
    assert codes(
        "open_interest", future=SimpleNamespace(**{**vars(future), "open_interest": None})
    ) == ["OI_UNAVAILABLE"]
    assert codes("underlying_trend", spot=None) == ["SPOT_QUOTE_UNAVAILABLE"]
    assert codes(
        "underlying_trend",
        spot=SimpleNamespace(**{**vars(spot), "provider_source_time": now - timedelta(hours=2)}),
    ) == ["SPOT_QUOTE_STALE"]
    assert codes("basis_abs") == ["TIMESTAMP_MISMATCH"]
    assert codes("change_in_open_interest") == ["OI_COMPARISON_UNAVAILABLE"]
    assert codes(
        "volume",
        future=SimpleNamespace(
            **{**vars(future), "provider_source_time": now - timedelta(hours=2)}
        ),
    ) == ["FUTURES_QUOTE_STALE"]
    assert codes("underlying_trend", spot=spot) == []
    values["underlying_trend"] = None
    assert codes("underlying_trend") == ["SPOT_DIRECTION_UNAVAILABLE"]


def test_mixed_futures_scan_reason_counts_and_summary_invariant(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch, missing_contract_symbol="INFY")
    response = client.post(
        BASE + "/futures/runs",
        json=payload(filters=[{"field": "volume", "operator": ">=", "value": 300}]),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    counts = run["counts"]
    assert counts["requested"] == counts["resolved"] == 5
    assert counts["contracts_evaluated"] == 4
    assert counts["not_evaluated"] == 1
    assert counts["matches"] == 3
    assert counts["contracts_evaluated"] + counts["not_evaluated"] == counts["resolved"]
    assert run["not_evaluated_reasons"] == {"FUTURES_QUOTE_UNAVAILABLE": 1}
    missing = next(row for row in run["rows"] if row["underlying"] == "INFY")
    assert missing["evaluation_reason"]["code"] == "FUTURES_QUOTE_UNAVAILABLE"
    assert missing["outcome"] == "NOT_EVALUATED"
    non_match = next(row for row in run["rows"] if row["underlying"] == "RELIANCE")
    assert non_match["outcome"] == "NON_MATCH"
    assert non_match["evaluation_reason"] is None


def test_stale_contract_does_not_supply_percentile_cohort(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch, stale_contract_symbol="INFY")
    response = client.post(BASE + "/futures/runs", json=payload(), headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["counts"]["not_evaluated"] == 5
    assert run["not_evaluated_reasons"] == {
        "FUTURES_QUOTE_STALE": 1,
        "VOLUME_HISTORY_INSUFFICIENT": 4,
    }
    assert all(row["relative_volume_cohort_size"] == 4 for row in run["rows"])
    assert (
        next(u for u in run["underlyings"] if u["symbol"] == "INFY")["evidence_status"]["quote"]
        == "STALE"
    )


def test_stale_optional_spot_does_not_block_volume_scan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch, spot_source_lag_minutes=8 * 24 * 60)
    request = payload(filters=[{"field": "volume", "operator": ">=", "value": 0}])
    response = client.post(BASE + "/futures/runs", json=request, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["counts"]["matches"] == 5
    request["filters"] = [{"field": "underlying_trend", "operator": "equals", "value": "Down"}]
    response = client.post(BASE + "/futures/runs", json=request, headers=HEADERS)
    assert response.json()["not_evaluated_reasons"] == {"SPOT_QUOTE_STALE": 5}
    assert response.json()["counts"]["contracts_evaluated"] == 0


def test_missing_required_evidence_precedes_failed_predicate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_futures(client, monkeypatch)
    response = client.post(
        BASE + "/futures/runs",
        json=payload(
            filters=[
                {"field": "volume", "operator": ">=", "value": 999999},
                {"field": "change_in_open_interest", "operator": ">=", "value": 1},
            ]
        ),
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["counts"]["contracts_evaluated"] == 0
    assert run["not_evaluated_reasons"] == {"OI_COMPARISON_UNAVAILABLE": 5}
    assert all(row["diagnostics"][0]["passed"] is False for row in run["rows"])
    assert all(row["outcome"] == "NOT_EVALUATED" for row in run["rows"])
