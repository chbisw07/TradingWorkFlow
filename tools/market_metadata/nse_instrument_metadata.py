#!/usr/bin/env python3
"""
nse_instrument_metadata.py

Build a database-ready NSE instrument/company metadata CSV for TWF.

V3.2 goals
--------
* Discover the full NSE equity universe from the official NSE bulk CSV.
* Never use NSE's per-symbol quote-equity API.
* Prefer an optional authoritative bulk NSE/NSE Indices classification file.
* Use Yahoo Finance only as a fallback/enrichment source for:
    - sector
    - industry
    - market capitalization
    - market-cap currency
* Keep source/as-of provenance per attribute.
* Use explicit exact-match benchmark mapping; NO loose substring matching.
* Derive a deterministic TWF market-cap rank/category after the full run.
* Preserve unresolved rows.
* Identify rights-entitlement instruments and attempt inheritance from the
  underlying equity when the underlying is present in the same output.
* Support resume/checkpoint.
* Support a quarterly "market-cap refresh only" workflow.

Important terminology
---------------------
The TWF market-cap category in this file is NOT an AMFI category.

Default TWF rank rule:
    LARGE : rank 1-100
    MID   : rank 101-250
    SMALL : rank 251-1000
    MICRO : rank 1001+

Market-cap classification policy
--------------------------------
Raw market_cap is the primary fact.

Two relative-rank classifications are produced only when the run represents
the full universe:

1. market_cap_category
       LARGE : rank 1-100
       MID   : rank 101-250
       SMALL : rank 251+

   This follows the familiar Indian relative-rank convention, but this program
   does NOT claim the value is an AMFI classification unless an
   AMFI source is later imported.

2. twf_cap_tier
       LARGE : rank 1-100
       MID   : rank 101-250
       SMALL : rank 251-1000
       MICRO : rank 1001+

   This is a TWF analytical tier.

If --limit is used, market_cap_rank and both category fields are intentionally
left blank because a partial sample cannot produce meaningful relative ranks.

Install
-------
    pip install requests yfinance

Typical usage
-------------
# 20-row smoke test:
    python nse_instrument_metadata.py --limit 20 --use-yahoo

# Full NSE universe:
    python nse_instrument_metadata.py --use-yahoo

# Resume interrupted run:
    python nse_instrument_metadata.py --use-yahoo --resume

# If an authoritative bulk classification CSV is available:
    python nse_instrument_metadata.py \
        --classification-csv nse_industry_classification.csv \
        --use-yahoo

# Quarterly market-cap refresh using the previous V3 CSV as seed:
    python nse_instrument_metadata.py \
        --seed-csv nse_instrument_metadata.csv \
        --refresh-market-cap-only \
        --use-yahoo

Outputs
-------
    nse_instrument_metadata.csv
    nse_instrument_unresolved.csv
    nse_instrument_metadata_summary.json

The output schema is intentionally close to what TWF can later persist in its
instrument/company metadata database.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import requests

NSE_MAIN_EQUITY_CSV = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

UTILITY_VERSION = "3.2"
METADATA_SCHEMA_VERSION = "1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "var" / "market_metadata"
DEFAULT_OUTPUT = DEFAULT_OUTPUT_DIR / "nse_instrument_metadata.csv"
DEFAULT_UNRESOLVED = DEFAULT_OUTPUT_DIR / "nse_instrument_unresolved.csv"
DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / "nse_instrument_metadata_summary.json"
DEFAULT_CHECKPOINT = DEFAULT_OUTPUT_DIR / ".nse_instrument_metadata_checkpoint.json"
APP_TIMEZONE = ZoneInfo("Asia/Kolkata")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

MARKET_CAP_CATEGORY_METHOD = "RELATIVE_RANK_1_100_101_250_251_PLUS"
TWF_CAP_TIER_METHOD = "TWF_RELATIVE_RANK_V2_1_100_101_250_251_1000_1001_PLUS"


# ---------------------------------------------------------------------------
# Exact benchmark mapping
# ---------------------------------------------------------------------------
#
# These mappings are TWF context mappings, NOT claims of official index
# membership.
#
# Rules are intentionally exact/normalized.  There is no:
#
#     if keyword in free_text
#
# logic, because V2 proved that loose substring matching can misclassify
# "Credit Services" as "IT Services".
#
# Industry mapping wins over sector mapping.
#
# Expand these dictionaries only after validating actual Yahoo industry values.
#

YAHOO_INDUSTRY_CONTEXT_BENCHMARK: dict[str, tuple[str, str]] = {
    # Technology
    "information technology services": ("NIFTY IT", "NIFTYIT"),
    "software - application": ("NIFTY IT", "NIFTYIT"),
    "software - infrastructure": ("NIFTY IT", "NIFTYIT"),
    # Banking / financial services
    "banks - regional": ("NIFTY BANK", "NIFTYBANK"),
    "banks - diversified": ("NIFTY BANK", "NIFTYBANK"),
    "credit services": ("NIFTY FINANCIAL SERVICES", "NIFTY_FIN_SERVICE"),
    "asset management": ("NIFTY FINANCIAL SERVICES", "NIFTY_FIN_SERVICE"),
    "capital markets": ("NIFTY FINANCIAL SERVICES", "NIFTY_FIN_SERVICE"),
    "financial conglomerates": (
        "NIFTY FINANCIAL SERVICES",
        "NIFTY_FIN_SERVICE",
    ),
    "insurance - life": ("NIFTY FINANCIAL SERVICES", "NIFTY_FIN_SERVICE"),
    "insurance - diversified": (
        "NIFTY FINANCIAL SERVICES",
        "NIFTY_FIN_SERVICE",
    ),
    # Pharma / healthcare
    "drug manufacturers - general": ("NIFTY PHARMA", "NIFTYPHARMA"),
    "drug manufacturers - specialty & generic": (
        "NIFTY PHARMA",
        "NIFTYPHARMA",
    ),
    "biotechnology": ("NIFTY PHARMA", "NIFTYPHARMA"),
    "medical care facilities": (
        "NIFTY HEALTHCARE INDEX",
        "NIFTY_HEALTHCARE",
    ),
    "medical devices": ("NIFTY HEALTHCARE INDEX", "NIFTY_HEALTHCARE"),
    "diagnostics & research": (
        "NIFTY HEALTHCARE INDEX",
        "NIFTY_HEALTHCARE",
    ),
    # Auto
    "auto manufacturers": ("NIFTY AUTO", "NIFTYAUTO"),
    "auto parts": ("NIFTY AUTO", "NIFTYAUTO"),
    # Metal / mining -- intentionally excludes chemicals/cement
    "steel": ("NIFTY METAL", "NIFTYMETAL"),
    "aluminum": ("NIFTY METAL", "NIFTYMETAL"),
    "copper": ("NIFTY METAL", "NIFTYMETAL"),
    "other industrial metals & mining": ("NIFTY METAL", "NIFTYMETAL"),
    # Realty
    "real estate - development": ("NIFTY REALTY", "NIFTYREALTY"),
    "real estate services": ("NIFTY REALTY", "NIFTYREALTY"),
    "real estate - diversified": ("NIFTY REALTY", "NIFTYREALTY"),
    # FMCG-like
    "packaged foods": ("NIFTY FMCG", "NIFTYFMCG"),
    "household & personal products": ("NIFTY FMCG", "NIFTYFMCG"),
    "beverages - non-alcoholic": ("NIFTY FMCG", "NIFTYFMCG"),
    "tobacco": ("NIFTY FMCG", "NIFTYFMCG"),
    # Energy / oil & gas
    "oil & gas integrated": ("NIFTY OIL & GAS", "NIFTYOILGAS"),
    "oil & gas refining & marketing": ("NIFTY OIL & GAS", "NIFTYOILGAS"),
    "oil & gas exploration & production": (
        "NIFTY OIL & GAS",
        "NIFTYOILGAS",
    ),
    "oil & gas equipment & services": ("NIFTY OIL & GAS", "NIFTYOILGAS"),
}

# Only broad Yahoo sectors for which a context benchmark is reasonably safe.
# We intentionally do NOT force Basic Materials, Industrials, Consumer
# Cyclical, Consumer Defensive or Communication Services into a single index.
YAHOO_SECTOR_CONTEXT_BENCHMARK: dict[str, tuple[str, str]] = {
    "technology": ("NIFTY IT", "NIFTYIT"),
    "financial services": (
        "NIFTY FINANCIAL SERVICES",
        "NIFTY_FIN_SERVICE",
    ),
    "healthcare": ("NIFTY HEALTHCARE INDEX", "NIFTY_HEALTHCARE"),
    "real estate": ("NIFTY REALTY", "NIFTYREALTY"),
    "energy": ("NIFTY OIL & GAS", "NIFTYOILGAS"),
    "utilities": ("NIFTY ENERGY", "NIFTYENERGY"),
}


@dataclass(frozen=True)
class DatasetRun:
    metadata_schema_version: str
    dataset_run_id: str
    dataset_generated_at: str


@dataclass(frozen=True)
class CheckpointState:
    completed_keys: frozenset[str]
    dataset_run: DatasetRun | None = None


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if self.passed else "FAIL",
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class UniverseInstrument:
    exchange: str
    symbol: str
    series: str
    isin: str
    company_name: str
    listing_date: str


@dataclass
class MetadataRow:
    # Durable / tradable identity
    exchange: str
    symbol: str
    series: str
    isin: str
    company_name: str
    listing_date: str

    # Dataset-level snapshot identity. All rows in one snapshot share these.
    metadata_schema_version: str = ""
    dataset_run_id: str = ""
    dataset_generated_at: str = ""

    # Instrument relationship
    instrument_kind: str = "EQUITY"
    underlying_symbol: str = ""
    underlying_resolution_method: str = ""

    # Optional authoritative NSE four-level classification
    macro_sector_code: str = ""
    macro_sector: str = ""
    sector_code: str = ""
    basic_industry_code: str = ""
    basic_industry: str = ""
    nse_classification_source: str = ""
    nse_classification_as_of: str = ""

    # Practical sector / industry identity used by TWF
    sector: str = ""
    sector_source: str = ""
    sector_as_of: str = ""
    industry_code: str = ""
    industry: str = ""
    industry_source: str = ""
    industry_as_of: str = ""

    # Market capitalization
    market_cap: str = ""
    market_cap_currency: str = ""
    market_cap_source: str = ""
    market_cap_as_of: str = ""
    market_cap_rank: str = ""
    market_cap_category: str = ""
    market_cap_category_method: str = ""
    twf_cap_tier: str = ""
    twf_cap_tier_method: str = ""

    # TWF market-context benchmark mapping.
    # This is NOT official index membership.
    context_benchmark: str = ""
    context_benchmark_symbol: str = ""
    benchmark_mapping_source: str = ""
    benchmark_mapping_basis: str = ""

    # Record-level resolution / provenance
    resolution_status: str = "UNRESOLVED"
    classification_completeness: str = "NONE"
    confidence: str = "0.0"
    retrieved_at: str = ""
    notes: str = ""


OUTPUT_FIELDS = [field.name for field in fields(MetadataRow)]


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(APP_TIMEZONE).isoformat(timespec="seconds")


def today_iso() -> str:
    return datetime.now(APP_TIMEZONE).date().isoformat()


class AppTimezoneFormatter(logging.Formatter):
    """Render log record timestamps in TWF's explicit operational timezone."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        instant = datetime.fromtimestamp(record.created, APP_TIMEZONE)
        if datefmt:
            return instant.strftime(datefmt)
        return instant.isoformat(sep=" ", timespec="milliseconds").replace(".", ",", 1)


