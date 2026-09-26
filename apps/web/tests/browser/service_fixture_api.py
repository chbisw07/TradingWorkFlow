"""Browser-only construction of deterministic, network-free service scenarios."""

from datetime import UTC, datetime

from fastapi import FastAPI
from broker_fixture import BrowserVault, BrowserProvider, add_provider_return

from twf.config.settings import Settings
from twf.integrations.adapters import (
    SyntheticLLMService,
    SyntheticScannerService,
    SyntheticScenario,
    SyntheticTIService,
    SyntheticTMService,
)
from twf.integrations.registry import ServiceRegistry
from twf.main import create_app as application

REFERENCE_TIME = datetime(2026, 9, 25, 12, tzinfo=UTC)


def create_app() -> FastAPI:
    settings = Settings()
    clients = (
        SyntheticScannerService(reference_time=REFERENCE_TIME),
        SyntheticTIService(scenario=SyntheticScenario.STALE, reference_time=REFERENCE_TIME),
        SyntheticTMService(scenario=SyntheticScenario.UNAVAILABLE, reference_time=REFERENCE_TIME),
        SyntheticLLMService(scenario=SyntheticScenario.EMPTY, reference_time=REFERENCE_TIME),
    )
    app = application(
        settings,
        secret_store=BrowserVault(),
        broker_auth_provider=BrowserProvider(),
        service_registry=ServiceRegistry(settings.service_clients, clients=clients),
    )

    add_provider_return(app)
    return app
