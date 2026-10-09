"""Authenticated, bounded read APIs for system-global instrument metadata."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as ApiPath

from twf.api.auth import Database, get_current_user, require_origin
from twf.infrastructure.identity import User
from twf.instrument_metadata.contracts import (
    BulkLookup,
    BulkLookupResult,
    InstrumentMetadata,
    MetadataStatus,
)
from twf.instrument_metadata.service import InstrumentMetadataService
from twf.schemas import ErrorResponse

router = APIRouter(prefix="/api/v1/instrument-metadata", tags=["Instrument metadata"])
UserDependency = Annotated[User, Depends(get_current_user)]


def service(session: Database) -> InstrumentMetadataService:
    return InstrumentMetadataService(session)


@router.get("/status", responses={401: {"model": ErrorResponse}})
def status(session: Database, user: UserDependency, response: Response) -> MetadataStatus:
    del user
    response.headers["Cache-Control"] = "private, max-age=60"
    return service(session).get_last_refresh_status()


@router.get(
    "/by-isin/{isin}", responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
)
def by_isin(
    isin: Annotated[str, ApiPath(min_length=1, max_length=32)],
    session: Database,
    user: UserDependency,
    response: Response,
) -> InstrumentMetadata:
    del user
    item = service(session).get_by_isin(isin)
    if item is None:
        raise HTTPException(404)
    response.headers["Cache-Control"] = "private, max-age=300"
    return item


@router.post(
    "/lookup",
    dependencies=[Depends(require_origin)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def lookup(payload: BulkLookup, session: Database, user: UserDependency) -> BulkLookupResult:
    del user
    return service(session).get_many_by_symbols(payload.exchange, payload.symbols)


@router.get(
    "/{exchange}/{symbol}",
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def by_symbol(
    exchange: Annotated[str, ApiPath(min_length=1, max_length=16)],
    symbol: Annotated[str, ApiPath(min_length=1, max_length=128)],
    session: Database,
    user: UserDependency,
    response: Response,
) -> InstrumentMetadata:
    del user
    item = service(session).get_by_symbol(exchange, symbol)
    if item is None:
        raise HTTPException(404)
    response.headers["Cache-Control"] = "private, max-age=300"
    return item
