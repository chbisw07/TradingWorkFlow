"""Owner-scoped Dhan market-data credential settings."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import Field, SecretStr
from starlette.responses import JSONResponse

from twf.api.auth import require_origin
from twf.api.errors import error_response
from twf.api.mcp import Who
from twf.discovery.dhan_credentials import (
    DhanCredentialFailure,
    DhanCredentialManager,
    DhanCredentialStatus,
)
from twf.integrations.contracts import Contract

router = APIRouter(
    prefix="/api/v1/settings/market-data/dhan",
    tags=["Dhan market data settings"],
)


def manager(request: Request) -> DhanCredentialManager:
    return cast(DhanCredentialManager, request.app.state.dhan_credentials)


Manager = Annotated[DhanCredentialManager, Depends(manager)]


class DhanCredentials(Contract):
    generation: int = Field(ge=0, strict=True)
    client_id: SecretStr = Field(min_length=1, max_length=128, repr=False)
    access_token: SecretStr = Field(min_length=8, max_length=4096, repr=False)


class DhanRevision(Contract):
    generation: int = Field(ge=0, strict=True)


async def dhan_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DhanCredentialFailure)
    response = error_response(
        request,
        exc.status,
        exc.code,
        "Dhan market-data configuration could not be completed.",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("")
def status(who: Who, service: Manager) -> DhanCredentialStatus:
    return service.status(who.owner_id)


@router.put("/credentials", dependencies=[Depends(require_origin)])
def configure(payload: DhanCredentials, who: Who, service: Manager) -> DhanCredentialStatus:
    return service.configure(
        who.owner_id,
        payload.generation,
        payload.client_id,
        payload.access_token,
    )


@router.post("/test", dependencies=[Depends(require_origin)])
async def test_connection(
    payload: DhanRevision, who: Who, service: Manager
) -> DhanCredentialStatus:
    return await service.test_connection(who.owner_id, payload.generation)


@router.post("/disconnect", dependencies=[Depends(require_origin)])
def disconnect(payload: DhanRevision, who: Who, service: Manager) -> DhanCredentialStatus:
    return service.disconnect(who.owner_id, payload.generation)
