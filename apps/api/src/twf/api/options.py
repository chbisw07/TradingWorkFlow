"""Owner-scoped read-only canonical option-chain endpoints."""

from datetime import date
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from starlette.responses import JSONResponse

from twf.api.brokers import Who
from twf.api.errors import error_response
from twf.discovery.dhan_credentials import DhanCredentialManager
from twf.discovery.market_data import DhanMarketDataProvider
from twf.options.chain_contracts import OptionChainRequest, OptionChainSnapshot
from twf.options.chain_service import ChainFailure, OptionChainService
from twf.options.dhan_chain import DhanOptionChainSource

router = APIRouter(prefix="/api/v1/options", tags=["Canonical option chains"])


class OptionChainRegistry:
    def __init__(self) -> None:
        self.sources: dict[tuple[UUID, int], DhanOptionChainSource] = {}

    def get(
        self, owner: UUID, generation: int, provider: DhanMarketDataProvider
    ) -> DhanOptionChainSource:
        key = owner, generation
        for old in tuple(self.sources):
            if old[0] == owner and old != key:
                del self.sources[old]
        if key not in self.sources or self.sources[key].provider is not provider:
            if len(self.sources) >= 64:
                del self.sources[next(iter(self.sources))]
            self.sources[key] = DhanOptionChainSource(provider)
        return self.sources[key]


def service(request: Request, who: Who) -> OptionChainService:
    manager = cast(DhanCredentialManager, request.app.state.dhan_credentials)
    capture = manager.capture(who.user_id, ready_only=True)
    if not isinstance(capture.provider, DhanMarketDataProvider):
        raise ChainFailure("provider_unavailable", 503)
    registry = cast(OptionChainRegistry, request.app.state.option_chains)
    return OptionChainService(
        registry.get(who.user_id, capture.status.generation, capture.provider)
    )


async def chain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ChainFailure)
    response = error_response(
        request, exc.status, exc.code, "Option chain data is unavailable for this request."
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/underlyings")
async def underlyings(
    request: Request,
    response: Response,
    who: Who,
    query: str = Query(default="", max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
) -> tuple[str, ...]:
    response.headers["Cache-Control"] = "private, no-store"
    return await service(request, who).underlyings(query, limit)


@router.get("/expiries")
async def expiries(
    request: Request,
    response: Response,
    who: Who,
    underlying: str = Query(min_length=1, max_length=80),
) -> tuple[date, ...]:
    response.headers["Cache-Control"] = "private, no-store"
    return await service(request, who).expiries(underlying.strip().upper())


@router.get("/chain")
async def chain(
    request: Request,
    response: Response,
    who: Who,
    query: Annotated[OptionChainRequest, Query()],
) -> OptionChainSnapshot:
    response.headers["Cache-Control"] = "private, no-store"
    return await service(request, who).snapshot(query)
