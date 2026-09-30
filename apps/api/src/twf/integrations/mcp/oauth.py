"""Bounded authorization-code + S256 PKCE; explicit verified issuer/client metadata."""

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode

from pydantic import SecretStr

from twf.integrations.mcp.contracts import Code, Failure, ProviderConfig, TokenBundle
from twf.integrations.mcp.http import HTTPFactory


class AuthStrategy(Protocol):
    def headers(self, token: TokenBundle | None) -> dict[str, str]: ...


class NoAuth:
    def headers(self, token: TokenBundle | None) -> dict[str, str]:
        return {}


class ApiKeyAuth:
    """Bounded API key mode uses the standard Authorization Bearer header only."""

    def headers(self, token: TokenBundle | None) -> dict[str, str]:
        if token is None:
            raise Failure(Code.AUTH_REQUIRED)
        value = token.access_token.get_secret_value()
        if not value or len(value) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise Failure(Code.AUTH_FAILED)
        return {"Authorization": f"Bearer {value}"}


class OAuth21Auth(ApiKeyAuth):
    def __init__(self, http: HTTPFactory) -> None:
        self.http = http

    @staticmethod
    def begin(config: ProviderConfig, state: str, verifier: str) -> str:
        oauth = config.oauth
        if oauth is None:
            raise Failure(Code.NOT_CONFIGURED)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(
            b"="
        )
        return (
            oauth.authorization_endpoint
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": oauth.client_id,
                    "redirect_uri": oauth.redirect_uri,
                    "state": state,
                    "code_challenge": challenge.decode(),
                    "code_challenge_method": "S256",
                    "scope": " ".join(oauth.scopes),
                    "resource": config.endpoint,
                }
            )
        )

    async def tokens(
        self,
        config: ProviderConfig,
        fields: dict[str, str],
        request_id: str,
        previous: TokenBundle | None = None,
    ) -> TokenBundle:
        oauth = config.oauth
        if oauth is None:
            raise Failure(Code.NOT_CONFIGURED)
        async with self.http.client(
            config, frozenset({oauth.token_endpoint}), {"X-Request-ID": request_id}
        ) as client:
            response = await client.post(
                oauth.token_endpoint,
                data={
                    **fields,
                    "client_id": oauth.client_id,
                    "resource": config.endpoint,
                },
            )
        if response.status_code != 200:
            raise Failure(Code.AUTH_FAILED)
        try:
            data = json.loads(response.content)
            if not isinstance(data, dict) or str(data.get("token_type", "")).lower() != "bearer":
                raise ValueError
            access = data["access_token"]
            refresh = data.get("refresh_token")
            expiry = data.get("expires_in")
            scope = data.get("scope", " ".join(oauth.scopes))
            if not isinstance(access, str) or not access or len(access) > 8192:
                raise ValueError
            if refresh is not None and (
                not isinstance(refresh, str) or not refresh or len(refresh) > 8192
            ):
                raise ValueError
            if expiry is not None and (type(expiry) is not int or not 0 < expiry <= 31536000):
                raise ValueError
            if (
                not isinstance(scope, str)
                or len(scope) > 2048
                or not set(scope.split()) <= set(oauth.scopes)
            ):
                raise ValueError
            bundle = TokenBundle(
                access_token=SecretStr(access),
                refresh_token=SecretStr(refresh)
                if refresh
                else previous.refresh_token
                if previous
                else None,
                scopes=tuple(scope.split()),
                expires_at=datetime.now(UTC) + timedelta(seconds=expiry) if expiry else None,
            )
            self.headers(bundle)
            return bundle
        except (ValueError, KeyError, TypeError):
            raise Failure(Code.SCHEMA_MISMATCH) from None

    async def exchange(
        self,
        config: ProviderConfig,
        code: str,
        verifier: str,
        request_id: str,
    ) -> TokenBundle:
        assert config.oauth
        return await self.tokens(
            config,
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": config.oauth.redirect_uri,
            },
            request_id,
        )

    async def refresh(
        self,
        config: ProviderConfig,
        old: TokenBundle,
        request_id: str,
    ) -> TokenBundle:
        if old.refresh_token is None:
            raise Failure(Code.REAUTH_REQUIRED)
        return await self.tokens(
            config,
            {
                "grant_type": "refresh_token",
                "refresh_token": old.refresh_token.get_secret_value(),
            },
            request_id,
            old,
        )

    async def revoke(
        self,
        config: ProviderConfig,
        token: TokenBundle,
        request_id: str,
        *,
        seen: set[str] | None = None,
    ) -> None:
        oauth = config.oauth
        if oauth is None or oauth.revocation_endpoint is None:
            return
        async with self.http.client(
            config, frozenset({oauth.revocation_endpoint}), {"X-Request-ID": request_id}
        ) as client:
            # Revoke both if present; revoking access does not necessarily revoke refresh.
            for value, hint in (
                (token.refresh_token, "refresh_token"),
                (token.access_token, "access_token"),
            ):
                if value is None:
                    continue
                digest = hashlib.sha256(value.get_secret_value().encode()).hexdigest()
                if seen is not None and digest in seen:
                    continue
                response = await client.post(
                    oauth.revocation_endpoint,
                    data={
                        "client_id": oauth.client_id,
                        "token": value.get_secret_value(),
                        "token_type_hint": hint,
                    },
                )
                if response.status_code != 200:
                    raise Failure(Code.UNAVAILABLE)
                if seen is not None:
                    seen.add(digest)


def nonce() -> str:
    return secrets.token_urlsafe(32)
