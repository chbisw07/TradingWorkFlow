"""Authenticated manual order workflow; confirm accepts only a durable preview ID."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from twf.api.auth import require_origin
from twf.api.brokers import Service, Who
from twf.brokers.order_contracts import Capability, Choices, IntentView, OrderDraft, OrderSelection
from twf.brokers.order_service import OrderService, invalid, resolver
from twf.brokers.quotes import QuoteBatch, QuoteRequest, read_quotes
from twf.options.contracts import OptionContractRequest
from twf.options.resolver import OptionResolutionError

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


class CanonicalOptionOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    side: Literal["BUY", "SELL"]
    product: str = Field(max_length=12)
    order_type: str = Field(max_length=12)
    quantity: int = Field(gt=0, le=1000000, strict=True)
    lots: int | None = Field(default=None, gt=0, le=1000000, strict=True)
    price: Decimal | None = Field(
        default=None, gt=0, lt=1000000000, max_digits=17, decimal_places=8, allow_inf_nan=False
    )
    trigger_price: Decimal | None = Field(
        default=None, gt=0, lt=1000000000, max_digits=17, decimal_places=8, allow_inf_nan=False
    )
    validity: str = Field(default="DAY", max_length=8)


class CanonicalOptionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract: OptionContractRequest
    order: CanonicalOptionOrder


@router.post("/option-preview", dependencies=[Depends(require_origin)])
async def option_preview(
    account_id: UUID, payload: CanonicalOptionPreview, who: Who, broker: Service
) -> IntentView:
    orders = OrderService(broker)
    try:
        resolved = resolver(await orders.catalog(who, account_id)).resolve(payload.contract)
    except OptionResolutionError as exc:
        raise invalid(str(exc), exc.code) from exc
    order = OrderDraft.model_validate(
        {
            **payload.order.model_dump(),
            "reference": resolved.mapping.reference,
            "native_token": resolved.mapping.native_token,
        }
    )
    return await orders.preview(who, account_id, order)
