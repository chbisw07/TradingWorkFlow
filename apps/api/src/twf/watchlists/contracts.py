"""Bounded, provider-neutral collection and inbound contracts."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from twf.discovery.domain import InstrumentIdentity
from twf.integrations.contracts import Contract

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Kind = Literal["EQUITY", "INDEX", "FUTURE", "OPTION"]


class CreateWatchlist(Contract):
    name: Name
    description: str = Field(default="", max_length=240)


class UpdateWatchlist(Contract):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=240)
    favorite: bool | None = None
    archived: bool | None = None


class SourceMetadata(Contract):
    source: Literal["manual", "import", "scanner", "discovery"] = "manual"
    run_id: UUID | None = None
    candidate_id: UUID | None = None


class AddItems(Contract):
    instrument_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    source_metadata: SourceMetadata = SourceMetadata()


class WatchlistSelection(Contract):
    watchlist_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)


class TransferItems(Contract):
    target_id: UUID
    instrument_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    move: bool = False


class ImportItems(Contract):
    csv: str = Field(min_length=1, max_length=32768)


class NoteInput(Contract):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class UniverseSnapshot(Contract):
    watchlist_id: UUID
    revision: int
    captured_at: datetime
    instruments: tuple[InstrumentIdentity, ...]
