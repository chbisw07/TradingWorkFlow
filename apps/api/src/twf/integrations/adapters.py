"""Bounded health adapters. No provider SDKs, retries, or domain operations."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import httpx
from pydantic import ValidationError

from twf.integrations.config import ServiceDescriptor, endpoint_origin
from twf.integrations.contracts import (
    CONTRACT_VERSION,
    DeploymentMode,
    ErrorCode,
    Health,
    HealthResult,
    RequestContext,
    ServiceFailure,
    ServiceIdentity,
    ServiceKind,
    validate_result,
)


class LocalAdapter:
    mode = DeploymentMode.LOCAL

    def __init__(
        self,
        identity: ServiceIdentity,
        handler: Callable[[RequestContext], Awaitable[HealthResult]],
    ) -> None:
        self.identity = identity
        self._handler = handler

    async def health(self, context: RequestContext) -> HealthResult:
        try:
            return validate_result(await self._handler(context), self.identity, context)
        except ServiceFailure:
            raise
        except Exception:
            raise ServiceFailure(ErrorCode.SERVICE_UNAVAILABLE) from None


class SyntheticScenario(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    DENIED = "DENIED"
    INCOMPATIBLE = "INCOMPATIBLE"
    STALE = "STALE"
    EMPTY = "EMPTY"


FIXTURE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class SyntheticAdapter:
    mode = DeploymentMode.SYNTHETIC

    def __init__(
        self,
        identity: ServiceIdentity,
        *,
        scenario: SyntheticScenario = SyntheticScenario.AVAILABLE,
        reference_time: datetime = FIXTURE_TIME,
    ) -> None:
        if not isinstance(scenario, SyntheticScenario):
            raise ValueError("Synthetic scenario must be a SyntheticScenario")
        if reference_time.utcoffset() is None:
            raise ValueError("Synthetic reference time must be timezone-aware")
        self.identity = identity
        self._scenario = scenario
        self._reference_time = reference_time.astimezone(UTC)

    async def health(self, context: RequestContext) -> HealthResult:
        errors = {
            SyntheticScenario.UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
            SyntheticScenario.TIMEOUT: ErrorCode.TIMEOUT,
            SyntheticScenario.DENIED: ErrorCode.AUTHORIZATION_FAILED,
            SyntheticScenario.INCOMPATIBLE: ErrorCode.CONTRACT_MISMATCH,
        }
        if self._scenario in errors:
            # Logical failure fixture: no sleeps, sockets, credentials or retries.
            raise ServiceFailure(errors[self._scenario])
        health = {
            SyntheticScenario.DEGRADED: Health.DEGRADED,
            SyntheticScenario.EMPTY: Health.UNKNOWN,
        }.get(self._scenario, Health.AVAILABLE)
        as_of = self._reference_time
        if self._scenario == SyntheticScenario.STALE:
            as_of -= timedelta(minutes=10)
        return HealthResult(
            identity=self.identity,
            request_id=context.request_id,
            health=health,
            as_of=as_of,
            synthetic=True,
        )


def synthetic_identity(kind: ServiceKind) -> ServiceIdentity:
    return ServiceIdentity(
        service_id=f"synthetic-{kind.value.lower()}",
        service_kind=kind,
        provider="twf-fixture",
        service_version="1",
    )


class SyntheticScannerService(SyntheticAdapter):
    def __init__(
        self,
        *,
        scenario: SyntheticScenario = SyntheticScenario.AVAILABLE,
        reference_time: datetime = FIXTURE_TIME,
    ) -> None:
        super().__init__(
            synthetic_identity(ServiceKind.SCANNER),
            scenario=scenario,
            reference_time=reference_time,
        )


class SyntheticTIService(SyntheticAdapter):
    def __init__(
        self,
        *,
        scenario: SyntheticScenario = SyntheticScenario.AVAILABLE,
        reference_time: datetime = FIXTURE_TIME,
    ) -> None:
        super().__init__(
            synthetic_identity(ServiceKind.TI),
            scenario=scenario,
            reference_time=reference_time,
        )


class SyntheticTMService(SyntheticAdapter):
    def __init__(
        self,
        *,
        scenario: SyntheticScenario = SyntheticScenario.AVAILABLE,
        reference_time: datetime = FIXTURE_TIME,
    ) -> None:
        super().__init__(
            synthetic_identity(ServiceKind.TM),
            scenario=scenario,
            reference_time=reference_time,
        )


class SyntheticLLMService(SyntheticAdapter):
    def __init__(
        self,
        *,
        scenario: SyntheticScenario = SyntheticScenario.AVAILABLE,
        reference_time: datetime = FIXTURE_TIME,
    ) -> None:
        super().__init__(
            synthetic_identity(ServiceKind.LLM),
            scenario=scenario,
            reference_time=reference_time,
        )


class RemoteAdapter:
    mode = DeploymentMode.REMOTE

    def __init__(
        self,
        descriptor: ServiceDescriptor,
        *,
        allowed_origins: tuple[str, ...],
        production: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        from twf.integrations.config import validate_policy

        validate_policy((descriptor,), allowed_origins, production)
        if descriptor.mode != self.mode or descriptor.endpoint is None:
            raise ServiceFailure(ErrorCode.CONFIGURATION_ERROR)
        self.identity = descriptor.identity
        self._origin = endpoint_origin(descriptor.endpoint)
        self._timeout = descriptor.timeout_seconds
        self._transport = transport

    async def health(self, context: RequestContext) -> HealthResult:
        try:
            async with asyncio.timeout(self._timeout):
                # Per-operation ownership: no persistent cookie jar or borrowed browser headers.
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self._transport,
                    headers={
                        "Accept": "application/json",
                        "X-Request-ID": context.request_id,
                        "X-TWF-Contract-Version": CONTRACT_VERSION,
                    },
                ) as client:
                    async with client.stream("GET", f"{self._origin}/health") as response:
                        if response.status_code != 200:
                            codes = {
                                401: ErrorCode.AUTHENTICATION_FAILED,
                                403: ErrorCode.AUTHORIZATION_FAILED,
                                503: ErrorCode.SERVICE_UNAVAILABLE,
                            }
                            raise ServiceFailure(
                                codes.get(response.status_code, ErrorCode.REMOTE_ERROR)
                            )
                        if response.headers.get("content-type", "").split(";")[0] != (
                            "application/json"
                        ):
                            raise ServiceFailure(ErrorCode.INVALID_RESPONSE)
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 16384:
                                raise ServiceFailure(ErrorCode.INVALID_RESPONSE)
            data = json.loads(body)
            if not isinstance(data, dict) or not isinstance(data.get("identity"), dict):
                raise ServiceFailure(ErrorCode.INVALID_RESPONSE)
            if data["identity"].get("contract_version") != CONTRACT_VERSION:
                raise ServiceFailure(ErrorCode.CONTRACT_MISMATCH)
            return validate_result(
                HealthResult.model_validate_json(body, strict=True), self.identity, context
            )
        except (TimeoutError, httpx.TimeoutException):
            raise ServiceFailure(ErrorCode.TIMEOUT) from None
        except httpx.RequestError:
            raise ServiceFailure(ErrorCode.SERVICE_UNAVAILABLE) from None
        except (ValueError, ValidationError):
            raise ServiceFailure(ErrorCode.INVALID_RESPONSE) from None
