"""Personal watchlists. No execution endpoint and no credentials in responses."""

import csv
import io
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.responses import JSONResponse

from twf.api.auth import require_origin
from twf.api.errors import error_response
from twf.api.mcp import Manager, Who
from twf.brokers.contracts import Instrument
from twf.brokers.order_service import OrderService, executable
from twf.brokers.service import Principal
from twf.discovery.dhan_credentials import DhanCredentialManager
from twf.discovery.market_data import DhanMarketDataProvider, MarketDataFailure, _stable
from twf.discovery.market_intelligence import (
    IntelligenceKind,
    MarketIntelligenceBatch,
    TapTideMarketIntelligence,
)
from twf.watchlists.catalog import WatchlistCatalog, kind
from twf.watchlists.contracts import (
    AddItems,
    CreateWatchlist,
    ImportItems,
    Kind,
    NoteInput,
    SourceMetadata,
    TransferItems,
    UniverseSnapshot,
    UpdateWatchlist,
)
from twf.watchlists.market import WatchlistHistoryCache, WatchlistQuoteCache
from twf.watchlists.reference import ReferenceSnapshot, WatchlistReferenceCache
from twf.watchlists.service import WatchlistFailure, WatchlistService

router = APIRouter(prefix="/api/v1/watchlists", tags=["Watchlists"])


def service(request: Request, who: Who) -> WatchlistService:
    return WatchlistService(request.app.state.session_factory, who.owner_id)


Service = Annotated[WatchlistService, Depends(service)]


def catalog(request: Request, who: Who) -> WatchlistCatalog:
    credentials = cast(DhanCredentialManager, request.app.state.dhan_credentials)
    capture = credentials.capture(who.owner_id, ready_only=True)
    if not isinstance(capture.provider, DhanMarketDataProvider):
        raise WatchlistFailure("DHAN_NOT_READY", 503)
    return WatchlistCatalog(capture.provider)


Catalog = Annotated[WatchlistCatalog, Depends(catalog)]


