"""S&D domain ports composed with the accepted service-client foundation primitives."""

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol, TypeVar, cast
from uuid import UUID

from pydantic import Field

from twf.discovery.domain import (
    CandidateInput,
    DiscoveryEvidence,
    Instant,
    InstrumentIdentity,
    ProducerIdentity,
    ScanMatch,
    ScanRun,
    SourceMode,
)
from twf.integrations.contracts import (
    Contract,
    DeploymentMode,
    ErrorCode,
    Health,
    Identifier,
    RequestContext,
)
from twf.settings_contracts import CapabilityPolicy


class DomainErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    STALE_DATA = "STALE_DATA"
    RATE_LIMITED = "RATE_LIMITED"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
    CANCELLED = "CANCELLED"


class ProviderError(Contract):
    code: ErrorCode | DomainErrorCode
    provider_id: Identifier
    operation: Identifier
    request_id: Identifier
    retryable: bool = False


class ProviderFailure(Exception):
    def __init__(self, error: ProviderError) -> None:
        self.error = error
        super().__init__(error.code.value)


class ProviderManifest(Contract):
    identity: ProducerIdentity
    capabilities: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    source_modes: tuple[SourceMode, ...] = Field(min_length=1, max_length=4)
    max_items: int = Field(strict=True, gt=0, le=1000)
    # Parameters are an allowlist, not executable provider-specific expressions.
    supported_metrics: tuple[Identifier, ...] = ()
    supported_operators: tuple[Identifier, ...] = ()
    supported_timeframes: tuple[Identifier, ...] = ()


class OperationContext(Contract):
    owner_id: UUID
    correlation: RequestContext
    as_of: Instant


class ProviderHealth(Contract):
    identity: ProducerIdentity
    request_id: Identifier
    health: Health
    as_of: Instant
    source_mode: SourceMode


T = TypeVar("T")


class ProviderBatch[T](Contract):
    identity: ProducerIdentity
    owner_id: UUID
    request_id: Identifier
    as_of: Instant
    source_mode: SourceMode
    completeness: str = Field(pattern=r"^(COMPLETE|PARTIAL)$")
    items: tuple[T, ...] = Field(max_length=1000)
    next_cursor: Identifier | None = None
    limitations: tuple[Identifier, ...] = Field(default=(), max_length=16)


class Provider(Protocol):
    @property
    def manifest(self) -> ProviderManifest: ...
    @property
    def mode(self) -> DeploymentMode: ...
    async def health(self, context: OperationContext) -> ProviderHealth: ...


class UniverseProvider(Provider, Protocol):
    async def resolve(self, context: OperationContext) -> ProviderBatch[InstrumentIdentity]: ...


class CandidateSource(Provider, Protocol):
    async def nominate(self, context: OperationContext) -> ProviderBatch[CandidateInput]: ...


class ScanProvider(Provider, Protocol):
    async def scan(
        self, context: OperationContext, run: ScanRun, instruments: tuple[InstrumentIdentity, ...]
    ) -> ProviderBatch[ScanMatch]: ...


class MarketIntelligenceProvider(Provider, Protocol):
    async def observe(
        self, context: OperationContext, instruments: tuple[InstrumentIdentity, ...]
    ) -> ProviderBatch[DiscoveryEvidence]: ...


class CandidateIntelligenceProvider(Provider, Protocol):
    async def annotate(
        self, context: OperationContext, inputs: tuple[CandidateInput, ...]
    ) -> ProviderBatch[DiscoveryEvidence]: ...


class LLMService(Provider, Protocol):
    """Future optional port only; no binding, client, synthetic call or inference in S2-1."""

    async def interpret(
        self, context: OperationContext, evidence: tuple[DiscoveryEvidence, ...]
    ) -> ProviderBatch[DiscoveryEvidence]: ...


OPERATION_SCHEMAS: dict[str, type[Contract]] = {
    "sd.universe": ProviderBatch[InstrumentIdentity],
    "sd.scan": ProviderBatch[ScanMatch],
    "sd.candidate-source": ProviderBatch[CandidateInput],
    "sd.market-context": ProviderBatch[DiscoveryEvidence],
    "sd.candidate-intelligence": ProviderBatch[DiscoveryEvidence],
}


