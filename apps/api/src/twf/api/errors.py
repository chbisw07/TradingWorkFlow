from http import HTTPStatus

from fastapi import Request
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from twf.api.dependencies import get_request_id
from twf.schemas import ErrorDetail, ErrorResponse


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, request_id=get_request_id(request))
    )
    return JSONResponse(status_code=status, content=body.model_dump())


async def http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    try:
        message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        message = "HTTP request failed"
    response = error_response(request, exc.status_code, f"HTTP_{exc.status_code}", message)
    # Preserve protocol headers (e.g. Allow / Retry-After), not arbitrary details.
    for name, value in (exc.headers or {}).items():
        if name.lower() in {"allow", "retry-after", "www-authenticate"}:
            response.headers[name] = value
    return response


async def validation_error(request: Request, exc: Exception) -> JSONResponse:
    # Pydantic errors may carry raw input or secret-bearing exception context.
    return error_response(request, 422, "INVALID_REQUEST", "Request validation failed")


async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request.app.state.logger.error("request_failed", extra={"exception_type": type(exc).__name__})
    return error_response(request, 500, "INTERNAL_ERROR", "Internal server error")
