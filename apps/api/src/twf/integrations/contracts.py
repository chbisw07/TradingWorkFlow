"""Versioned foundation contracts; domain operations belong to later contracts."""

from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]
CONTRACT_VERSION: Literal["foundation.health.v1"] = "foundation.health.v1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ServiceKind(StrEnum):
    SCANNER = "SCANNER"
    TI = "TI"
    TM = "TM"
    LLM = "LLM"


class DeploymentMode(StrEnum):
    LOCAL = "LOCAL"
    REMOTE = "REMOTE"
    SYNTHETIC = "SYNTHETIC"


class Health(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class ErrorCode(StrEnum):
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    REMOTE_ERROR = "REMOTE_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"


class ServiceFailure(Exception):
    def __init__(self, code: ErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class ServiceIdentity(Contract):
    service_id: Identifier
    service_kind: ServiceKind
    provider: Identifier
    service_version: Identifier
    contract_version: Literal["foundation.health.v1"] = CONTRACT_VERSION
    capabilities: tuple[Literal["foundation.health"], ...] = ("foundation.health",)


class RequestContext(Contract):
    request_id: Identifier = Field(default_factory=lambda: uuid4().hex)


class HealthResult(Contract):
    identity: ServiceIdentity
    request_id: Identifier
    health: Health
    as_of: AwareDatetime
    synthetic: bool


class ServiceClient(Protocol):
    @property
    def identity(self) -> ServiceIdentity: ...

    @property
    def mode(self) -> DeploymentMode: ...

    async def health(self, context: RequestContext) -> HealthResult: ...


def validate_result(
    result: HealthResult, identity: ServiceIdentity, context: RequestContext
) -> HealthResult:
    if result.identity != identity or result.request_id != context.request_id:
        raise ServiceFailure(ErrorCode.INVALID_RESPONSE)
    return result
