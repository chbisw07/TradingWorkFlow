"""Owner-visible OE-3 Queue contracts. Only READY and HELD are active in V1."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from twf.integrations.contracts import Contract
from twf.orders.contracts import OrderView


class QueueState(StrEnum):
    READY = "READY"
    HELD = "HELD"


class QueueEventType(StrEnum):
    QUEUE_ADMITTED = "QUEUE_ADMITTED"
    QUEUE_HELD = "QUEUE_HELD"
    QUEUE_RELEASED = "QUEUE_RELEASED"


class AdmitOrder(Contract):
    twf_order_id: UUID
    expected_order_version: int | None = Field(default=None, ge=1)


class QueueChange(Contract):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, min_length=1, max_length=512)


class QueueEntryView(Contract):
    queue_entry_id: UUID
    twf_order_id: UUID
    owner_id: UUID
    queue_state: QueueState
    version: int
    admitted_at: datetime
    updated_at: datetime
    created_by: str
    reason_code: str | None
    reason_message: str | None
    order: OrderView


class QueuePage(Contract):
    items: tuple[QueueEntryView, ...]
    next_cursor: str | None
    has_more: bool


class QueueEventView(Contract):
    event_id: UUID
    queue_entry_id: UUID
    twf_order_id: UUID
    sequence: int
    queue_version: int
    event_type: QueueEventType
    from_state: QueueState | None
    to_state: QueueState
    actor: str
    reason_code: str | None
    reason_message: str | None
    occurred_at: datetime
