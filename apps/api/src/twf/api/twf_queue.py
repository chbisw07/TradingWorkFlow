"""Owner-scoped TWF Queue API. No generic state setter or broker operation."""

import logging
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import JSONResponse

from twf.api.auth import require_origin
from twf.api.brokers import Who
from twf.api.errors import error_response
from twf.infrastructure.identity import AuthSession, User
from twf.orders.context import OrderContext
from twf.queue.contracts import AdmitOrder, QueueChange, QueueEntryView, QueueEventView
from twf.queue.errors import QueueError, QueueErrorCode
from twf.queue.service import QueueService

router = APIRouter(prefix="/api/v1/twf-queue", tags=["TWF Queue"])
logger = logging.getLogger(__name__)


def _service(request: Request, who: Who) -> QueueService:
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    with factory() as db:
        user = db.get(User, who.user_id)
        login = db.get(AuthSession, who.session_hash)
        if user is None or login is None:
            raise QueueError(QueueErrorCode.UNAUTHORIZED, "Please sign in again")
        try:
            context = OrderContext.from_authenticated_session(user, login)
        except ValueError as exc:
            raise QueueError(QueueErrorCode.UNAUTHORIZED, "Please sign in again") from exc
    return QueueService(factory, context)


Service = Annotated[QueueService, Depends(_service)]


async def queue_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, QueueError)
    logger.warning(
        "twf_queue_operation_rejected",
        extra={"code": exc.code.value, "path": request.url.path},
    )
    status = {
        QueueErrorCode.UNAUTHORIZED: 401,
        QueueErrorCode.ORDER_NOT_FOUND: 404,
        QueueErrorCode.QUEUE_ENTRY_NOT_FOUND: 404,
        QueueErrorCode.ORDER_NOT_READY: 409,
        QueueErrorCode.ORDER_VERSION_CONFLICT: 409,
        QueueErrorCode.QUEUE_VERSION_CONFLICT: 409,
        QueueErrorCode.RETRYABLE_CONCURRENCY_CONFLICT: 409,
        QueueErrorCode.QUEUE_INVARIANT_FAILURE: 409,
        QueueErrorCode.INVALID_QUEUE_TRANSITION: 409,
    }[exc.code]
    response = error_response(request, status, exc.code.value, str(exc))
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("")
def list_entries(
    service: Service, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> tuple[QueueEntryView, ...]:
    return service.list_entries(limit=limit)


@router.get("/by-order/{order_id}")
def get_for_order(order_id: UUID, service: Service) -> QueueEntryView:
    return service.get_for_order(order_id)


@router.get("/{entry_id}")
def get_entry(entry_id: UUID, service: Service) -> QueueEntryView:
    return service.get_entry(entry_id)


@router.get("/{entry_id}/history")
def history(entry_id: UUID, service: Service) -> tuple[QueueEventView, ...]:
    return service.history(entry_id)


@router.post("/admit", dependencies=[Depends(require_origin)])
def admit(payload: AdmitOrder, service: Service) -> QueueEntryView:
    return service.admit(
        payload.twf_order_id, expected_order_version=payload.expected_order_version
    )


@router.post("/{entry_id}/hold", dependencies=[Depends(require_origin)])
def hold(entry_id: UUID, payload: QueueChange, service: Service) -> QueueEntryView:
    return service.hold(entry_id, expected_version=payload.expected_version, reason=payload.reason)


@router.post("/{entry_id}/release", dependencies=[Depends(require_origin)])
def release(entry_id: UUID, payload: QueueChange, service: Service) -> QueueEntryView:
    return service.release(entry_id, expected_version=payload.expected_version)
