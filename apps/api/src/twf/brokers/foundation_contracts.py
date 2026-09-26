"""BW-2.1 provider, account, capability, and permission contracts."""

from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

ProviderId = Annotated[
    str, StringConstraints(min_length=1, max_length=48, pattern=r"^[a-z][a-z0-9-]*$")
]

AccountLabel = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BrokerPermission(StrEnum):
    READ = "broker.read"
    CONFIGURE = "broker.configure"
    CONNECT = "broker.connect"
    DISCONNECT = "broker.disconnect"
    TRADE = "broker.trade"
    CANCEL_MODIFY = "broker.cancel_modify"
    RESOLVE_UNKNOWN = "broker.resolve_unknown"


class BrokerPermissionPolicy(Protocol):
    def allows(
        self, actor_user_id: UUID, permission: BrokerPermission, owner_user_id: UUID
    ) -> bool: ...


class PersonalBrokerPermissionPolicy:
    """Personal ownership only; no role, mode, or connection state can elevate authority."""

    _read_only = {
        BrokerPermission.READ,
        BrokerPermission.CONFIGURE,
        BrokerPermission.CONNECT,
        BrokerPermission.DISCONNECT,
    }

    def allows(
        self, actor_user_id: UUID, permission: BrokerPermission, owner_user_id: UUID
    ) -> bool:
        return actor_user_id == owner_user_id and permission in self._read_only


class ProviderAuthMethod(StrEnum):
    BROWSER_REDIRECT_CALLBACK = "BROWSER_REDIRECT_CALLBACK"
    API_KEY_SECRET = "API_KEY_SECRET"
    OAUTH_AUTHORIZATION_CODE = "OAUTH_AUTHORIZATION_CODE"
    MANUAL_TOKEN = "MANUAL_TOKEN"
    NONE = "NONE"


class ProviderCapabilities(Contract):
    read: bool = False
    catalog: bool = False
    search: bool = False
    commands: bool = False


class ProviderDefinition(Contract):
    provider_id: ProviderId
    display_name: str = Field(min_length=1, max_length=80)
    supported_modes: tuple[Literal["LIVE"], ...] = ("LIVE",)
    auth_method: ProviderAuthMethod
    capabilities: ProviderCapabilities = ProviderCapabilities()


ZERODHA = ProviderDefinition(
    provider_id="zerodha",
    display_name="Zerodha",
    auth_method=ProviderAuthMethod.BROWSER_REDIRECT_CALLBACK,
    capabilities=ProviderCapabilities(read=True, catalog=True, search=True, commands=False),
)
PROVIDERS = MappingProxyType({ZERODHA.provider_id: ZERODHA})


class ProviderStatus(Contract):
    provider_id: ProviderId
    display_name: str
    supported_modes: tuple[str, ...]
    auth_method: ProviderAuthMethod
    capabilities: ProviderCapabilities
    supported: Literal[True] = True
    configured: bool
    connectable: bool = False
    trading_enabled: Literal[False] = False


class BrokerAccountCreate(Contract):
    provider_id: ProviderId
    label: AccountLabel


class BrokerAccountConfiguration(Contract):
    expected_revision: int = Field(ge=1)
    label: AccountLabel
    enabled: bool


class BrokerAccountView(Contract):
    broker_account_id: UUID
    owner_user_id: UUID
    provider_id: ProviderId
    provider_account_id: str | None
    mode: Literal["LIVE"] = "LIVE"
    label: str
    enabled: bool
    configured: bool
    configuration_revision: int
    connection_generation: int
    authentication_state: Literal[
        "NOT_CONFIGURED",
        "DISCONNECTED",
        "AUTHENTICATING",
        "AUTH_REQUIRED",
        "AUTH_IN_PROGRESS",
        "CONNECTED",
        "REAUTH_REQUIRED",
        "ERROR",
    ]
    read_health: Literal["UNKNOWN", "AVAILABLE", "DEGRADED", "UNAVAILABLE"]
    last_successful_read_at: AwareDatetime | None
    last_failure_at: AwareDatetime | None
    connectable: bool = False
    trading_enabled: Literal[False] = False
    created_at: datetime
    updated_at: datetime
