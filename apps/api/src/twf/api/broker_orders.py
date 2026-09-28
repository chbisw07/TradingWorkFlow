"""Authenticated manual order workflow; confirm accepts only a durable preview ID."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from twf.api.auth import require_origin
from twf.api.brokers import Service, Who
from twf.brokers.order_contracts import Capability, Choices, IntentView, OrderDraft, OrderSelection
from twf.brokers.order_service import OrderService
from twf.brokers.quotes import QuoteBatch, QuoteRequest, read_quotes

router = APIRouter(
    prefix="/api/v1/brokers/accounts/{account_id}/order-entry", tags=["Manual orders"]
)


@router.get("/capabilities")
async def capabilities(
    account_id: UUID,
    who: Who,
    broker: Service,
    reference: str = Query(default="", max_length=200),
    native_token: str = Query(default="", max_length=20),
) -> Capability:
    return await OrderService(broker).capability(who, account_id, reference, native_token)


@router.get("/choices")
async def choices(
    account_id: UUID, who: Who, broker: Service, query: Annotated[OrderSelection, Query()]
) -> Choices:
    return await OrderService(broker).choices(who, account_id, query)


@router.post("/preview", dependencies=[Depends(require_origin)])
async def preview(account_id: UUID, order: OrderDraft, who: Who, broker: Service) -> IntentView:
    return await OrderService(broker).preview(who, account_id, order)


@router.get("/intents")
def intents(account_id: UUID, who: Who, broker: Service) -> list[IntentView]:
    return OrderService(broker).list_intents(who, account_id)


@router.get("/intents/{intent_id}")
def intent(account_id: UUID, intent_id: UUID, who: Who, broker: Service) -> IntentView:
    return OrderService(broker).get(who, account_id, intent_id)


@router.post("/intents/{intent_id}/confirm", dependencies=[Depends(require_origin)])
async def confirm(account_id: UUID, intent_id: UUID, who: Who, broker: Service) -> IntentView:
    return await OrderService(broker).confirm(who, account_id, intent_id)


@router.post("/intents/{intent_id}/reconcile", dependencies=[Depends(require_origin)])
async def reconcile(account_id: UUID, intent_id: UUID, who: Who, broker: Service) -> IntentView:
    return await OrderService(broker).reconcile(who, account_id, intent_id)


@router.post("/quotes", dependencies=[Depends(require_origin)])
async def quotes(account_id: UUID, query: QuoteRequest, who: Who, broker: Service) -> QuoteBatch:
    return await read_quotes(broker, who, account_id, query)
