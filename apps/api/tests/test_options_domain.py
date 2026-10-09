"""O1 provider-neutral option identity and exact mapping tests."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from twf.brokers.contracts import Instrument
from twf.options import (
    OptionContract,
    OptionContractRequest,
    OptionResolutionError,
    OptionResolver,
    OptionType,
    UnderlyingType,
)
from twf.options.contracts import option_contract_id


def option(
    *,
    underlying: str = "NIFTY",
    expiry: date | None = None,
    strike: str = "25000",
    kind: str = "CE",
    token: str | None = "123",
    symbol: str = "NIFTY26DEC25000CE",
    lot: str = "75",
) -> Instrument:
    expiry = expiry or date.today() + timedelta(days=30)
    return Instrument(
        symbol=symbol,
        exchange="NFO",
        reference=f"ZERODHA:NFO:{symbol}",
        native_token=token,
        name=underlying,
        underlying=underlying,
        expiry=expiry.isoformat(),
        strike=Decimal(strike),
        kind=kind,
        segment="NFO-OPT",
        lot_size=Decimal(lot),
        tick_size=Decimal("0.05"),
    )


@pytest.mark.parametrize(
    ("underlying_type", "kind"),
    [
        (UnderlyingType.INDEX, "CE"),
        (UnderlyingType.INDEX, "PE"),
        (UnderlyingType.EQUITY, "CE"),
        (UnderlyingType.EQUITY, "PE"),
    ],
)
def test_contract_identity_is_structural_and_provider_neutral(
    underlying_type: UnderlyingType, kind: str
) -> None:
    expiry = date.today() + timedelta(days=30)
    contract = OptionContract(
        canonical_id=option_contract_id("NFO", "NIFTY", expiry, Decimal("25000"), OptionType(kind)),
        exchange="nfo",
        segment="nfo-opt",
        underlying_symbol="nifty",
        underlying_type=underlying_type,
        expiry=expiry,
        strike=Decimal("25000.00"),
        option_type=OptionType(kind),
        lot_size=75,
        display_symbol=f"NIFTY {expiry.isoformat()} 25000 {kind}",
        tick_size=Decimal("0.05"),
    )
    assert contract.canonical_id == f"NFO:NIFTY:{expiry.isoformat()}:25000:{kind}"
    assert "ZERODHA" not in contract.model_dump_json()


def test_ce_pe_aliases_are_typed_and_identity_rejects_mismatch() -> None:
    assert OptionType("CALL") is OptionType.CE
    assert OptionType("PUT") is OptionType.PE
    expiry = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError, match="canonical_id"):
        OptionContract(
            canonical_id="wrong",
            exchange="NFO",
            segment="NFO-OPT",
            underlying_symbol="NIFTY",
            expiry=expiry,
            strike=Decimal("25000"),
            option_type=OptionType.CE,
            lot_size=75,
            display_symbol="NIFTY option",
            tick_size=Decimal("0.05"),
        )


def test_exact_resolver_distinguishes_expiry_strike_and_right() -> None:
    first = date.today() + timedelta(days=30)
    second = date.today() + timedelta(days=60)
    catalog = [
        option(expiry=first, kind="CE", token="1", symbol="FIRSTCE"),
        option(expiry=first, kind="PE", token="2", symbol="FIRSTPE"),
        option(expiry=second, kind="CE", token="3", symbol="SECONDCE"),
        option(expiry=first, strike="25100", kind="CE", token="4", symbol="OTHERSTRIKE"),
    ]
    resolver = OptionResolver(
        catalog,
        provider="zerodha",
        today=date.today(),
        resolved_at=datetime.now(UTC),
    )
    resolved = resolver.resolve(
        OptionContractRequest(
            exchange="NFO",
            underlying_symbol="NIFTY",
            expiry=first,
            strike=Decimal("25000"),
            option_type=OptionType.CE,
        )
    )
    assert resolved.mapping.trading_symbol == "FIRSTCE"
    assert resolved.mapping.native_token == "1"
    assert resolved.contract.option_type is OptionType.CE
    assert resolved.contract.lot_size == 75

    with pytest.raises(OptionResolutionError) as missing:
        resolver.resolve(
            OptionContractRequest(
                exchange="NFO",
                underlying_symbol="NIFTY",
                expiry=first,
                strike=Decimal("25200"),
                option_type=OptionType.CE,
            )
        )
    assert missing.value.code == "OPTION_CONTRACT_NOT_FOUND"


def test_expired_and_missing_broker_mapping_fail_closed() -> None:
    expired = option(expiry=date.today() - timedelta(days=1), token="8", symbol="EXPIRED")
    with pytest.raises(OptionResolutionError) as stale:
        OptionResolver([expired], provider="zerodha", today=date.today()).resolve_instrument(
            expired
        )
    assert stale.value.code == "OPTION_EXPIRED"

    unmapped = option(token=None, symbol="UNMAPPED")
    with pytest.raises(OptionResolutionError) as missing:
        OptionResolver([unmapped], provider="zerodha", today=date.today()).resolve_instrument(
            unmapped
        )
    assert missing.value.code == "BROKER_INSTRUMENT_UNAVAILABLE"


def test_invalid_lot_and_malformed_expiry_are_rejected() -> None:
    with pytest.raises(OptionResolutionError) as lot:
        OptionResolver([option(lot="1.5")], provider="zerodha", today=date.today()).contracts()
    assert lot.value.code == "OPTION_LOT_SIZE_INVALID"

    malformed = option().model_copy(update={"expiry": "not-a-date"})
    with pytest.raises(OptionResolutionError) as expiry:
        OptionResolver([malformed], provider="zerodha", today=date.today()).contracts()
    assert expiry.value.code == "OPTION_EXPIRY_INVALID"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        (
            {"underlying_symbol": "BANKNIFTY"},
            "OPTION_CONTRACT_NOT_FOUND",
        ),
        (
            {"expiry": date.today() + timedelta(days=31)},
            "OPTION_CONTRACT_NOT_FOUND",
        ),
        (
            {"strike": Decimal("25000.01")},
            "OPTION_CONTRACT_NOT_FOUND",
        ),
        (
            {"option_type": "PE"},
            "OPTION_CONTRACT_NOT_FOUND",
        ),
    ],
)
def test_resolver_rejects_nonexistent_structural_components(
    changes: dict[str, object], code: str
) -> None:
    expiry = date.today() + timedelta(days=30)
    resolver = OptionResolver([option(expiry=expiry)], provider="zerodha", today=date.today())
    values: dict[str, object] = {
        "exchange": "NFO",
        "underlying_symbol": "NIFTY",
        "expiry": expiry,
        "strike": Decimal("25000"),
        "option_type": "CE",
    }
    values.update(changes)
    with pytest.raises(OptionResolutionError) as failure:
        resolver.resolve(OptionContractRequest.model_validate(values))
    assert failure.value.code == code


def test_identity_changes_with_expiry_strike_type_and_lot_is_master_truth() -> None:
    first = date.today() + timedelta(days=30)
    second = date.today() + timedelta(days=60)
    resolver = OptionResolver(
        [
            option(expiry=first, strike="25000", kind="CE", lot="75", token="1"),
            option(expiry=first, strike="25000", kind="PE", lot="75", token="2"),
            option(expiry=first, strike="25100", kind="CE", lot="50", token="3"),
            option(expiry=second, strike="25000", kind="CE", lot="25", token="4"),
        ],
        provider="zerodha",
        today=date.today(),
    )
    contracts = resolver.contracts()
    assert len({contract.canonical_id for contract in contracts}) == 4
    assert {contract.lot_size for contract in contracts} == {25, 50, 75}
