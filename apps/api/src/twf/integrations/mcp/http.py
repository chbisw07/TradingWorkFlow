"""Exact destinations, public pinned addresses, bounded bytes and sanitized errors."""

import asyncio
import ipaddress
import logging
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar

import httpx2
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from twf.integrations.mcp.contracts import Code, Failure, ProviderConfig
from twf.integrations.mcp.lifecycle import operation

Fence = Callable[[], Awaitable[None]]
dispatch_fence: ContextVar[Fence | None] = ContextVar("mcp_dispatch_fence", default=None)

Resolver = Callable[[str], Awaitable[tuple[str, ...]]]


async def resolve(host: str) -> tuple[str, ...]:
    rows = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return tuple(str(row[4][0]) for row in rows)


class BudgetStream(httpx2.AsyncByteStream):
    def __init__(self, inner: httpx2.AsyncByteStream, budget: list[int]) -> None:
        self.inner, self.budget = inner, budget

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.inner:
            self.budget[0] -= len(chunk)
            if self.budget[0] < 0:
                raise Failure(Code.SCHEMA_MISMATCH)
            yield chunk

    async def aclose(self) -> None:
        await self.inner.aclose()


class SafeTransport(httpx2.AsyncBaseTransport):
    def __init__(
        self,
        urls: frozenset[str],
        limit: int,
        *,
        inner: httpx2.AsyncBaseTransport | None = None,
        resolver: Resolver = resolve,
        fence: Fence | None = None,
        deadline: float | None = None,
    ) -> None:
        self.urls, self.resolver = urls, resolver
        self.fence, self.deadline = fence, deadline
        self.operation = operation.get()
        self.retired = False
        self.closed = False
        self.failure: Failure | None = None
        self.session_id: str | None = None
        self.inner = inner or httpx2.AsyncHTTPTransport(trust_env=False, retries=0)
        self.budget = [limit]
        self.requests_left = 24

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if self.operation is not None:
            self.operation.check()
        if self.retired:
            raise Failure(Code.STALE)
        if str(request.url) not in self.urls or self.requests_left <= 0:
            raise Failure(Code.DENIED)
        self.requests_left -= 1
        host = request.url.host
        addresses = await self.resolver(host)
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise Failure(Code.DENIED)
        # Resolve once and connect to that exact public address; preserve TLS SNI/Host.
        request.url = request.url.copy_with(host=addresses[0])
        request.headers["Host"] = host
        request.headers["Accept-Encoding"] = "identity"
        request.extensions["sni_hostname"] = host
        # DNS/preparation may suspend. Authority is checked after them, immediately
        # before handing credentials to the network transport, including SDK GETs.
        if self.deadline is not None and asyncio.get_running_loop().time() >= self.deadline:
            self.retired = True
            raise Failure(Code.TIMEOUT)
        if self.fence is not None:
            try:
                await self.fence()
            except Failure as exc:
                self.failure = exc
                self.retired = True
                raise
            except BaseException:
                self.retired = True
                raise
        if self.operation is not None:
            self.operation.check()
        if self.retired:
            raise self.failure or Failure(Code.STALE)
        if self.deadline is not None and asyncio.get_running_loop().time() >= self.deadline:
            self.retired = True
            raise Failure(Code.TIMEOUT)
        response = await self.inner.handle_async_request(request)
        self.session_id = response.headers.get("mcp-session-id", self.session_id)
        if response.headers.get("content-encoding", "identity") != "identity":
            await response.aclose()
            raise Failure(Code.SCHEMA_MISMATCH)
        if sum(len(k) + len(v) for k, v in response.headers.raw) > 16384:
            await response.aclose()
            raise Failure(Code.SCHEMA_MISMATCH)
        if response.status_code in (401, 403, 429) or 300 <= response.status_code < 400:
            status = response.status_code
            retry = response.headers.get("retry-after", "")
            await response.aclose()
            if status == 429:
                raise Failure(
                    Code.RATE_LIMITED,
                    min(int(retry), 3600)
                    if retry.isascii() and retry.isdigit() and len(retry) <= 6
                    else None,
                )
            raise Failure(Code.AUTH_REQUIRED if status in (401, 403) else Code.DENIED)
        assert isinstance(response.stream, httpx2.AsyncByteStream)
        response.stream = BudgetStream(response.stream, self.budget)
        return response

    async def aclose(self) -> None:
        self.retired = True
        if not self.closed:
            try:
                await self.inner.aclose()
                self.closed = True
            except BaseException:
                if self.operation is not None:
                    self.operation.close_failed = True
                raise


class HTTPFactory:
    def __init__(
        self,
        inner_factory: Callable[[], httpx2.AsyncBaseTransport] | None = None,
        resolver: Resolver = resolve,
    ) -> None:
        self.inner_factory, self.resolver = inner_factory, resolver

    def client(
        self,
        config: ProviderConfig,
        urls: frozenset[str],
        headers: dict[str, str],
        *,
        fence: Fence | None = None,
        deadline: float | None = None,
    ) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=SafeTransport(
                urls,
                config.max_response_bytes,
                inner=self.inner_factory() if self.inner_factory else None,
                resolver=self.resolver,
                fence=fence or dispatch_fence.get(),
                deadline=deadline,
            ),
            timeout=config.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            headers=headers,
        )


def suppress_library_logs() -> None:
    # SDK debug/error logs can contain remote payloads/session IDs. TWF emits only
    # normalized operation metadata. Apply at composition, not import time.
    for name in ("mcp", "httpx2", "httpcore2"):
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False


def mapped(error: BaseException) -> Failure:
    if isinstance(error, Failure):
        return error
    if isinstance(error, BaseExceptionGroup):
        for item in error.exceptions:
            failure = mapped(item)
            if failure.code != Code.UNAVAILABLE:
                return failure
    if isinstance(error, MCPError):
        return Failure(
            {
                -32700: Code.SCHEMA_MISMATCH,
                -32600: Code.SCHEMA_MISMATCH,
                -32601: Code.TOOL_NOT_FOUND,
                -32602: Code.INVALID_ARGUMENTS,
            }.get(error.code, Code.UNAVAILABLE)
        )
    if isinstance(error, (ValidationError, ValueError)):
        return Failure(Code.SCHEMA_MISMATCH)
    if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
        return Failure(Code.TIMEOUT)
    return Failure(Code.UNAVAILABLE)
