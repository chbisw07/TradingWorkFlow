from typing import Literal

from pydantic import BaseModel

from twf.config.settings import Environment


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: Literal["application_initialization_only"] = "application_initialization_only"
    satellite_dependencies_checked: Literal[False] = False
    database_checked: Literal[False] = False


class StatusResponse(BaseModel):
    service: str
    version: str
    environment: Environment
    api_version: Literal["v1"] = "v1"
    status: Literal["ok"] = "ok"


class MetadataResponse(BaseModel):
    service_name: str
    service_version: str
    api_version: Literal["v1"] = "v1"
    environment: Environment


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None
    details: None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
