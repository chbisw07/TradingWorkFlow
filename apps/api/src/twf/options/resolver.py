"""Exact option resolution from a broker instrument master without symbol parsing."""

from collections.abc import Iterable
from datetime import UTC, date, datetime

from twf.brokers.contracts import Instrument
from twf.options.contracts import (
    BrokerOptionMapping,
    OptionContract,
    OptionContractRequest,
    OptionType,
    ResolvedOption,
    UnderlyingType,
    option_contract_id,
    strike_text,
)


class OptionResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _contract(item: Instrument, today: date) -> OptionContract:
    if item.kind not in ("CE", "PE") or not item.underlying or not item.expiry:
        raise OptionResolutionError("OPTION_CONTRACT_INVALID", "Option identity is incomplete.")
    try:
        expiry = date.fromisoformat(item.expiry)
    except ValueError as exc:
        raise OptionResolutionError("OPTION_EXPIRY_INVALID", "Option expiry is invalid.") from exc
    if item.strike is None or item.strike <= 0:
        raise OptionResolutionError("OPTION_STRIKE_INVALID", "Option strike is invalid.")
    if (
        not item.lot_size
        or item.lot_size <= 0
        or item.lot_size != item.lot_size.to_integral_value()
    ):
        raise OptionResolutionError("OPTION_LOT_SIZE_INVALID", "Option lot size is unavailable.")
    if not item.tick_size or item.tick_size <= 0:
        raise OptionResolutionError("OPTION_TICK_SIZE_INVALID", "Option tick size is unavailable.")
    option_type = OptionType(item.kind)
    canonical_id = option_contract_id(
        item.exchange, item.underlying, expiry, item.strike, option_type
    )
    active = expiry >= today and item.is_active is not False
    return OptionContract(
        canonical_id=canonical_id,
        exchange=item.exchange,
        segment=item.segment or "NFO-OPT",
        underlying_symbol=item.underlying,
        underlying_type=UnderlyingType(item.underlying_type or "UNKNOWN"),
        expiry=expiry,
        strike=item.strike,
        option_type=option_type,
        lot_size=int(item.lot_size),
        display_symbol=(
            f"{item.underlying.upper()} {expiry.strftime('%d-%b-%Y').upper()} "
            f"{strike_text(item.strike)} {option_type.value}"
        ),
        tick_size=item.tick_size,
        freeze_quantity=item.freeze_quantity,
        contract_multiplier=item.contract_multiplier,
        currency=item.currency or "INR",
        is_active=active,
        last_trading_date=(
            date.fromisoformat(item.last_trading_date) if item.last_trading_date else expiry
        ),
    )


class OptionResolver:
    def __init__(
        self,
        instruments: Iterable[Instrument],
        *,
        provider: str,
        today: date,
        resolved_at: datetime | None = None,
        master_version: str | None = None,
    ) -> None:
        self.instruments = tuple(instruments)
        self.provider = provider
        self.today = today
        self.resolved_at = resolved_at or datetime.now(UTC)
        self.master_version = master_version

    def contracts(self, *, include_expired: bool = False) -> tuple[OptionContract, ...]:
        result: dict[str, OptionContract] = {}
        for item in self.instruments:
            if item.kind not in ("CE", "PE"):
                continue
            contract = _contract(item, self.today)
            if include_expired or contract.is_active:
                result[contract.canonical_id] = contract
        return tuple(
            sorted(
                result.values(),
                key=lambda x: (x.underlying_symbol, x.expiry, x.strike, x.option_type),
            )
        )

    def resolve(self, request: OptionContractRequest) -> ResolvedOption:
        matches: list[tuple[OptionContract, Instrument]] = []
        for item in self.instruments:
            if item.kind not in ("CE", "PE"):
                continue
            contract = _contract(item, self.today)
            if (
                contract.exchange == request.exchange
                and contract.underlying_symbol == request.underlying_symbol
                and contract.expiry == request.expiry
                and contract.strike == request.strike
                and contract.option_type == request.option_type
            ):
                matches.append((contract, item))
        if not matches:
            raise OptionResolutionError(
                "OPTION_CONTRACT_NOT_FOUND", "The exact listed option contract was not found."
            )
        contract, item = matches[0]
        if len(matches) != 1 or not item.native_token or not item.reference:
            raise OptionResolutionError(
                "BROKER_INSTRUMENT_UNAVAILABLE",
                "The broker has no exact execution mapping for this option contract.",
            )
        if not contract.is_active or contract.expiry < self.today:
            raise OptionResolutionError("OPTION_EXPIRED", "The selected option has expired.")
        return ResolvedOption(
            contract=contract,
            mapping=BrokerOptionMapping(
                provider=self.provider,
                canonical_id=contract.canonical_id,
                exchange=item.exchange,
                trading_symbol=item.symbol,
                native_token=item.native_token,
                reference=item.reference,
                lot_size=contract.lot_size,
                tick_size=contract.tick_size,
                resolved_at=self.resolved_at,
                master_version=self.master_version,
            ),
        )

    def describe_instrument(self, item: Instrument) -> ResolvedOption:
        contract = _contract(item, self.today)
        if not item.native_token or not item.reference:
            raise OptionResolutionError(
                "BROKER_INSTRUMENT_UNAVAILABLE",
                "The broker has no exact execution mapping for this option contract.",
            )
        return ResolvedOption(
            contract=contract,
            mapping=BrokerOptionMapping(
                provider=self.provider,
                canonical_id=contract.canonical_id,
                exchange=item.exchange,
                trading_symbol=item.symbol,
                native_token=item.native_token,
                reference=item.reference,
                lot_size=contract.lot_size,
                tick_size=contract.tick_size,
                resolved_at=self.resolved_at,
                master_version=self.master_version,
            ),
        )

    def resolve_instrument(self, item: Instrument) -> ResolvedOption:
        contract = _contract(item, self.today)
        return self.resolve(
            OptionContractRequest(
                exchange=contract.exchange,
                underlying_symbol=contract.underlying_symbol,
                expiry=contract.expiry,
                strike=contract.strike,
                option_type=contract.option_type,
            )
        )

    def enrich(self, item: Instrument, *, require_active: bool = True) -> Instrument:
        resolved = (
            self.resolve_instrument(item) if require_active else self.describe_instrument(item)
        )
        contract = resolved.contract
        return item.model_copy(
            update={
                "canonical_id": contract.canonical_id,
                "underlying_type": contract.underlying_type.value,
                "option_type": contract.option_type.value,
                "currency": contract.currency,
                "is_active": contract.is_active,
                "last_trading_date": contract.last_trading_date.isoformat()
                if contract.last_trading_date
                else None,
                "freeze_quantity": contract.freeze_quantity,
                "contract_multiplier": contract.contract_multiplier,
            }
        )
