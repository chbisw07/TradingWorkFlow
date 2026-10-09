"""Manual authority, immutable previews, one durable claim, and broker-truth recovery."""

import asyncio
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from twf.brokers.contracts import BrokerFailure, Instrument
from twf.brokers.order_contracts import (
    Capability,
    Choices,
    ExecutionAdapter,
    IntentView,
    OrderDraft,
    OrderSelection,
)
from twf.brokers.service import BrokerService, Principal, public, utc
from twf.infrastructure.order_intent import OrderIntent
from twf.options import OptionResolutionError, OptionResolver

UNKNOWN = "Submission status uncertain. Check Orders and refresh before placing another order."


def invalid(message: str, code: str = "ORDER_VALIDATION_FAILED") -> BrokerFailure:
    return BrokerFailure(code, message, 422)


def resolver(items: list[Instrument], *, resolved_at: datetime | None = None) -> OptionResolver:
    return OptionResolver(
        items,
        provider="zerodha",
        today=datetime.now(ZoneInfo("Asia/Kolkata")).date(),
        resolved_at=resolved_at,
    )


def normalize_equity_search(value: str) -> str:
    """Normalize search text only; never rewrite broker execution identity."""
    return re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def company_search_name(value: str) -> str:
    # Optional terminal Ltd/Limited makes common user/provider spellings equivalent.
    words = value.split()
    if len(words) > 1 and words[-1] in ("ltd", "limited"):
        words.pop()
    return " ".join(words)


def equity_relevance(item: Instrument, term: str) -> int | None:
    if not term:
        return None
    symbol = normalize_equity_search(item.symbol)
    name = company_search_name(normalize_equity_search(item.name or ""))
    name_term = company_search_name(term)
    if symbol == term:
        return 0
    if symbol.startswith(term):
        return 1
    if name == name_term:
        return 2
    if name.startswith(name_term):
        return 3
    # Every query word must match a word prefix in one field; no fuzzy matching.
    if any(
        all(any(word.startswith(part) for word in field.split()) for part in query.split())
        for field, query in ((symbol, term), (name, name_term))
    ):
        return 4
    if term in symbol or name_term in name:
        return 5
    return None


def executable(item: Instrument) -> bool:
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    return bool(
        item.native_token
        and item.tick_size
        and item.tick_size > 0
        and item.lot_size
        and item.lot_size > 0
        and item.lot_size == item.lot_size.to_integral_value()
        and (
            (
                item.kind == "EQ"
                and item.exchange in ("NSE", "BSE")
                and item.segment == item.exchange
                and item.lot_size == 1
            )
            or (
                item.exchange == "NFO"
                and item.kind in ("FUT", "CE", "PE")
                and item.segment == ("NFO-FUT" if item.kind == "FUT" else "NFO-OPT")
                and item.expiry
                and item.expiry >= today
                and item.underlying
                and (item.kind == "FUT" or (item.strike is not None and item.strike > 0))
            )
        )
    )


def view(row: OrderIntent) -> IntentView:
    order = OrderDraft.model_validate_json(row.order_json)
    item = Instrument.model_validate_json(row.instrument_json)
    option = None
    if item.kind in ("CE", "PE"):
        try:
            option = resolver([item], resolved_at=utc(row.created_at)).describe_instrument(item)
        except OptionResolutionError:
            option = None
    instrument_type = (
        "EQUITY" if item.kind == "EQ" else "FUTURE" if item.kind == "FUT" else "OPTION"
    )
    warnings = (
        [
            "Short option positions may have substantial or theoretically unbounded risk, "
            "depending on the contract and underlying."
        ]
        if instrument_type == "OPTION" and order.side == "SELL"
        else []
    )
    estimated_value = order.price * order.quantity if order.price is not None else None
    return IntentView.model_validate(
        dict(
            id=row.id,
            account_id=row.account_id,
            account_name=row.account_name,
            instrument=item,
            order=order,
            source=row.source,
            execution_authority=row.execution_authority,
            status=row.status,
            created_at=utc(row.created_at),
            expires_at=utc(row.expires_at),
            submitted_at=utc(row.submitted_at) if row.submitted_at else None,
            broker_order_id=row.broker_order_id,
            provider_status=row.provider_status,
            failure=row.failure,
            instrument_type=instrument_type,
            option_contract=option.contract if option else None,
            broker_option_mapping=option.mapping if option else None,
            warnings=warnings,
            estimated_value=estimated_value,
            premium_outlay=(
                estimated_value if instrument_type == "OPTION" and order.side == "BUY" else None
            ),
        )
    )


