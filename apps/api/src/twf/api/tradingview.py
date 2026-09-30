"""Bounded read-only scan API; no arbitrary tool names or remote destinations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from starlette.responses import JSONResponse

from twf.api.auth import require_origin
from twf.api.errors import error_response
from twf.api.mcp import Manager, Who
from twf.discovery.domain import InstrumentIdentity, ScanDefinition, ScanProfileReference
from twf.discovery.providers import ProviderFailure
from twf.discovery.tradingview.provider import Execution, Status, TradingViewAdapter
from twf.integrations.contracts import Contract

router = APIRouter(prefix="/api/v1/scan-providers/tradingview", tags=["Scan providers"])


class ScanRequest(Contract):
    generation: int = Field(ge=0, strict=True)
    run_id: UUID
    definition: ScanDefinition
    profile: ScanProfileReference
    instruments: tuple[InstrumentIdentity, ...] = Field(min_length=1, max_length=64)


def adapter(request: Request, service: Manager) -> TradingViewAdapter:
    return TradingViewAdapter(service, request.app.state.settings.tradingview_scan)


Adapter = Annotated[TradingViewAdapter, Depends(adapter)]


@router.get("/{identity}/status")
def status(identity: UUID, who: Who, service: Adapter) -> Status:
    return service.status(who, identity)


@router.post("/{identity}/scan", dependencies=[Depends(require_origin)])
async def scan(identity: UUID, payload: ScanRequest, who: Who, service: Adapter) -> Execution:
    return await service.execute(
        who,
        identity,
        payload.generation,
        payload.definition,
        payload.profile,
        payload.instruments,
        payload.run_id,
    )


async def scan_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProviderFailure)
    code = exc.error.code.value
    status = {
        "AUTHORIZATION_FAILED": 403,
        "AUTHENTICATION_FAILED": 401,
        "INVALID_REQUEST": 422,
        "UNSUPPORTED_CAPABILITY": 422,
        "PROVENANCE_MISMATCH": 409,
        "TIMEOUT": 504,
        "RATE_LIMITED": 429,
    }.get(code, 503)
    response = error_response(
        request, status, code, "Scan provider could not complete this request."
    )
    response.headers["Cache-Control"] = "no-store"
    return response
