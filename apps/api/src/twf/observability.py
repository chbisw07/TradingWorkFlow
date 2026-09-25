import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from twf.config.settings import Settings

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings

    def format(self, record: logging.LogRecord) -> str:
        # Explicit allowlist. Never serialize request bodies, headers, settings,
        # exception messages, or arbitrary extras.
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": self.settings.service_name,
            "environment": self.settings.environment,
            "event": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        for key in (
            "method",
            "route",
            "status_code",
            "duration_ms",
            "exception_type",
            "user_id",
            "service_id",
            "operation",
            "outcome",
            "operation_request_id",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)


def create_logger(settings: Settings) -> logging.Logger:
    """App-owned logger: no root reconfiguration or import-time handlers."""
    logger = logging.Logger("twf", level=settings.effective_log_level)
    logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(settings))
    logger.addHandler(handler)
    return logger
