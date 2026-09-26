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
