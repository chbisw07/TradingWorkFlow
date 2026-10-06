"""Dhan catalog boundary for watchlists; scanner resolution is unchanged."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from twf.discovery.domain import InstrumentIdentity
from twf.discovery.market_data import DhanMarketDataProvider, _exchange_segment, _identity, _stable
from twf.watchlists.contracts import Kind


def kind(item: InstrumentIdentity) -> Kind:
    value = item.instrument_type or ""
    if value.startswith("FUT"):
        return "FUTURE"
    if value.startswith("OPT"):
        return "OPTION"
    return "INDEX" if item.segment == "INDEX" else "EQUITY"


def row_kind(row: dict[str, str]) -> Kind | None:
    return {
        "EQUITY": "EQUITY",
        "INDEX": "INDEX",
        "FUTIDX": "FUTURE",
        "FUTSTK": "FUTURE",
        "OPTIDX": "OPTION",
        "OPTSTK": "OPTION",
    }.get(row["SEM_INSTRUMENT_NAME"].upper())  # type: ignore[return-value]


def canonical(row: dict[str, str]) -> InstrumentIdentity | None:
    if row_kind(row) is None or row["SEM_EXM_EXCH_ID"] not in {"NSE", "BSE"}:
        return None
    try:
        item = _identity(row)
        if row_kind(row) in {"FUTURE", "OPTION"}:
            expiry = datetime.fromisoformat(row.get("SEM_EXPIRY_DATE", "")[:10]).replace(tzinfo=UTC)
            if expiry.date() < datetime.now(UTC).date():
                return None
            right = {"CE": "CALL", "PE": "PUT"}.get(row.get("SEM_OPTION_TYPE", ""))
            strike = Decimal(row.get("SEM_STRIKE_PRICE", "0"))
            if row_kind(row) == "OPTION" and (not right or strike <= 0):
                return None
            underlying_symbol = row.get("SM_SYMBOL_NAME", "").strip().upper()
            item = InstrumentIdentity.model_validate(
                {
                    **item.model_dump(),
                    "segment": "FNO",
                    "underlying": {
                        "underlying_id": _stable(
                            "underlying",
                            f"{item.exchange}:{underlying_symbol}",
                        ),
                        "source": {
                            "namespace": "dhan-symbol",
                            "native_id": f"{item.exchange}:{underlying_symbol}",
                            "revision": "scrip-master-v1",
                        },
                        "mapping": {"id": "dhan-scrip-master-underlying", "version": "1"},
                        "ambiguous": not bool(underlying_symbol),
                    },
                    "expiry": expiry,
                    "strike": strike if right else None,
                    "right": right,
                }
            )
        return item
    except (ValueError, InvalidOperation):
        return None


class WatchlistCatalog:
    def __init__(self, provider: DhanMarketDataProvider) -> None:
        self.provider = provider

    async def instruments(self) -> tuple[InstrumentIdentity, ...]:
        return tuple(i for row in await self.provider._load_master() if (i := canonical(row)))

    async def search(
        self, query: str, instrument_type: Kind | None
    ) -> tuple[InstrumentIdentity, ...]:
        q = query.strip().upper()
        if not q:
            return ()
        # Filter/rank cheap raw metadata before constructing immutable domain identities.
        rows = [
            r
            for r in await self.provider._load_master()
            if q in r["SEM_TRADING_SYMBOL"].upper()
            and row_kind(r)
            and (not instrument_type or row_kind(r) == instrument_type)
        ]
        rows.sort(
            key=lambda r: (
                r["SEM_TRADING_SYMBOL"].upper() != q,
                not r["SEM_TRADING_SYMBOL"].upper().startswith(q),
                r["SEM_EXM_EXCH_ID"] != "NSE",
                r["SEM_TRADING_SYMBOL"],
                r["SEM_SMST_SECURITY_ID"],
            )
        )
        output = []
        for row in rows:
            if item := canonical(row):
                output.append(item)
                if len(output) == 40:
                    break
        return tuple(output)

    async def resolve(self, ids: tuple[UUID, ...]) -> tuple[InstrumentIdentity, ...]:
        wanted = set(ids)
        found = {}
        for row in await self.provider._load_master():
            key = _stable("instrument", f"{_exchange_segment(row)}:{row['SEM_SMST_SECURITY_ID']}")
            if key in wanted and (item := canonical(row)):
                found[key] = item
        return tuple(found[i] for i in dict.fromkeys(ids) if i in found)

    async def resolve_symbols(self, symbols: set[str]) -> dict[str, tuple[InstrumentIdentity, ...]]:
        output: dict[str, tuple[InstrumentIdentity, ...]] = {}
        for row in await self.provider._load_master():
            symbol = f"{row['SEM_EXM_EXCH_ID']}:{row['SEM_TRADING_SYMBOL']}".upper()
            if symbol in symbols and (item := canonical(row)):
                output[symbol] = (*output.get(symbol, ()), item)
        return output
