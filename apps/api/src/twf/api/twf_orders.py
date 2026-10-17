"""Owner-scoped OE-2 manual TWF Order API. No Queue or broker execution routes."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import JSONResponse

from twf.api.auth import require_origin
from twf.api.brokers import Service, Who
from twf.api.errors import error_response
from twf.infrastructure.identity import AuthSession, User
from twf.orders.context import OrderContext, _SubsystemOriginIssuer, _TrustedSubsystemOrigin
from twf.orders.contracts import OrderEventView, OrderView, Source
from twf.orders.errors import OrderError, OrderErrorCode
from twf.orders.resolution import _bind_trusted_canonical_resolver
from twf.orders.service import OrderService
from twf.twf_orders.manual import ManualCreateInput, ManualCreation, ManualOrderInput, ManualPreview
from twf.twf_orders.manual import create as create_manual
from twf.twf_orders.manual import preview as preview_manual

router = APIRouter(prefix="/api/v1/twf-orders", tags=["TWF Orders"])


class _ReadOnlyResolver:
    def resolve(self, instrument_id: UUID) -> None:
        return None


def _reader(request: Request, who: Who) -> OrderService:
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    with factory() as db:
        user = db.get(User, who.user_id)
        login = db.get(AuthSession, who.session_hash)
        if user is None or login is None:
            raise OrderError(OrderErrorCode.UNAUTHORIZED, "Please sign in again")
        context = OrderContext.from_authenticated_session(user, login)
    return OrderService(factory, context, _bind_trusted_canonical_resolver(_ReadOnlyResolver()))


Reader = Annotated[OrderService, Depends(_reader)]


async def order_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, OrderError)
    status = {
        OrderErrorCode.UNAUTHORIZED: 401,
        OrderErrorCode.ORDER_NOT_FOUND: 404,
        OrderErrorCode.VERSION_CONFLICT: 409,
        OrderErrorCode.RETRYABLE_CONCURRENCY_CONFLICT: 409,
    }.get(exc.code, 422)
    response = error_response(request, status, exc.code.value, str(exc))
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("")
def list_orders(
    service: Reader, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> tuple[OrderView, ...]:
    return service.list_orders(limit=limit)


@router.get("/{order_id}")
def get_order(order_id: UUID, service: Reader) -> OrderView:
    return service.get_order(order_id)


@router.get("/{order_id}/history")
def history(order_id: UUID, service: Reader) -> tuple[OrderEventView, ...]:
    return service.get_order_history(order_id)


@router.post("/preview", dependencies=[Depends(require_origin)])
async def preview(payload: ManualOrderInput, who: Who, broker: Service) -> ManualPreview:
    return await preview_manual(broker, who, payload)


@router.post("", dependencies=[Depends(require_origin)])
async def create(payload: ManualCreateInput, who: Who, broker: Service) -> ManualCreation:
    return await create_manual(broker, who, payload)


async def _source_origin(
    request: Request,
    who: Who,
    source: Source,
    reference: UUID,
    broker: Service,
    payload: ManualOrderInput,
) -> _TrustedSubsystemOrigin:
    """Issue provenance only for a server-owned source containing this exact instrument."""
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from twf.brokers.contracts import BrokerFailure
    from twf.discovery.domain import InstrumentIdentity
    from twf.discovery.market_data import _stable
    from twf.infrastructure.scanner_v2 import ScannerRunRow
    from twf.twf_orders.manual import _resolve

    if source not in {Source.WATCHLIST, Source.SCANNER}:
        raise BrokerFailure("SOURCE_UNAVAILABLE", "This order source is not implemented.", 422)
    identity, _, _ = await _resolve(broker, who, payload)

    def same_instrument(candidate: InstrumentIdentity) -> bool:
        exchange = (
            candidate.exchange
            if identity.instrument_type == "EQUITY"
            else {"NSE": "NFO", "BSE": "BFO"}.get(candidate.exchange, candidate.exchange)
        )
        if exchange != identity.exchange:
            return False
        if identity.instrument_type == "EQUITY":
            return candidate.instrument_type == "EQUITY" and candidate.symbol == identity.symbol
        return (
            candidate.instrument_type == identity.instrument_type
            and (
                candidate.underlying.underlying_id == identity.underlying.underlying_id
                or (
                    candidate.underlying.mapping.id == "dhan-scrip-master-underlying"
                    and candidate.underlying.underlying_id
                    == _stable(
                        "underlying", f"{candidate.exchange}:{identity.underlying.source.native_id}"
                    )
                )
            )
            and (
                candidate.expiry_date
                or (
                    candidate.expiry.astimezone(ZoneInfo("Asia/Kolkata")).date()
                    if candidate.expiry
                    else None
                )
            )
            == identity.expiry_date
            and candidate.strike == identity.strike
            and candidate.right == identity.right
            and candidate.lot_size == identity.lot_size
        )

    matched = False
    if source == Source.SCANNER:
        with request.app.state.session_factory() as db:
            run = db.get(ScannerRunRow, reference)
            if run is None or run.owner_id != who.user_id:
                raise BrokerFailure("SOURCE_NOT_FOUND", "Order source not found.", 404)
            rows = run.payload.get("rows", [])
        for row in rows:
            if row.get("instrument"):
                matched = matched or same_instrument(
                    InstrumentIdentity.model_validate(row["instrument"])
                )
            contract = row.get("contract")
            if contract and identity.instrument_type != "EQUITY":
                matched = matched or (
                    {"NSE": "NFO", "BSE": "BFO"}.get(
                        contract.get("exchange"), contract.get("exchange")
                    )
                    == identity.exchange
                    and contract.get("underlying_symbol") == identity.underlying.source.native_id
                    and contract.get("expiry") == str(identity.expiry_date)
                    and contract.get("option_type")
                    == {"CALL": "CE", "PUT": "PE"}.get(identity.right or "")
                    and (
                        Decimal(str(contract["strike"]))
                        if contract.get("strike") is not None
                        else None
                    )
                    == identity.strike
                    and contract.get("lot_size") == identity.lot_size
                    and (
                        identity.instrument_type in {"OPTSTK", "OPTIDX"}
                        if contract.get("option_type")
                        else contract.get("instrument_type") == identity.instrument_type
                    )
                )
    else:
        from twf.api.watchlists import snapshot_for
        from twf.integrations.contracts import RequestContext
        from twf.integrations.mcp.contracts import Context
        from twf.watchlists.service import WatchlistService

        context = Context(
            owner_id=who.user_id,
            session_hash=who.session_hash,
            correlation=RequestContext(request_id=request.state.request_id),
        )
        snapshot = await snapshot_for(
            reference,
            WatchlistService(request.app.state.session_factory, who.user_id),
            request,
            context,
        )
        matched = any(same_instrument(candidate) for candidate in snapshot.instruments)
    if not matched:
        raise BrokerFailure(
            "SOURCE_INSTRUMENT_MISMATCH", "The exact instrument is not present in this source.", 422
        )
    return _SubsystemOriginIssuer(
        source, lambda owner, key: owner == who.user_id and key == str(reference) and matched
    ).issue(who.user_id, str(reference))


@router.post("/from/{source}/{reference}/preview", dependencies=[Depends(require_origin)])
async def sourced_preview(
    source: Source,
    reference: UUID,
    payload: ManualOrderInput,
    request: Request,
    who: Who,
    broker: Service,
) -> ManualPreview:
    origin = await _source_origin(request, who, source, reference, broker, payload)
    return await preview_manual(broker, who, payload, _origin=origin)


@router.post("/from/{source}/{reference}", dependencies=[Depends(require_origin)])
async def sourced_create(
    source: Source,
    reference: UUID,
    payload: ManualCreateInput,
    request: Request,
    who: Who,
    broker: Service,
) -> ManualCreation:
    origin = await _source_origin(request, who, source, reference, broker, payload)
    return await create_manual(broker, who, payload, _origin=origin)
