"""Authenticated global market summary API."""

from typing import cast

from fastapi import APIRouter, Request, Response

from twf.api.mcp import Who
from twf.discovery.dhan_credentials import DhanCredentialManager
from twf.discovery.market_summary import (
    GlobalMarketSummary,
    GlobalMarketSummaryService,
    MarketSummaryCache,
)
from twf.watchlists.market import WatchlistHistoryCache, WatchlistQuoteCache

router = APIRouter(prefix="/api/v1/market", tags=["Market summary"])


@router.get("/summary")
async def summary(request: Request, response: Response, who: Who) -> GlobalMarketSummary:
    credentials = cast(DhanCredentialManager, request.app.state.dhan_credentials)
    capture = credentials.capture(who.owner_id, ready_only=True)
    response.headers["Cache-Control"] = "private, no-store"
    return await GlobalMarketSummaryService(
        who.owner_id,
        capture.status.generation,
        capture.provider,
        cast(WatchlistQuoteCache, request.app.state.watchlist_quotes),
        cast(WatchlistHistoryCache, request.app.state.watchlist_history),
        cast(MarketSummaryCache, request.app.state.market_summary_cache),
    ).summary()
