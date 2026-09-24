from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from twf.api.errors import http_error, unexpected_error, validation_error
from twf.api.routes import create_router
from twf.config.settings import Settings
from twf.middleware import ErrorBoundaryMiddleware, RequestContextMiddleware
from twf.observability import create_logger
from twf.schemas import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct an isolated application without opening database connections."""
    settings = settings if settings is not None else Settings()
    logger = create_logger(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.initialized = True
        logger.info("application_started")
        try:
            yield
        finally:
            app.state.initialized = False
            logger.info("application_stopped")

    app = FastAPI(
        title="TradingWorkFlow API",
        description="TWF application gateway shell. No satellite health or trading authority.",
        version=settings.service_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        middleware=[
            Middleware(RequestContextMiddleware, logger=logger),
            Middleware(
                CORSMiddleware,
                allow_origins=settings.allowed_origins,
                allow_credentials=False,
                allow_methods=["GET"],
                allow_headers=["X-Request-ID", "Content-Type"],
                expose_headers=["X-Request-ID"],
            ),
            Middleware(ErrorBoundaryMiddleware),
        ],
        responses={code: {"model": ErrorResponse} for code in (404, 405, 422, 500)},
    )
    app.state.settings = settings
    app.state.logger = logger
    app.state.initialized = False
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, unexpected_error)
    app.include_router(create_router(settings))
    return app
