"""Finite, application-owned registry. Capability checks precede adapter execution."""

import asyncio
import logging
from time import monotonic
from typing import Protocol
from uuid import UUID

from twf.integrations.adapters import RemoteAdapter, SyntheticAdapter
from twf.integrations.config import ServiceDescriptor
from twf.integrations.contracts import (
    Contract,
    DeploymentMode,
    ErrorCode,
    Health,
    HealthResult,
    RequestContext,
    ServiceClient,
    ServiceFailure,
    ServiceIdentity,
    validate_result,
)


class CapabilityPolicy(Protocol):
    def allows(self, user_id: UUID, service_id: str, capability: str) -> bool: ...


class FoundationPolicy:
    """Authenticated users can inspect registered health only; no domain entitlements."""

    def allows(self, user_id: UUID, service_id: str, capability: str) -> bool:
        return capability == "foundation.health"


class ServiceStatus(Contract):
    identity: ServiceIdentity
    mode: DeploymentMode
    configured: bool = True
    enabled: bool
    active: bool
    health: Health = Health.UNKNOWN
    observation: HealthResult | None = None
    error: ErrorCode | None = None


class ServiceRegistry:
    def __init__(
        self,
        descriptors: tuple[ServiceDescriptor, ...],
        *,
        allowed_origins: tuple[str, ...] = (),
        production: bool = False,
        clients: tuple[ServiceClient, ...] = (),
        policy: CapabilityPolicy | None = None,
    ) -> None:
        from twf.integrations.config import validate_policy

        validate_policy(descriptors, allowed_origins, production)
        self._descriptors = {item.identity.service_id: item for item in descriptors}
        self._clients = {client.identity.service_id: client for client in clients}
        if (
            len(self._clients) != len(clients)
            or not self._clients.keys() <= self._descriptors.keys()
        ):
            raise ServiceFailure(ErrorCode.CONFIGURATION_ERROR)
        self._policy = policy or FoundationPolicy()
        for descriptor in descriptors:
            key = descriptor.identity.service_id
            if key not in self._clients and descriptor.enabled:
                if descriptor.mode == DeploymentMode.REMOTE:
                    self._clients[key] = RemoteAdapter(
                        descriptor, allowed_origins=allowed_origins, production=production
                    )
                elif descriptor.mode == DeploymentMode.SYNTHETIC:
                    self._clients[key] = SyntheticAdapter(descriptor.identity)
            client = self._clients.get(key)
            if client and (
                client.identity != descriptor.identity or client.mode != descriptor.mode
            ):
                raise ServiceFailure(ErrorCode.CONFIGURATION_ERROR)

    def require(self, user_id: UUID, service_id: str, capability: str) -> ServiceDescriptor:
        descriptor = self._descriptors.get(service_id)
        if descriptor is None or capability not in descriptor.identity.capabilities:
            raise ServiceFailure(ErrorCode.UNSUPPORTED_CAPABILITY)
        if not self._policy.allows(user_id, service_id, capability):
            raise ServiceFailure(ErrorCode.AUTHORIZATION_FAILED)
        return descriptor

    async def statuses(
        self, user_id: UUID, context: RequestContext, logger: logging.Logger
    ) -> tuple[ServiceStatus, ...]:
        async def inspect(descriptor: ServiceDescriptor) -> ServiceStatus:
            client = self._clients.get(descriptor.identity.service_id)
            base = ServiceStatus(
                identity=descriptor.identity,
                mode=descriptor.mode,
                enabled=descriptor.enabled,
                active=descriptor.enabled and client is not None,
            )
            try:
                self.require(user_id, descriptor.identity.service_id, "foundation.health")
            except ServiceFailure as error:
                return base.model_copy(update={"active": False, "error": error.code})
            if not descriptor.enabled or client is None:
                return base
            start = monotonic()
            outcome = "UNKNOWN"
            try:
                async with asyncio.timeout(descriptor.timeout_seconds):
                    result = validate_result(
                        await client.health(context), descriptor.identity, context
                    )
                outcome = result.health.value
                return base.model_copy(update={"health": result.health, "observation": result})
            except Exception as error:
                code = (
                    error.code
                    if isinstance(error, ServiceFailure)
                    else ErrorCode.TIMEOUT
                    if isinstance(error, TimeoutError)
                    else ErrorCode.SERVICE_UNAVAILABLE
                )
                outcome = code.value
                return base.model_copy(update={"health": Health.UNAVAILABLE, "error": code})
            finally:
                logger.info(
                    "service_operation",
                    extra={
                        "service_id": descriptor.identity.service_id,
                        "operation": "foundation.health",
                        "outcome": outcome,
                        "operation_request_id": context.request_id,
                        "duration_ms": round((monotonic() - start) * 1000, 2),
                    },
                )

        return tuple(await asyncio.gather(*(inspect(item) for item in self._descriptors.values())))
