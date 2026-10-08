"""Scanner APIs: owner-scoped, explicit real mode, no execution shortcut."""

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from twf.api.auth import require_origin
from twf.api.mcp import Manager, Who
from twf.api.watchlists import WatchlistNews, reject_system_write
from twf.brokers.contracts import Instrument
from twf.brokers.order_service import OrderService, executable
from twf.brokers.service import Principal
from twf.discovery.dhan_credentials import DhanCredentialCapture, DhanCredentialManager
from twf.discovery.domain import InstrumentIdentity
from twf.discovery.market_intelligence import MarketIntelligenceBatch, TapTideMarketIntelligence
from twf.scanner_v2.contracts import (
    FIELD_SPECS,
    SavedInput,
    ScanConfig,
    compatible_comparison_fields,
)
from twf.scanner_v2.service import ScannerService
from twf.scanner_v2.tapetide import TapTideScanner
from twf.scanner_v2.templates import templates
from twf.watchlists.contracts import AddItems, SourceMetadata
from twf.watchlists.reference import ReferenceSnapshot
from twf.watchlists.service import WatchlistFailure, WatchlistService

router = APIRouter(prefix="/api/v1/scanner", tags=["Scanner V2"])


def service(request: Request, who: Who) -> ScannerService:
    return ScannerService(
        request.app.state.session_factory,
        who.owner_id,
        request.app.state.system_universes,
    )


@router.get("/catalog")
def catalog(who: Who, manager: Manager) -> dict[str, Any]:
    ready, _, _ = TapTideMarketIntelligence(manager, who).readiness()
    return {
        "fields": [
            {
                "field": field,
                "category": spec.category,
                "label": spec.label,
                "enabled": ready if spec.category == "Fundamentals (TapTide)" else True,
                "field_type": spec.field_type.value,
                "operators": list(spec.operators),
                "default_operator": spec.default_operator,
                "default_value": spec.default_value,
                "comparison_fields": list(compatible_comparison_fields(field)),
                "enum_values": list(spec.enum_values),
                "minimum": spec.minimum,
                "maximum": spec.maximum,
                "minimum_exclusive": spec.minimum_exclusive,
                "unit": spec.unit,
            }
            for field, spec in FIELD_SPECS.items()
        ],
        "templates": templates(),
        "max_universe": 20,
        "universes": {
            "WATCHLIST": True,
            "CUSTOM": True,
            "INDEX": False,
            "SECTOR": False,
            "MARKET": False,
        },
        "universe_limitation": (
            "No complete constituent feed is configured. "
            "Use an explicit Watchlist or Custom universe."
        ),
    }


@router.get("/saved")
def saved(request: Request, who: Who) -> list[dict[str, Any]]:
    return service(request, who).saved()


@router.post("/saved", dependencies=[Depends(require_origin)])
def save(payload: SavedInput, request: Request, who: Who) -> dict[str, Any]:
    return service(request, who).save(payload)


@router.patch("/saved/{key}", dependencies=[Depends(require_origin)])
def update(key: UUID, payload: SavedInput, request: Request, who: Who) -> dict[str, Any]:
    return service(request, who).save(payload, key)


@router.get("/runs")
def history(request: Request, who: Who) -> list[dict[str, Any]]:
    return service(request, who).history()


@router.get("/runs/{key}")
def run(key: UUID, request: Request, who: Who) -> dict[str, Any]:
    return service(request, who).run(key)


def market(request: Request, who: Who) -> DhanCredentialCapture:
    credentials = cast(DhanCredentialManager, request.app.state.dhan_credentials)
    return credentials.capture(who.owner_id, ready_only=True)


Market = Annotated[DhanCredentialCapture, Depends(market)]


@router.post("/runs", dependencies=[Depends(require_origin)])
async def execute(
    payload: ScanConfig, request: Request, who: Who, capture: Market, manager: Manager
) -> dict[str, Any]:
    async def reference_values(selected: InstrumentIdentity) -> dict[str, Any]:
        ref = await request.app.state.watchlist_reference.read(manager, who, selected)
        return cast(dict[str, Any], ref.model_dump(mode="json"))

    return await service(request, who).execute(
        payload,
        capture.provider,
        capture.status.generation,
        request.app.state.scanner_history,
        reference_values,
    )


@router.get("/movers")
async def movers(request: Request, who: Who, manager: Manager) -> dict[str, Any]:
    return await TapTideScanner(TapTideMarketIntelligence(manager, who)).read()


@router.post("/provider-screen", dependencies=[Depends(require_origin)])
async def provider_screen(payload: ScanConfig, who: Who, manager: Manager) -> dict[str, Any]:
    return await TapTideScanner(TapTideMarketIntelligence(manager, who)).read(payload)


def instrument(request: Request, who: Who, key: UUID, identity: UUID) -> InstrumentIdentity:
    record = service(request, who).run(key)
    for row in record["rows"]:
        if row.get("instrument", {}).get("instrument_id") == str(identity):
            return InstrumentIdentity.model_validate(row["instrument"])
    raise WatchlistFailure("SCAN_INSTRUMENT_NOT_FOUND", 404)


@router.post("/runs/{key}/watchlists/{watchlist_id}", dependencies=[Depends(require_origin)])
def add(
    key: UUID, watchlist_id: UUID, payload: AddItems, request: Request, who: Who
) -> dict[str, Any]:
    reject_system_write(watchlist_id, request)
    record = service(request, who).run(key)
    matches = {
        UUID(r["instrument"]["instrument_id"]): InstrumentIdentity.model_validate(r["instrument"])
        for r in record["rows"]
        if r["outcome"] == "MATCH"
    }
    if not set(payload.instrument_ids).issubset(matches):
        raise WatchlistFailure("ONLY_MATCHED_RESULTS_CAN_BE_ADDED", 422)
    return WatchlistService(request.app.state.session_factory, who.owner_id).add(
        watchlist_id,
        tuple(matches[i] for i in dict.fromkeys(payload.instrument_ids)),
        SourceMetadata(source="scanner", run_id=key),
    )


@router.get("/runs/{key}/items/{identity}/reference")
async def reference(
    key: UUID, identity: UUID, request: Request, who: Who, manager: Manager
) -> ReferenceSnapshot:
    selected = instrument(request, who, key, identity)
    return cast(
        ReferenceSnapshot, await request.app.state.watchlist_reference.read(manager, who, selected)
    )


@router.get("/runs/{key}/items/{identity}/news")
async def news(
    key: UUID, identity: UUID, request: Request, who: Who, manager: Manager
) -> MarketIntelligenceBatch:
    return await WatchlistNews(manager, who, request.app.state.market_intelligence_cache).observe(
        (instrument(request, who, key, identity),)
    )


@router.get("/runs/{key}/items/{identity}/broker-instrument")
async def broker_instrument(
    key: UUID, identity: UUID, account_id: UUID, request: Request, who: Who
) -> Instrument:
    selected = instrument(request, who, key, identity)
    if selected.segment != "EQ":
        raise WatchlistFailure("NON_TRADABLE_INSTRUMENT", 422)
    catalog = await OrderService(request.app.state.broker_service).catalog(
        Principal(who.owner_id, who.session_hash), account_id
    )
    matches = [
        i
        for i in catalog
        if executable(i)
        and i.symbol == selected.symbol
        and i.exchange == selected.exchange
        and i.kind == "EQ"
    ]
    if len(matches) != 1:
        raise WatchlistFailure("EXACT_BROKER_CONTRACT_UNAVAILABLE_USE_BROKERS", 422)
    return matches[0]
