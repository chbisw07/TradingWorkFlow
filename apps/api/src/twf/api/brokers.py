from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from twf.api.auth import Database, get_current_user
from twf.brokers.contracts import BrokerSnapshot, UnifiedBrokerSnapshot
from twf.brokers.service import BrokerService
from twf.infrastructure.identity import User
from twf.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/v1/brokers",
    tags=["Broker read foundation"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def broker_principal(user: Annotated[User, Depends(get_current_user)], session: Database) -> UUID:
    owner = user.id
    session.rollback()
    return owner


@router.get("/overview")
def overview(
    request: Request, response: Response, owner: Annotated[UUID, Depends(broker_principal)]
) -> UnifiedBrokerSnapshot:
    response.headers["Cache-Control"] = "no-store"
    service = cast(BrokerService, request.app.state.broker_service)
    return service.overview(owner, request.state.request_id)


@router.get("/accounts/{account_id}")
def room(
    account_id: UUID,
    request: Request,
    response: Response,
    owner: Annotated[UUID, Depends(broker_principal)],
) -> BrokerSnapshot:
    response.headers["Cache-Control"] = "no-store"
    service = cast(BrokerService, request.app.state.broker_service)
    try:
        return service.room(owner, account_id, request.state.request_id)
    except LookupError:
        raise HTTPException(404) from None
