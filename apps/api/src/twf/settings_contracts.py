"""Finite personal preference contracts; no tenant, integration or trading authority."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_serializer

Scope = Literal["PLATFORM", "ACCOUNT", "USER", "WORKSPACE", "WORKFLOW"]
SettingClass = Literal["PRESENTATION", "USER_WORKFLOW", "SYSTEM_INTEGRATION"]
Mutability = Literal["HOT", "WARM", "COLD"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SecretReference(Contract):
    reference_id: UUID
    ownership: Literal["PLATFORM_MANAGED", "ACCOUNT_MANAGED", "USER_MANAGED"]
    owner_id: UUID
    # No secret-bearing field or free-form metadata is accepted.


class PreferenceValues(Contract):
    density: Literal["comfortable", "compact"] | None = None
    default_horizon: Literal["5d", "15d"] | None = None

    @field_validator("density", "default_horizon", mode="before")
    @classmethod
    def no_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Omit a value to inherit its default")
        return value

    def stored(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "density": self.density,
                "default_horizon": self.default_horizon,
            }.items()
            if value is not None
        }

    @model_serializer
    def serialize(self) -> dict[str, str]:
        return self.stored()


class ResolvedValues(Contract):
    density: Literal["comfortable", "compact"] = "comfortable"
    default_horizon: Literal["5d", "15d"] = "5d"


class Definition(Contract):
    key: str
    setting_class: SettingClass
    allowed_scopes: tuple[Scope, ...] = ("USER",)
    default: str
    choices: tuple[str, ...]
    mutability: Mutability = "HOT"
    schema_version: int = 1
    permission: str = "settings:own"
    capability: str


DEFINITIONS = (
    Definition(
        key="density",
        setting_class="PRESENTATION",
        default="comfortable",
        choices=("comfortable", "compact"),
        capability="foundation.appearance",
    ),
    Definition(
        key="default_horizon",
        setting_class="USER_WORKFLOW",
        default="5d",
        choices=("5d", "15d"),
        capability="foundation.workflow_preferences",
    ),
)


class CapabilityPolicy(Protocol):
    def allows(self, user_id: UUID, capability: str) -> bool: ...


class FoundationPolicy:
    def allows(self, user_id: UUID, capability: str) -> bool:
        return capability in {"foundation.appearance", "foundation.workflow_preferences"}


class RevisionInput(Contract):
    revision: StrictInt = Field(ge=0)
    scope: Literal["USER"] = "USER"


class ValuesInput(RevisionInput):
    values: PreferenceValues


class ProfileInput(Contract):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[\w .()-]+$")
    values: PreferenceValues
    scope: Literal["USER"] = "USER"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A profile name is required")
        return value


class ProfileEdit(ProfileInput):
    revision: StrictInt = Field(ge=1)


class ApplyInput(RevisionInput):
    profile_revision: StrictInt = Field(ge=1)


class SettingsView(Contract):
    revision: int
    scope: Literal["USER"] = "USER"
    schema_version: int = 1
    overrides: PreferenceValues
    effective: ResolvedValues
    sources: dict[str, Literal["USER", "PLATFORM"]]
    active_profile_id: UUID | None = None
    applied_profile_revision: int | None = None


class ProfileView(Contract):
    id: UUID
    name: str
    revision: int
    schema_version: int = 1
    values: PreferenceValues
    state: Literal["VALIDATED"] = "VALIDATED"
