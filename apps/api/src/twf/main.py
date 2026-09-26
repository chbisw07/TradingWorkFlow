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
from twf.api.broker_auth import router as broker_auth_router
from twf.api.broker_foundation import router as broker_foundation_router
from twf.api.brokers import router as brokers_router
from twf.api.errors import http_error, unexpected_error, validation_error
from twf.api.preferences import router as preferences_router
from twf.api.preferences import settings_error
from twf.api.routes import create_router
from twf.api.services import router as services_router
from twf.brokers.foundation_contracts import PersonalBrokerPermissionPolicy
from twf.brokers.service import BrokerService
from twf.brokers.zerodha_auth import AuthProvider, KiteAuthClient
from twf.config.settings import Settings
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.integrations.registry import ServiceRegistry
from twf.login_limit import LoginLimit
from twf.middleware import ErrorBoundaryMiddleware, RequestContextMiddleware
from twf.observability import create_logger
from twf.preferences import SettingsFailure
from twf.schemas import ErrorResponse
from twf.secrets import SecretStore, select_secret_store


def create_app(
    settings: Settings | None = None,
    *,
    engine_factory: Callable[[Settings], Engine] = create_database_engine,
    service_registry: ServiceRegistry | None = None,
    broker_service: BrokerService | None = None,
    secret_store: SecretStore | None = None,
    broker_auth_provider: AuthProvider | None = None,
) -> FastAPI:
    """Construct an isolated application without opening database connections."""
    settings = settings if settings is not None else Settings()
    selected_secret_store = select_secret_store(settings, secret_store)
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
                allow_methods=["GET", "POST", "PATCH"],
                allow_headers=["X-Request-ID", "Content-Type"],
                expose_headers=["X-Request-ID"],
            ),
            Middleware(ErrorBoundaryMiddleware),
        ],
        responses={code: {"model": ErrorResponse} for code in (404, 405, 422, 500)},
    )
    app.state.broker_service = broker_service if broker_service is not None else BrokerService()
    app.state.broker_permission_policy = PersonalBrokerPermissionPolicy()
    app.state.secret_store = selected_secret_store
    app.state.broker_auth_provider = broker_auth_provider or KiteAuthClient()
    app.state.login_limit = LoginLimit()
    app.state.settings = settings
    app.state.service_registry = service_registry or ServiceRegistry(
        settings.service_clients,
        allowed_origins=settings.service_allowed_origins,
        production=settings.environment == "production",
    )
    app.state.logger = logger
    app.state.initialized = False
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, unexpected_error)
    app.include_router(create_router(settings))
    app.include_router(auth_router)
    app.include_router(preferences_router)
    app.include_router(services_router)
    app.include_router(brokers_router)
    app.include_router(broker_foundation_router)
    app.include_router(broker_auth_router)
    app.add_exception_handler(SettingsFailure, settings_error)
    return app
