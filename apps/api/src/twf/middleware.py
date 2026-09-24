import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from twf.api.errors import unexpected_error
from twf.observability import request_id_context

_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, logger: logging.Logger) -> None:
        self.app = app
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        values = Headers(scope=scope).getlist("x-request-id")
        candidate = values[0].strip() if len(values) == 1 else ""
        request_id = candidate if _REQUEST_ID.fullmatch(candidate) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        started = perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            try:
                self.logger.info(
                    "request_completed",
                    extra={
                        "method": scope["method"],
                        "route": getattr(scope.get("route"), "path", "unmatched"),
                        "status_code": status,
                        "duration_ms": round((perf_counter() - started) * 1000, 3),
                    },
                )
            finally:
                request_id_context.reset(token)


class ErrorBoundaryMiddleware:
    """Catch before Starlette's outer error layer so CORS/ID wrap 500s too."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def track_start(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track_start)
        except Exception as exc:
            if started:
                # Cannot replace an already-started response. Future streaming
                # endpoints must own mid-stream errors; none exist in this shell.
                raise
            response = await unexpected_error(Request(scope), exc)
            await response(scope, receive, send)
