"""Provider-shaped ownership regressions through Holdings and Overview routes."""

from decimal import Decimal
from typing import Any

import httpx
import pytest
from broker_provider_fixture import provider
from fastapi.testclient import TestClient
from test_broker_v1 import bound, service
from test_broker_v1 import client as client

from twf.brokers.zerodha import ZerodhaAdapter


@pytest.mark.parametrize(
    ("changes", "quantity", "average", "value", "cost", "percent"),
    [
        pytest.param({}, "10", "100", "1200", "1000", "20", id="settled-only"),
        pytest.param(
            {"t1_quantity": 10, "pnl": 400}, "20", "100", "2400", "2000", "20", id="mixed"
        ),
        pytest.param(
            {"quantity": 0, "t1_quantity": 10},
            "10",
            "100",
            "1200",
            "1000",
            "20",
            id="unsettled-only",
        ),
        pytest.param(
            {"mtf": {"quantity": 5, "used_quantity": 2, "average_price": 80, "value": 400}},
            "15",
            None,
            "1800",
            None,
            None,
            id="mtf-cost-coverage-unknown",
        ),
        pytest.param(
            {"quantity": 0, "mtf": {"quantity": 5, "average_price": 80, "value": 400}},
            "5",
            None,
            "600",
            None,
            None,
            id="mtf-only",
        ),
        pytest.param(
            {"last_price": None}, "10", "100", None, "1000", "20", id="missing-last-price"
        ),
        pytest.param({"average_price": 0}, "10", "0", "1200", "0", None, id="zero-cost"),
        pytest.param({"quantity": 0}, "0", "100", "0", "0", None, id="zero-quantity"),
        pytest.param({"average_price": None}, "10", None, "1200", None, None, id="missing-average"),
        pytest.param({"pnl": None}, "10", "100", "1200", "1000", None, id="missing-pnl"),
        pytest.param(
            {"pnl": -200}, "10", "100", "1200", "1000", "-20", id="provider-loss-preserved"
        ),
        pytest.param(
            {
                "collateral_quantity": 7,
                "pledged_quantity": 7,
                "authorised_quantity": 10,
                "used_quantity": 2,
                "realised_quantity": 10,
                "opening_quantity": 10,
            },
            "10",
            "100",
            "1200",
            "1000",
            "20",
            id="no-double-counting",
        ),
        pytest.param({"quantity": None}, None, None, None, None, None, id="missing-settled"),
        pytest.param({"t1_quantity": None}, None, None, None, None, None, id="missing-t1"),
        pytest.param({"mtf": None}, None, None, None, None, None, id="missing-mtf"),
        pytest.param({"mtf": {}}, None, None, None, None, None, id="missing-mtf-quantity"),
        pytest.param({"mtf": "bad"}, None, None, None, None, None, id="malformed-mtf"),
        pytest.param({"t1_quantity": -1}, None, None, None, None, None, id="negative-component"),
        pytest.param(
            {"t1_quantity": "NaN"}, None, None, None, None, None, id="nonfinite-component"
        ),
        pytest.param({"t1_quantity": 0.5}, None, None, None, None, None, id="fractional-component"),
        pytest.param({"t1_quantity": False}, None, None, None, None, None, id="boolean-component"),
    ],
)
def test_holdings_and_overview_ownership_basis(
    client: TestClient,
    changes: dict[str, Any],
    quantity: str | None,
    average: str | None,
    value: str | None,
    cost: str | None,
    percent: str | None,
) -> None:
    account = bound(client)
    row = {
        "instrument_token": 1,
        "tradingsymbol": "HAL",
        "exchange": "NSE",
        "quantity": 10,
        "t1_quantity": 0,
        "average_price": 100,
        "last_price": 120,
        "pnl": 200,
        "mtf": {"quantity": 0, "used_quantity": 0, "average_price": 0, "value": 0},
        **changes,
    }
    # Include a known row to prove an unknown row cannot turn into a partial total.
    known = {
        **row,
        "tradingsymbol": "UNMAPPED",
        "instrument_token": 999,
        "quantity": 2,
        "t1_quantity": 0,
        "average_price": 100,
        "last_price": 120,
        "pnl": 40,
        "mtf": {"quantity": 0},
    }

    def response(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/portfolio/holdings":
            return httpx.Response(200, json={"status": "success", "data": [row, known]})
        return provider(request)

    service(client).adapter = ZerodhaAdapter(transport=httpx.MockTransport(response))
    holdings = client.get(f"/api/v1/brokers/accounts/{account}/holdings")
    overview = client.get(f"/api/v1/brokers/accounts/{account}/overview")
    assert holdings.status_code == overview.status_code == 200
    actual, other = holdings.json()["data"]
    for field, expected in (
        ("quantity", quantity),
        ("average", average),
        ("value", value),
        ("pnl_percent", percent),
    ):
        assert (Decimal(actual[field]) if actual[field] is not None else None) == (
            Decimal(expected) if expected is not None else None
        ), field
    assert actual["pnl"] == (str(row["pnl"]) if row["pnl"] is not None else None)
    assert actual["instrument"]["symbol"] == "HAL"
    assert other["instrument"]["symbol"] == "UNMAPPED"
    assert Decimal(other["value"]) == 240
    if cost is not None:
        assert Decimal(actual["quantity"]) * Decimal(actual["average"]) == Decimal(cost)
    aggregate = overview.json()["data"]["holdings_value"]
    assert (Decimal(aggregate) if aggregate is not None else None) == (
        Decimal(value) + 240 if value is not None else None
    )
