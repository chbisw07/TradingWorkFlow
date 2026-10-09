"""Owned operation tasks: public deadlines do not wait for shielded local close."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import anyio

from twf.integrations.mcp.contracts import Code, Failure


class Operation:
    def __init__(self, timeout: float) -> None:
        self.id = uuid4()
        self.loop = asyncio.get_running_loop()
        self.started = asyncio.get_running_loop().time()
        self.created_at = datetime.now(UTC)
        self.deadline = self.started + timeout
        self.deadline_at = self.created_at + timedelta(seconds=timeout)
        self.expired: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.timer = asyncio.get_running_loop().call_at(self.deadline, self.expire)
        self.cancel_scope: anyio.CancelScope | None = None
        self.retired = False
        self.configured = False
        self.close_failed = False
        self.outcome = "SUCCESS"
        self.provider_outcome: str | None = None
        self.terminal: str | None = None
        self.success_audit: Callable[[], None] | None = None
        self.finish: Callable[[Operation], Awaitable[None]] | None = None
        self.confirm: Callable[[Operation], Awaitable[None]] | None = None
        self.delivered = False
        self.auth_invalidation_required = False
        self.tool_name: str | None = None
        self.is_tool_operation = False

    def bound(self, timeout: float) -> None:
        self.deadline = min(self.deadline, self.started + timeout)
        self.deadline_at = self.created_at + timedelta(seconds=self.deadline - self.started)

        def reschedule() -> None:
            self.timer.cancel()
            self.timer = self.loop.call_at(self.deadline, self.expire)

        self.loop.call_soon_threadsafe(reschedule)
        self.check()

    def configure(self, timeout: float) -> None:
        # Before reading the registered provider, use the smallest possible budget.
        # Once identified, its absolute deadline still starts at invocation entry.
        self.check()
        if not self.configured:
            self.configured = True
            self.deadline = self.started + timeout
        self.bound(timeout)

    def expire(self) -> None:
        self.abort(Code.TIMEOUT)

    def abort(self, code: Code) -> None:
        self.retired = True
        if self.terminal is None:
            self.terminal = code.value
        self.outcome = self.terminal
        if not self.expired.done():
            self.expired.set_result(None)
        if self.cancel_scope:
            self.cancel_scope.cancel()

    def check(self) -> None:
        if self.retired or time.monotonic() >= self.deadline:
            raise Failure(Code.TIMEOUT)


operation: ContextVar[Operation | None] = ContextVar("mcp_operation", default=None)


class Operations:
    """Strong task ownership, bounded admission, shutdown drain and safe diagnostics.

    Durable permits are completed by the owning task only after all contexts unwind.
    A process loss leaves its permit unresolved, never automatically re-admissible.
    """

    def __init__(self) -> None:
        self.tasks: dict[Operation, asyncio.Task[Any]] = {}
        self.stopping = False

    async def run[T](self, timeout: float, work: Callable[[], Awaitable[T]]) -> T:
        parent = operation.get()
        if parent is not None:
            parent.bound(timeout)
            return await work()
        if self.stopping or len(self.tasks) >= 128:
            raise Failure(Code.UNAVAILABLE)
        scope = Operation(timeout)

        async def owned() -> T:
            binding = operation.set(scope)
            original_failure: Failure | None = None
            try:
                with anyio.CancelScope() as cancel_scope:
                    scope.cancel_scope = cancel_scope
                    try:
                        receipts = {
                            t for s, t in self.tasks.items() if s.delivered and not t.done()
                        }
                        if receipts:
                            await asyncio.wait(receipts)
                        scope.check()
                        result = await work()
                        scope.check()
                        return result
                    except Failure as exc:
                        original_failure = exc
                        if scope.terminal is None:
                            scope.outcome = exc.code.value
                        raise
                    except BaseException:
                        if scope.terminal is None:
                            scope.outcome = Code.UNAVAILABLE.value
                        raise
                raise Failure(Code.TIMEOUT)
            finally:
                # Retire before finalization: no cleanup callback can send with this permit.
                scope.retired = True
                try:
                    with anyio.CancelScope(shield=True):
                        if scope.finish:
                            await scope.finish(scope)
                finally:
                    operation.reset(binding)
                if scope.outcome != "SUCCESS":
                    if original_failure and original_failure.code.value == scope.outcome:
                        raise original_failure
                    raise Failure(Code(scope.outcome))

        task = asyncio.create_task(owned(), name=f"mcp-operation-{scope.id}")
        self.tasks[scope] = task

        def completed(done: asyncio.Task[Any]) -> None:
            scope.timer.cancel()
            if self.tasks.get(scope) is done:
                self.tasks.pop(scope, None)
            if not done.cancelled():
                done.exception()  # Consume late failures; no raw payload logging.

        task.add_done_callback(completed)

        def repair_finished() -> None:
            # The caller may win after commit but before task-result delivery.
            # Keep negative-only reconciliation owned and consume its failures.
            if task.done() and scope.finish is not None:

                async def reconcile() -> None:
                    assert scope.finish is not None
                    await scope.finish(scope)

                repair = asyncio.create_task(reconcile(), name=f"mcp-settle-{scope.id}")
                self.tasks[scope] = repair
                repair.add_done_callback(completed)

        try:
            waiters: set[asyncio.Future[Any]] = {task, scope.expired}
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
            # Check AFTER successful unwind and bookkeeping, not only on errors.
            if scope.expired.done() or asyncio.get_running_loop().time() >= scope.deadline:
                scope.expire()
                repair_finished()
                raise Failure(Code.TIMEOUT)
            result = task.result()
            # The durable SUCCESS candidate is known; receipt bookkeeping follows
            # this final caller boundary. Never clear its recovery marker earlier.
            scope.delivered = True
            scope.timer.cancel()
            if scope.confirm:

                async def confirm_delivery() -> None:
                    assert scope.confirm is not None
                    await scope.confirm(scope)
                    if scope.success_audit:
                        scope.success_audit()

                receipt = asyncio.create_task(confirm_delivery(), name=f"mcp-receipt-{scope.id}")
                self.tasks[scope] = receipt
                receipt.add_done_callback(completed)
            elif scope.success_audit:
                scope.success_audit()
            return result
        except asyncio.CancelledError:
            scope.abort(Code.CANCELLED)
            repair_finished()
            raise

    async def wait_receipts(self, timeout: float = 1.0) -> None:
        """Bounded local handoff before a new generation; never cancel receipt ownership."""
        receipts = {t for s, t in self.tasks.items() if s.delivered and not t.done()}
        if receipts:
            _, pending = await asyncio.wait(receipts, timeout=timeout)
            if pending:
                raise Failure(Code.STALE)

    async def drain(self, timeout: float = 1.0) -> bool:
        until = asyncio.get_running_loop().time() + timeout
        while any(not task.done() for task in self.tasks.values()):
            remaining = until - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            await asyncio.wait(set(self.tasks.values()), timeout=remaining)
        return True

    async def shutdown(self) -> None:
        self.stopping = True
        for scope in list(self.tasks):
            if not scope.delivered:
                scope.expire()
        await self.drain()
        # Any remaining tasks retain strong ownership until process exit. Their durable
        # permits are unresolved; another worker cannot infer drain from lease expiry.
