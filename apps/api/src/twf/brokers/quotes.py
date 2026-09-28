"""Ephemeral, bounded exact-contract quote reads; no quote database or order authority."""

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from twf.brokers.contracts import BrokerFailure, Credentials, Instrument
from twf.brokers.order_service import OrderService
from twf.brokers.service import BrokerService, Principal, stale


class QuoteIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = Field(min_length=1, max_length=200)
    native_token: str = Field(pattern=r"^[0-9]{1,20}$")


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruments: list[QuoteIdentity] = Field(min_length=1, max_length=30)


class Quote(QuoteIdentity):
    price: Decimal | None


class QuoteBatch(BaseModel):
    received_at: datetime
    quotes: list[Quote]


@runtime_checkable
class QuoteAdapter(Protocol):
    async def execution_catalog(self, credentials: Credentials) -> list[Instrument]: ...
    async def quote(
        self, credentials: Credentials, instruments: list[Instrument]
    ) -> list[Quote]: ...


async def read_quotes(
    broker: BrokerService, who: Principal, account_id: UUID, query: QuoteRequest
) -> QuoteBatch:
    account, credentials = await asyncio.to_thread(broker.capture, who, account_id)
    adapter = broker.adapter
    if not isinstance(adapter, QuoteAdapter):
        raise BrokerFailure("QUOTES_UNAVAILABLE", "Quotes are unavailable.", 503)
    started = time.monotonic()
    deadline = min(3.0, broker.settings.broker_deadline_seconds)
    try:
        async with asyncio.timeout(deadline):
            catalog = await adapter.execution_catalog(credentials)
            # Resolve the reference AND token; never accept client-supplied display symbols.
            identities = {(x.reference, x.native_token) for x in query.instruments}
            items = [OrderService.resolve(catalog, ref, token) for ref, token in sorted(identities)]
            quotes = await adapter.quote(credentials, items)
            if time.monotonic() - started >= deadline:
                raise TimeoutError
            received = datetime.now(UTC)
    except TimeoutError:
        raise BrokerFailure("PROVIDER_TIMEOUT", "Broker quote request timed out.", 504) from None
    current, _ = await asyncio.to_thread(broker.capture, who, account_id)
    if current.generation != account.generation:
        raise stale()
    # Do not advance account/portfolio snapshot freshness just because a quote was read.
    return QuoteBatch(received_at=received, quotes=quotes)
