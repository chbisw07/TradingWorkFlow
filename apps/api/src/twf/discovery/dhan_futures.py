"""Structured Dhan futures master mapping; no trading/display-symbol parsing."""

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from twf.discovery.dhan_benchmarks import DhanIndexLookup, normalized_index_name

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
FIELDS = {
    "EXCH_ID",
    "SEGMENT",
    "SECURITY_ID",
    "INSTRUMENT",
    "UNDERLYING_SYMBOL",
    "UNDERLYING_SECURITY_ID",
    "SYMBOL_NAME",
    "DISPLAY_NAME",
    "LOT_SIZE",
    "SM_EXPIRY_DATE",
    "TICK_SIZE",
    "SERIES",
}


def parse_master(content: bytes) -> tuple[dict[str, str], ...]:
    """Adapt detailed fields to TWF identity fields. Derivative ticks are paise."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if not FIELDS.issubset(reader.fieldnames or ()):
        raise ValueError("Invalid detailed instrument master schema")
    rows = []
    for count, raw in enumerate(reader):
        if count >= 250_000:
            raise ValueError("Instrument master exceeds bound")
        r = {k: (v or "").strip() for k, v in raw.items() if k}
        if r["EXCH_ID"] != "NSE":
            continue
        kind = r["INSTRUMENT"]
        if kind not in {"FUTSTK", "FUTIDX", "EQUITY", "INDEX"}:
            continue
        tick = r["TICK_SIZE"]
        if kind in {"FUTSTK", "FUTIDX"}:
            try:
                tick = str(Decimal(tick) / 100)
            except InvalidOperation:
                tick = ""
        rows.append(
            {
                "SEM_EXM_EXCH_ID": r["EXCH_ID"],
                "SEM_SEGMENT": r["SEGMENT"],
                "SEM_SMST_SECURITY_ID": r["SECURITY_ID"],
                "SEM_INSTRUMENT_NAME": kind,
                "SEM_TRADING_SYMBOL": r["UNDERLYING_SYMBOL"]
                if kind == "EQUITY"
                else r["SYMBOL_NAME"],
                "SEM_CUSTOM_SYMBOL": r["DISPLAY_NAME"],
                "SM_SYMBOL_NAME": r["UNDERLYING_SYMBOL"].upper(),
                "UNDERLYING_SECURITY_ID": r["UNDERLYING_SECURITY_ID"],
                "SEM_EXPIRY_DATE": r["SM_EXPIRY_DATE"],
                "SEM_LOT_UNITS": r["LOT_SIZE"],
                "SEM_TICK_SIZE": tick,
                "SEM_SERIES": r["SERIES"],
            }
        )
    if not rows:
        raise ValueError("Empty detailed instrument master")
    return tuple(rows)


class FuturesMaster:
    """One snapshot, indexed once; active dates are checked on every run."""

    def __init__(self, rows: tuple[dict[str, str], ...], today: date):
        self.indexes = DhanIndexLookup(rows)
        self.contracts: dict[str, list[tuple[date, dict[str, str]]]] = {}
        self.failures: dict[str, str] = {}
        for row in rows:
            symbol = row.get("SM_SYMBOL_NAME", "").strip().upper()
            kind = row.get("SEM_INSTRUMENT_NAME")
            if row.get("SEM_EXM_EXCH_ID") != "NSE":
                continue
            if kind in {"EQUITY", "INDEX"}:
                self.failures.setdefault(row["SEM_TRADING_SYMBOL"].upper(), "NO_ACTIVE_FUTURES")
                continue
            if not symbol or kind not in {"FUTSTK", "FUTIDX"}:
                continue
            self.failures.setdefault(symbol, "NO_ACTIVE_FUTURES")
            try:
                if row.get("SEM_SEGMENT") != "D":
                    raise ValueError
                expiry = date.fromisoformat(row["SEM_EXPIRY_DATE"][:10])
                lot, tick = Decimal(row["SEM_LOT_UNITS"]), Decimal(row["SEM_TICK_SIZE"])
                security = row["SEM_SMST_SECURITY_ID"]
                if (
                    not security.isdecimal()
                    or int(security) <= 0
                    or not row["SEM_TRADING_SYMBOL"]
                    or not lot.is_finite()
                    or lot <= 0
                    or lot != int(lot)
                    or not tick.is_finite()
                    or tick <= 0
                ):
                    raise ValueError
            except (KeyError, ValueError, InvalidOperation):
                self.failures[symbol] = "INVALID_FUTURES_METADATA"
                continue
            if expiry >= today:
                self.contracts.setdefault(symbol, []).append((expiry, row))
        for contracts in self.contracts.values():
            contracts.sort(
                key=lambda c: (c[0], int(c[1]["SEM_SMST_SECURITY_ID"]), c[1]["SEM_TRADING_SYMBOL"])
            )

    def symbol(self, value: str) -> str:
        symbol = value.strip().upper()
        if symbol in self.contracts or symbol in self.failures:
            return symbol
        matches = self.indexes.candidates(symbol)
        if len(matches) == 1:
            return matches[0]["SEM_TRADING_SYMBOL"].upper()
        # Only index names have whitespace/underscore aliases; never rewrite equities.
        names = {
            s
            for s, contracts in self.contracts.items()
            if contracts[0][1]["SEM_INSTRUMENT_NAME"] == "FUTIDX"
            and normalized_index_name(s) == normalized_index_name(symbol)
        }
        return next(iter(names)) if len(names) == 1 else symbol

    def resolve(
        self, value: str, expiry: date | None = None
    ) -> tuple[tuple[date, dict[str, str]] | None, str | None]:
        symbol = self.symbol(value)
        candidates = self.contracts.get(symbol, [])
        if not candidates:
            return None, self.failures.get(symbol, "NO_MASTER_MATCH")
        if expiry is not None:
            candidates = [c for c in candidates if c[0] == expiry]
            if not candidates:
                return None, "EXPIRY_NOT_FOUND"
        return candidates[0], None
