"""Stable OE-1 failure categories for future application/API adapters."""

from enum import StrEnum


class OrderErrorCode(StrEnum):
    UNAUTHORIZED = "UNAUTHORIZED"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    INVALID_ORDER = "INVALID_ORDER"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    INVALID_TRANSITION_AUTHORITY = "INVALID_TRANSITION_AUTHORITY"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    RETRYABLE_CONCURRENCY_CONFLICT = "RETRYABLE_CONCURRENCY_CONFLICT"
    IMMUTABLE_FIELD = "IMMUTABLE_FIELD"
    TERMINAL_ORDER = "TERMINAL_ORDER"


class OrderError(ValueError):
    def __init__(self, code: OrderErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)
