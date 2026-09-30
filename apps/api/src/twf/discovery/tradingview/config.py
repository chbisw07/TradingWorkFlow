"""Operator configuration and official public-client metadata; no token infrastructure."""

from typing import Literal

from pydantic import Field

from twf.integrations.contracts import Contract
from twf.integrations.mcp.contracts import AuthMode, OAuthConfig, ProviderConfig

ENDPOINT = "https://mcp.tradingview.com/mcp"


class TradingViewSettings(Contract):
    enabled: bool = False
    # No guessed schema is silently enabled for a real account.
    response_contract_verified: bool = False
    response_contract: Literal["nested-data-v1"] = "nested-data-v1"
    market: Literal["india"] = "india"
    max_items: int = Field(default=20, ge=1, le=64, strict=True)
    timeout_seconds: float = Field(default=8, gt=0, le=60, allow_inf_nan=False)
    snapshot_ttl_seconds: int = Field(default=60, ge=1, le=300, strict=True)
    sort_by: Literal["close", "volume"] = "volume"
    sort_order: Literal["asc", "desc"] = "desc"


def configuration(client_id: str, redirect_uri: str) -> ProviderConfig:
    """Public-client metadata verified at TradingView's official issuer endpoint."""
    return ProviderConfig(
        provider_id="tradingview",
        display_name="TradingView",
        endpoint=ENDPOINT,
        auth_mode=AuthMode.OAUTH_2_1,
        oauth=OAuthConfig(
            issuer="https://www.tradingview.com",
            authorization_endpoint="https://www.tradingview.com/mcp/oauth/authorize",
            token_endpoint="https://www.tradingview.com/mcp/oauth/token",
            revocation_endpoint="https://www.tradingview.com/mcp/oauth/revoke",
            client_id=client_id,
            redirect_uri=redirect_uri,
            scopes=("mcp:read", "mcp:tools"),
        ),
    )
