"""Authenticated owner-scoped portfolio observations; GET only."""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request, Response

from twf.api.broker_auth import Use
from twf.api.broker_foundation import invoke
from twf.brokers.portfolio_contracts import NativePortfolio, PortfolioProvider
from twf.portfolio import BrokerPortfolio
from twf.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/v1/broker-portfolio",
    tags=["Native portfolio observations"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409)},
)


@router.get("/accounts/{account_id}")
def read(account_id: UUID, request: Request, response: Response, use: Use) -> NativePortfolio:
    response.headers["Cache-Control"] = "no-store"
    service = BrokerPortfolio(use, cast(PortfolioProvider, request.app.state.portfolio_provider))
    return invoke(lambda: service.read(account_id))
