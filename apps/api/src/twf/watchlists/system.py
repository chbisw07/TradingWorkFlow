"""Application-owned catalogue for read-only system watchlist universes."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from twf.discovery.market_data import DhanMarketDataProvider
from twf.watchlists.catalog import WatchlistCatalog, kind
from twf.watchlists.contracts import UniverseSnapshot
from twf.watchlists.service import WatchlistFailure

_SYSTEM_ID_PREFIX = "https://tradingworkflow.local/system-universe/"
_SYMBOL = re.compile(r"^[A-Z0-9&.\-]+$")
_MAX_DOWNLOAD_BYTES = 512_000
_MAX_CONSTITUENTS = 600
_CACHE_TTL = timedelta(hours=24)
_STALE_LIMIT = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class SystemUniverseDefinition:
    code: str
    name: str
    description: str
    expected_count: int
    source_page: str | None
    constituent_url: str | None
    instrument_types: tuple[str, ...] = ("EQUITY",)
    enabled: bool = True
    pending_reason: str | None = None

    @property
    def id(self) -> UUID:
        return uuid5(NAMESPACE_URL, f"{_SYSTEM_ID_PREFIX}{self.code}")


DEFINITIONS: tuple[SystemUniverseDefinition, ...] = (
    SystemUniverseDefinition(
        "NIFTY_500",
        "Nifty 500",
        "Large, mid and small-cap equities represented by the Nifty 500 index.",
        500,
        "https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-500",
        "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    ),
    SystemUniverseDefinition(
        "NIFTY_SMALLCAP_250",
        "Nifty Smallcap 250",
        "Equities represented by the Nifty Smallcap 250 index.",
        250,
        "https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-smallcap-250",
        "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    ),
    SystemUniverseDefinition(
        "NIFTY_PHARMA",
        "Nifty Pharma",
        "Pharmaceutical-sector equities represented by the Nifty Pharma index.",
        20,
        "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-pharma",
        "https://nsearchives.nseindia.com/content/indices/ind_niftypharmalist.csv",
    ),
    SystemUniverseDefinition(
        "NIFTY_ENERGY",
        "Nifty Energy",
        "Energy-sector equities represented by the Nifty Energy index.",
        40,
        "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-energy",
        "https://nsearchives.nseindia.com/content/indices/ind_niftyenergylist.csv",
    ),
    SystemUniverseDefinition(
        "NIFTY_MIDCAP_100",
        "Nifty Midcap 100",
        "Mid-cap equities represented by the Nifty Midcap 100 index.",
        100,
        "https://www.niftyindices.com/indices/equity/broad-based-indices/NIFTY-Midcap-100",
        "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap100list.csv",
    ),
    SystemUniverseDefinition(
        "NIFTY_BANK",
        "Nifty Bank",
        "Banking equities represented by the Nifty Bank index.",
        14,
        "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-bank",
        "https://nsearchives.nseindia.com/content/indices/ind_niftybanklist.csv",
    ),
    SystemUniverseDefinition(
        "NIFTY_METAL",
        "Nifty Metal",
        "Metals-sector equities represented by the Nifty Metal index.",
        15,
        "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-metal",
        "https://nsearchives.nseindia.com/content/indices/ind_niftymetallist.csv",
    ),
    SystemUniverseDefinition(
        "NIFTY_REALTY",
        "Nifty Realty",
        "Real-estate equities represented by the Nifty Realty index.",
        10,
        "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-realty",
        "https://nsearchives.nseindia.com/content/indices/ind_niftyrealtylist.csv",
    ),
    SystemUniverseDefinition(
        "FNO_100",
        "F&O 100",
        "Proposed high-liquidity derivatives universe.",
        100,
        None,
        None,
        instrument_types=(),
        enabled=False,
        pending_reason="Definition pending",
    ),
    SystemUniverseDefinition(
        "FNO_50",
        "F&O 50",
        "Proposed compact high-liquidity derivatives universe.",
        50,
        None,
        None,
        instrument_types=(),
        enabled=False,
        pending_reason="Definition pending",
    ),
)

_BY_ID = {definition.id: definition for definition in DEFINITIONS}
_BY_CODE = {definition.code: definition for definition in DEFINITIONS}


@dataclass(frozen=True, slots=True)
class _Membership:
    symbols: tuple[str, ...]
    received_at: datetime
    freshness: str


FetchConstituents = Callable[[SystemUniverseDefinition], Awaitable[bytes]]


class SystemUniverseCatalog:
    """Central bounded cache for official system-universe memberships."""

    def __init__(self, fetcher: FetchConstituents | None = None) -> None:
        self._fetcher = fetcher or self._fetch_official
        self._cache: dict[str, _Membership] = {}
        self._locks = {definition.code: asyncio.Lock() for definition in DEFINITIONS}

    @staticmethod
    def definition(key: UUID | str) -> SystemUniverseDefinition | None:
        if isinstance(key, UUID):
            return _BY_ID.get(key)
        try:
            return _BY_ID.get(UUID(key))
        except ValueError:
            return _BY_CODE.get(key.upper())

    def summaries(self) -> list[dict[str, Any]]:
        return [self._summary(definition) for definition in DEFINITIONS]

    def _summary(self, definition: SystemUniverseDefinition) -> dict[str, Any]:
        cached = self._cache.get(definition.code)
        available_count = len(cached.symbols) if cached else definition.expected_count
        return {
            "id": str(definition.id),
            "name": definition.name,
            "description": definition.description,
            "count": available_count,
            "revision": self._revision(cached.symbols) if cached else 0,
            "created_at": None,
            "updated_at": cached.received_at.isoformat() if cached else None,
            "archived": False,
            "favorite": False,
            "pinned": False,
            "ordering": 0,
            "ownership_kind": "SYSTEM",
            "read_only": True,
            "system_code": definition.code,
            "enabled": definition.enabled,
            "availability": "READY" if definition.enabled else "DEFINITION_PENDING",
            "pending_reason": definition.pending_reason,
            "expected_count": definition.expected_count,
            "instrument_type_summary": list(definition.instrument_types),
            "source_reference": definition.source_page,
            "source_received_at": cached.received_at.isoformat() if cached else None,
            "freshness": cached.freshness if cached else "NOT_LOADED",
        }

    async def membership(self, key: UUID | str) -> tuple[SystemUniverseDefinition, _Membership]:
        definition = self.definition(key)
        if definition is None:
            raise WatchlistFailure("WATCHLIST_NOT_FOUND", 404)
        if not definition.enabled or definition.constituent_url is None:
            raise WatchlistFailure("SYSTEM_UNIVERSE_DEFINITION_PENDING", 409)

        now = datetime.now(UTC)
        cached = self._cache.get(definition.code)
        if cached is not None and now - cached.received_at <= _CACHE_TTL:
            return definition, cached

        async with self._locks[definition.code]:
            cached = self._cache.get(definition.code)
            now = datetime.now(UTC)
            if cached is not None and now - cached.received_at <= _CACHE_TTL:
                return definition, cached
            try:
                payload = await self._fetcher(definition)
                symbols = self._parse_csv(payload)
                membership = _Membership(symbols, now, "CURRENT")
                self._cache[definition.code] = membership
                return definition, membership
            except Exception as exc:
                if cached is not None and now - cached.received_at <= _STALE_LIMIT:
                    return definition, _Membership(cached.symbols, cached.received_at, "STALE")
                if isinstance(exc, WatchlistFailure):
                    raise
                raise WatchlistFailure("SYSTEM_UNIVERSE_UNAVAILABLE", 503) from exc

    async def detail(self, key: UUID | str, provider: DhanMarketDataProvider) -> dict[str, Any]:
        definition, membership = await self.membership(key)
        watchlist_catalog = WatchlistCatalog(provider)
        resolved = await watchlist_catalog.resolve_symbols(
            {f"NSE:{symbol}" for symbol in membership.symbols}
        )
        by_symbol = {}
        for symbol in membership.symbols:
            matches = tuple(
                item
                for item in resolved.get(f"NSE:{symbol}", ())
                if item.exchange.upper() == "NSE" and kind(item) == "EQUITY"
            )
            if len(matches) == 1:
                by_symbol[symbol] = matches[0]
        added_at = membership.received_at.isoformat()
        items = []
        for position, symbol in enumerate(membership.symbols):
            instrument = by_symbol.get(symbol)
            if instrument is None:
                continue
            items.append(
                {
                    "instrument": instrument.model_dump(mode="json"),
                    "kind": "EQUITY",
                    "ordering": position,
                    "added_at": added_at,
                    "source": {
                        "source": "built_in_watchlist",
                        "source_watchlist_id": str(definition.id),
                        "source_watchlist_code": definition.code,
                        "source_watchlist_name": definition.name,
                    },
                }
            )
        if not items:
            raise WatchlistFailure("SYSTEM_UNIVERSE_UNAVAILABLE", 503)
        detail = self._summary(definition)
        detail.update(
            {
                "count": len(items),
                "revision": self._revision(membership.symbols),
                "updated_at": membership.received_at.isoformat(),
                "items": items,
                "notes": [],
                "activity": [],
                "instrument_type_summary": list(definition.instrument_types),
                "unresolved_count": len(membership.symbols) - len(items),
                "availability": ("READY" if len(items) == len(membership.symbols) else "PARTIAL"),
                "freshness": membership.freshness,
            }
        )
        return detail

    async def snapshot(self, key: UUID | str, provider: DhanMarketDataProvider) -> UniverseSnapshot:
        detail = await self.detail(key, provider)
        return UniverseSnapshot.model_validate(
            {
                "watchlist_id": detail["id"],
                "name": detail["name"],
                "revision": detail["revision"],
                "captured_at": datetime.now(UTC),
                "ownership_kind": "SYSTEM",
                "system_code": detail["system_code"],
                "source_reference": detail["source_reference"],
                "source_updated_at": detail["source_received_at"],
                "instruments": [item["instrument"] for item in detail["items"]],
            }
        )

    @staticmethod
    async def _fetch_official(definition: SystemUniverseDefinition) -> bytes:
        assert definition.constituent_url is not None
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(8.0),
            headers={"Accept": "text/csv", "User-Agent": "TradingWorkFlow/1.0"},
        ) as client:
            response = await client.get(definition.constituent_url)
        if response.status_code != 200:
            raise WatchlistFailure("SYSTEM_UNIVERSE_SOURCE_FAILED", 503)
        payload = response.content
        if not payload or len(payload) > _MAX_DOWNLOAD_BYTES:
            raise WatchlistFailure("SYSTEM_UNIVERSE_SOURCE_INVALID", 503)
        return payload

    @staticmethod
    def _parse_csv(payload: bytes) -> tuple[str, ...]:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise WatchlistFailure("SYSTEM_UNIVERSE_SOURCE_INVALID", 503) from exc
        reader = csv.DictReader(io.StringIO(text))
        symbol_key = next(
            (key for key in reader.fieldnames or [] if key.strip().lower() == "symbol"),
            None,
        )
        if symbol_key is None:
            raise WatchlistFailure("SYSTEM_UNIVERSE_SOURCE_INVALID", 503)
        symbols: list[str] = []
        seen: set[str] = set()
        for row in reader:
            symbol = (row.get(symbol_key) or "").strip().upper()
            if not symbol or not _SYMBOL.fullmatch(symbol) or symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
            if len(symbols) > _MAX_CONSTITUENTS:
                raise WatchlistFailure("SYSTEM_UNIVERSE_SOURCE_INVALID", 503)
        if not symbols:
            raise WatchlistFailure("SYSTEM_UNIVERSE_SOURCE_INVALID", 503)
        return tuple(symbols)

    @staticmethod
    def _revision(symbols: tuple[str, ...]) -> int:
        if not symbols:
            return 0
        digest = hashlib.sha256("\n".join(symbols).encode()).digest()
        return int.from_bytes(digest[:4], "big")
