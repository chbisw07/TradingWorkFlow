from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from twf.api.dependencies import get_settings
from twf.config.settings import Settings
from twf.schemas import HealthResponse, MetadataResponse, ReadinessResponse, StatusResponse


def create_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    v1 = APIRouter(prefix=settings.api_prefix)

    @router.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Process liveness only; does not probe persistence or satellites."""
        return HealthResponse()

    @router.get(
        "/ready",
        response_model=ReadinessResponse,
        tags=["health"],
        responses={503: {"model": ReadinessResponse}},
    )
    def ready(request: Request, response: Response) -> ReadinessResponse:
        """Only completed application initialization, never external readiness."""
        initialized = bool(request.app.state.initialized)
        response.status_code = 200 if initialized else 503
        return ReadinessResponse(status="ready" if initialized else "not_ready")

    @v1.get("/status", response_model=StatusResponse, tags=["status"])
    def status(config: Annotated[Settings, Depends(get_settings)]) -> StatusResponse:
        return StatusResponse(
            service=config.service_name,
            version=config.service_version,
            environment=config.environment,
            api_version=config.api_version,
        )

    @v1.get("/meta", response_model=MetadataResponse, tags=["status"])
    def metadata(config: Annotated[Settings, Depends(get_settings)]) -> MetadataResponse:
        return MetadataResponse(
            service_name=config.service_name,
            service_version=config.service_version,
            api_version=config.api_version,
            environment=config.environment,
        )

    router.include_router(v1)
    return router
