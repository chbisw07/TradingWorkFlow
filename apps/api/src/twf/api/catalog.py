"""Authenticated native catalog/search endpoints; no market quotes or commands."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from twf.api.auth import require_origin
from twf.api.broker_auth import Use
from twf.api.broker_foundation import invoke
from twf.brokers.catalog_contracts import (
    CatalogProvider,
    CatalogSearch,
    CatalogStatus,
    InstrumentQuery,
)
from twf.catalog import BrokerCatalog
from twf.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/v1/broker-catalog/accounts",
    tags=["Native instrument catalog"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)


@router.get("/{account_id}/instruments")
def search(
    account_id: UUID,
    query: Annotated[InstrumentQuery, Query()],
    request: Request,
    response: Response,
    use: Use,
) -> CatalogSearch:
    response.headers["Cache-Control"] = "no-store"
    service = BrokerCatalog(use, cast(CatalogProvider, request.app.state.catalog_provider))
    return invoke(lambda: service.search(account_id, query))


@router.post("/{account_id}/refresh", dependencies=[Depends(require_origin)])
def refresh(account_id: UUID, request: Request, response: Response, use: Use) -> CatalogStatus:
    response.headers["Cache-Control"] = "no-store"
    service = BrokerCatalog(use, cast(CatalogProvider, request.app.state.catalog_provider))
    return invoke(lambda: service.refresh(account_id))