class OrderService:
    def __init__(self, broker: BrokerService) -> None:
        self.broker = broker

    def adapter(self) -> ExecutionAdapter:
        if not self.broker.settings.broker_manual_trading_enabled or not isinstance(
            self.broker.adapter, ExecutionAdapter
        ):
            raise BrokerFailure("MANUAL_TRADING_DISABLED", "Manual trading is not enabled.", 409)
        return self.broker.adapter

    def owned(self, db: Session, who: Principal, account_id: UUID, intent_id: UUID) -> OrderIntent:
        self.broker.owned(db, who, account_id)
        row = db.scalar(
            select(OrderIntent)
            .where(
                OrderIntent.id == intent_id,
                OrderIntent.account_id == account_id,
                OrderIntent.user_id == who.user_id,
            )
            .with_for_update()
        )
        if not row:
            raise BrokerFailure("ORDER_INTENT_NOT_FOUND", "Order intent not found.", 404)
        return row

    def list_intents(self, who: Principal, account_id: UUID) -> list[IntentView]:
        with self.broker.factory() as db:
            self.broker.owned(db, who, account_id)
            return [
                view(row)
                for row in db.scalars(
                    select(OrderIntent)
                    .where(
                        OrderIntent.account_id == account_id,
                        OrderIntent.user_id == who.user_id,
                        OrderIntent.status != "PREVIEWED",
                    )
                    .order_by(OrderIntent.created_at.desc(), OrderIntent.id)
                    .limit(50)
                )
            ]

    def get(self, who: Principal, account_id: UUID, intent_id: UUID) -> IntentView:
        with self.broker.factory() as db:
            return view(self.owned(db, who, account_id, intent_id))

    async def catalog(self, who: Principal, account_id: UUID) -> list[Instrument]:
        adapter = self.adapter()
        return (await self.broker.read(who, account_id, adapter.execution_catalog)).data

    async def capability(
        self, who: Principal, account_id: UUID, reference: str = "", native_token: str = ""
    ) -> Capability:
        # Return disabled status honestly without requiring a connected account.
        with self.broker.factory() as db:
            account = self.broker.owned(db, who, account_id)
            adapter = self.broker.adapter
            enabled = (
                public(account).state == "connected"
                and account.provider == "zerodha"
                and self.broker.settings.broker_manual_trading_enabled
                and isinstance(adapter, ExecutionAdapter)
            )
        broker_capabilities = (
            adapter.execution_capabilities() if isinstance(adapter, ExecutionAdapter) else None
        )
        if not enabled or not reference:
            if broker_capabilities:
                return Capability(enabled=enabled, broker=broker_capabilities)
            return Capability(enabled=enabled)
        item = self.resolve(await self.catalog(who, account_id), reference, native_token)
        return self.adapter().order_capability(item)

    @staticmethod
    def resolve(catalog: list[Instrument], reference: str, token: str) -> Instrument:
        items = [x for x in catalog if x.reference == reference and x.native_token == token]
        if len(items) != 1:
            code = (
                "BROKER_INSTRUMENT_UNAVAILABLE"
                if ":NFO:" in reference
                else "ORDER_VALIDATION_FAILED"
            )
            raise invalid(
                "The broker has no exact execution mapping for the selected contract."
                if code == "BROKER_INSTRUMENT_UNAVAILABLE"
                else "Select an executable contract from the current broker catalog.",
                code,
            )
        item = items[0]
        if item.kind in ("CE", "PE"):
            try:
                return resolver(items).enrich(item)
            except OptionResolutionError as exc:
                raise invalid(str(exc), exc.code) from exc
        if not executable(item):
            raise invalid("Select an executable contract from the current broker catalog.")
        return item

    async def choices(self, who: Principal, account_id: UUID, query: OrderSelection) -> Choices:
        items = [
            x
            for x in await self.catalog(who, account_id)
            if executable(x)
            and (
                x.kind == "EQ"
                if query.asset == "equity"
                else x.kind == "FUT"
                if query.asset == "futures"
                else x.kind in ("CE", "PE")
            )
        ]
        term = query.q.strip().casefold()
        underlyings = sorted(
            {x.underlying for x in items if x.underlying and term in x.underlying.casefold()}
        )
        if query.asset == "equity":
            term = normalize_equity_search(query.q)
            ranked: list[tuple[int, Instrument]] = []
            for item in items:
                if query.exchange != "BOTH" and item.exchange != query.exchange:
                    continue
                rank = equity_relevance(item, term)
                if rank is not None:
                    ranked.append((rank, item))
            # One authoritative ranking, before pagination, inside the exchange scope.
            ranked.sort(
                key=lambda pair: (
                    pair[0],
                    pair[1].symbol.casefold(),
                    pair[1].exchange,
                    pair[1].native_token or "",
                )
            )
            items = [item for _, item in ranked]
        else:
            items = [x for x in items if x.underlying == query.underlying]
        expiries = sorted({x.expiry for x in items if x.expiry})
        if query.asset != "equity":
            items = [x for x in items if x.expiry == query.expiry]
        option_types = sorted({x.kind for x in items if x.kind in ("CE", "PE")})
        if query.asset == "options":
            items = [x for x in items if x.kind == query.option_type]
        strikes = sorted({x.strike for x in items if x.strike is not None})
        if query.asset == "options":
            items = [x for x in items if x.strike == query.strike]
        start = (query.page - 1) * 30
        return Choices(
            underlyings=underlyings,
            expiries=expiries,
            option_types=option_types,
            strikes=strikes,
            instruments=[
                resolver([item]).enrich(item) if item.kind in ("CE", "PE") else item
                for item in items[start : start + 30]
            ],
            total=len(items),
            page=query.page,
        )

    def validate(self, item: Instrument, order: OrderDraft) -> None:
        capability = self.adapter().order_capability(item)
        rule = next((x for x in capability.order_types if x.name == order.order_type), None)
        if not capability.enabled or order.product not in capability.products or not rule:
            raise invalid("This product or order type is not supported for the selected contract.")
        if order.validity not in rule.validities or order.quantity > capability.max_quantity:
            raise invalid("Unsupported validity or quantity.")
        if item.kind in ("CE", "PE"):
            if order.side == "BUY" and not capability.broker.option_buy_supported:
                raise invalid("This broker does not support option buys.")
            if order.side == "SELL" and not capability.broker.option_sell_supported:
                raise invalid("This broker does not support option sells.")
            resolved = resolver([item]).resolve_instrument(item)
            if not resolved.contract.is_active:
                raise invalid("The selected option has expired.", "OPTION_EXPIRED")
            if (
                resolved.contract.freeze_quantity
                and order.quantity > resolved.contract.freeze_quantity
            ):
                raise invalid("Quantity exceeds the exchange freeze quantity.")
        if item.kind == "EQ":
            if order.lots is not None:
                raise invalid("Enter equity quantity in shares, not lots.")
        elif order.lots is None or order.quantity != order.lots * (item.lot_size or 0):
            raise invalid("Quantity must equal lots multiplied by the current contract lot size.")
        if rule.price_required != (order.price is not None):
            raise invalid("Price is required only for a price-bearing order type.")
        if rule.trigger_required != (order.trigger_price is not None):
            raise invalid("Trigger price is required only for a broker stop-limit order.")
        for price in (order.price, order.trigger_price):
            if price is not None and (not item.tick_size or price % item.tick_size != 0):
                raise invalid("Price must align with the contract tick size.")
        if (
            order.trigger_price is not None
            and order.price is not None
            and (
                (order.side == "BUY" and order.price < order.trigger_price)
                or (order.side == "SELL" and order.price > order.trigger_price)
            )
        ):
            raise invalid("Buy limit must be at or above trigger; sell limit at or below trigger.")

    async def preview(self, who: Principal, account_id: UUID, order: OrderDraft) -> IntentView:
        adapter = self.adapter()
        account, credentials = self.broker.capture(who, account_id)
        item = self.resolve(
            await self.broker.deadline(adapter.execution_catalog(credentials)),
            order.reference,
            order.native_token,
        )
        self.validate(item, order)
        now = datetime.now(UTC)

        def save(db: Session) -> IntentView:
            current = self.broker.owned(db, who, account_id)
            if (
                current.generation != account.generation
                or public(current).state != "connected"
                or current.provider != "zerodha"
                or not current.identity
            ):
                raise invalid("Connection changed. Reopen the order ticket.")
            row = OrderIntent(
                id=uuid4(),
                user_id=who.user_id,
                account_id=account_id,
                account_name=current.name,
                provider=current.provider,
                session_hash=who.session_hash,
                generation=current.generation,
                broker_identity=current.identity,
                instrument_json=item.model_dump_json(),
                order_json=order.model_dump_json(),
                source="BROKER_WORKSPACE",
                execution_authority="MANUAL_USER",
                tag=uuid4().hex[:20],
                status="PREVIEWED",
                created_at=now,
                expires_at=now + timedelta(minutes=5),
            )
            db.add(row)
            db.flush()
            return view(row)

        result = await self.broker.write(save)

        # Independent bounded optional estimates: neither failure blocks the order.
        async def cash() -> None:
            try:
                async with asyncio.timeout(2):
                    funds = await self.broker.adapter.get_funds(credentials)
                    result.available_cash = next(
                        (x.cash for x in funds if x.segment == "equity"), None
                    )
            except Exception:
                pass

        async def margin() -> None:
            try:
                async with asyncio.timeout(2):
                    result.estimated_margin = await adapter.estimate_margin(
                        credentials, item, order
                    )
                    if result.estimated_margin is not None:
                        result.margin_status = "AVAILABLE"
            except Exception:
                pass

        async def quote() -> None:
            try:
                async with asyncio.timeout(2):
                    result.reference_price = await adapter.reference_price(credentials, item)
            except Exception:
                pass

        await asyncio.gather(cash(), margin(), quote())
        effective_price = order.price or result.reference_price
        if effective_price is not None:
            result.estimated_value = effective_price * order.quantity
            if result.instrument_type == "OPTION" and order.side == "BUY":
                result.premium_outlay = result.estimated_value
        return result

    async def confirm(self, who: Principal, account_id: UUID, intent_id: UUID) -> IntentView:
        existing = self.get(who, account_id, intent_id)
        if existing.status != "PREVIEWED":
            return existing  # Retry observes the original attempt; never sends another order.
        adapter = self.adapter()
        account, credentials = self.broker.capture(who, account_id)
        item = self.resolve(
            await self.broker.deadline(adapter.execution_catalog(credentials)),
            existing.order.reference,
            existing.order.native_token,
        )
        self.validate(item, existing.order)
        if item != existing.instrument:
            raise invalid("Contract metadata changed. Create a new preview.")

        def claim(db: Session) -> tuple[IntentView, str | None]:
            row = self.owned(db, who, account_id, intent_id)
            if row.status != "PREVIEWED":
                return view(row), None
            current = self.broker.owned(db, who, account_id)
            if (
                row.session_hash != who.session_hash
                or row.generation != current.generation
                or account.generation != current.generation
                or public(current).state != "connected"
                or utc(row.expires_at) <= datetime.now(UTC)
            ):
                raise invalid("Preview expired or connection changed. Create a new preview.")
            row.status, row.submitted_at = "SUBMITTING", datetime.now(UTC)
            return view(row), row.tag

        claimed, tag = await self.broker.write(claim)
        if tag is None:
            return claimed
        # The claim transaction has COMMITTED before the only provider write.
        order_id: str | None = None
        failure: str | None = UNKNOWN
        status = "SUBMISSION_UNKNOWN"
        try:
            order_id = await self.broker.deadline(
                adapter.place_order(credentials, item, claimed.order, tag)
            )
            status, failure = "SUBMITTED", None
        except BrokerFailure as exc:
            if exc.code == "ORDER_REJECTED":
                status, failure = "BROKER_REJECTED", exc.message
        except Exception:
            # Never expose exception/provider bodies, and never retry this write.
            pass

        def finish(db: Session) -> IntentView:
            row = db.get(OrderIntent, intent_id, with_for_update=True)
            assert row is not None
            if row.status == "SUBMITTING":
                row.status, row.failure, row.broker_order_id = status, failure, order_id
            return view(row)

        try:
            return await self.broker.write(finish)
        except BrokerFailure:
            # Durable SUBMITTING remains recoverable after a lost DB acknowledgement.
            return claimed.model_copy(update={"status": "SUBMISSION_UNKNOWN", "failure": UNKNOWN})

    async def reconcile(self, who: Principal, account_id: UUID, intent_id: UUID) -> IntentView:
        existing = self.get(who, account_id, intent_id)
        if existing.status in ("PREVIEWED", "BROKER_REJECTED"):
            return existing
        account, credentials = self.broker.capture(who, account_id)
        with self.broker.factory() as db:
            row = self.owned(db, who, account_id, intent_id)
            if row.broker_identity != account.identity:
                raise invalid("Reconnect the original broker identity to check this order.")
            tag = row.tag
        orders = await self.broker.deadline(self.broker.adapter.get_orders(credentials))
        # The tag is a correlation aid, not provider idempotency. Require exact terms too.
        matches = [
            x
            for x in orders
            if x.tag == tag
            and x.instrument.reference == existing.instrument.reference
            and x.side == existing.order.side
            and x.quantity == existing.order.quantity
            and x.product == existing.order.product
            and x.kind == existing.order.order_type
            and (x.price or Decimal(0)) == (existing.order.price or Decimal(0))
            and x.validity == existing.order.validity
            and (x.trigger_price or Decimal(0)) == (existing.order.trigger_price or Decimal(0))
        ]
        if existing.broker_order_id:
            # Once acknowledged, ID in this owned broker account is authoritative,
            # including manual modifications/cancellations made later in Kite.
            matches = [x for x in orders if x.id == existing.broker_order_id]

        def save(db: Session) -> IntentView:
            row = self.owned(db, who, account_id, intent_id)
            current = self.broker.owned(db, who, account_id)
            if current.generation != account.generation:
                raise invalid("Connection changed. Refresh to check the order.")
            if len(matches) == 1 and (
                not row.broker_order_id or row.broker_order_id == matches[0].id
            ):
                row.broker_order_id, row.provider_status = matches[0].id, matches[0].status
                row.status, row.failure = "SUBMITTED", None
            elif (
                row.status == "SUBMITTING"
                and row.submitted_at
                and (
                    datetime.now(UTC) - utc(row.submitted_at)
                    > timedelta(seconds=self.broker.settings.broker_deadline_seconds + 5)
                )
            ):
                row.status, row.failure = "SUBMISSION_UNKNOWN", UNKNOWN
            # Absence (including next trading day) NEVER authorizes a new attempt.
            return view(row)

        return await self.broker.write(save)