def configure_logging(level: str) -> None:
    formatter = AppTimezoneFormatter("%(asctime)s %(levelname)s %(message)s")
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
    root_logger.setLevel(getattr(logging, level))


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"none", "null", "nan", "n/a", "na"}:
        return ""
    return text


def normalized_text(value: str) -> str:
    return " ".join(clean(value).casefold().replace("_", " ").split())


def normalize_header(value: str) -> str:
    return " ".join(value.replace("\ufeff", "").strip().upper().replace("_", " ").split())


def first_value(row: dict[str, str], candidates: Iterable[str]) -> str:
    normalized = {normalize_header(k): clean(v) for k, v in row.items() if k}
    for candidate in candidates:
        value = normalized.get(normalize_header(candidate), "")
        if value:
            return value
    return ""


def note_tokens(value: str) -> list[str]:
    return [token.strip() for token in clean(value).split(";") if token.strip()]


def append_note_unique(current: str, extra: str) -> str:
    """Append notes deterministically while removing inherited duplicates."""
    output: list[str] = []
    seen: set[str] = set()
    for token in [*note_tokens(current), *note_tokens(extra)]:
        key = normalized_text(token)
        if key and key not in seen:
            output.append(token)
            seen.add(key)
    return "; ".join(output)


def has_duplicate_notes(value: str) -> bool:
    tokens = [normalized_text(token) for token in note_tokens(value)]
    return len(tokens) != len(set(tokens))


def new_dataset_run() -> DatasetRun:
    return DatasetRun(
        metadata_schema_version=METADATA_SCHEMA_VERSION,
        dataset_run_id=str(uuid.uuid4()),
        dataset_generated_at=now_iso(),
    )


