"""Owner-scoped Scan & Discover product API; no opportunity or trading authority."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.responses import JSONResponse

from twf.api.auth import Database, get_current_user, require_origin
from twf.api.errors import error_response
from twf.discovery.product import (
    CandidateDetail,
    DiscoverySettings,
    DiscoverySettingsUpdate,
    HistoricalScanDetail,
    LifecycleRequest,
    LLMExplanation,
    MarketContextSnapshot,
    PaginatedCandidates,
    ProductScanRequest,
    ProviderStatus,
    ScanResult,
    ScanSummary,
)
from twf.discovery.product_service import ProductFailure, ScanDiscoverService
from twf.infrastructure.identity import User

router = APIRouter(
    prefix="/api/v1/discovery",
    tags=["Scan & Discover"],
)


def use_cases(
    request: Request,
    response: Response,
    session: Database,
    user: Annotated[User, Depends(get_current_user)],
) -> ScanDiscoverService:
    response.headers["Cache-Control"] = "no-store"
    return ScanDiscoverService(session, user.id, getattr(request.state, "request_id", None))


Service = Annotated[ScanDiscoverService, Depends(use_cases)]


@router.get("/status")
def status(service: Service) -> tuple[ProviderStatus, ...]:
    return service.providers()


@router.get("/settings")
def settings(service: Service) -> DiscoverySettings:
    return service.settings()


@router.put("/settings", dependencies=[Depends(require_origin)])
def update_settings(payload: DiscoverySettingsUpdate, service: Service) -> DiscoverySettings:
    return service.save_settings(payload)


@router.post("/scans", dependencies=[Depends(require_origin)], status_code=201)
async def run_scan(payload: ProductScanRequest, service: Service, request: Request) -> ScanResult:
    result = await service.run_scan(payload)
    request.app.state.logger.info(
        "discovery_scan_completed",
        extra={
            "provider": result.summary.provider.value,
            "duration_ms": round(
                (result.summary.completed_at - result.summary.started_at).total_seconds() * 1000,
                3,
            ),
            "match_count": result.summary.match_count,
            "candidate_count": result.summary.candidate_count,
            "context_availability": result.summary.context_availability.value,
        },
    )
    return result


@router.get("/scans")
def scan_history(
    service: Service,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    include_archived: bool = Query(default=False),
) -> tuple[ScanSummary, ...]:
    return service.history(limit, offset, include_archived)


@router.get("/scans/{run_id}")
def scan_detail(run_id: UUID, service: Service) -> HistoricalScanDetail:
    return service.historical_detail(run_id)


@router.post("/scans/{run_id}/archive", dependencies=[Depends(require_origin)])
def archive_scan(run_id: UUID, service: Service) -> ScanSummary:
    return service.set_scan_archived(run_id, True)


@router.post("/scans/{run_id}/restore", dependencies=[Depends(require_origin)])
def restore_scan(run_id: UUID, service: Service) -> ScanSummary:
    return service.set_scan_archived(run_id, False)


@router.get("/candidates")
def candidates(
    service: Service,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> PaginatedCandidates:
    return service.candidates(limit, offset)


@router.get("/candidates/{candidate_id}")
def candidate(
    candidate_id: UUID,
    service: Service,
    history_limit: int = Query(default=50, ge=1, le=100),
) -> CandidateDetail:
    return service.detail(candidate_id, history_limit)


@router.post("/candidates/{candidate_id}/lifecycle", dependencies=[Depends(require_origin)])
def lifecycle(candidate_id: UUID, payload: LifecycleRequest, service: Service) -> CandidateDetail:
    return service.lifecycle(candidate_id, payload.action, payload.revision, payload.reason)


@router.post("/candidates/{candidate_id}/explain", dependencies=[Depends(require_origin)])
def explain(candidate_id: UUID, service: Service) -> LLMExplanation:
    return service.explain(candidate_id)


@router.get("/market-context")
def market_context(service: Service) -> MarketContextSnapshot | None:
    return service.latest_context()


async def product_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProductFailure)
    response = error_response(
        request,
        exc.status,
        exc.code,
        {
            404: "Discovery record was not found.",
            409: "Discovery state changed or the requested capability is disabled.",
            422: "Discovery transition is not valid.",
            503: "Optional discovery explanation is unavailable; discovery remains usable.",
        }.get(exc.status, "Discovery request could not be completed."),
    )
    response.headers["Cache-Control"] = "no-store"
    return response
