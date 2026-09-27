"""Browser-only approved-store double and provider responses. Never deployed."""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from twf.brokers.zerodha_auth import AuthGrant, ProviderAuthFailure
from twf.secrets import MemorySecretStore, SecretScope, SecretValue, StoredSecret

class BrowserVault:
    production_safe = True
    def __init__(self) -> None:
        self.store = MemorySecretStore()
    def put(self, scope: SecretScope, value: SecretValue) -> StoredSecret:
        return self.store.put(scope, value)
    def get(self, scope: SecretScope, reference: str) -> SecretValue:
        return self.store.get(scope, reference)
    def exists(self, scope: SecretScope, reference: str) -> bool:
        return self.store.exists(scope, reference)
    def delete(self, scope: SecretScope, reference: str) -> bool:
        return self.store.delete(scope, reference)

class BrowserProvider:
    def exchange(self, api_key: str, secret: SecretValue, request_token: SecretValue) -> AuthGrant:
        if request_token.reveal() == "expired-request-token":
            raise ProviderAuthFailure("REAUTH_REQUIRED")
        return AuthGrant(api_key, SecretValue(api_key))
    def profile(self, api_key: str, token: SecretValue) -> str:
        return api_key

def add_provider_return(app: FastAPI) -> None:
    assert app.state.settings.environment == "test"
    @app.get("/fixture/kite-login")
    def kite_login(state: str, expired: bool = False) -> RedirectResponse:
        from urllib.parse import urlencode
        return RedirectResponse(app.state.settings.zerodha_callback_url + "?" + urlencode({
            "state": state, "request_token": "expired-request-token" if expired else "browser-request-token"
        }), status_code=303)

class BrowserCatalog:
    def __init__(self) -> None:
        self.refreshed: set[str] = set()

    def fetch(self, api_key: str, token: SecretValue):
        from time import monotonic
        from twf.brokers.zerodha_catalog import KiteCatalogClient
        body = b"""instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
1,11,HAL,HINDUSTAN AERONAUTICS,0,,,0.05,1,EQ,NSE,NSE
2,12,HAL26OCTFUT,HAL,0,2026-10-29,,0.05,150,FUT,NFO-FUT,NFO
3,13,HAL26OCT4500CE,HAL,0,2026-10-29,4500,0.05,150,CE,NFO-OPT,NFO
4,14,HAL26OCT4500PE,HAL,0,2026-10-29,4500,0.05,150,PE,NFO-OPT,NFO
"""
        # Each account publishes A first, then B reuses the same native tokens.
        revision = "B" if api_key in self.refreshed else "A"
        self.refreshed.add(api_key)
        body += "".join(
            f"{500 + i},{600 + i},PAGE{revision}{i:02},PAGE,0,,,0.05,1,EQ,NSE,NSE\n"
            for i in range(30)
        ).encode()
        return KiteCatalogClient().parse(body, monotonic() + 30)


class BrowserPortfolio:
    def read(self, dataset, api_key, token):
        import json
        from time import monotonic
        from twf.brokers.zerodha_portfolio import KitePortfolioClient
        assert token.reveal() == api_key
        holding = dict(instrument_token=1, tradingsymbol="HAL", exchange="NSE", product="CNC", quantity=5,
                       used_quantity=1, t1_quantity=2, average_price=100, last_price=110, pnl=50)
        position = dict(instrument_token=3, tradingsymbol="HAL26OCT4500CE", exchange="NFO", product="NRML",
                        quantity=150, average_price=10, last_price=12, pnl=300, realised=0, unrealised=300,
                        overnight_quantity=150, buy_quantity=150, sell_quantity=0, multiplier=1)
        data = [holding] if dataset == "holdings" else {"net": [position], "day": []}
        return KitePortfolioClient().parse(json.dumps({"status": "success", "data": data}).encode(), dataset, monotonic() + 2)
