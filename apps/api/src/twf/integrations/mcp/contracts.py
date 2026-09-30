"""Versioned configuration and application types, independent of MCP SDK types."""

from enum import StrEnum
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, SecretStr, model_validator

from twf.integrations.contracts import Contract, Health, Identifier, RequestContext
from twf.settings_contracts import SecretReference


class AuthMode(StrEnum):
    NONE = "NONE"
    API_KEY = "API_KEY"
    OAUTH_2_1 = "OAUTH_2_1"


class State(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    DISCONNECTING = "DISCONNECTING"
    REAUTH_DRAINING = "REAUTH_DRAINING"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"


class Code(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    AUTH_FAILED = "AUTHENTICATION_FAILED"
    DENIED = "AUTHORIZATION_FAILED"
    UNAVAILABLE = "SERVICE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    RATE_LIMITED = "RATE_LIMITED"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
    INVALID_ARGUMENTS = "INVALID_TOOL_ARGUMENTS"
    SCHEMA_MISMATCH = "INVALID_RESPONSE"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    STALE = "STALE_GENERATION"
    REVOKED = "REVOKED_CREDENTIAL"
    CLOSED = "CONNECTION_CLOSED"
    STORAGE = "SECRET_STORE_UNAVAILABLE"


class Failure(Exception):
    def __init__(self, code: Code, retry_after: int | None = None) -> None:
        self.code = code
        self.retry_after = retry_after
        super().__init__(code.value)


def https_url(value: str) -> str:
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.port not in (None, 443)
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
        or "\\" in value
        or "%" in value
    ):
        raise ValueError("An explicit HTTPS endpoint without credentials is required")
    return value


class OAuthConfig(Contract):
    # Operator-verified explicit metadata and preregistered public clients only.
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str | None = None
    client_id: str = Field(min_length=1, max_length=512)
    redirect_uri: str
    scopes: tuple[
        Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:/-]+$")], ...
    ] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def urls(self) -> Self:
        for value in (
            self.issuer,
            self.authorization_endpoint,
            self.token_endpoint,
            self.revocation_endpoint,
        ):
            if value:
                https_url(value)
        url = urlsplit(self.redirect_uri)
        if url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}:
            https_url(
                self.redirect_uri.replace("http:", "https:", 1).replace(
                    f":{url.port}", "" if url.port else ""
                )
            )
        else:
            https_url(self.redirect_uri)
        return self


class ProviderConfig(Contract):
    schema_version: Literal["mcp.connection.v1"] = "mcp.connection.v1"
    provider_id: Identifier
    display_name: str = Field(min_length=1, max_length=80)
    endpoint: str
    auth_mode: AuthMode = AuthMode.NONE
    oauth: OAuthConfig | None = None
    timeout_seconds: float = Field(default=10, ge=0.05, le=30, allow_inf_nan=False)
    max_response_bytes: int = Field(default=262144, ge=1024, le=1048576)
    max_tools: int = Field(default=64, ge=1, le=128)
    max_pages: int = Field(default=4, ge=1, le=8)
    # Mutating/ambiguous calls are never automatically retried.
    retry_count: Literal[0] = 0
    refresh_policy: Literal["EXPLICIT"] = "EXPLICIT"
    health_policy: Literal["INITIALIZE_AND_LIST_TOOLS"] = "INITIALIZE_AND_LIST_TOOLS"

    @model_validator(mode="after")
    def valid(self) -> Self:
        https_url(self.endpoint)
        if (self.auth_mode == AuthMode.OAUTH_2_1) != (self.oauth is not None):
            raise ValueError("OAuth configuration must match the authentication mode")
        return self


class Context(Contract):
    owner_id: UUID
    session_hash: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False, exclude=True)
    # Shared workspaces have no accepted membership model yet; fail closed.
    scope: Literal["USER"] = "USER"
    correlation: RequestContext = Field(default_factory=RequestContext)


class Tool(Contract):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    input_schema: dict[str, JsonValue]
    # Remote metadata remains untrusted. No readOnlyHint grants authority.
    description: str | None = Field(default=None, max_length=2048)


class ToolPolicy(Contract):
    # Constructed by server business adapters, never accepted from a frontend request.
    allowed: frozenset[str] = frozenset()


class ConnectionView(Contract):
    id: UUID
    owner_id: UUID
    scope: Literal["USER"] = "USER"
    provider_type: Literal["MCP"] = "MCP"
    provider_id: str
    display_name: str
    enabled: bool
    generation: int
    state: State
    health: Health
    secret_ref: SecretReference | None = None
    tools: tuple[Tool, ...] = ()
    error: Code | None = None
    cleanup_pending: bool = False
    operations_pending: int = 0
    recovery_required: bool = False
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_success_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None


class TokenBundle(Contract):
    # Only encrypted storage and auth strategy may serialize raw values explicitly.
    access_token: SecretStr = Field(repr=False)
    refresh_token: SecretStr | None = Field(default=None, repr=False)
    token_type: Literal["Bearer"] = "Bearer"
    scopes: tuple[str, ...] = ()
    expires_at: AwareDatetime | None = None


class Authorization(Contract):
    authorization_url: str = Field(repr=False)
    generation: int
