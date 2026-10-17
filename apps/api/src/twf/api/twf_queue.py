"""Owner-scoped TWF Queue API with explicit governed dispatch; no generic state setter."""

import logging
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import JSONResponse

from twf.api.auth import require_origin
from twf.api.brokers import Service as BrokerServiceDependency
from twf.api.brokers import Who
from twf.api.errors import error_response
from twf.infrastructure.identity import AuthSession, User
from twf.orders.context import OrderContext
from twf.queue.contracts import (
    AdmitOrder,
    PolicyChange,
    PolicyView,
    QueueChange,
    QueueEntryView,
    QueueEventView,
    QueuePage,
    QueueState,
)
from twf.queue.dispatch import DispatchService
from twf.queue.errors import QueueError, QueueErrorCode
from twf.queue.policy import change_policy, locked_policy
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
        QueueErrorCode.INVALID_CURSOR: 400,
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
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    state: QueueState | None = None,
) -> QueuePage:
    return service.list_entries(limit=limit, cursor=cursor, state=state)


@router.get("/by-order/{order_id}")
def get_for_order(order_id: UUID, service: Service) -> QueueEntryView:
    return service.get_for_order(order_id)


@router.get("/policy/{account_id}")
def get_policy(account_id: UUID, service: Service, broker: BrokerServiceDependency) -> PolicyView:
    def operation(db: Session) -> PolicyView:
        owner = service._owner(db)
        row = locked_policy(db, owner, account_id)
        return PolicyView.model_validate(row, from_attributes=True).model_copy(
            update={"execution_enabled": broker.settings.queue_dispatch_enabled}
        )

    return broker.transaction(operation)


@router.post("/policy/{account_id}", dependencies=[Depends(require_origin)])
def set_policy(
    account_id: UUID, payload: PolicyChange, service: Service, broker: BrokerServiceDependency
) -> PolicyView:
    def operation(db: Session) -> PolicyView:
        owner = service._owner(db)
        previous = locked_policy(db, owner, account_id).current_dispatch_mode
        row = change_policy(
            db,
            owner,
            account_id,
            payload.current_dispatch_mode,
            payload.expected_version,
            service.context.actor,
        )
        return PolicyView.model_validate(row, from_attributes=True).model_copy(
            update={
                "execution_enabled": broker.settings.queue_dispatch_enabled,
                "previous_dispatch_mode": previous,
            }
        )

    return broker.transaction(operation)


@router.get("/{entry_id}")
def get_entry(entry_id: UUID, service: Service) -> QueueEntryView:
    return service.get_entry(entry_id)


@router.get("/{entry_id}/history")
def history(entry_id: UUID, service: Service) -> tuple[QueueEventView, ...]:
    return service.history(entry_id)


@router.post("/admit", dependencies=[Depends(require_origin)])
def admit(payload: AdmitOrder, service: Service) -> QueueEntryView:
    return service.admit(
        payload.twf_order_id,
        expected_order_version=payload.expected_order_version,
        broker_account_id=payload.broker_account_id,
    )


@router.post("/{entry_id}/hold", dependencies=[Depends(require_origin)])
def hold(entry_id: UUID, payload: QueueChange, service: Service) -> QueueEntryView:
    return service.hold(entry_id, expected_version=payload.expected_version, reason=payload.reason)


@router.post("/{entry_id}/release", dependencies=[Depends(require_origin)])
def release(entry_id: UUID, payload: QueueChange, service: Service) -> QueueEntryView:
    return service.release(entry_id, expected_version=payload.expected_version)


@router.post("/{entry_id}/dispatch", dependencies=[Depends(require_origin)])
async def dispatch(
    entry_id: UUID,
    payload: QueueChange,
    service: Service,
    who: Who,
    broker: BrokerServiceDependency,
) -> QueueEntryView:
    await DispatchService(broker).dispatch(entry_id, who, expected_version=payload.expected_version)
    return service.get_entry(entry_id)


@router.post("/{entry_id}/cancel", dependencies=[Depends(require_origin)])
async def cancel(
    entry_id: UUID,
    payload: QueueChange,
    service: Service,
    who: Who,
    broker: BrokerServiceDependency,
) -> QueueEntryView:
    await DispatchService(broker).cancel(who, entry_id, payload.expected_version)
    return service.get_entry(entry_id)


@router.get("/aliases/orders")
def order_aliases(service: Service) -> dict[str, str]:
    from sqlalchemy import select

    from twf.infrastructure.dispatch import OrderPublicID
    from twf.infrastructure.twf_order import TWFOrderRecord

    with service.sessions() as db:
        owner = service._owner(db)
        rows = db.execute(
            select(OrderPublicID.twf_order_id, OrderPublicID.public_order_id)
            .join(TWFOrderRecord, TWFOrderRecord.twf_order_id == OrderPublicID.twf_order_id)
            .where(TWFOrderRecord.owner_id == owner)
            .order_by(TWFOrderRecord.created_at.desc(), TWFOrderRecord.twf_order_id)
            .limit(100)
        ).all()
        return {str(key): value for key, value in rows}