def parse_int(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return int(value)

    text = clean(value).replace(",", "")
    if not text:
        return None

    try:
        return int(float(text))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# NSE universe
# ---------------------------------------------------------------------------


def download_text(url: str, timeout: float, retries: int) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/csv,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                timeout=timeout,
                headers=headers,
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(min(2**attempt, 8))

    raise RuntimeError(f"Failed to download {url}: {last_exc}")


def parse_nse_universe(text: str) -> list[UniverseInstrument]:
    reader = csv.DictReader(text.splitlines())
    instruments: list[UniverseInstrument] = []

    for raw in reader:
        symbol = first_value(raw, ("SYMBOL",))
        if not symbol:
            continue

        instruments.append(
            UniverseInstrument(
                exchange="NSE",
                symbol=symbol,
                series=first_value(raw, ("SERIES",)),
                isin=first_value(raw, ("ISIN NUMBER", "ISIN")),
                company_name=first_value(
                    raw,
                    ("NAME OF COMPANY", "COMPANY NAME"),
                ),
                listing_date=first_value(
                    raw,
                    ("DATE OF LISTING", "LISTING DATE"),
                ),
            )
        )

    return instruments


def load_universe(args: argparse.Namespace) -> list[UniverseInstrument]:
    if args.input_csv:
        logging.info("Loading NSE universe from %s", args.input_csv)
        text = Path(args.input_csv).read_text(encoding="utf-8-sig")
    else:
        logging.info("Downloading NSE equity universe")
        text = download_text(
            NSE_MAIN_EQUITY_CSV,
            args.timeout,
            args.retries,
        )

    instruments = parse_nse_universe(text)
    if not instruments:
        raise RuntimeError("NSE universe parsed zero rows")

    # Dedupe by ISIN first, symbol second.
    chosen: dict[str, UniverseInstrument] = {}
    series_priority = {
        "EQ": 0,
        "BE": 1,
        "BZ": 2,
        "SM": 3,
        "ST": 4,
    }

    for item in instruments:
        key = f"ISIN:{item.isin}" if item.isin else f"SYM:{item.symbol.upper()}"

        existing = chosen.get(key)
        if existing is None:
            chosen[key] = item
            continue

        old_rank = series_priority.get(existing.series.upper(), 99)
        new_rank = series_priority.get(item.series.upper(), 99)
        if new_rank < old_rank:
            chosen[key] = item

    result = sorted(chosen.values(), key=lambda item: item.symbol)

    logging.info(
        "Eligible unique NSE equity/security rows: %d",
        len(result),
    )
    return result


# ---------------------------------------------------------------------------
# Instrument-kind / underlying handling
# ---------------------------------------------------------------------------


def infer_instrument_relationship(
    symbol: str,
    series: str,
    company_name: str,
) -> tuple[str, str, str]:
    """
    Conservative relationship inference.

    A symbol ending in '-RE' is treated as RIGHTS_ENTITLEMENT and points to the
    stripped symbol as a candidate underlying.

    This does not claim the relationship is exchange-authoritative.  We record
    the inference method explicitly.
    """
    symbol_upper = symbol.upper()

    if symbol_upper.endswith("-RE") and len(symbol_upper) > 3:
        return (
            "RIGHTS_ENTITLEMENT",
            symbol_upper[:-3],
            "SYMBOL_SUFFIX_INFERRED",
        )

    # Keep ordinary listed-company rows simple.
    return "EQUITY", "", ""


# ---------------------------------------------------------------------------
# Optional authoritative bulk classification
# ---------------------------------------------------------------------------


def load_bulk_classification(
    path: Path | None,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    if path is None:
        return {}, {}

    logging.info("Loading bulk classification CSV: %s", path)

    by_isin: dict[str, dict[str, str]] = {}
    by_symbol: dict[str, dict[str, str]] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)

        for raw in reader:
            isin = first_value(raw, ("ISIN", "ISIN NUMBER", "ISIN NO"))
            symbol = first_value(
                raw,
                ("SYMBOL", "TICKER", "SECURITY SYMBOL"),
            )

            normalized = {
                "macro_sector_code": first_value(
                    raw,
                    (
                        "MES CODE",
                        "MACRO SECTOR CODE",
                        "MACRO ECONOMIC SECTOR CODE",
                    ),
                ),
                "macro_sector": first_value(
                    raw,
                    (
                        "MACRO ECONOMIC SECTOR",
                        "MACRO-ECONOMIC SECTOR",
                        "MACRO SECTOR",
                    ),
                ),
                "sector_code": first_value(
                    raw,
                    ("SECT CODE", "SECTOR CODE"),
                ),
                "sector": first_value(raw, ("SECTOR",)),
                "industry_code": first_value(
                    raw,
                    ("IND CODE", "INDUSTRY CODE"),
                ),
                "industry": first_value(raw, ("INDUSTRY",)),
                "basic_industry_code": first_value(
                    raw,
                    ("BASIC IND CODE", "BASIC INDUSTRY CODE"),
                ),
                "basic_industry": first_value(
                    raw,
                    ("BASIC INDUSTRY",),
                ),
            }

            if not any(normalized.values()):
                continue

            if isin:
                by_isin[isin] = normalized
            if symbol:
                by_symbol[symbol.upper()] = normalized

    logging.info(
        "Bulk classification loaded: %d ISIN keys, %d symbol keys",
        len(by_isin),
        len(by_symbol),
    )

    return by_isin, by_symbol


def apply_bulk_classification(
    row: MetadataRow,
    by_isin: dict[str, dict[str, str]],
    by_symbol: dict[str, dict[str, str]],
    source_path: Path | None,
) -> bool:
    data: dict[str, str] | None = None
    method = ""

    if row.isin and row.isin in by_isin:
        data = by_isin[row.isin]
        method = "ISIN"
    elif row.symbol.upper() in by_symbol:
        data = by_symbol[row.symbol.upper()]
        method = "SYMBOL"

    if not data:
        return False

    row.macro_sector_code = clean(data.get("macro_sector_code"))
    row.macro_sector = clean(data.get("macro_sector"))
    row.sector_code = clean(data.get("sector_code"))
    row.industry_code = clean(data.get("industry_code"))
    row.basic_industry_code = clean(data.get("basic_industry_code"))
    row.basic_industry = clean(data.get("basic_industry"))

    authoritative_sector = clean(data.get("sector"))
    authoritative_industry = clean(data.get("industry"))

    if authoritative_sector:
        row.sector = authoritative_sector
        row.sector_source = "NSE_BULK_CLASSIFICATION"
        row.sector_as_of = today_iso()

    if authoritative_industry:
        row.industry = authoritative_industry
        row.industry_source = "NSE_BULK_CLASSIFICATION"
        row.industry_as_of = today_iso()

    row.nse_classification_source = str(source_path) if source_path else "NSE_BULK_CLASSIFICATION"
    row.nse_classification_as_of = today_iso()

    if any(
        (
            row.macro_sector,
            row.sector,
            row.industry,
            row.basic_industry,
        )
    ):
        row.resolution_status = "RESOLVED"
        row.classification_completeness = (
            "NSE_4_LEVEL"
            if all(
                (
                    row.macro_sector,
                    row.sector,
                    row.industry,
                    row.basic_industry,
                )
            )
            else "NSE_PARTIAL"
        )
        row.confidence = "1.0"

        if method:
            row.notes = append_note_unique(
                row.notes,
                f"NSE_CLASSIFICATION_MATCH={method}",
            )

        return True

    return False


# ---------------------------------------------------------------------------
# Seed / resume helpers
# ---------------------------------------------------------------------------


def canonical_key(isin: str, symbol: str) -> str:
    return f"ISIN:{isin}" if isin else f"SYM:{symbol.upper()}"


def load_seed_csv(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}

    logging.info("Loading seed metadata from %s", path)

    seed: dict[str, dict[str, str]] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for raw in csv.DictReader(fh):
            isin = clean(raw.get("isin"))
            symbol = clean(raw.get("symbol"))
            if not isin and not symbol:
                continue

            normalized = {k: clean(v) for k, v in raw.items() if k}
            if not normalized.get("market_cap_category"):
                normalized["market_cap_category"] = clean(normalized.get("official_cap_category"))
            if not normalized.get("market_cap_category_method"):
                normalized["market_cap_category_method"] = clean(
                    normalized.get("official_cap_category_method")
                )
            seed[canonical_key(isin, symbol)] = normalized

    logging.info("Seed rows loaded: %d", len(seed))
    return seed


def apply_seed(row: MetadataRow, seed: dict[str, dict[str, str]]) -> None:
    existing = seed.get(canonical_key(row.isin, row.symbol))
    if not existing:
        return

    # Preserve identity from current NSE universe, but reuse metadata fields.
    protected_identity = {
        "exchange",
        "symbol",
        "series",
        "isin",
        "company_name",
        "listing_date",
        "metadata_schema_version",
        "dataset_run_id",
        "dataset_generated_at",
    }

    for field_name in OUTPUT_FIELDS:
        if field_name in protected_identity:
            continue

        value = clean(existing.get(field_name))
        if value:
            setattr(row, field_name, value)


# ---------------------------------------------------------------------------
# Yahoo enrichment
# ---------------------------------------------------------------------------


def yahoo_lookup(
    row: MetadataRow,
    pause: float,
    refresh_market_cap_only: bool,
) -> bool:
    """
    Enrich from Yahoo Finance.

    Yahoo is NOT promoted to NSE four-level classification truth.

    Sector/industry are accepted as practical TWF metadata with explicit
    provenance.

    Market cap is stored independently from classification provenance.
    """
    try:
        import yfinance as yf  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "Yahoo enrichment requested but yfinance is not installed. Run: pip install yfinance"
        ) from exc

    ticker_symbol = f"{row.symbol}.NS"

    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.get_info()

        if not isinstance(info, dict):
            row.notes = append_note_unique(
                row.notes,
                "YAHOO_INFO_NOT_OBJECT",
            )
            return False

        changed = False
        as_of = today_iso()

        # Market cap is independent and can be refreshed quarterly even when
        # sector/industry already exist from a stronger source.
        market_cap = parse_int(info.get("marketCap"))
        currency = clean(info.get("currency"))

        if market_cap is not None and market_cap > 0:
            row.market_cap = str(market_cap)
            row.market_cap_currency = currency or "INR"
            row.market_cap_source = "YAHOO"
            row.market_cap_as_of = as_of
            changed = True

        if not refresh_market_cap_only:
            yahoo_sector = clean(info.get("sector"))
            yahoo_industry = clean(info.get("industry"))

            # Never overwrite authoritative NSE-sourced values.
            if yahoo_sector and row.sector_source != "NSE_BULK_CLASSIFICATION":
                row.sector = yahoo_sector
                row.sector_source = "YAHOO"
                row.sector_as_of = as_of
                changed = True

            if yahoo_industry and row.industry_source != "NSE_BULK_CLASSIFICATION":
                row.industry = yahoo_industry
                row.industry_source = "YAHOO"
                row.industry_as_of = as_of
                changed = True

        if changed:
            # Resolution is based on classification identity, not solely
            # market-cap availability.
            if row.sector or row.industry:
                row.resolution_status = "RESOLVED"

                if row.nse_classification_source and all(
                    (
                        row.macro_sector,
                        row.sector,
                        row.industry,
                        row.basic_industry,
                    )
                ):
                    row.classification_completeness = "NSE_4_LEVEL"
                    row.confidence = "1.0"
                elif row.sector_source == "YAHOO" or row.industry_source == "YAHOO":
                    row.classification_completeness = (
                        "SECTOR_INDUSTRY" if row.sector and row.industry else "PARTIAL"
                    )
                    # Practical confidence for TWF usage; not an exchange
                    # authority score.
                    row.confidence = max_confidence(
                        row.confidence,
                        "0.85",
                    )

            return True

        row.notes = append_note_unique(
            row.notes,
            "YAHOO_NO_USEFUL_METADATA",
        )
        return False

    except Exception as exc:
        row.notes = append_note_unique(
            row.notes,
            f"YAHOO_ERROR:{type(exc).__name__}:{exc}",
        )
        return False

    finally:
        if pause > 0:
            time.sleep(pause)


