"""Operator-owned configuration, never populated from user profile endpoints."""

import ipaddress
import re
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from twf.integrations.contracts import Contract, DeploymentMode, ServiceIdentity


def endpoint_origin(endpoint: str) -> str:
    try:
        url = urlsplit(endpoint)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
            or any(ord(c) < 33 or ord(c) > 126 for c in endpoint)
            or "\\" in endpoint
            or "%" in endpoint
            or "*" in endpoint
        ):
            raise ValueError
        port = url.port
        if port == 0:
            raise ValueError
        host = url.hostname.removesuffix(".").lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            ):
                raise ValueError("Invalid service hostname") from None
        else:
            if address.is_link_local or address.is_multicast or address.is_unspecified:
                raise ValueError("Unsafe service address")
        if ":" in host:
            host = f"[{host}]"
        default = 443 if url.scheme == "https" else 80
        return f"{url.scheme}://{host}" + (f":{port}" if port and port != default else "")
    except ValueError:
        raise ValueError("Service endpoint must be an explicit HTTP(S) origin") from None


class ServiceDescriptor(Contract):
    identity: ServiceIdentity
    mode: DeploymentMode
    enabled: bool = False
    endpoint: str | None = Field(default=None, repr=False)
    timeout_seconds: float = Field(default=2, ge=0.1, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_endpoint(self) -> Self:
        if self.mode == DeploymentMode.REMOTE:
            if self.endpoint is None:
                raise ValueError("Remote services require an endpoint")
            endpoint_origin(self.endpoint)
        elif self.endpoint is not None:
            raise ValueError("Only remote services accept endpoints")
        return self


def validate_policy(
    descriptors: tuple[ServiceDescriptor, ...], allowed_origins: tuple[str, ...], production: bool
) -> None:
    origins = {endpoint_origin(origin) for origin in allowed_origins}
    if len(descriptors) > 16:
        raise ValueError("At most sixteen service descriptors are supported")
    identifiers = [descriptor.identity.service_id for descriptor in descriptors]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Service identifiers must be unique")
    for descriptor in descriptors:
        if production and descriptor.mode == DeploymentMode.SYNTHETIC:
            raise ValueError("Synthetic services are restricted to development and test")
        if descriptor.endpoint is not None:
            origin = endpoint_origin(descriptor.endpoint)
            if origin not in origins or (production and not origin.startswith("https://")):
                raise ValueError("Service endpoint is not permitted by operator policy")
