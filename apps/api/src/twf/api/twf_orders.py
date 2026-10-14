"""Owner-scoped OE-2 manual TWF Order API. No Queue or broker execution routes."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import JSONResponse

from twf.api.auth import require_origin
from twf.api.brokers import Service, Who
from twf.api.errors import error_response
from twf.infrastructure.identity import AuthSession, User
from twf.orders.context import OrderContext
from twf.orders.contracts import OrderEventView, OrderView
from twf.orders.errors import OrderError, OrderErrorCode
from twf.orders.resolution import _bind_trusted_canonical_resolver
from twf.orders.service import OrderService
from twf.twf_orders.manual import ManualCreateInput, ManualCreation, ManualOrderInput, ManualPreview
from twf.twf_orders.manual import create as create_manual
from twf.twf_orders.manual import preview as preview_manual

router = APIRouter(prefix="/api/v1/twf-orders", tags=["TWF Orders"])


class _ReadOnlyResolver:
    def resolve(self, instrument_id: UUID) -> None:
        return None


def _reader(request: Request, who: Who) -> OrderService:
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    with factory() as db:
        user = db.get(User, who.user_id)
        login = db.get(AuthSession, who.session_hash)
        if user is None or login is None:
            raise OrderError(OrderErrorCode.UNAUTHORIZED, "Please sign in again")
        context = OrderContext.from_authenticated_session(user, login)
    return OrderService(factory, context, _bind_trusted_canonical_resolver(_ReadOnlyResolver()))


Reader = Annotated[OrderService, Depends(_reader)]


async def order_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, OrderError)
    status = {
        OrderErrorCode.UNAUTHORIZED: 401,
        OrderErrorCode.ORDER_NOT_FOUND: 404,
        OrderErrorCode.VERSION_CONFLICT: 409,
        OrderErrorCode.RETRYABLE_CONCURRENCY_CONFLICT: 409,
    }.get(exc.code, 422)
    response = error_response(request, status, exc.code.value, str(exc))
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("")
def list_orders(
    service: Reader, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> tuple[OrderView, ...]:
    return service.list_orders(limit=limit)


@router.get("/{order_id}")
def get_order(order_id: UUID, service: Reader) -> OrderView:
    return service.get_order(order_id)


@router.get("/{order_id}/history")
def history(order_id: UUID, service: Reader) -> tuple[OrderEventView, ...]:
    return service.get_order_history(order_id)


@router.post("/preview", dependencies=[Depends(require_origin)])
async def preview(payload: ManualOrderInput, who: Who, broker: Service) -> ManualPreview:
    return await preview_manual(broker, who, payload)


@router.post("", dependencies=[Depends(require_origin)])
async def create(payload: ManualCreateInput, who: Who, broker: Service) -> ManualCreation:
    return await create_manual(broker, who, payload)
