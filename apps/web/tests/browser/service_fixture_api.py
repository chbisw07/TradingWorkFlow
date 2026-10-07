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
    app = application(
        settings,
        broker_adapter=ZerodhaAdapter(transport=httpx.MockTransport(OrderProvider())),
        service_registry=ServiceRegistry(settings.service_clients, clients=clients),
    )

    from twf.api.watchlists import catalog
    from twf.watchlists.catalog import WatchlistCatalog
    from test_watchlists import provider
    app.dependency_overrides[catalog] = lambda: WatchlistCatalog(provider())
    from twf.api.scanner_v2 import market
    from twf.discovery.dhan_credentials import DhanCredentialCapture, DhanCredentialStatus
    from twf.discovery.domain import SourceMode
    from internal_scanner_support import series

    scanner_provider = provider()
    async def scanner_history(instrument, interval, **kwargs):
        values = [100.0 + (n * 0.3) + (n % 7) * 0.8 for n in range(300)]
        result = series(values, instrument=instrument, interval="1d", step=86400)
        return result.model_copy(update={"provenance": result.provenance.model_copy(
            update={"mode": SourceMode.EOD, "producer": result.provenance.producer.model_copy(
                update={"provider": "dhan"})})})
    from twf.discovery.market_data import QuoteSnapshot
    from datetime import UTC, datetime
    from decimal import Decimal
    async def scanner_quotes(instruments):
        return tuple(QuoteSnapshot(instrument=i, last_price=Decimal("193.7"),
            received_at=datetime.now(UTC), provider="dhan") for i in instruments)
    scanner_provider.get_quotes = scanner_quotes
    scanner_provider.get_ohlcv = scanner_history
    app.dependency_overrides[market] = lambda: DhanCredentialCapture(
        provider=scanner_provider,
        status=DhanCredentialStatus(state="READY", configured=True, enabled=True,
            generation=1, source="NONE"))
    return app