async def watchlist_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, WatchlistFailure)
    response = error_response(
        request,
        exc.status,
        exc.code,
        "Watchlist request could not be completed. " + exc.code.replace("_", " ").lower() + ".",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("")
def lists(service: Service) -> list[dict[str, Any]]:
    return service.list()


@router.post("", dependencies=[Depends(require_origin)], status_code=201)
def create(payload: CreateWatchlist, service: Service) -> dict[str, Any]:
    return service.create(payload)


@router.get("/instruments")
async def search(
    catalog: Catalog,
    q: str = Query(min_length=1, max_length=80),
    instrument_type: Kind | None = None,
) -> list[dict[str, Any]]:
    try:
        return [
            {"instrument": i.model_dump(mode="json"), "kind": kind(i)}
            for i in await catalog.search(q, instrument_type)
        ]
    except MarketDataFailure as exc:
        raise WatchlistFailure(exc.code.value, 503) from None


@router.get("/{key}")
def detail(key: UUID, service: Service) -> dict[str, Any]:
    return service.detail(key)


@router.patch("/{key}", dependencies=[Depends(require_origin)])
def update(key: UUID, payload: UpdateWatchlist, service: Service) -> dict[str, Any]:
    return service.update(key, payload)


@router.post("/{key}/items", dependencies=[Depends(require_origin)])
async def add(key: UUID, payload: AddItems, service: Service, catalog: Catalog) -> dict[str, Any]:
    service.detail(key)  # Owner authorization BEFORE provider I/O; DB scope has closed.
    try:
        instruments = await catalog.resolve(payload.instrument_ids)
    except MarketDataFailure as exc:
        raise WatchlistFailure(exc.code.value, 503) from None
    if len(instruments) != len(set(payload.instrument_ids)):
        raise WatchlistFailure("UNRESOLVED_INSTRUMENT", 422)
    return service.add(key, instruments, payload.source_metadata)


@router.delete("/{key}/items/{instrument_id}", dependencies=[Depends(require_origin)])
def remove(key: UUID, instrument_id: UUID, service: Service) -> dict[str, bool]:
    service.remove(key, (instrument_id,))
    return {"removed": True}


@router.post("/{key}/remove", dependencies=[Depends(require_origin)])
def remove_many(key: UUID, payload: AddItems, service: Service) -> dict[str, bool]:
    service.remove(key, payload.instrument_ids)
    return {"removed": True}


@router.post("/{key}/transfer", dependencies=[Depends(require_origin)])
def transfer(key: UUID, payload: TransferItems, service: Service) -> dict[str, Any]:
    return service.transfer(key, payload.target_id, payload.instrument_ids, payload.move)


@router.post("/{key}/notes", dependencies=[Depends(require_origin)], status_code=201)
def note(key: UUID, payload: NoteInput, service: Service) -> dict[str, bool]:
    service.note(key, payload.text)
    return {"saved": True}


@router.get("/{key}/universe")
def universe(key: UUID, service: Service) -> UniverseSnapshot:
    return service.snapshot(key)


@router.get("/{key}/export")
def export(key: UUID, service: Service) -> Response:
    return Response(
        service.export(key),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="watchlist.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{key}/import", dependencies=[Depends(require_origin)])
async def import_csv(
    key: UUID, payload: ImportItems, service: Service, catalog: Catalog
) -> dict[str, Any]:
    service.detail(key)
    try:
        rows = list(csv.DictReader(io.StringIO(payload.csv)))
    except csv.Error:
        raise WatchlistFailure("INVALID_CSV", 422) from None
    if not rows or len(rows) > 100 or "canonical_symbol" not in rows[0]:
        raise WatchlistFailure("CSV_REQUIRES_CANONICAL_SYMBOL_MAX_100_ROWS", 422)
    try:
        instruments = await catalog.resolve_symbols(
            {(r.get("canonical_symbol") or "").strip().upper() for r in rows}
        )
    except MarketDataFailure as exc:
        raise WatchlistFailure(exc.code.value, 503) from None
    valid = []
    invalid = []
    for position, row in enumerate(rows, 2):
        symbol = (row.get("canonical_symbol") or "").strip().upper()
        matches = instruments.get(symbol, ())
        if len(matches) != 1:
            invalid.append(
                {"row": position, "symbol": symbol[:100], "reason": "UNRESOLVED_OR_AMBIGUOUS"}
            )
        else:
            valid.append(matches[0])
    result = service.add(key, tuple(valid), SourceMetadata(source="import"))
    return {**result, "invalid": invalid}


@router.get("/{key}/quotes")
async def quotes(key: UUID, service: Service, request: Request, who: Who) -> dict[str, Any]:
    snapshot = service.snapshot(key)
    credentials = cast(DhanCredentialManager, request.app.state.dhan_credentials)
    capture = credentials.capture(who.owner_id, ready_only=True)
    cache = cast(WatchlistQuoteCache, request.app.state.watchlist_quotes)
    return await cache.read(
        who.owner_id, capture.status.generation, capture.provider, snapshot.instruments
    )


@router.get("/{key}/items/{instrument_id}/chart")
async def chart(
    key: UUID,
    instrument_id: UUID,
    service: Service,
    request: Request,
    who: Who,
    period: str = Query(default="1M", pattern="^(1D|1W|1M|3M|1Y)$"),
) -> dict[str, Any]:
    snapshot = service.snapshot(key)
    instrument = next((i for i in snapshot.instruments if i.instrument_id == instrument_id), None)
    if instrument is None:
        raise WatchlistFailure("INSTRUMENT_NOT_FOUND", 404)
    credentials = cast(DhanCredentialManager, request.app.state.dhan_credentials)
    capture = credentials.capture(who.owner_id, ready_only=True)
    if capture.provider is None:
        return {"provider": "dhan", "bars": [], "error": "AUTH_REQUIRED"}
    interval, count = {
        "1D": ("5m", 75),
        "1W": ("1d", 5),
        "1M": ("1d", 22),
        "3M": ("1d", 66),
        "1Y": ("1d", 252),
    }[period]
    cache = cast(WatchlistHistoryCache, request.app.state.watchlist_history)
    return await cache.read(
        who.owner_id, capture.status.generation, capture.provider, instrument, interval, count
    )


class WatchlistNews(TapTideMarketIntelligence):
    tool_kinds = {
        "get_market_news": IntelligenceKind.NEWS_SENTIMENT,
        "get_stock_events": IntelligenceKind.CORPORATE_EVENT,
    }


@router.get("/{key}/items/{instrument_id}/news")
async def news(
    key: UUID, instrument_id: UUID, service: Service, request: Request, who: Who, manager: Manager
) -> MarketIntelligenceBatch:
    snapshot = service.snapshot(key)
    instrument = next((i for i in snapshot.instruments if i.instrument_id == instrument_id), None)
    if instrument is None:
        raise WatchlistFailure("INSTRUMENT_NOT_FOUND", 404)
    return await WatchlistNews(manager, who, request.app.state.market_intelligence_cache).observe(
        (instrument,)
    )


@router.get("/{key}/items/{instrument_id}/broker-instrument")
async def broker_instrument(
    key: UUID, instrument_id: UUID, account_id: UUID, service: Service, request: Request, who: Who
) -> Instrument:
    snapshot = service.snapshot(key)
    selected = next((i for i in snapshot.instruments if i.instrument_id == instrument_id), None)
    if selected is None or kind(selected) == "INDEX":
        raise WatchlistFailure("NON_TRADABLE_INSTRUMENT", 422)
    broker = OrderService(request.app.state.broker_service)
    instruments = await broker.catalog(Principal(who.owner_id, who.session_hash), account_id)
    exchange = (
        selected.exchange
        if kind(selected) == "EQUITY"
        else {"NSE": "NFO", "BSE": "BFO"}[selected.exchange]
    )
    expected_kind = {
        "EQUITY": "EQ",
        "FUTURE": "FUT",
        "OPTION": "CE" if selected.right == "CALL" else "PE",
    }[kind(selected)]
    # Equity uses the exact symbol. Derivatives use the catalog underlying identity
    # plus exact expiry/right/strike, because native contract-symbol formats differ.
    matches = [
        i
        for i in instruments
        if executable(i)
        and (
            i.symbol == selected.symbol
            if kind(selected) == "EQUITY"
            else (
                not selected.underlying.ambiguous
                and selected.underlying.mapping.id == "dhan-scrip-master-underlying"
                and bool(i.underlying)
                and selected.underlying.underlying_id
                == _stable(
                    "underlying", f"{selected.exchange}:{(i.underlying or '').strip().upper()}"
                )
            )
        )
        and i.exchange == exchange
        and i.kind == expected_kind
        and (
            kind(selected) == "EQUITY"
            or (
                i.expiry == (selected.expiry.date().isoformat() if selected.expiry else None)
                and (kind(selected) != "OPTION" or i.strike == selected.strike)
            )
        )
    ]
    if len(matches) != 1:
        raise WatchlistFailure("EXACT_BROKER_CONTRACT_UNAVAILABLE_USE_BROKERS", 422)
    return matches[0]


@router.get("/{key}/items/{instrument_id}/reference")
async def reference(
    key: UUID, instrument_id: UUID, service: Service, request: Request, who: Who, manager: Manager
) -> ReferenceSnapshot:
    snapshot = service.snapshot(key)
    instrument = next((i for i in snapshot.instruments if i.instrument_id == instrument_id), None)
    if instrument is None:
        raise WatchlistFailure("INSTRUMENT_NOT_FOUND", 404)
    cache = cast(WatchlistReferenceCache, request.app.state.watchlist_reference)
    return await cache.read(manager, who, instrument)
