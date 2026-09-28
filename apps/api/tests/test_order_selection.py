"""Selection API regressions through real routes and the synthetic CSV transport."""

from typing import Any

import order_provider_fixture
import pytest
from fastapi.testclient import TestClient
from order_provider_fixture import EXPIRIES, OrderProvider
from test_broker_orders import orders as orders
from test_broker_v1 import HEADERS
from test_broker_v1 import client as client


@pytest.mark.parametrize(
    "exchange,expected",
    [(None, ["NSE"]), ("NSE", ["NSE"]), ("BSE", ["BSE"]), ("BOTH", ["BSE", "NSE"])],
)
def test_equity_exchange_ranking_and_identity(
    client: TestClient, orders: tuple[str, OrderProvider], exchange: str | None, expected: list[str]
) -> None:
    base, provider = orders
    params = {"asset": "equity", "q": "  rElIaNcE  "}
    if exchange:
        params["exchange"] = exchange
    response = client.get(base + "/choices", params=params)
    assert response.status_code == 200, response.text
    rows = response.json()["instruments"]
    exact = rows[: len(expected)]
    assert [x["exchange"] for x in exact] == expected
    assert all(x["symbol"] == "RELIANCE" for x in exact)
    assert all(x["kind"] == "EQ" and x["segment"] == x["exchange"] for x in rows)
    assert all(x["exchange"] in expected for x in rows)
    assert not any(x["symbol"] in {"DEBTREL", "DEBTSEG"} for x in rows)
    if "NSE" in expected:
        assert [x["symbol"] for x in rows[len(expected) :]] == ["RELIANCEPOWER", "AREL", "ZZREL"]
    for item in exact:
        cap = client.get(
            base + "/capabilities",
            params={"reference": item["reference"], "native_token": item["native_token"]},
        ).json()
        assert cap["instrument"] == item
        preview = client.post(
            base + "/preview",
            headers=HEADERS,
            json={
                "reference": item["reference"],
                "native_token": item["native_token"],
                "side": "BUY",
                "product": "CNC",
                "order_type": "LIMIT",
                "quantity": 1,
                "price": "100",
                "validity": "DAY",
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["instrument"] == item
    assert not provider.calls  # Discovery/preview never dispatches an order.


def test_ranking_before_pagination_and_empty_query(
    client: TestClient, orders: tuple[str, OrderProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, _ = orders
    monkeypatch.setattr(
        order_provider_fixture,
        "CATALOG",
        order_provider_fixture.CATALOG
        + "".join(
            f"{100 + i},AAA{i:02},SOME RELIANCE COMPANY,,,1,EQ,NSE,NSE,0.05\n" for i in range(35)
        ),
    )
    assert client.get(base + "/choices").json()["instruments"] == []
    params: dict[str, Any] = {"asset": "equity", "q": "reliance"}
    first = client.get(base + "/choices", params=params).json()
    second = client.get(base + "/choices", params={**params, "page": 2}).json()
    assert first["total"] == 39 and len(first["instruments"]) == 30
    assert [x["symbol"] for x in first["instruments"][:3]] == ["RELIANCE", "RELIANCEPOWER", "AREL"]
    ids = [x["reference"] for x in first["instruments"] + second["instruments"]]
    assert len(ids) == len(set(ids)) == 39
    assert first == client.get(base + "/choices", params=params).json()
    assert client.get(base + "/choices", params={"exchange": "NFO"}).status_code == 422


def test_futures_and_options_only_return_fully_narrowed_contracts(
    client: TestClient, orders: tuple[str, OrderProvider]
) -> None:
    base, _ = orders

    def get(**params: str) -> Any:
        response = client.get(base + "/choices", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    for asset in ("futures", "options"):
        initial = get(asset=asset, q="reliance")
        assert initial["underlyings"] == ["RELIANCE"]
        assert initial["instruments"] == [] and initial["expiries"] == []
        narrowed = get(asset=asset, underlying="RELIANCE")
        assert narrowed["expiries"] == sorted(EXPIRIES)
        assert narrowed["instruments"] == []
    future = get(asset="futures", underlying="RELIANCE", expiry=EXPIRIES[0])
    assert [(x["symbol"], x["kind"], x["native_token"]) for x in future["instruments"]] == [
        ("RELIANCEFUT1", "FUT", "22")
    ]
    params = {"asset": "options", "underlying": "RELIANCE", "expiry": EXPIRIES[0]}
    assert get(**params)["option_types"] == ["CE", "PE"]
    assert get(**params)["instruments"] == []
    assert get(**params, option_type="CE")["strikes"] == ["1400", "1500"]
    assert get(**params, option_type="CE")["instruments"] == []
    assert get(**params, option_type="PE")["strikes"] == ["1300"]
    selected = get(**params, option_type="CE", strike="1400")["instruments"]
    assert [(x["reference"], x["native_token"]) for x in selected] == [
        ("ZERODHA:NFO:RELIANCECE1", "23")
    ]
    assert get(**params, option_type="PE", strike="1400")["instruments"] == []
    assert get(asset="options", underlying="RELIANCE", expiry=EXPIRIES[1], option_type="CE")[
        "strikes"
    ] == ["1600"]
    assert get(asset="futures", underlying="RELIANCE", expiry="2000-01-01")["instruments"] == []
    assert get(asset="futures", underlying="RELIANCE", expiry="2099-01-01")["instruments"] == []


def test_catalog_eq_classification_limit_is_not_hidden(
    client: TestClient, orders: tuple[str, OrderProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Kite may classify debt as EQ with the same segment/lot/tick fields as stocks.
    # No synthetic debt flag or symbol heuristic can claim to solve that ambiguity.
    base, _ = orders
    monkeypatch.setattr(
        order_provider_fixture,
        "CATALOG",
        order_provider_fixture.CATALOG + "90,NCAPBULAD,RELIANCE CAPITAL,,,1,EQ,BSE,BSE,0.05\n",
    )
    rows = client.get(base + "/choices", params={"q": "reliance", "exchange": "BSE"}).json()[
        "instruments"
    ]
    assert rows[0]["symbol"] == "RELIANCE"
    assert any(x["symbol"] == "NCAPBULAD" for x in rows)


@pytest.mark.parametrize(
    "query",
    [
        "RELIANCE",
        "REL",
        "RELI",
        "Reliance Industries",
        "Reliance Ind",
        "Reliance Industries Ltd",
        "Reliance Industries Limited",
        "rELiaNcE iNDustries",
        "  Reliance   Industries  ",
        "Reliance-Industries",
        "Reliance/Industries",
        "Reliance.Industries, Ltd.",
        "ＲＥＬＩＡＮＣＥ",
        "ind rel",
    ],
)
@pytest.mark.parametrize("exchange", ["NSE", "BSE", "BOTH"])
def test_equity_symbol_company_normalization_and_scope(
    client: TestClient, orders: tuple[str, OrderProvider], query: str, exchange: str
) -> None:
    base, provider = orders
    response = client.get(
        base + "/choices", params={"asset": "equity", "q": query, "exchange": exchange}
    )
    assert response.status_code == 200, response.text
    rows = response.json()["instruments"]
    expected = ["BSE", "NSE"] if exchange == "BOTH" else [exchange]
    assert [x["exchange"] for x in rows[: len(expected)]] == expected
    assert all(x["symbol"] == "RELIANCE" for x in rows[: len(expected)])
    assert all(x["exchange"] in expected and x["kind"] == "EQ" for x in rows)
    for item in rows[: len(expected)]:
        assert item["native_token"] == ("11" if item["exchange"] == "NSE" else "12")
        assert item["reference"] == f"ZERODHA:{item['exchange']}:RELIANCE"
        assert item["name"] == "RELIANCE INDUSTRIES"  # display metadata is never rewritten
        assert item["segment"] == item["exchange"]
    assert not provider.calls


def test_six_rank_tiers_missing_names_and_company_suffixes(
    client: TestClient, orders: tuple[str, OrderProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, _ = orders
    monkeypatch.setattr(
        order_provider_fixture,
        "CATALOG",
        order_provider_fixture.CATALOG
        + (
            "40,ZPREFIX,RELIANCE VENTURES,,,1,EQ,NSE,NSE,0.05\n"
            "41,MWORD,THE RELIANCE INDUSTRIES,,,1,EQ,NSE,NSE,0.05\n"
            "42,ASUB,XRELIANCEX,,,1,EQ,NSE,NSE,0.05\n"
            "43,NONAME,,,,1,EQ,NSE,NSE,0.05\n"
            "44,ACME,Acme Industries Limited,,,1,EQ,NSE,NSE,0.05\n"
        ),
    )

    def search(query: str) -> list[dict[str, Any]]:
        response = client.get(base + "/choices", params={"q": query})
        assert response.status_code == 200, response.text
        return list(response.json()["instruments"])

    assert [x["symbol"] for x in search("reliance")] == [
        "RELIANCE",
        "RELIANCEPOWER",
        "AREL",
        "ZPREFIX",
        "MWORD",
        "ZZREL",
        "ASUB",
    ]
    assert search("name")[0]["symbol"] == "NONAME"  # substring fallback
    assert search("NONAME")[0]["name"] is None
    for query in ("Acme Industries", "Acme Industries Ltd", "acme ind", "ind acm"):
        assert search(query)[0]["name"] == "Acme Industries Limited"
    assert search("   - / .   ") == []
    assert search("reliance nonexistent") == []  # all query words are required
