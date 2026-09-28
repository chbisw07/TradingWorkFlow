"""Browser-only construction of deterministic, network-free service scenarios."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from twf.brokers.zerodha import ZerodhaAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "api" / "tests"))
from order_provider_fixture import OrderProvider
from fastapi import FastAPI
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
    settings = Settings(broker_manual_trading_enabled=True)
    clients = (
        SyntheticScannerService(reference_time=REFERENCE_TIME),
        SyntheticTIService(
            scenario=SyntheticScenario.STALE, reference_time=REFERENCE_TIME
        ),
        SyntheticTMService(
            scenario=SyntheticScenario.UNAVAILABLE, reference_time=REFERENCE_TIME
        ),
        SyntheticLLMService(
            scenario=SyntheticScenario.EMPTY, reference_time=REFERENCE_TIME
        ),
    )
    return application(
        settings,
        broker_adapter=ZerodhaAdapter(transport=httpx.MockTransport(OrderProvider())),
        service_registry=ServiceRegistry(settings.service_clients, clients=clients),
    )
