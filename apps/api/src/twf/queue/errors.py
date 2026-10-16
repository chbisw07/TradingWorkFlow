"""Typed Queue errors; database and provider details stay at the boundary."""

from enum import StrEnum


class QueueErrorCode(StrEnum):
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_CURSOR = "INVALID_CURSOR"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    QUEUE_ENTRY_NOT_FOUND = "QUEUE_ENTRY_NOT_FOUND"
    ORDER_NOT_READY = "ORDER_NOT_READY"
    QUEUE_VERSION_CONFLICT = "QUEUE_VERSION_CONFLICT"
    ORDER_VERSION_CONFLICT = "ORDER_VERSION_CONFLICT"
    INVALID_QUEUE_TRANSITION = "INVALID_QUEUE_TRANSITION"
    QUEUE_INVARIANT_FAILURE = "QUEUE_INVARIANT_FAILURE"
    RETRYABLE_CONCURRENCY_CONFLICT = "RETRYABLE_CONCURRENCY_CONFLICT"


class QueueError(ValueError):
    def __init__(self, code: QueueErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)
