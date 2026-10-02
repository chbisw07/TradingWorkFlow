"""Authenticated personal provider settings; no arbitrary tool invocation endpoint."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, SecretStr
from starlette.responses import JSONResponse

from twf import auth
from twf.api.auth import Database, require_origin
from twf.api.errors import error_response
from twf.integrations.contracts import Contract, RequestContext
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import (
    AuthMode,
    Authorization,
    Code,
    ConnectionView,
    Context,
    Failure,
)

router = APIRouter(prefix="/api/v1/settings/mcp", tags=["MCP provider connections"])
DECOMMISSIONED_PRODUCT_PROVIDERS = frozenset({"tradingview"})


def principal(request: Request, response: Response, db: Database) -> Context:
    token = request.cookies.get(request.app.state.settings.session_cookie_name)
    login, user = auth.resolve_session(db, token), auth.current_user(db, token)
    if not login or not user:
        raise Failure(Code.DENIED)
    who = Context(
        owner_id=user.id,
        session_hash=login.token_hash,
        correlation=RequestContext(request_id=request.state.request_id),
    )
    db.rollback()
    response.headers["Cache-Control"] = "no-store"
    return who


Who = Annotated[Context, Depends(principal)]


def manager(request: Request) -> ConnectionManager:
    return cast(ConnectionManager, request.app.state.mcp_manager)


Manager = Annotated[ConnectionManager, Depends(manager)]


class ProviderRegistration(Contract):
    provider_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=80)
    auth_mode: AuthMode


class Create(Contract):
    provider_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=80)


class Revision(Contract):
    generation: int = Field(ge=0, strict=True)


class Connect(Revision):
    api_key: SecretStr | None = Field(default=None, repr=False, max_length=8192)


class Callback(Contract):
    state: str = Field(min_length=1, max_length=128, repr=False)
    code: str = Field(min_length=1, max_length=2048, repr=False)


async def mcp_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, Failure)
    statuses = {
        Code.DENIED: 403,
        Code.NOT_CONFIGURED: 404,
        Code.STALE: 409,
        Code.AUTH_REQUIRED: 401,
        Code.REAUTH_REQUIRED: 401,
        Code.AUTH_FAILED: 400,
        Code.RATE_LIMITED: 429,
        Code.INVALID_ARGUMENTS: 422,
        Code.CLOSED: 409,
        Code.REVOKED: 409,
        Code.TOOL_NOT_ALLOWED: 403,
        Code.TIMEOUT: 504,
    }
    response = error_response(
        request,
        statuses.get(exc.code, 503),
        exc.code.value,
        "Provider operation could not be completed.",
    )
    response.headers["Cache-Control"] = "no-store"
    if exc.retry_after is not None:
        response.headers["Retry-After"] = str(exc.retry_after)
    return response


@router.get("/providers")
def providers(who: Who, service: Manager) -> tuple[ProviderRegistration, ...]:
    del who
    return tuple(
        ProviderRegistration(
            provider_id=item.provider_id,
            display_name=item.display_name,
            auth_mode=item.auth_mode,
        )
        for item in sorted(service.providers.values(), key=lambda row: row.display_name)
        if item.provider_id not in DECOMMISSIONED_PRODUCT_PROVIDERS
    )


@router.get("/connections")
def connections(who: Who, service: Manager) -> tuple[ConnectionView, ...]:
    return service.connections(who)


@router.post("/connections", dependencies=[Depends(require_origin)])
async def create(payload: Create, who: Who, service: Manager) -> ConnectionView:
    if payload.provider_id in DECOMMISSIONED_PRODUCT_PROVIDERS:
        raise Failure(Code.NOT_CONFIGURED)
    return await service.create(who, payload.provider_id, payload.display_name)


@router.get("/connections/{identity}")
def status(identity: UUID, who: Who, service: Manager) -> ConnectionView:
    return service.status(who, identity)


@router.post("/connections/{identity}/connect", dependencies=[Depends(require_origin)])
async def connect(identity: UUID, payload: Connect, who: Who, service: Manager) -> ConnectionView:
    return await service.connect(who, identity, payload.generation, payload.api_key)


@router.post("/connections/{identity}/authorize", dependencies=[Depends(require_origin)])
async def authorize(identity: UUID, payload: Revision, who: Who, service: Manager) -> Authorization:
    return await service.begin(who, identity, payload.generation)


@router.post("/connections/{identity}/callback", dependencies=[Depends(require_origin)])
async def callback(identity: UUID, payload: Callback, who: Who, service: Manager) -> ConnectionView:
    # Same-origin POST conduit keeps accepted SameSite=Strict cookies unchanged.
    # Future frontend landing page must immediately scrub code/state from its URL.
    return await service.callback(who, identity, payload.state, payload.code)


@router.post("/connections/{identity}/refresh", dependencies=[Depends(require_origin)])
async def refresh(identity: UUID, payload: Revision, who: Who, service: Manager) -> ConnectionView:
    return await service.refresh(who, identity, payload.generation)


@router.post("/connections/{identity}/disconnect", dependencies=[Depends(require_origin)])
async def disconnect(
    identity: UUID, payload: Revision, who: Who, service: Manager
) -> ConnectionView:
    return await service.disconnect(who, identity, payload.generation)


@router.post("/connections/{identity}/test", dependencies=[Depends(require_origin)])
async def test_connection(
    identity: UUID, payload: Revision, who: Who, service: Manager
) -> ConnectionView:
    return await service.test_connection(who, identity, payload.generation)


@router.post("/connections/{identity}/cleanup", dependencies=[Depends(require_origin)])
async def cleanup(identity: UUID, who: Who, service: Manager) -> ConnectionView:
    await service.cleanup(who, identity)
    return service.status(who, identity)


@router.post("/connections/{identity}/recover", dependencies=[Depends(require_origin)])
async def recover(identity: UUID, who: Who, service: Manager) -> ConnectionView:
    return await service.recover(who, identity)
