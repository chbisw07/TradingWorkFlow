from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from twf import __version__
from twf.config.settings import Environment, Settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class StatusResponse(BaseModel):
    service: Literal["twf-api"] = "twf-api"
    version: str
    environment: Environment
    status: Literal["ok"] = "ok"


def create_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Process liveness only; does not probe persistence or satellites."""
        return HealthResponse()

    @router.get("/api/v1/status", response_model=StatusResponse, tags=["status"])
    def status() -> StatusResponse:
        return StatusResponse(version=__version__, environment=settings.environment)

    return router
