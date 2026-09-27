from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from starlette.responses import JSONResponse

from twf import auth
from twf.api.auth import Database, require_origin
from twf.api.errors import error_response
from twf.brokers.contracts import (
    Account,
    BrokerFailure,
    CatalogPage,
    Credentials,
    Funds,
    Holding,
    Order,
    Overview,
    Position,
    Provider,
    Search,
    Snapshot,
)
from twf.brokers.service import BrokerService, Principal

router = APIRouter(prefix="/api/v1/brokers", tags=["Read-only brokers"])


def principal(request: Request, response: Response, db: Database) -> Principal:
    token = request.cookies.get(request.app.state.settings.session_cookie_name)
    login = auth.resolve_session(db, token)
    user = auth.current_user(db, token)
    if not login or not user:
        raise BrokerFailure("UNAUTHORIZED", "Please sign in.", 401)
    result = Principal(user.id, login.token_hash)
    db.rollback()  # No auth read transaction remains during broker writes or network I/O.
    response.headers["Cache-Control"] = "no-store"
    return result


Who = Annotated[Principal, Depends(principal)]


def service(request: Request) -> BrokerService:
    return cast(BrokerService, request.app.state.broker_service)


Service = Annotated[BrokerService, Depends(service)]


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["zerodha"] = "zerodha"
    name: str = Field(min_length=1, max_length=80)
    api_key: SecretStr = Field(min_length=8, max_length=128)
    api_secret: SecretStr = Field(min_length=8, max_length=128)
    account_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def name_valid(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid name")
        return value.strip()

    @field_validator("api_key", "api_secret")
    @classmethod
    def secret_valid(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().isalnum() or not value.get_secret_value().isascii():
            raise ValueError("Invalid credentials")
        return value


class Callback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$", repr=False)
    request_token: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,256}$", repr=False)


class ConnectResult(BaseModel):
    login_url: str


class SetupInfo(BaseModel):
    callback_url: str
    storage_available: bool
    storage_message: str | None = None


async def broker_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BrokerFailure)
    request.app.state.logger.info("broker_request_rejected", extra={"reason": exc.code})
    response = error_response(request, exc.status, exc.code, exc.message)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/providers")
def providers(who: Who) -> list[Provider]:
    return [
        Provider(id=slug, name=name, supported=slug == "zerodha")
        for slug, name in (
            ("zerodha", "Zerodha"),
            ("angel-one", "Angel One"),
            ("fyers", "Fyers"),
            ("dhan", "Dhan"),
            ("upstox", "Upstox"),
        )
    ]


@router.get("/setup")
def setup(who: Who, broker: Service) -> SetupInfo:
    message = None
    try:
        broker.secrets.cipher()
        available = True
    except BrokerFailure as exc:
        available = False
        message = exc.message
    return SetupInfo(
        callback_url=broker.settings.broker_callback_url,
        storage_available=available,
        storage_message=message,
    )


@router.get("/accounts")
def accounts(who: Who, broker: Service) -> list[Account]:
    return broker.list_accounts(who)


@router.post("/accounts", dependencies=[Depends(require_origin)])
async def configure(payload: Configuration, who: Who, broker: Service) -> Account:
    return await broker.configure(
        who,
        payload.name,
        Credentials(api_key=payload.api_key, api_secret=payload.api_secret),
        payload.account_id,
    )


@router.post("/accounts/{account_id}/connect", dependencies=[Depends(require_origin)])
async def connect(account_id: UUID, who: Who, broker: Service) -> ConnectResult:
    return ConnectResult(login_url=await broker.connect(who, account_id))


@router.post("/callback", dependencies=[Depends(require_origin)])
async def callback(payload: Callback, who: Who, broker: Service) -> Account:
    return await broker.callback(who, payload.state, payload.request_token)


@router.post("/accounts/{account_id}/disconnect", dependencies=[Depends(require_origin)])
async def disconnect(account_id: UUID, who: Who, broker: Service) -> Account:
    return await broker.disconnect(who, account_id)


@router.get("/accounts/{account_id}/{kind}")
async def portfolio(
    account_id: UUID,
    kind: Literal["overview", "holdings", "positions", "orders", "funds", "instruments"],
    who: Who,
    broker: Service,
    query: Annotated[Search, Query()],
) -> Snapshot[Overview | list[Holding] | list[Position] | list[Order] | list[Funds] | CatalogPage]:
    return await broker.portfolio(who, account_id, kind, query)
