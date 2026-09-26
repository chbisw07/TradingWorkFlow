"""Fixed-destination Kite auth/profile adapter; no portfolio or command transport."""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from twf.secrets import SecretValue


class ProviderAuthFailure(Exception):
    def __init__(self, code: str = "PROVIDER_UNAVAILABLE") -> None:
        self.code = code
        super().__init__(code)


class ProviderAuthTimeout(ProviderAuthFailure):
    def __init__(self) -> None:
        super().__init__("PROVIDER_TIMEOUT")


@dataclass(frozen=True)
class AuthGrant:
    subject: str
    token: SecretValue


class AuthProvider(Protocol):
    def exchange(
        self, api_key: str, secret: SecretValue, request_token: SecretValue
    ) -> AuthGrant: ...
    def profile(self, api_key: str, token: SecretValue) -> str: ...


class Profile(BaseModel):
    user_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    broker: str


class Exchange(Profile):
    api_key: str = Field(min_length=1, max_length=128)
    access_token: str = Field(
        min_length=1, max_length=4096, pattern=r"^[A-Za-z0-9_-]+$", repr=False
    )


class KiteAuthClient:
    TOTAL_DEADLINE_SECONDS = 5.0

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    def _request[T: BaseModel](
        self,
        method: str,
        path: str,
        response_type: type[T],
        *,
        data: dict[str, str] | None = None,
        authorization: str | None = None,
    ) -> T:
        # The public adapter stays synchronous for the existing worker-thread use cases.
        # Async I/O lets the total deadline cancel a blocked read, without orphan workers.
        deadline = monotonic() + self.TOTAL_DEADLINE_SECONDS
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self._fetch(method, path, response_type, deadline, data, authorization)
            )
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                # Unlike asyncio.run(), closing does not join the default executor.
                # An OS resolver already running there cannot be interrupted; its
                # cancelled result must not delay the safe timeout or start HTTP I/O.
                loop.close()

    async def _fetch[T: BaseModel](
        self,
        method: str,
        path: str,
        response_type: type[T],
        deadline: float,
        data: dict[str, str] | None,
        authorization: str | None,
    ) -> T:
        def check_deadline() -> None:
            if monotonic() >= deadline:
                raise ProviderAuthTimeout()

        headers = {"X-Kite-Version": "3", "Accept": "application/json"}
        if authorization is not None:
            headers["Authorization"] = authorization
        try:
            check_deadline()
            async with asyncio.timeout(max(0.0, deadline - monotonic())):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=httpx.Timeout(5.0, connect=5.0, read=5.0, write=5.0, pool=5.0),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        method, "https://api.kite.trade" + path, headers=headers, data=data
                    ) as response:
                        check_deadline()
                        if response.status_code == 403:
                            raise ProviderAuthFailure("REAUTH_REQUIRED")
                        if response.status_code == 429:
                            raise ProviderAuthFailure("RATE_LIMITED")
                        if response.status_code != 200:
                            raise ProviderAuthFailure()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            check_deadline()
                            if len(body) + len(chunk) > 65536:
                                raise ProviderAuthFailure("INVALID_PROVIDER_RESPONSE")
                            body.extend(chunk)
                        check_deadline()
                        payload = json.loads(body)
                        check_deadline()
                        if not isinstance(payload, dict) or payload.get("status") != "success":
                            raise ProviderAuthFailure("INVALID_PROVIDER_RESPONSE")
                        result = response_type.model_validate(payload.get("data"))
                        # Bounded synchronous parsing cannot yield to cancellation. Reject
                        # overruns explicitly so a late parse can never authorize a binding.
                        check_deadline()
                check_deadline()
                return result
        except (TimeoutError, httpx.TimeoutException):
            raise ProviderAuthTimeout() from None
        except ProviderAuthFailure:
            raise
        except httpx.HTTPError:
            check_deadline()
            raise ProviderAuthFailure() from None
        except (ValueError, ValidationError):
            check_deadline()
            raise ProviderAuthFailure("INVALID_PROVIDER_RESPONSE") from None

    def exchange(self, api_key: str, secret: SecretValue, request_token: SecretValue) -> AuthGrant:
        checksum = hashlib.sha256(
            (api_key + request_token.reveal() + secret.reveal()).encode()
        ).hexdigest()
        grant = self._request(
            "POST",
            "/session/token",
            Exchange,
            data={
                "api_key": api_key,
                "request_token": request_token.reveal(),
                "checksum": checksum,
            },
        )
        if grant.broker != "ZERODHA" or grant.api_key != api_key:
            raise ProviderAuthFailure("IDENTITY_MISMATCH")
        return AuthGrant(grant.user_id, SecretValue(grant.access_token))

    def profile(self, api_key: str, token: SecretValue) -> str:
        profile = self._request(
            "GET", "/user/profile", Profile, authorization=f"token {api_key}:{token.reveal()}"
        )
        if profile.broker != "ZERODHA":
            raise ProviderAuthFailure("IDENTITY_MISMATCH")
        return profile.user_id