def max_confidence(current: str, proposed: str) -> str:
    try:
        return str(max(float(current or 0), float(proposed)))
    except ValueError:
        return proposed


# ---------------------------------------------------------------------------
# Exact context benchmark mapping
# ---------------------------------------------------------------------------


def apply_context_benchmark(row: MetadataRow) -> None:
    row.context_benchmark = ""
    row.context_benchmark_symbol = ""
    row.benchmark_mapping_source = ""
    row.benchmark_mapping_basis = ""

    industry_key = normalized_text(row.industry)
    sector_key = normalized_text(row.sector)

    if industry_key in YAHOO_INDUSTRY_CONTEXT_BENCHMARK:
        name, symbol = YAHOO_INDUSTRY_CONTEXT_BENCHMARK[industry_key]
        row.context_benchmark = name
        row.context_benchmark_symbol = symbol
        row.benchmark_mapping_source = "TWF_EXACT_RULE_V1"
        row.benchmark_mapping_basis = f"INDUSTRY:{row.industry}"
        return

    if sector_key in YAHOO_SECTOR_CONTEXT_BENCHMARK:
        name, symbol = YAHOO_SECTOR_CONTEXT_BENCHMARK[sector_key]
        row.context_benchmark = name
        row.context_benchmark_symbol = symbol
        row.benchmark_mapping_source = "TWF_EXACT_RULE_V1"
        row.benchmark_mapping_basis = f"SECTOR:{row.sector}"


# ---------------------------------------------------------------------------
# Rights-entitlement inheritance
# ---------------------------------------------------------------------------


