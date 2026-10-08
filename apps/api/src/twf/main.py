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
from twf.api.broker_orders import router as broker_orders_router
from twf.api.brokers import broker_error
from twf.api.brokers import router as brokers_router
from twf.api.dhan_market_data import dhan_error
from twf.api.dhan_market_data import router as dhan_market_data_router
from twf.api.discovery import product_error
from twf.api.discovery import router as discovery_router
from twf.api.errors import http_error, unexpected_error, validation_error
from twf.api.mcp import mcp_error
from twf.api.mcp import router as mcp_router
from twf.api.preferences import router as preferences_router
from twf.api.preferences import settings_error
from twf.api.routes import create_router
from twf.api.scanner_v2 import router as scanner_v2_router
from twf.api.services import router as services_router
from twf.api.watchlists import router as watchlists_router
from twf.api.watchlists import watchlist_error
from twf.brokers.contracts import BrokerAdapter, BrokerFailure
from twf.brokers.service import BrokerService
from twf.brokers.zerodha import ZerodhaAdapter
from twf.config.settings import Settings
from twf.discovery.dhan_credentials import DhanCredentialFailure, DhanCredentialManager
from twf.discovery.market_data import DhanMarketDataProvider
from twf.discovery.market_intelligence import TapTideSnapshotCache
from twf.discovery.product_service import ProductFailure
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import Failure as MCPFailure
from twf.integrations.registry import ServiceRegistry
from twf.login_limit import LoginLimit
from twf.middleware import ErrorBoundaryMiddleware, RequestContextMiddleware
from twf.observability import create_logger
from twf.preferences import SettingsFailure
from twf.scanner_v2.service import ScannerHistory
from twf.schemas import ErrorResponse
from twf.watchlists.market import WatchlistHistoryCache, WatchlistQuoteCache
from twf.watchlists.reference import WatchlistReferenceCache
from twf.watchlists.service import WatchlistFailure
from twf.watchlists.system import SystemUniverseCatalog


def create_app(
    settings: Settings | None = None,
    *,
    engine_factory: Callable[[Settings], Engine] = create_database_engine,
    service_registry: ServiceRegistry | None = None,
    broker_adapter: BrokerAdapter | None = None,
) -> FastAPI:
    """Construct an isolated application without opening database connections."""
    settings = settings if settings is not None else Settings()
    logger = create_logger(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = engine_factory(settings)
        app.state.database_engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.broker_service = BrokerService(
            app.state.session_factory, settings, broker_adapter or ZerodhaAdapter()
        )
        app.state.mcp_manager = ConnectionManager(
            app.state.session_factory, settings, settings.mcp_providers, logger=logger
        )
        app.state.market_data_provider = DhanMarketDataProvider(settings.dhan_market_data)
        app.state.dhan_credentials = DhanCredentialManager(app.state.session_factory, settings)
        app.state.market_intelligence_cache = TapTideSnapshotCache()
        app.state.scanner_history = ScannerHistory()
        app.state.watchlist_quotes = WatchlistQuoteCache()
        app.state.watchlist_history = WatchlistHistoryCache()
        app.state.watchlist_reference = WatchlistReferenceCache()
        if getattr(app.state, "system_universes", None) is None:
            app.state.system_universes = SystemUniverseCatalog()
        app.state.auth_dummy_hash = PasswordHasher().hash(secrets.token_urlsafe(32))
        app.state.initialized = True
        logger.info("application_started")
        try:
            yield
        finally:
            app.state.initialized = False
            await app.state.mcp_manager.operations.shutdown()
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
    app.include_router(brokers_router)
    app.include_router(broker_orders_router)
    app.add_exception_handler(BrokerFailure, broker_error)
    app.include_router(auth_router)
    app.include_router(preferences_router)
    app.include_router(services_router)
    app.include_router(mcp_router)
    app.include_router(dhan_market_data_router)
    app.include_router(discovery_router)
    app.include_router(watchlists_router)
    app.include_router(scanner_v2_router)
    app.add_exception_handler(WatchlistFailure, watchlist_error)
    app.add_exception_handler(ProductFailure, product_error)
    app.add_exception_handler(MCPFailure, mcp_error)
    app.add_exception_handler(DhanCredentialFailure, dhan_error)
    app.add_exception_handler(SettingsFailure, settings_error)
    return app
