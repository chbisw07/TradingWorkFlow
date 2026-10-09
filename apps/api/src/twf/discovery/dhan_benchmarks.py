"""Dhan-only index aliases. IDs always come from the current instrument master."""

import re
from dataclasses import dataclass
from enum import StrEnum


class BenchmarkSupportStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED_BY_DHAN = "UNSUPPORTED_BY_DHAN"
    UNRESOLVED_ALIAS = "UNRESOLVED_ALIAS"
    INVALID_METADATA_MAPPING = "INVALID_METADATA_MAPPING"


# Verified against Dhan's public compact master on 2026-10-09. These are name
# adaptations, never an alternative security-ID master or a sector classifier.
# Values are (provider-neutral display name, exact Dhan trading symbol).
BENCHMARK_ALIASES: dict[str, tuple[str, str]] = {
    "NIFTYIT": ("NIFTY IT", "NIFTYIT"),
    "NIFTYBANK": ("NIFTY BANK", "BANKNIFTY"),
    "NIFTYMETAL": ("NIFTY METAL", "NIFTY METAL"),
    "NIFTYPHARMA": ("NIFTY PHARMA", "NIFTY PHARMA"),
    "NIFTYAUTO": ("NIFTY AUTO", "NIFTY AUTO"),
    "NIFTYREALTY": ("NIFTY REALTY", "NIFTY REALTY"),
    "NIFTYENERGY": ("NIFTY ENERGY", "NIFTY ENERGY"),
    "NIFTYOILGAS": ("NIFTY OIL & GAS", "NIFTY OIL AND GAS"),
    "NIFTY_FIN_SERVICE": ("NIFTY FINANCIAL SERVICES", "FINNIFTY"),
    "NIFTY_HEALTHCARE": ("NIFTY HEALTHCARE INDEX", "NIFTY HEALTHCARE"),
    "NIFTYFMCG": ("NIFTY FMCG", "NIFTY FMCG"),
}
# Empty deliberately: absent aliases or failed HTTP calls do not prove that an
# index is unsupported. Only confirmed provider limitations may be added here.
UNSUPPORTED_BENCHMARKS: frozenset[str] = frozenset()


def normalized_index_name(value: str) -> str:
    """Case/spacing/underscore normalization only; no fuzzy or substring match."""
    return re.sub(r"[\s_]", "", value.upper())


def benchmark_alias(symbol: str) -> tuple[str, str] | None:
    key = normalized_index_name(symbol)
    return next(
        (
            value
            for name, value in BENCHMARK_ALIASES.items()
            if key in {normalized_index_name(name), normalized_index_name(value[0])}
        ),
        None,
    )


@dataclass(frozen=True)
class BenchmarkSupport:
    """Internal diagnostic. Never added to metadata or candidate packets."""

    benchmark: str
    symbol: str
    status: BenchmarkSupportStatus
    reason: str | None = None
    dhan_name: str | None = None
    security_id: str | None = None
    exchange_segment: str | None = None
    instrument_type: str | None = None


class DhanIndexLookup:
    """One derived lookup per cached master snapshot, not per candidate."""

    def __init__(self, rows: tuple[dict[str, str], ...]) -> None:
        self.exact: dict[str, list[dict[str, str]]] = {}
        self.normalized: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            if (
                row.get("SEM_EXM_EXCH_ID"),
                row.get("SEM_SEGMENT"),
                row.get("SEM_INSTRUMENT_NAME", "").upper(),
            ) != ("NSE", "I", "INDEX"):
                continue
            self.exact.setdefault(row["SEM_TRADING_SYMBOL"].upper(), []).append(row)
            for name in {
                normalized_index_name(row.get(key, ""))
                for key in ("SEM_TRADING_SYMBOL", "SEM_CUSTOM_SYMBOL", "SM_SYMBOL_NAME")
            } - {""}:
                self.normalized.setdefault(name, []).append(row)

    def candidates(self, symbol: str) -> tuple[dict[str, str], ...]:
        # Exact match wins. Ambiguity at any stage is returned to the existing
        # resolver; never "resolved" by silently falling through to another stage.
        rows = self.exact.get(symbol.strip().upper())
        if rows is None:
            rows = self.normalized.get(normalized_index_name(symbol))
        if rows is None:
            alias = benchmark_alias(symbol)
            rows = self.exact.get(alias[1]) if alias else None
        return tuple(rows or ())
