"""Network-free Kite fixtures shared by API and browser tests only."""

import httpx

CSV = (
    "instrument_token,tradingsymbol,name,expiry,strike,lot_size,instrument_type,segment,exchange,tick_size\n"
    "1,HAL,HINDUSTAN AERONAUTICS,,,1,EQ,NSE,NSE,0.05\n"
    "2,NIFTY26OCT25000CE,NIFTY,2026-10-29,25000,65,CE,NFO-OPT,NFO,0.05\n"
)

# Synthetic quantities/values; no personal account or order identifiers.
CLOSED_POSITION = {
    "tradingsymbol": "HDFCBANK26OCT730PE",
    "exchange": "NFO",
    "product": "NRML",
    "quantity": 0,
    "average_price": 0,
    "last_price": 20.15,
    "pnl": -1007.5,
    "realised": 0,
    "unrealised": -1007.5,
    "buy_quantity": 1300,
    "sell_quantity": 1300,
    "buy_value": 28600,
    "sell_value": 27592.5,
}


def provider(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    item = {
        "instrument_token": 1,
        "tradingsymbol": "HAL",
        "exchange": "NSE",
        "quantity": 2,
        "average_price": 100,
        "last_price": 120,
        "pnl": 40,
    }
    data: object
    if path == "/session/token":
        data = {"api_key": "testapikey123", "access_token": "testtoken123", "user_id": "AB1234"}
    elif path == "/user/profile":
        data = {"user_id": "AB1234", "broker": "ZERODHA"}
    elif path == "/portfolio/holdings":
        data = [
            {
                **item,
                "quantity": 10,
                "t1_quantity": 10,
                "pnl": 400,
                "mtf": {"quantity": 0, "used_quantity": 0, "average_price": 0, "value": 0},
            }
        ]
    elif path == "/portfolio/positions":
        data = {
            "net": [
                {
                    **item,
                    "instrument_token": 2,
                    "tradingsymbol": "NIFTY26OCT25000CE",
                    "exchange": "NFO",
                    "product": "NRML",
                    "realised": 10,
                    "unrealised": 30,
                },
                CLOSED_POSITION,
            ]
        }
    elif path == "/orders":
        data = [
            {
                **item,
                "order_id": "order1",
                "order_timestamp": "2026-09-27 12:30:00",
                "transaction_type": "BUY",
                "order_type": "LIMIT",
                "price": 100,
                "status": "OPEN",
                "secret_field": "MUST_NOT_LEAK",
            }
        ]
    elif path == "/user/margins":
        data = {
            "equity": {
                "enabled": True,
                "net": 900,
                "available": {"cash": 1000, "collateral": 0},
                "utilised": {"debits": 100},
            }
        }
    elif path == "/instruments":
        return httpx.Response(200, text=CSV)
    else:
        raise AssertionError(path)
    return httpx.Response(200, json={"status": "success", "data": data})
