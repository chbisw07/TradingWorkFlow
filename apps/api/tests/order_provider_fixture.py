"""Only synthetic in-process HTTP: never contacts or loads a real broker account."""

import csv
import io
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs

import httpx
from broker_provider_fixture import provider

EXPIRIES = [(date.today() + timedelta(days=x)).isoformat() for x in (30, 60)]
CATALOG = (
    "instrument_token,tradingsymbol,name,expiry,strike,lot_size,instrument_type,segment,exchange,tick_size\n"
    "1,HAL,HINDUSTAN AERONAUTICS,,,1,EQ,NSE,NSE,0.05\n"
    "10,HAL,HINDUSTAN AERONAUTICS,,,1,EQ,BSE,BSE,0.05\n"
    f"3,NIFTYFUT2,NIFTY,{EXPIRIES[1]},,65,FUT,NFO-FUT,NFO,0.05\n"
    f"4,NIFTYFUT1,NIFTY,{EXPIRIES[0]},,65,FUT,NFO-FUT,NFO,0.05\n"
    f"5,NIFTYCE1,NIFTY,{EXPIRIES[0]},25000,65,CE,NFO-OPT,NFO,0.05\n"
    f"6,NIFTYPE1,NIFTY,{EXPIRIES[0]},25000,65,PE,NFO-OPT,NFO,0.05\n"
    f"7,NIFTYCE2,NIFTY,{EXPIRIES[1]},25500,65,CE,NFO-OPT,NFO,0.05\n"
    "8,EXPIRED,NIFTY,2000-01-01,25000,65,CE,NFO-OPT,NFO,0.05\n"
    "9,MISSINGTICK,NO TICK,,,1,EQ,NSE,NSE,\n"
    "11,RELIANCE,RELIANCE INDUSTRIES,,,1,EQ,NSE,NSE,0.05\n"
    "12,RELIANCE,RELIANCE INDUSTRIES,,,1,EQ,BSE,BSE,0.05\n"
    "13,AREL,RELIANCE,,,1,EQ,NSE,NSE,0.05\n"
    "14,RELIANCEPOWER,RELIANCE POWER,,,1,EQ,NSE,NSE,0.05\n"
    "15,ZZREL,SOME RELIANCE COMPANY,,,1,EQ,NSE,NSE,0.05\n"
    "16,DEBTREL,RELIANCE DEBT,,,1,BOND,NSE,NSE,0.05\n"
    "17,DEBTSEG,RELIANCE DEBT SEGMENT,,,1,EQ,BSE-DEBT,BSE,0.05\n"
    f"21,RELIANCEFUT2,RELIANCE,{EXPIRIES[1]},,250,FUT,NFO-FUT,NFO,0.05\n"
    f"22,RELIANCEFUT1,RELIANCE,{EXPIRIES[0]},,250,FUT,NFO-FUT,NFO,0.05\n"
    f"23,RELIANCECE1,RELIANCE,{EXPIRIES[0]},1400,250,CE,NFO-OPT,NFO,0.05\n"
    f"24,RELIANCECE2,RELIANCE,{EXPIRIES[0]},1500,250,CE,NFO-OPT,NFO,0.05\n"
    f"25,RELIANCEPE1,RELIANCE,{EXPIRIES[0]},1300,250,PE,NFO-OPT,NFO,0.05\n"
    f"26,RELIANCECE3,RELIANCE,{EXPIRIES[1]},1600,250,CE,NFO-OPT,NFO,0.05\n"
    "27,REL_EXPIRED,RELIANCE,2000-01-01,,250,FUT,NFO-FUT,NFO,0.05\n"
)


class OrderProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.books: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.mode = "success"
        self.quote_calls: list[list[str]] = []
        self.quote_rounds: dict[str, int] = defaultdict(int)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = request.headers.get("Authorization", "")
        if request.url.path == "/session/token":
            auth_fields = parse_qs(request.content.decode())
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "api_key": auth_fields["api_key"][0],
                        "access_token": "testtoken123",
                        "user_id": "AB1234",
                    },
                },
            )
        if request.url.path == "/quote/ltp":
            identities = request.url.params.get_list("i")
            self.quote_calls.append(identities)
            self.quote_rounds[key] += 1
            catalog = {
                f"{x['exchange']}:{x['tradingsymbol']}": x
                for x in csv.DictReader(io.StringIO(CATALOG))
            }
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        identity: {
                            "instrument_token": int(catalog[identity]["instrument_token"]),
                            "last_price": str(
                                Decimal(100)
                                + Decimal(catalog[identity]["instrument_token"])
                                + Decimal(self.quote_rounds[key]) / 20
                            ),
                            "raw_secret": "MUST_NOT_LEAK_testtoken123",
                        }
                        for identity in identities
                        if identity in catalog
                    },
                },
            )
        if request.url.path == "/instruments":
            return httpx.Response(200, text=CATALOG)
        if request.url.path == "/margins/orders":
            assert request.method == "POST"
            assert request.headers["Content-Type"].startswith("application/json")
            terms = json.loads(request.content)[0]
            assert set(terms) == {
                "exchange",
                "tradingsymbol",
                "transaction_type",
                "variety",
                "product",
                "order_type",
                "quantity",
                "price",
                "trigger_price",
            }
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [
                        {
                            "exchange": terms["exchange"],
                            "tradingsymbol": terms["tradingsymbol"],
                            "total": 75,
                        }
                    ],
                },
            )
        if request.url.path == "/orders/regular":
            assert request.method == "POST"
            fields = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.calls.append(fields)
            if self.mode == "reject":
                return httpx.Response(
                    400,
                    json={
                        "status": "error",
                        "error_type": "OrderException",
                        "message": "MUST_NOT_LEAK_testtoken123",
                    },
                )
            if self.mode == "server":
                return httpx.Response(503, text="MUST_NOT_LEAK_testsecret123")
            order_id = str(900000 + len(self.calls))
            self.books[key].append(
                {
                    **fields,
                    "order_id": order_id,
                    "status": "OPEN",
                    "instrument_token": 1,
                    "order_timestamp": "2026-09-28 12:30:00",
                }
            )
            if self.mode == "lost":
                raise httpx.ReadTimeout("MUST_NOT_LEAK_testsecret123")
            return httpx.Response(200, json={"status": "success", "data": {"order_id": order_id}})
        if request.url.path == "/orders":
            baseline = provider(request).json()["data"]
            return httpx.Response(
                200, json={"status": "success", "data": baseline + self.books[key]}
            )
        return provider(request)
