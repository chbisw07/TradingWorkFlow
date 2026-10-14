"""OE-1 state ownership. Queue and broker authority have no implementation here."""

from twf.orders.contracts import OrderState
from twf.orders.errors import OrderError, OrderErrorCode

QUEUE_STATES = frozenset({OrderState.QUEUED, OrderState.SUBMITTING})
BROKER_STATES = frozenset(
    {OrderState.BROKER_ACCEPTED, OrderState.PARTIALLY_FILLED, OrderState.FILLED}
)
TERMINAL_STATES = frozenset(
    {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
        OrderState.FAILED,
    }
)

# Only domain-owned transitions are enabled in OE-1. Future phases must add
# privileged queue/broker boundaries, not expand this public service method.
DOMAIN_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.DRAFT: frozenset({OrderState.READY, OrderState.CANCELLED, OrderState.REJECTED}),
    OrderState.READY: frozenset(
        {
            OrderState.BLOCKED,
            OrderState.REJECTED,
            OrderState.CANCELLED,
            OrderState.EXPIRED,
            OrderState.FAILED,
        }
    ),
    OrderState.BLOCKED: frozenset({OrderState.READY, OrderState.CANCELLED, OrderState.EXPIRED}),
}
REASON_REQUIRED = frozenset(
    {
        OrderState.BLOCKED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
        OrderState.FAILED,
    }
)


def check_domain_transition(current: OrderState, target: OrderState) -> None:
    if target in QUEUE_STATES | BROKER_STATES:
        raise OrderError(
            OrderErrorCode.INVALID_TRANSITION_AUTHORITY,
            "Queue and broker-truth states are unavailable to the order domain",
        )
    if current in TERMINAL_STATES:
        raise OrderError(OrderErrorCode.TERMINAL_ORDER, "Terminal orders cannot transition")
    if target not in DOMAIN_TRANSITIONS.get(current, frozenset()):
        raise OrderError(OrderErrorCode.INVALID_TRANSITION, f"{current} -> {target} is not allowed")
