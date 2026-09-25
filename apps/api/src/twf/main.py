import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Engine
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from twf.api.auth import router as auth_router
from twf.api.errors import http_error, unexpected_error, validation_error
from twf.api.preferences import router as preferences_router
from twf.api.preferences import settings_error
from twf.api.routes import create_router
from twf.config.settings import Settings
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.login_limit import LoginLimit
from twf.middleware import ErrorBoundaryMiddleware, RequestContextMiddleware
from twf.observability import create_logger
from twf.preferences import SettingsFailure
from twf.schemas import ErrorResponse


def create_app(
    settings: Settings | None = None,
    *,
    engine_factory: Callable[[Settings], Engine] = create_database_engine,
) -> FastAPI:
    """Construct an isolated application without opening database connections."""
    settings = settings if settings is not None else Settings()
    logger = create_logger(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = engine_factory(settings)
        app.state.database_engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.auth_dummy_hash = PasswordHasher().hash(secrets.token_urlsafe(32))
        app.state.initialized = True
        logger.info("application_started")
        try:
            yield
        finally:
            app.state.initialized = False
            app.state.session_factory = None
            app.state.database_engine = None
            engine.dispose()
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
    app.state.login_limit = LoginLimit()
    app.state.settings = settings
    app.state.logger = logger
    app.state.initialized = False
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, unexpected_error)
    app.include_router(create_router(settings))
    app.include_router(auth_router)
    app.include_router(preferences_router)
    app.add_exception_handler(SettingsFailure, settings_error)
    return app