def inherit_rights_entitlement_metadata(rows: list[MetadataRow]) -> None:
    by_symbol = {row.symbol.upper(): row for row in rows if row.symbol}

    for row in rows:
        if row.instrument_kind != "RIGHTS_ENTITLEMENT":
            continue

        if not row.underlying_symbol:
            continue

        underlying = by_symbol.get(row.underlying_symbol.upper())
        if underlying is None:
            row.notes = append_note_unique(
                row.notes,
                "UNDERLYING_NOT_FOUND_FOR_INHERITANCE",
            )
            continue

        # Classification identity can be inherited from the company equity.
        for field_name in (
            "macro_sector_code",
            "macro_sector",
            "sector_code",
            "sector",
            "industry_code",
            "industry",
            "basic_industry_code",
            "basic_industry",
            "nse_classification_source",
            "nse_classification_as_of",
            "sector_source",
            "sector_as_of",
            "industry_source",
            "industry_as_of",
            "context_benchmark",
            "context_benchmark_symbol",
            "benchmark_mapping_source",
            "benchmark_mapping_basis",
        ):
            current = clean(getattr(row, field_name))
            inherited = clean(getattr(underlying, field_name))
            if not current and inherited:
                setattr(row, field_name, inherited)

        # Market cap belongs to the underlying company; inherit it rather than
        # treating a rights entitlement as a separate company's capitalization.
        for field_name in (
            "market_cap",
            "market_cap_currency",
            "market_cap_source",
            "market_cap_as_of",
        ):
            current = clean(getattr(row, field_name))
            inherited = clean(getattr(underlying, field_name))
            if not current and inherited:
                setattr(row, field_name, inherited)

        if row.sector or row.industry:
            row.resolution_status = "RESOLVED_INHERITED"
            row.classification_completeness = underlying.classification_completeness or "INHERITED"
            row.confidence = underlying.confidence or "0.85"
            row.notes = append_note_unique(
                row.notes,
                f"INHERITED_FROM_UNDERLYING:{underlying.symbol}",
            )


# ---------------------------------------------------------------------------
# Market-cap ranking / category
# ---------------------------------------------------------------------------


def apply_market_cap_ranking(
    rows: list[MetadataRow],
    *,
    allow_relative_ranking: bool,
) -> None:
    """
    Rank unique company equities by market cap descending.

    Relative ranking is meaningful only when the dataset represents the full
    intended universe. If allow_relative_ranking=False (for example, a --limit
    smoke test), rank/category fields are intentionally left blank.

    Rights entitlements are excluded from independent ranking because they
    inherit the underlying company's market-cap metadata.
    """
    for row in rows:
        row.market_cap_rank = ""
        row.market_cap_category = ""
        row.market_cap_category_method = ""
        row.twf_cap_tier = ""
        row.twf_cap_tier_method = ""

    if not allow_relative_ranking:
        return

    eligible = [
        row
        for row in rows
        if row.instrument_kind == "EQUITY"
        and (parsed_cap := parse_int(row.market_cap)) is not None
        and parsed_cap > 0
    ]

    eligible.sort(
        key=lambda row: (
            -(parse_int(row.market_cap) or 0),
            row.symbol.upper(),
        )
    )

    by_symbol: dict[str, MetadataRow] = {}

    for rank, row in enumerate(eligible, start=1):
        row.market_cap_rank = str(rank)
        row.market_cap_category = market_cap_category(rank)
        row.market_cap_category_method = MARKET_CAP_CATEGORY_METHOD
        row.twf_cap_tier = twf_cap_tier(rank)
        row.twf_cap_tier_method = TWF_CAP_TIER_METHOD
        by_symbol[row.symbol.upper()] = row

    for row in rows:
        if row.instrument_kind == "RIGHTS_ENTITLEMENT" and row.underlying_symbol:
            underlying = by_symbol.get(row.underlying_symbol.upper())
            if underlying:
                row.market_cap_rank = underlying.market_cap_rank
                row.market_cap_category = underlying.market_cap_category
                row.market_cap_category_method = (
                    f"INHERITED:{underlying.market_cap_category_method}"
                )
                row.twf_cap_tier = underlying.twf_cap_tier
                row.twf_cap_tier_method = f"INHERITED:{underlying.twf_cap_tier_method}"


def market_cap_category(rank: int) -> str:
    if rank <= 100:
        return "LARGE"
    if rank <= 250:
        return "MID"
    return "SMALL"


def twf_cap_tier(rank: int) -> str:
    if rank <= 100:
        return "LARGE"
    if rank <= 250:
        return "MID"
    if rank <= 1000:
        return "SMALL"
    return "MICRO"


# ---------------------------------------------------------------------------
# Output / checkpoint
# ---------------------------------------------------------------------------


def metadata_row_from_universe(item: UniverseInstrument, dataset_run: DatasetRun) -> MetadataRow:
    instrument_kind, underlying, method = infer_instrument_relationship(
        item.symbol,
        item.series,
        item.company_name,
    )

    return MetadataRow(
        exchange=item.exchange,
        symbol=item.symbol,
        series=item.series,
        isin=item.isin,
        company_name=item.company_name,
        listing_date=item.listing_date,
        metadata_schema_version=dataset_run.metadata_schema_version,
        dataset_run_id=dataset_run.dataset_run_id,
        dataset_generated_at=dataset_run.dataset_generated_at,
        instrument_kind=instrument_kind,
        underlying_symbol=underlying,
        underlying_resolution_method=method,
        retrieved_at=now_iso(),
    )


def dataset_run_from_rows(rows: Iterable[MetadataRow]) -> DatasetRun | None:
    identities = {
        (
            row.metadata_schema_version,
            row.dataset_run_id,
            row.dataset_generated_at,
        )
        for row in rows
        if row.metadata_schema_version or row.dataset_run_id or row.dataset_generated_at
    }
    if not identities:
        return None
    if len(identities) != 1:
        raise ValueError("Existing output contains inconsistent dataset run identity")
    schema, run_id, generated_at = identities.pop()
    if not schema or not run_id or not generated_at:
        raise ValueError("Existing output contains incomplete dataset run identity")
    return DatasetRun(schema, run_id, generated_at)


def assign_dataset_run(rows: Iterable[MetadataRow], dataset_run: DatasetRun) -> None:
    for row in rows:
        row.metadata_schema_version = dataset_run.metadata_schema_version
        row.dataset_run_id = dataset_run.dataset_run_id
        row.dataset_generated_at = dataset_run.dataset_generated_at
        row.notes = append_note_unique(row.notes, "")


def load_checkpoint(path: Path) -> CheckpointState:
    if not path.exists():
        return CheckpointState(frozenset())

    try:
        payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        raw_keys = payload.get("completed_keys", [])
        completed = (
            frozenset(str(value) for value in raw_keys)
            if isinstance(raw_keys, list)
            else frozenset()
        )
        schema = clean(payload.get("metadata_schema_version"))
        run_id = clean(payload.get("dataset_run_id"))
        generated_at = clean(payload.get("dataset_generated_at"))
        dataset_run = (
            DatasetRun(schema, run_id, generated_at) if schema and run_id and generated_at else None
        )
        return CheckpointState(completed, dataset_run)
    except Exception as exc:
        logging.warning("Could not read checkpoint; ignoring it: %s", exc)
        return CheckpointState(frozenset())


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(value, encoding="utf-8")
    tmp.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def save_checkpoint(path: Path, completed: set[str], dataset_run: DatasetRun) -> None:
    atomic_write_json(
        path,
        {
            "updated_at": now_iso(),
            "metadata_schema_version": dataset_run.metadata_schema_version,
            "dataset_run_id": dataset_run.dataset_run_id,
            "dataset_generated_at": dataset_run.dataset_generated_at,
            "completed_keys": sorted(completed),
        },
    )


