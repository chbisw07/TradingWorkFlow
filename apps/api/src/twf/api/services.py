from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from twf.api.auth import Database, get_current_user
from twf.infrastructure.identity import User
from twf.integrations.contracts import Contract, RequestContext
from twf.integrations.registry import ServiceRegistry, ServiceStatus
from twf.schemas import ErrorResponse

router = APIRouter(prefix="/api/v1/services", tags=["Service foundation"])


def service_principal(user: Annotated[User, Depends(get_current_user)], session: Database) -> UUID:
    user_id = user.id
    # Authentication owns a read transaction. Release it before any satellite await.
    session.rollback()
    return user_id


class ServicesResponse(Contract):
    services: tuple[ServiceStatus, ...]


@router.get("", responses={401: {"model": ErrorResponse}})
async def services(
    request: Request,
    response: Response,
    user_id: Annotated[UUID, Depends(service_principal)],
) -> ServicesResponse:
    response.headers["Cache-Control"] = "no-store"
    registry = cast(ServiceRegistry, request.app.state.service_registry)
    context = RequestContext(request_id=request.state.request_id)
    return ServicesResponse(
        services=await registry.statuses(user_id, context, request.app.state.logger)
    )
