"""Owner-visible Queue contracts with admission snapshots and OE-4 dispatch outcomes."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from twf.integrations.contracts import Contract
from twf.orders.contracts import OrderView


class QueueState(StrEnum):
    READY = "READY"
    HELD = "HELD"
    DISPATCHING = "DISPATCHING"
    DISPATCHED = "DISPATCHED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    CANCELLED = "CANCELLED"


class QueueEventType(StrEnum):
    QUEUE_ADMITTED = "QUEUE_ADMITTED"
    QUEUE_HELD = "QUEUE_HELD"
    QUEUE_RELEASED = "QUEUE_RELEASED"
    DISPATCH_CLAIMED = "DISPATCH_CLAIMED"
    DISPATCH_SUBMITTED = "DISPATCH_SUBMITTED"
    DISPATCH_FAILED = "DISPATCH_FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"


class AdmitOrder(Contract):
    broker_account_id: UUID | None = None
    twf_order_id: UUID
    expected_order_version: int | None = Field(default=None, ge=1)


class QueueChange(Contract):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, min_length=1, max_length=512)


class QueueEntryView(Contract):
    effective_dispatch_mode: Literal["MANUAL", "AUTO"] = "MANUAL"
    broker_account_id: UUID | None = None
    policy_version: int = 0
    source_kind: str = "MANUAL"
    source_reference: str | None = None
    public_queue_id: str | None = None
    public_order_id: str | None = None
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
    details: dict[str, Any] = Field(default_factory=dict)
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


class PolicyChange(Contract):
    current_dispatch_mode: Literal["MANUAL", "AUTO"]
    expected_version: int = Field(ge=1)


class PolicyView(Contract):
    previous_dispatch_mode: Literal["MANUAL", "AUTO"] | None = None
    execution_enabled: bool = False
    broker_account_id: UUID
    current_dispatch_mode: Literal["MANUAL", "AUTO"]
    version: int
    updated_at: datetime
