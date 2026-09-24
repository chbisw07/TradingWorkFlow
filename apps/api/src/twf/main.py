from fastapi import FastAPI

from twf import __version__
from twf.api.routes import create_router
from twf.config.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct an isolated application without opening database connections."""
    settings = settings if settings is not None else Settings()
    app = FastAPI(title="TradingWorkFlow API", version=__version__)
    app.include_router(create_router(settings))
    return app