class ProviderAccess:
    """Small operation guard, not a registry, config store or health-protocol replacement."""

    def __init__(self, policy: CapabilityPolicy, *, timeout_seconds: float = 1.0) -> None:
        if not 0 < timeout_seconds <= 10:
            raise ValueError("Provider deadline must be within (0, 10] seconds")
        self.policy = policy
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def failure(
        provider: Provider,
        context: OperationContext,
        code: ErrorCode | DomainErrorCode,
        operation: str | None = None,
    ) -> ProviderFailure:
        return ProviderFailure(
            ProviderError(
                code=code,
                provider_id=provider.manifest.identity.service_id,
                operation=operation or provider.manifest.capabilities[0],
                request_id=context.correlation.request_id,
            )
        )

    async def call(
        self,
        provider: Provider,
        context: OperationContext,
        capability: str,
        contract_version: str,
        operation: Callable[[], Awaitable[ProviderBatch[T]]],
        *,
        enabled: bool = True,
    ) -> ProviderBatch[T]:
        manifest = provider.manifest
        if not enabled or not self.policy.allows(context.owner_id, capability):
            raise self.failure(provider, context, ErrorCode.AUTHORIZATION_FAILED, capability)
        if manifest.identity.contract_version != contract_version:
            raise self.failure(provider, context, ErrorCode.CONTRACT_MISMATCH, capability)
        if capability not in manifest.capabilities:
            raise self.failure(provider, context, ErrorCode.UNSUPPORTED_CAPABILITY, capability)
        schema = OPERATION_SCHEMAS.get(capability)
        if schema is None:
            raise self.failure(provider, context, ErrorCode.UNSUPPORTED_CAPABILITY, capability)
        if contract_version != capability + ".v1":
            raise self.failure(provider, context, ErrorCode.CONTRACT_MISMATCH, capability)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                result = await operation()
                # Validate again at the adapter boundary (including untrusted constructed models).
                result = cast(ProviderBatch[T], schema.model_validate(result.model_dump()))
                if (
                    result.identity != manifest.identity
                    or result.owner_id != context.owner_id
                    or result.request_id != context.correlation.request_id
                    or result.as_of != context.as_of
                ):
                    raise self.failure(provider, context, DomainErrorCode.PROVENANCE_MISMATCH)
                if (
                    result.source_mode not in manifest.source_modes
                    or len(result.items) > manifest.max_items
                ):
                    raise self.failure(provider, context, ErrorCode.INVALID_RESPONSE)
                if (
                    provider.mode == DeploymentMode.SYNTHETIC
                    and result.source_mode != SourceMode.SYNTHETIC
                ):
                    raise self.failure(provider, context, DomainErrorCode.PROVENANCE_MISMATCH)
                if result.completeness == "COMPLETE" and result.next_cursor is not None:
                    raise self.failure(provider, context, ErrorCode.INVALID_RESPONSE)
                for item in result.items:
                    if isinstance(item, (ScanMatch, CandidateInput, DiscoveryEvidence)):
                        if (
                            item.owner_id != context.owner_id
                            or item.provenance.producer != result.identity
                            or item.provenance.mode != result.source_mode
                        ):
                            raise self.failure(
                                provider, context, DomainErrorCode.PROVENANCE_MISMATCH
                            )
                        evidence = (item,) if isinstance(item, DiscoveryEvidence) else item.evidence
                        if any(
                            e.owner_id != context.owner_id
                            or e.received_at > context.as_of
                            or (
                                (e.provenance.mode == SourceMode.SYNTHETIC)
                                != (result.source_mode == SourceMode.SYNTHETIC)
                            )
                            or (
                                e.provenance.producer == result.identity
                                and e.provenance.mode != result.source_mode
                            )
                            for e in evidence
                        ):
                            raise self.failure(
                                provider, context, DomainErrorCode.PROVENANCE_MISMATCH
                            )
                # Recheck use permission after the await; prior approval is not a permanent grant.
                if not self.policy.allows(context.owner_id, capability):
                    raise self.failure(
                        provider, context, ErrorCode.AUTHORIZATION_FAILED, capability
                    )
                return result
        except TimeoutError:
            raise self.failure(provider, context, ErrorCode.TIMEOUT, capability) from None
        except ProviderFailure as exc:
            # Rebind correlation and strip arbitrary exception text from adapter failures.
            raise self.failure(provider, context, exc.error.code, capability) from None
        except Exception:
            raise self.failure(provider, context, ErrorCode.INVALID_RESPONSE, capability) from None