def normalized_metadata_mapping(raw: dict[str, str]) -> dict[str, str]:
    values = {field_name: clean(raw.get(field_name)) for field_name in OUTPUT_FIELDS}
    values["market_cap_category"] = values["market_cap_category"] or clean(
        raw.get("official_cap_category")
    )
    values["market_cap_category_method"] = values["market_cap_category_method"] or clean(
        raw.get("official_cap_category_method")
    )
    values["exchange"] = values["exchange"] or "NSE"
    return values


def load_existing_output(path: Path) -> dict[str, MetadataRow]:
    if not path.exists():
        return {}

    result: dict[str, MetadataRow] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for raw in csv.DictReader(fh):
            row = MetadataRow(**normalized_metadata_mapping(raw))
            result[canonical_key(row.isin, row.symbol)] = row
    return result


def partial_output_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.partial")


def write_rows_csv(path: Path, rows: Iterable[MetadataRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda value: value.symbol):
            writer.writerow(asdict(row))
    tmp.replace(path)


def write_main_csv(path: Path, rows: list[MetadataRow]) -> None:
    write_rows_csv(path, rows)


def unresolved_rows(rows: Iterable[MetadataRow]) -> list[MetadataRow]:
    return [row for row in rows if row.resolution_status not in {"RESOLVED", "RESOLVED_INHERITED"}]


def write_unresolved_csv(path: Path, rows: list[MetadataRow]) -> int:
    unresolved = unresolved_rows(rows)
    write_rows_csv(path, unresolved)
    return len(unresolved)


def context_mapping_for(row: MetadataRow) -> tuple[str, str, str, str]:
    industry_key = normalized_text(row.industry)
    sector_key = normalized_text(row.sector)
    if industry_key in YAHOO_INDUSTRY_CONTEXT_BENCHMARK:
        name, symbol = YAHOO_INDUSTRY_CONTEXT_BENCHMARK[industry_key]
        return name, symbol, "TWF_EXACT_RULE_V1", f"INDUSTRY:{row.industry}"
    if sector_key in YAHOO_SECTOR_CONTEXT_BENCHMARK:
        name, symbol = YAHOO_SECTOR_CONTEXT_BENCHMARK[sector_key]
        return name, symbol, "TWF_EXACT_RULE_V1", f"SECTOR:{row.sector}"
    return "", "", "", ""


def validate_snapshot(
    rows: list[MetadataRow],
    *,
    relative_ranking_applied: bool,
    minimum_universe_size: int,
    minimum_sector_coverage: float,
    minimum_market_cap_coverage: float,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    total = len(rows)

    if relative_ranking_applied and total < minimum_universe_size:
        errors.append(
            f"full universe has {total} rows; required minimum is {minimum_universe_size}"
        )

    symbols = [row.symbol.upper() for row in rows]
    if len(symbols) != len(set(symbols)):
        errors.append("symbols are not unique")
    isins = [row.isin.upper() for row in rows if row.isin]
    if len(isins) != len(set(isins)):
        errors.append("non-empty ISIN values are not unique")

    invalid_caps = [
        row.symbol for row in rows if row.market_cap and (parse_int(row.market_cap) or 0) <= 0
    ]
    if invalid_caps:
        errors.append(f"non-positive or malformed market cap: {','.join(invalid_caps[:10])}")

    with_sector = sum(bool(row.sector) for row in rows)
    with_market_cap = sum((parse_int(row.market_cap) or 0) > 0 for row in rows)
    sector_coverage = with_sector / total * 100 if total else 0.0
    cap_coverage = with_market_cap / total * 100 if total else 0.0
    if relative_ranking_applied and sector_coverage < minimum_sector_coverage:
        errors.append(
            f"sector coverage {sector_coverage:.2f}% is below {minimum_sector_coverage:.2f}%"
        )
    if relative_ranking_applied and cap_coverage < minimum_market_cap_coverage:
        errors.append(
            f"market-cap coverage {cap_coverage:.2f}% is below {minimum_market_cap_coverage:.2f}%"
        )

    ranked = sorted(
        (row for row in rows if row.instrument_kind == "EQUITY" and row.market_cap_rank),
        key=lambda row: int(row.market_cap_rank),
    )
    if relative_ranking_applied:
        expected_ranks = list(range(1, len(ranked) + 1))
        actual_ranks = [int(row.market_cap_rank) for row in ranked]
        if actual_ranks != expected_ranks:
            errors.append("market-cap rank is not contiguous")
        for row in ranked:
            rank = int(row.market_cap_rank)
            if row.market_cap_category != market_cap_category(rank):
                errors.append(f"market-cap category transition invalid for {row.symbol}")
            if row.twf_cap_tier != twf_cap_tier(rank):
                errors.append(f"TWF cap-tier transition invalid for {row.symbol}")
    else:
        ranked_fields = [
            row.symbol
            for row in rows
            if any(
                (
                    row.market_cap_rank,
                    row.market_cap_category,
                    row.market_cap_category_method,
                    row.twf_cap_tier,
                    row.twf_cap_tier_method,
                )
            )
        ]
        if ranked_fields:
            errors.append("partial universe contains rank/category fields")

    run_identities = {
        (row.metadata_schema_version, row.dataset_run_id, row.dataset_generated_at) for row in rows
    }
    if len(run_identities) != 1 or any(
        not part for part in next(iter(run_identities), ("", "", ""))
    ):
        errors.append("dataset run identity is missing or inconsistent")

    duplicate_note_symbols = [row.symbol for row in rows if has_duplicate_notes(row.notes)]
    if duplicate_note_symbols:
        errors.append(f"duplicate notes found: {','.join(duplicate_note_symbols[:10])}")

    for row in rows:
        expected = context_mapping_for(row)
        actual = (
            row.context_benchmark,
            row.context_benchmark_symbol,
            row.benchmark_mapping_source,
            row.benchmark_mapping_basis,
        )
        if actual != expected:
            errors.append(f"context benchmark is not exact-match-derived for {row.symbol}")
        if (
            normalized_text(row.industry) == "credit services"
            and row.context_benchmark == "NIFTY IT"
        ):
            errors.append(f"Credit Services incorrectly mapped to NIFTY IT for {row.symbol}")

    unresolved = len(unresolved_rows(rows))
    if unresolved:
        warnings.append(f"{unresolved} rows remain unresolved")
    return ValidationReport(tuple(dict.fromkeys(errors)), tuple(warnings))


def resolution_is_complete(value: str) -> bool:
    return value in {"RESOLVED", "RESOLVED_INHERITED"}


def build_change_summary(
    rows: list[MetadataRow], seed: dict[str, dict[str, str]]
) -> dict[str, Any]:
    if not seed:
        return {"seed_provided": False}

    current = {canonical_key(row.isin, row.symbol): row for row in rows}
    current_keys = set(current)
    seed_keys = set(seed)
    added = sorted(current[key].symbol for key in current_keys - seed_keys)
    removed = sorted(clean(seed[key].get("symbol")) for key in seed_keys - current_keys)

    fields = {
        "sector_changed": "sector",
        "industry_changed": "industry",
        "market_cap_changed": "market_cap",
        "market_cap_category_changed": "market_cap_category",
        "twf_cap_tier_changed": "twf_cap_tier",
    }
    details: dict[str, list[str]] = {name: [] for name in fields}
    newly_unresolved: list[str] = []
    newly_resolved: list[str] = []
    for key in sorted(current_keys & seed_keys):
        row = current[key]
        old = seed[key]
        for name, field_name in fields.items():
            if clean(getattr(row, field_name)) != clean(old.get(field_name)):
                details[name].append(row.symbol)
        was_resolved = resolution_is_complete(clean(old.get("resolution_status")))
        is_resolved = resolution_is_complete(row.resolution_status)
        if was_resolved and not is_resolved:
            newly_unresolved.append(row.symbol)
        elif not was_resolved and is_resolved:
            newly_resolved.append(row.symbol)

    summary: dict[str, Any] = {
        "seed_provided": True,
        "rows_added": len(added),
        "rows_removed": len(removed),
        "newly_unresolved": len(newly_unresolved),
        "newly_resolved": len(newly_resolved),
        "details": {
            "rows_added": added,
            "rows_removed": removed,
            "newly_unresolved": newly_unresolved,
            "newly_resolved": newly_resolved,
        },
    }
    for name, symbols in details.items():
        summary[name] = len(symbols)
        cast(dict[str, list[str]], summary["details"])[name] = symbols
    return summary


def summarize(
    rows: list[MetadataRow],
    *,
    dataset_run: DatasetRun,
    relative_ranking_applied: bool,
    unresolved_count: int,
    processed_this_run: int,
    validation: ValidationReport,
    change_summary: dict[str, Any],
) -> dict[str, Any]:
    sector_counts: dict[str, int] = {}
    market_cap_category_counts: dict[str, int] = {}
    twf_tier_counts: dict[str, int] = {}
    resolution_counts: dict[str, int] = {}
    benchmark_counts: dict[str, int] = {}
    instrument_kind_counts: dict[str, int] = {}
    with_sector = with_industry = with_market_cap = with_benchmark = 0

    for row in rows:
        resolution_counts[row.resolution_status] = (
            resolution_counts.get(row.resolution_status, 0) + 1
        )
        instrument_kind_counts[row.instrument_kind] = (
            instrument_kind_counts.get(row.instrument_kind, 0) + 1
        )
        if row.sector:
            with_sector += 1
            sector_counts[row.sector] = sector_counts.get(row.sector, 0) + 1
        if row.industry:
            with_industry += 1
        if (parse_int(row.market_cap) or 0) > 0:
            with_market_cap += 1
        if row.market_cap_category:
            market_cap_category_counts[row.market_cap_category] = (
                market_cap_category_counts.get(row.market_cap_category, 0) + 1
            )
        if row.twf_cap_tier:
            twf_tier_counts[row.twf_cap_tier] = twf_tier_counts.get(row.twf_cap_tier, 0) + 1
        if row.context_benchmark:
            with_benchmark += 1
            benchmark_counts[row.context_benchmark] = (
                benchmark_counts.get(row.context_benchmark, 0) + 1
            )

    total = len(rows)
    result: dict[str, Any] = {
        "metadata_schema_version": int(dataset_run.metadata_schema_version),
        "dataset_run_id": dataset_run.dataset_run_id,
        "dataset_generated_at": dataset_run.dataset_generated_at,
        "utility_version": UTILITY_VERSION,
        "generated_at": now_iso(),
        "total_rows": total,
        "with_sector": with_sector,
        "sector_coverage_percent": round(with_sector / total * 100 if total else 0.0, 2),
        "with_industry": with_industry,
        "industry_coverage_percent": round(with_industry / total * 100 if total else 0.0, 2),
        "with_market_cap": with_market_cap,
        "market_cap_coverage_percent": round(with_market_cap / total * 100 if total else 0.0, 2),
        "with_context_benchmark": with_benchmark,
        "resolution_counts": dict(sorted(resolution_counts.items())),
        "instrument_kind_counts": dict(sorted(instrument_kind_counts.items())),
        "market_cap_category_counts": dict(sorted(market_cap_category_counts.items())),
        "twf_cap_tier_counts": dict(sorted(twf_tier_counts.items())),
        "sector_counts": dict(sorted(sector_counts.items())),
        "context_benchmark_counts": dict(sorted(benchmark_counts.items())),
        "market_cap_category_method": MARKET_CAP_CATEGORY_METHOD,
        "twf_cap_tier_method": TWF_CAP_TIER_METHOD,
        "relative_ranking_applied": relative_ranking_applied,
        "processed_this_run": processed_this_run,
        "unresolved_output_rows": unresolved_count,
        "validation": validation.as_dict(),
        "change_summary": change_summary,
        "sources": {
            "universe": "NSE official bulk equity list",
            "classification": "optional NSE/NSE Indices bulk CSV",
            "enrichment": "optional Yahoo sector/industry/market cap",
            "context_benchmark": "TWF exact normalized analytical mapping",
        },
        "notes": [
            (
                "market_cap_category uses relative ranks 1-100 LARGE, 101-250 MID, "
                "251+ SMALL and is not claimed as AMFI-sourced data."
            ),
            "twf_cap_tier uses ranks 1-100 LARGE, 101-250 MID, 251-1000 SMALL, 1001+ MICRO.",
            "Context benchmark is an analytical mapping, not official index membership.",
            (
                "Benchmark mapping uses exact normalized values only; loose substring "
                "matching is prohibited."
            ),
            "Yahoo enrichment is offline and is not a runtime Scanner or Watchlist dependency.",
            "NSE per-symbol quote-equity API is intentionally not used.",
        ],
    }
    if not relative_ranking_applied:
        result["ranking_note"] = (
            "Relative market-cap rank/categories intentionally omitted because "
            "--limit produced a partial universe."
        )
    return result


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a validated TWF-ready NSE metadata snapshot."
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        help="Local NSE EQUITY_L.csv; otherwise download the official bulk CSV.",
    )
    parser.add_argument(
        "--classification-csv",
        type=Path,
        help="Optional bulk NSE/NSE Indices classification CSV.",
    )
    parser.add_argument(
        "--seed-csv",
        type=Path,
        help="Prior metadata snapshot reused before refresh; V3/V3.1 aliases supported.",
    )
    parser.add_argument("--use-yahoo", action="store_true")
    parser.add_argument("--refresh-market-cap-only", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--unresolved-output", type=Path, default=DEFAULT_UNRESOLVED)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Process first N rows; 0 means all.")
    parser.add_argument("--yahoo-pause", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument(
        "--minimum-universe-size",
        type=int,
        default=2001,
        help="Minimum row count for a full snapshot (default: 2001, i.e. >2000).",
    )
    parser.add_argument("--min-sector-coverage", type=float, default=80.0)
    parser.add_argument("--min-market-cap-coverage", type=float, default=75.0)
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    return parser


def choose_dataset_run(existing: Iterable[MetadataRow], checkpoint: CheckpointState) -> DatasetRun:
    existing_run = dataset_run_from_rows(existing)
    if existing_run and checkpoint.dataset_run and existing_run != checkpoint.dataset_run:
        raise ValueError("Existing output and checkpoint have different dataset run identity")
    return existing_run or checkpoint.dataset_run or new_dataset_run()


def checkpoint_rows(
    rows: list[MetadataRow],
    output_path: Path,
    checkpoint_path: Path,
    completed: set[str],
    dataset_run: DatasetRun,
) -> None:
    inherit_rights_entitlement_metadata(rows)
    apply_market_cap_ranking(rows, allow_relative_ranking=False)
    assign_dataset_run(rows, dataset_run)
    write_main_csv(partial_output_path(output_path), rows)
    save_checkpoint(checkpoint_path, completed, dataset_run)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)
    if args.refresh_market_cap_only and not args.use_yahoo:
        raise SystemExit("--refresh-market-cap-only requires --use-yahoo")
    if args.refresh_market_cap_only and not args.seed_csv:
        raise SystemExit("--refresh-market-cap-only requires --seed-csv")
    if args.limit < 0:
        raise SystemExit("--limit cannot be negative")

    output_path: Path = args.output
    unresolved_path: Path = args.unresolved_output
    summary_path: Path = args.summary_output
    checkpoint_path: Path = args.checkpoint
    for path in (output_path, unresolved_path, summary_path, checkpoint_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    universe = load_universe(args)
    if args.limit > 0:
        universe = universe[: args.limit]
        logging.info("Limit applied: %d rows", len(universe))

    by_isin, by_symbol = load_bulk_classification(args.classification_csv)
    seed = load_seed_csv(args.seed_csv)
    checkpoint = load_checkpoint(checkpoint_path) if args.resume else CheckpointState(frozenset())
    resume_source = partial_output_path(output_path)
    if not resume_source.exists():
        resume_source = output_path
    existing = load_existing_output(resume_source) if args.resume else {}
    dataset_run = choose_dataset_run(existing.values(), checkpoint)
    assign_dataset_run(existing.values(), dataset_run)
    completed = set(existing) | set(checkpoint.completed_keys)
    rows_by_key: dict[str, MetadataRow] = dict(existing)
    logging.info("Dataset run: %s", dataset_run.dataset_run_id)
    if args.resume:
        logging.info("Resume mode: %d existing output rows", len(existing))

    processed_now = 0
    try:
        for index, item in enumerate(universe, start=1):
            key = canonical_key(item.isin, item.symbol)
            if args.resume and key in completed:
                continue
            logging.info("[%d/%d] %s %s", index, len(universe), item.symbol, item.company_name)
            row = metadata_row_from_universe(item, dataset_run)
            apply_seed(row, seed)
            apply_bulk_classification(row, by_isin, by_symbol, args.classification_csv)
            if args.use_yahoo and row.instrument_kind == "EQUITY":
                yahoo_lookup(row, max(0.0, args.yahoo_pause), args.refresh_market_cap_only)
            apply_context_benchmark(row)
            if row.resolution_status == "UNRESOLVED" and (row.sector or row.industry):
                row.resolution_status = "RESOLVED"
                row.classification_completeness = (
                    "SECTOR_INDUSTRY" if row.sector and row.industry else "PARTIAL"
                )
            if row.resolution_status == "UNRESOLVED" and row.instrument_kind == "EQUITY":
                row.notes = append_note_unique(row.notes, "NO_SECTOR_INDUSTRY_RESOLUTION")
            row.retrieved_at = now_iso()
            rows_by_key[key] = row
            completed.add(key)
            processed_now += 1
            if args.checkpoint_every > 0 and processed_now % args.checkpoint_every == 0:
                checkpoint_rows(
                    list(rows_by_key.values()),
                    output_path,
                    checkpoint_path,
                    completed,
                    dataset_run,
                )
    except KeyboardInterrupt:
        logging.warning("Interrupted; saving atomic partial output and checkpoint")
        checkpoint_rows(
            list(rows_by_key.values()),
            output_path,
            checkpoint_path,
            completed,
            dataset_run,
        )
        return 130

    rows = list(rows_by_key.values())
    inherit_rights_entitlement_metadata(rows)
    for row in rows:
        apply_context_benchmark(row)
    relative_ranking_applied = args.limit <= 0
    apply_market_cap_ranking(rows, allow_relative_ranking=relative_ranking_applied)
    assign_dataset_run(rows, dataset_run)
    validation = validate_snapshot(
        rows,
        relative_ranking_applied=relative_ranking_applied,
        minimum_universe_size=args.minimum_universe_size,
        minimum_sector_coverage=args.min_sector_coverage,
        minimum_market_cap_coverage=args.min_market_cap_coverage,
    )
    change_summary = build_change_summary(rows, seed)
    unresolved_count = len(unresolved_rows(rows))
    summary = summarize(
        rows,
        dataset_run=dataset_run,
        relative_ranking_applied=relative_ranking_applied,
        unresolved_count=unresolved_count,
        processed_this_run=processed_now,
        validation=validation,
        change_summary=change_summary,
    )

    if not validation.passed:
        checkpoint_rows(rows, output_path, checkpoint_path, completed, dataset_run)
        atomic_write_json(summary_path, summary)
        for error in validation.errors:
            logging.error("Validation: %s", error)
        return 2

    write_main_csv(output_path, rows)
    write_unresolved_csv(unresolved_path, rows)
    save_checkpoint(checkpoint_path, completed, dataset_run)
    atomic_write_json(summary_path, summary)
    partial_output_path(output_path).unlink(missing_ok=True)

    logging.info(
        "Done: total=%d sector=%d (%.2f%%) market_cap=%d (%.2f%%) unresolved=%d",
        summary["total_rows"],
        summary["with_sector"],
        summary["sector_coverage_percent"],
        summary["with_market_cap"],
        summary["market_cap_coverage_percent"],
        unresolved_count,
    )
    if change_summary.get("seed_provided"):
        logging.info("Change summary: %s", json.dumps(change_summary, sort_keys=True))
    logging.info("Main CSV: %s", output_path.resolve())
    logging.info("Unresolved CSV: %s", unresolved_path.resolve())
    logging.info("Summary JSON: %s", summary_path.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
