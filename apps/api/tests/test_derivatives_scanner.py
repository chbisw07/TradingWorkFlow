"""O4 option filtering, exact evidence, bounded provider use and isolation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from internal_scanner_support import series
from pydantic import ValidationError
from test_option_chain import Source, contract
from test_scanner_v2 import install_market
from test_watchlists import HEADERS
from test_watchlists import client as client  # noqa: F401
from test_watchlists import provider as market_provider

from twf.discovery.domain import SourceMode
from twf.infrastructure.scanner_v2 import SavedScannerRow, ScannerRunRow
from twf.options.chain_service import ChainFailure
from twf.scanner_v2.derivatives import DerivativeFilter, DerivativeScanConfig, evaluate

BASE = "/api/v1/scanner/derivatives"


def test_derivatives_catalog_api_and_openapi_match_typed_registry(client: TestClient) -> None:
    from twf.scanner_v2.derivatives import FIELDS

    response = client.get(BASE + "/catalog")
    assert response.status_code == 200, response.text
    catalog = response.json()
    fields = {item["field"]: item for item in catalog["fields"]}
    assert fields.keys() == FIELDS.keys()
    assert len(fields) == 24
    assert fields["moneyness"]["values"] == ["ITM", "ATM", "OTM"]
    assert fields["moneyness"]["operators"] == ["equals", "not_equals"]
    assert fields["dte"]["kind"] == "integer"
    assert "between" in fields["dte"]["operators"]
    assert fields["spread_percent"]["unit"] == "%"
    assert fields["volume_percentile"]["maximum"] == 100
    assert fields["volume_vs_chain_median"]["unit"] == "x"
    assert fields["volume_oi_percent"]["unit"] == "%"
    assert fields["implied_volatility"]["provider_dependent"] is True
    assert fields["delta"]["provider_dependent"] is True
    assert fields["theta"]["provider_dependent"] is True
    assert BASE + "/catalog" in client.get("/openapi.json").json()["paths"]


def config(**updates: Any) -> dict[str, Any]:
    return {
        "name": "ATM calls",
        "universe": {"source": "CUSTOM", "symbols": ["NIFTY", "UNKNOWN"]},
        "filters": [
            {"field": "option_type", "operator": "equals", "value": "CE"},
            {"field": "moneyness", "operator": "equals", "value": ["ATM"]},
            {"field": "volume", "operator": ">=", "value": 20},
        ],
        "strike_window": 5,
        **updates,
    }


@pytest.mark.parametrize(
    "field,operator,value",
    [
        ("moneyness", ">", "ATM"),
        ("open_interest", ">", "delta"),
        ("dte", "between", [5, 2]),
        ("volume", ">=", -1),
        ("volume_percentile", ">=", 101),
        ("volume_vs_chain_median", ">=", -1),
        ("volume_oi_percent", ">=", -1),
        ("option_type", "not_equals", "BOTH"),
        ("delta", "between", [2, 3]),
        ("unknown", "equals", 1),
    ],
)
def test_typed_filters_reject_invalid_predicates(field: str, operator: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        DerivativeFilter.model_validate(dict(field=field, operator=operator, value=value))


def test_both_option_types_match_without_side_bias() -> None:
    both = (DerivativeFilter(field="option_type", operator="equals", value="BOTH"),)
    assert evaluate(both, {"option_type": "CE"}, quote_available=True)["outcome"] == "MATCH"
    assert evaluate(both, {"option_type": "PE"}, quote_available=True)["outcome"] == "MATCH"


@pytest.mark.parametrize(
    "field,operator,value,observed,expected",
    [
        ("option_type", "equals", "CE", "PE", "NON_MATCH"),
        ("moneyness", "equals", ("ATM", "OTM"), "OTM", "MATCH"),
        ("moneyness", "equals", ("ATM",), "ITM", "NON_MATCH"),
        ("dte", "between", (3, 10), 2, "NON_MATCH"),
        ("dte", "between", (3, 10), 3, "MATCH"),
        ("dte", "between", (3, 10), 10, "MATCH"),
        ("dte", "between", (3, 10), 11, "NON_MATCH"),
        ("strike_distance_percent", "<=", 2, 1.5, "MATCH"),
        ("ltp", "between", (20, 300), 125, "MATCH"),
        ("volume", ">=", 100_000, 150_000, "MATCH"),
        ("volume_percentile", ">=", 70, 69.9, "NON_MATCH"),
        ("volume_percentile", ">=", 70, 70, "MATCH"),
        ("volume_percentile", ">=", 70, 90, "MATCH"),
        ("volume_vs_chain_median", ">=", 1.5, 1.49, "NON_MATCH"),
        ("volume_vs_chain_median", ">=", 1.5, 1.5, "MATCH"),
        ("volume_vs_chain_median", ">=", 1.5, 3, "MATCH"),
        ("volume_oi_percent", ">=", 20, 19.9, "NON_MATCH"),
        ("volume_oi_percent", ">=", 20, 20, "MATCH"),
        ("volume_oi_percent", ">=", 20, 50, "MATCH"),
        ("open_interest", ">=", 500_000, 499_999, "NON_MATCH"),
        ("change_in_open_interest", "<", 0, -80_000, "MATCH"),
        ("spread_percent", "<=", 2, 4.5, "NON_MATCH"),
        ("implied_volatility", "<=", 25, 22, "MATCH"),
        ("delta", "between", (-0.65, -0.35), -0.5, "MATCH"),
        ("theta", "<", 0, -5, "MATCH"),
        ("underlying_trend", "equals", "Up", "Down", "NON_MATCH"),
        ("underlying_rsi", "<", 30, 26, "MATCH"),
        ("underlying_supertrend", "equals", "Up", "Up", "MATCH"),
        ("underlying_change", ">", 0, 1.2, "MATCH"),
    ],
)
def test_typed_predicate_boundaries(
    field: str,
    operator: Literal[">", ">=", "<", "<=", "equals", "between", "not_equals"],
    value: Any,
    observed: Any,
    expected: str,
) -> None:
    predicate = DerivativeFilter(field=field, operator=operator, value=value)
    result = evaluate((predicate,), {field: observed}, quote_available=True)
    assert result["outcome"] == expected
    assert result["diagnostics"][0]["observed"] == observed
    assert result["diagnostics"][0]["passed"] is (expected == "MATCH")


def test_config_deduplicates_and_bounds_and_never_accepts_synthetic() -> None:
    validated = DerivativeScanConfig.model_validate(
        config(universe={"source": "CUSTOM", "symbols": ["nifty", "NIFTY", "reliance"]})
    )
    assert validated.universe.symbols == ("NIFTY", "RELIANCE")
    for value in [
        config(data_mode="SYNTHETIC"),
        config(universe={"source": "CUSTOM", "symbols": ["A", "B", "C", "D", "E", "F"]}),
        config(expiry_mode="EXACT"),
        config(filters=[]),
    ]:
        with pytest.raises(ValidationError):
            DerivativeScanConfig.model_validate(value)


def test_missing_active_evidence_and_nonmatch_diagnostics() -> None:
    filters = (
        DerivativeFilter(field="volume", operator=">=", value=20),
        DerivativeFilter(field="implied_volatility", operator="<=", value=30),
    )
    unavailable = evaluate(
        filters, {"volume": 40, "implied_volatility": None}, quote_available=True
    )
    assert unavailable["outcome"] == "NOT_EVALUATED"
    assert unavailable["diagnostics"][1]["passed"] is None
    assert unavailable["missing_evidence"] == ["IV %"]
    nonmatch = evaluate(filters[:1], {"volume": 10}, quote_available=True)
    assert nonmatch["outcome"] == "NON_MATCH"
    assert nonmatch["diagnostics"][0]["observed"] == 10
    assert nonmatch["diagnostics"][0]["threshold"] == 20
    assert (
        evaluate(filters[:1], {"volume": 40}, quote_available=False)["outcome"] == "NOT_EVALUATED"
    )


def test_api_exact_contract_partial_underlying_history_saved_and_owner_isolation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_market(client, monkeypatch)
    source = Source()
    monkeypatch.setattr(cast(Any, client.app).state.option_chains, "get", lambda *args: source)
    response = client.post(BASE + "/runs", json=config(), headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["data_mode"] == "REAL" and run["market_data_provider"] == "dhan"
    assert run["counts"]["requested"] == 2
    assert run["counts"]["resolved"] == 1
    assert run["counts"]["chains_evaluated"] == source.calls == 1
    assert run["counts"]["matches"] == 1
    assert run["underlyings"][1]["failure"] == "NO_OPTION_CONTRACTS"
    match = next(r for r in run["rows"] if r["outcome"] == "MATCH")
    assert match["contract"]["canonical_id"].endswith(":100:CE")
    assert match["contract"]["option_type"] == "CE"
    assert match["market"]["volume"] == "30"
    assert match["provenance"]["provider"] == "dhan"
    assert len(match["diagnostics"]) == 3
    assert all(d["passed"] is True for d in match["diagnostics"])
    source.spot = Decimal("999")
    source.missing = {match["contract"]["canonical_id"]}
    assert client.get(BASE + "/runs/" + run["id"]).json()["rows"] == run["rows"]
    assert source.calls == 1  # history reads archived truth, not a new O2 quote
    assert client.get("/api/v1/scanner/runs").json() == []
    saved = client.post(BASE + "/saved", json={"config": config()}, headers=HEADERS)
    assert saved.status_code == 200, saved.text
    assert len(client.get(BASE + "/saved").json()) == 1
    assert client.get("/api/v1/scanner/saved").json() == []
    # Apply per-type limits after the discriminator; many newer equity records
    # must not hide the O4 saved setup or immutable O4 run.
    factory = cast(Any, client.app).state.session_factory
    with factory.begin() as db:
        owner = db.get(SavedScannerRow, UUID(saved.json()["id"])).owner_id
        timestamp = datetime.now(UTC)
        db.add_all(
            SavedScannerRow(
                id=uuid4(),
                owner_id=owner,
                config={"scanner_type": "EQUITY_INDEX"},
                archived=False,
                created_at=timestamp,
                updated_at=timestamp + timedelta(seconds=i),
            )
            for i in range(101)
        )
        db.add_all(
            ScannerRunRow(
                id=uuid4(),
                owner_id=owner,
                payload={"config": {"scanner_type": "EQUITY_INDEX"}, "rows": []},
                created_at=timestamp + timedelta(seconds=i),
            )
            for i in range(51)
        )
    assert len(client.get(BASE + "/saved").json()) == 1
    assert len(client.get(BASE + "/runs").json()) == 1
    assert len(client.get("/api/v1/scanner/saved").json()) == 100
    assert len(client.get("/api/v1/scanner/runs").json()) == 50
    from test_watchlists import login

    login(client, "bob")
    assert client.get(BASE + "/runs/" + run["id"]).status_code == 404
    assert client.get(BASE + "/saved").json() == []


@pytest.mark.parametrize("direction", ["Up", "Down"])
def test_option_run_preserves_underlying_trend_without_a_technical_filter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, direction: str
) -> None:
    market = market_provider()

    async def history(instrument: Any, interval: str, **kwargs: Any) -> Any:
        closes = list(range(100, 401))
        if direction == "Down":
            closes.reverse()
        bars = series(
            [float(value) for value in closes], instrument=instrument, interval="1d", step=86400
        )
        return bars.model_copy(
            update={
                "provenance": bars.provenance.model_copy(
                    update={
                        "mode": SourceMode.EOD,
                        "producer": bars.provenance.producer.model_copy(
                            update={"provider": "dhan"}
                        ),
                    }
                )
            }
        )

    monkeypatch.setattr(market, "get_ohlcv", history)
    monkeypatch.setattr(
        cast(Any, client.app).state.dhan_credentials,
        "capture",
        lambda *args, **kwargs: SimpleNamespace(
            provider=market, status=SimpleNamespace(generation=3)
        ),
    )
    source = Source()
    monkeypatch.setattr(cast(Any, client.app).state.option_chains, "get", lambda *args: source)
    payload = config(universe={"source": "CUSTOM", "symbols": ["NIFTY"]})
    response = client.post(BASE + "/runs", json=payload, headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["rows"]
    assert {row["technical"]["trend"] for row in run["rows"]} == {direction}
    assert {row["observed"]["underlying_trend"] for row in run["rows"]} == {direction}
    archived = client.get(BASE + "/runs/" + run["id"])
    assert archived.status_code == 200
    assert {row["technical"]["trend"] for row in archived.json()["rows"]} == {direction}


def test_relative_volume_filters_archive_exact_metrics_without_extra_chain_calls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_market(client, monkeypatch)
    source = Source()
    monkeypatch.setattr(cast(Any, client.app).state.option_chains, "get", lambda *args: source)
    filters = [
        {"field": "volume_percentile", "operator": ">=", "value": 70},
        {"field": "volume_vs_chain_median", "operator": ">=", "value": 1},
        {"field": "volume_oi_percent", "operator": ">=", "value": 20},
    ]
    payload = config(
        universe={"source": "CUSTOM", "symbols": ["NIFTY"]},
        filters=filters,
    )
    response = client.post(BASE + "/runs", json=payload, headers=HEADERS)
    assert response.status_code == 200, response.text
    run = response.json()
    assert source.calls == 1
    assert run["counts"]["matches"] > 0
    first = run["rows"][0]
    assert first["market"]["volume"] == "30"
    assert first["volume_percentile"] == 100
    assert first["volume_chain_median"] == 30
    assert first["volume_vs_chain_median"] == 1
    assert first["volume_oi_percent"] == 60
    assert first["relative_volume_cohort_size"] >= 5
    assert first["oi_percentile"] == 100
    assert first["oi_chain_median"] == 50
    assert first["oi_vs_chain_median"] == 1
    assert first["oi_change_percent"] is None
    assert first["oi_interpretation"]["label"] == "Insufficient evidence"
    assert [d["passed"] for d in first["diagnostics"]] == [True, True, True]
    assert first["observed"]["volume_oi_percent"] == 60
    saved = client.post(BASE + "/saved", json={"config": payload}, headers=HEADERS)
    assert saved.status_code == 200
    assert client.get(BASE + "/saved").json()[0]["config"]["filters"] == filters
    source.missing = {c.canonical_id for c in source.items}
    assert client.get(BASE + "/runs/" + run["id"]).json()["rows"][0] == first
    assert source.calls == 1


def test_watchlist_optionability_uses_active_o2_master_and_preserves_snapshot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_watchlists import add, create

    install_market(client, monkeypatch)
    source = Source()
    monkeypatch.setattr(cast(Any, client.app).state.option_chains, "get", lambda *args: source)
    key = create(client, "O4 optionability")
    add(client, key)
    projection = client.get(BASE + f"/watchlists/{key}/optionable")
    assert projection.status_code == 200, projection.text
    assert projection.json() == {
        "watchlist_id": key,
        "members": 5,
        "optionable": 1,
        "symbols": ["NIFTY"],
        "max_underlyings": 5,
    }
    run = client.post(
        BASE + "/runs",
        json=config(universe={"source": "WATCHLIST", "watchlist_id": key, "symbols": ["NIFTY"]}),
        headers=HEADERS,
    )
    assert run.status_code == 200, run.text
    assert run.json()["config"]["universe"]["symbols"] == ["NIFTY"]
    assert run.json()["counts"]["requested"] == 1
    archived = client.get(BASE + "/runs/" + run.json()["id"]).json()
    assert archived["config"]["universe"] == run.json()["config"]["universe"]
    auto = client.post(
        BASE + "/runs",
        json=config(universe={"source": "WATCHLIST", "watchlist_id": key, "symbols": []}),
        headers=HEADERS,
    )
    assert auto.status_code == 200, auto.text
    assert auto.json()["counts"]["requested"] == 1
    assert auto.json()["config"]["universe"]["symbols"] == ["NIFTY"]
    saved = client.post(
        BASE + "/saved",
        json={
            "config": config(universe={"source": "WATCHLIST", "watchlist_id": key, "symbols": []})
        },
        headers=HEADERS,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["config"]["universe"]["watchlist_id"] == key
    assert client.get(BASE + "/saved").json()[0]["config"]["universe"]["watchlist_id"] == key

    from test_watchlists import instruments

    nifty_id = next(str(item.instrument_id) for item in instruments() if item.symbol == "NIFTY")
    removed = client.delete(f"/api/v1/watchlists/{key}/items/{nifty_id}", headers=HEADERS)
    assert removed.status_code == 200, removed.text
    current = client.get(BASE + f"/watchlists/{key}/optionable")
    assert current.status_code == 200
    assert current.json()["optionable"] == 0
    archived_after_mutation = client.get(BASE + "/runs/" + run.json()["id"]).json()
    assert archived_after_mutation["config"]["universe"]["symbols"] == ["NIFTY"]
    assert archived_after_mutation["rows"] == archived["rows"]


def test_watchlist_selection_reuses_only_selected_optionable_underlying(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_watchlists import add, create

    install_market(client, monkeypatch)
    source = Source()
    monkeypatch.setattr(cast(Any, client.app).state.option_chains, "get", lambda *args: source)
    key = create(client, "O4 universe")
    add(client, key)
    run = client.post(
        BASE + "/runs",
        json=config(universe={"source": "WATCHLIST", "watchlist_id": key, "symbols": ["NIFTY"]}),
        headers=HEADERS,
    )
    assert run.status_code == 200, run.text
    assert run.json()["counts"]["requested"] == 1
    assert run.json()["counts"]["matches"] == 1
    assert source.calls == 1
    assert [u["symbol"] for u in run.json()["underlyings"]] == ["NIFTY"]


def test_exact_expiry_missing_underlying_is_not_evaluated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_market(client, monkeypatch)
    source = Source()
    monkeypatch.setattr(cast(Any, client.app).state.option_chains, "get", lambda *args: source)
    payload = config(expiry_mode="EXACT", exact_expiry="2099-12-30")
    run = client.post(BASE + "/runs", json=payload, headers=HEADERS).json()
    assert run["counts"]["matches"] == 0 and source.calls == 0
    assert run["underlyings"][0]["failure"] == "EXPIRY_NOT_AVAILABLE"


def test_unavailable_chain_is_not_counted_and_other_underlyings_continue(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_market(client, monkeypatch)

    class PartlyUnavailable(Source):
        async def market(self, underlying: str, expiry: Any, contracts: Any) -> Any:
            if underlying == "BANKNIFTY":
                self.calls += 1
                raise ChainFailure("provider_unavailable", 503)
            return await super().market(underlying, expiry, contracts)

    source = PartlyUnavailable()
    source.items = tuple(
        contract(strike, side, underlying=symbol)
        for symbol in ("NIFTY", "BANKNIFTY", "RELIANCE")
        for strike in (95, 100, 105)
        for side in ("CE", "PE")
    )
    monkeypatch.setattr(cast(Any, client.app).state.option_chains, "get", lambda *args: source)
    run = client.post(
        BASE + "/runs",
        json=config(universe={"source": "CUSTOM", "symbols": ["NIFTY", "BANKNIFTY", "RELIANCE"]}),
        headers=HEADERS,
    ).json()
    assert source.calls == 3
    assert run["counts"]["resolved"] == 3
    assert run["counts"]["chains_evaluated"] == 2
    assert run["counts"]["matches"] == 2
    assert run["underlyings"][1]["outcome"] == "NOT_EVALUATED"
    assert run["underlyings"][1]["failure"] == "CHAIN_MARKET_UNAVAILABLE"
    assert {row["underlying"] for row in run["rows"]} == {"NIFTY", "RELIANCE"}


def test_oi_interpretation_uses_archived_exact_contract_without_provider_calls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from twf.options.chain_service import ChainMarketBatch

    install_market(client, monkeypatch)

    class MovingSource(Source):
        async def market(self, underlying: str, expiry: Any, contracts: Any) -> Any:
            batch = await super().market(underlying, expiry, contracts)
            current = self.calls == 2
            quotes = {
                key: quote.model_copy(
                    update={
                        "ltp": Decimal("11" if current else "10"),
                        "open_interest": Decimal("60" if current else "50"),
                        "change_in_open_interest": Decimal("10" if current else "0"),
                    }
                )
                for key, quote in batch.quotes.items()
            }
            return ChainMarketBatch(
                spot=Decimal("102" if current else "100"),
                quotes=quotes,
                received_at=datetime.now(UTC),
            )

    source = MovingSource()
    monkeypatch.setattr(cast(Any, client.app).state.option_chains, "get", lambda *args: source)
    payload = config(
        universe={"source": "CUSTOM", "symbols": ["NIFTY"]},
        filters=[{"field": "option_type", "operator": "equals", "value": "CE"}],
    )
    first_response = client.post(BASE + "/runs", json=payload, headers=HEADERS)
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    second_response = client.post(BASE + "/runs", json=payload, headers=HEADERS)
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert source.calls == 2
    prior = first["rows"][0]
    current = second["rows"][0]
    assert prior["oi_interpretation"]["label"] == "Insufficient evidence"
    assert current["oi_interpretation"]["label"] == "Call long buildup"
    assert current["oi_interpretation"]["inferred"] is True
    assert current["oi_interpretation"]["premium_change_percent"] == 10
    assert current["oi_interpretation"]["oi_window_change_percent"] == 20
    assert current["oi_interpretation"]["underlying_change_percent"] == 2
    assert current["oi_interpretation"]["window_seconds"] > 0
    assert current["oi_interpretation"]["freshness"] == "SOURCE_TIME_UNAVAILABLE"
    assert current["outcome"] == prior["outcome"] == "MATCH"
    assert current["reason"] == prior["reason"] == "1/1 active filters matched"
    source.fail = True
    assert client.get(BASE + "/runs/" + second["id"]).json()["rows"][0] == current
    assert source.calls == 2
