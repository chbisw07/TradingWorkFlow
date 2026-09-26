"""Authenticated BW-2.1 provider/account metadata API; deliberately no connect route."""

from collections.abc import Callable
from typing import Annotated, TypeVar, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from twf.api.auth import Database, get_current_user, require_origin
from twf.broker_foundation import BrokerFoundation, BrokerFoundationFailure
from twf.brokers.foundation_contracts import (
    BrokerAccountConfiguration,
    BrokerAccountCreate,
    BrokerAccountView,
    BrokerPermissionPolicy,
    ProviderStatus,
)
from twf.infrastructure.identity import User
from twf.schemas import ErrorResponse
from twf.secrets import SecretStore

router = APIRouter(
    prefix="/api/v1",
    tags=["Broker provider/account foundation"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
Result = TypeVar("Result")


def foundation(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Database,
) -> BrokerFoundation:
    return BrokerFoundation(
        session,
        user.id,
        cast(BrokerPermissionPolicy, request.app.state.broker_permission_policy),
        cast(SecretStore, request.app.state.secret_store),
        request.app.state.settings.environment,
        request.state.request_id,
        logger=request.app.state.logger,
    )


def invoke[Result](operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except BrokerFoundationFailure as error:
        raise HTTPException(error.status) from None


@router.get("/broker-providers")
def providers(
    response: Response, use: Annotated[BrokerFoundation, Depends(foundation)]
) -> tuple[ProviderStatus, ...]:
    response.headers["Cache-Control"] = "no-store"
    return invoke(use.providers)


@router.get("/broker-accounts")
def accounts(
    response: Response, use: Annotated[BrokerFoundation, Depends(foundation)]
) -> tuple[BrokerAccountView, ...]:
    response.headers["Cache-Control"] = "no-store"
    return invoke(use.list_accounts)


@router.post(
    "/broker-accounts",
    status_code=201,
    dependencies=[Depends(require_origin)],
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_account(
    payload: BrokerAccountCreate,
    response: Response,
    use: Annotated[BrokerFoundation, Depends(foundation)],
) -> BrokerAccountView:
    response.headers["Cache-Control"] = "no-store"
    return invoke(lambda: use.create_account(payload))


@router.patch(
    "/broker-accounts/{account_id}/configuration",
    dependencies=[Depends(require_origin)],
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def configure_account(
    account_id: UUID,
    payload: BrokerAccountConfiguration,
    response: Response,
    use: Annotated[BrokerFoundation, Depends(foundation)],
) -> BrokerAccountView:
    response.headers["Cache-Control"] = "no-store"
    return invoke(lambda: use.configure_account(account_id, payload))
