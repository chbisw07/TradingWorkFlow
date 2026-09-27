"""Kite GET-only portfolio boundary; DTOs never leave this adapter."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal, DecimalException
from time import monotonic
from typing import Annotated

import httpx
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
)

from twf.brokers.portfolio_contracts import (
    DatasetName,
    NativeIdentity,
    NativeObservation,
    PortfolioFailure,
    ProviderObservation,
)
from twf.secrets import SecretValue

Label = Annotated[
    str, StringConstraints(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f]+$")
]


def bounded_decimal(value: object) -> Decimal:
    # Validate the original exponent before Pydantic/context normalization can
    # underflow an extreme provider number into an apparently legitimate zero.
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Invalid numeric observation")
    try:
        number = Decimal(str(value))
    except DecimalException:
        raise ValueError("Invalid numeric observation") from None
    if not number.is_finite() or number.copy_abs() > Decimal("1e18"):
        raise ValueError("Invalid numeric observation")
    exponent = number.as_tuple().exponent
    if number and isinstance(exponent, int) and exponent < -12:
        raise ValueError("Unsupported numeric precision")
    return number if number else Decimal(0)


Number = Annotated[
    Decimal, BeforeValidator(bounded_decimal), Field(allow_inf_nan=False, ge=-1e18, le=1e18)
]
Positive = Annotated[
    Decimal, BeforeValidator(bounded_decimal), Field(allow_inf_nan=False, ge=0, le=1e18)
]
Quantity = Annotated[int, Field(strict=True, ge=-(2**63), lt=2**63)]


class Financing(BaseModel):
    quantity: Quantity | None = None
    value: Number | None = None


class KiteRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    instrument_token: int = Field(strict=True, gt=0, le=2**32 - 1)
    tradingsymbol: Label
    exchange: Label
    product: Label
    quantity: Quantity
    average_price: Positive | None = None
    last_price: Positive | None = None
    close_price: Positive | None = None
    pnl: Number | None = None
    used_quantity: Quantity | None = None
    t1_quantity: Quantity | None = None
    realised_quantity: Quantity | None = None
    authorised_quantity: Quantity | None = None
    collateral_quantity: Quantity | None = None
    collateral_type: Annotated[str, StringConstraints(max_length=64)] | None = None
    mtf: Financing | None = None
    day_change: Number | None = None
    day_change_percentage: Number | None = None
    overnight_quantity: Quantity | None = None
    buy_quantity: Quantity | None = None
    sell_quantity: Quantity | None = None
    buy_price: Positive | None = None
    sell_price: Positive | None = None
    realised: Number | None = None
    unrealised: Number | None = None
    multiplier: Positive | None = None

    def normalize(self, dataset: DatasetName) -> NativeObservation:
        def number(value: int | None) -> Decimal | None:
            return Decimal(value) if value is not None else None

        quantity = Decimal(self.quantity)
        value = (
            quantity * self.last_price
            if dataset == "holdings" and self.last_price is not None
            else None
        )
        cost = quantity * self.average_price if self.average_price is not None else None
        return NativeObservation(
            instrument=NativeIdentity(
                native_id=str(self.instrument_token),
                symbol=self.tradingsymbol,
                exchange=self.exchange,
            ),
            product=self.product,
            product_known=self.product in {"CNC", "MIS", "NRML", "CO", "BO", "MTF"},
            quantity=quantity,
            average_price=self.average_price,
            last_price=self.last_price,
            close_price=self.close_price,
            pnl=self.pnl,
            current_value=value,
            pnl_percent=self.pnl / cost * 100
            if dataset == "holdings" and self.pnl is not None and cost and cost > 0
            else None,
            used_quantity=number(self.used_quantity),
            available_quantity=quantity - self.used_quantity
            if dataset == "holdings"
            and self.used_quantity is not None
            and 0 <= self.used_quantity <= quantity
            else None,
            unsettled_quantity=number(self.t1_quantity),
            settled_quantity=number(self.realised_quantity),
            authorised_quantity=number(self.authorised_quantity),
            collateral_quantity=number(self.collateral_quantity),
            collateral_type=self.collateral_type or None,
            financed_quantity=number(self.mtf.quantity) if self.mtf else None,
            financed_value=self.mtf.value if self.mtf else None,
            day_change=self.day_change,
            day_change_percent=self.day_change_percentage,
            overnight_quantity=number(self.overnight_quantity),
            buy_quantity=number(self.buy_quantity),
            sell_quantity=number(self.sell_quantity),
            buy_average=self.buy_price,
            sell_average=self.sell_price,
            realized_pnl=self.realised,
            unrealized_pnl=self.unrealised,
            multiplier=self.multiplier,
        )


class KitePortfolioClient:
    TOTAL_DEADLINE_SECONDS = 8.0
    MAX_BYTES = 4 * 1024 * 1024
    MAX_ROWS = 10000

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    @staticmethod
    def check(deadline: float) -> None:
        if monotonic() >= deadline:
            raise PortfolioFailure("TIMEOUT")

    def read(self, dataset: DatasetName, api_key: str, token: SecretValue) -> ProviderObservation:
        if dataset not in ("holdings", "positions"):
            raise PortfolioFailure("INVALID_RESPONSE")
        deadline = monotonic() + self.TOTAL_DEADLINE_SECONDS
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._fetch(dataset, api_key, token, deadline))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    async def _fetch(
        self, dataset: DatasetName, api_key: str, token: SecretValue, deadline: float
    ) -> ProviderObservation:
        try:
            async with asyncio.timeout(max(0, deadline - monotonic())):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=httpx.Timeout(5.0),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "GET",
                        f"https://api.kite.trade/portfolio/{dataset}",
                        headers={
                            "X-Kite-Version": "3",
                            "Authorization": f"token {api_key}:{token.reveal()}",
                            "Accept": "application/json",
                            "Accept-Encoding": "identity",
                        },
                    ) as response:
                        if response.status_code in (401, 403):
                            raise PortfolioFailure("AUTH_EXPIRED")
                        if response.status_code == 429:
                            raise PortfolioFailure("RATE_LIMITED")
                        if response.status_code != 200:
                            raise PortfolioFailure("UNAVAILABLE")
                        # Reject unexpected encoding: prevents unbounded decompression.
                        if response.headers.get("content-encoding", "identity") != "identity":
                            raise PortfolioFailure("INVALID_RESPONSE")
                        body = bytearray()
                        async for chunk in response.aiter_raw():
                            self.check(deadline)
                            if len(body) + len(chunk) > self.MAX_BYTES:
                                raise PortfolioFailure("TOO_LARGE")
                            body.extend(chunk)
                        return self.parse(bytes(body), dataset, deadline)
        except (TimeoutError, httpx.TimeoutException):
            raise PortfolioFailure("TIMEOUT") from None
        except httpx.HTTPError:
            self.check(deadline)
            raise PortfolioFailure("UNAVAILABLE") from None

    def parse(self, body: bytes, dataset: DatasetName, deadline: float) -> ProviderObservation:
        self.check(deadline)
        try:
            payload = json.loads(body, parse_float=Decimal)
            if not isinstance(payload, dict) or payload.get("status") != "success":
                raise ValueError()
            data = payload["data"]
            groups = [data] if dataset == "holdings" else [data["net"], data["day"]]
            if any(not isinstance(group, list) for group in groups):
                raise ValueError()
            total = sum(len(group) for group in groups)
            if total > self.MAX_ROWS:
                raise PortfolioFailure("TOO_LARGE")
            normalized = []
            rejected = 0
            for group in groups:
                rows = []
                seen = set()
                for value in group:
                    self.check(deadline)
                    try:
                        row = KiteRow.model_validate(value)
                        key = (row.instrument_token, row.exchange, row.tradingsymbol, row.product)
                        if key in seen or (dataset == "holdings" and row.quantity < 0):
                            raise ValueError()
                        seen.add(key)
                        rows.append(row.normalize(dataset))
                    except (ValidationError, ValueError):
                        rejected += 1
                normalized.append(tuple(rows))
            self.check(deadline)
            return ProviderObservation(
                rows=normalized[0],
                activity_rows=normalized[1] if dataset == "positions" else (),
                received_at=datetime.now(UTC),
                total_rows=total,
                rejected_rows=rejected,
            )
        except (ValueError, KeyError, TypeError, RecursionError):
            self.check(deadline)
            raise PortfolioFailure("INVALID_RESPONSE") from None
