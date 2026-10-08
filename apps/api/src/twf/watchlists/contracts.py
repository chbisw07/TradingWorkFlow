"""Bounded, provider-neutral collection and inbound contracts."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

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
    source: Literal["manual", "import", "scanner", "discovery", "built_in_watchlist"] = "manual"
    run_id: UUID | None = None
    candidate_id: UUID | None = None
    source_watchlist_id: UUID | None = None
    source_watchlist_code: str | None = Field(default=None, max_length=80)
    source_watchlist_name: str | None = Field(default=None, max_length=80)


class AddItems(Contract):
    instrument_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    source_metadata: SourceMetadata = SourceMetadata()


class WatchlistSelection(Contract):
    watchlist_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)


class TransferItems(Contract):
    target_id: UUID
    instrument_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    move: bool = False


class CopySystemItems(Contract):
    target_id: UUID
    instrument_ids: tuple[UUID, ...] = Field(default=(), max_length=500)
    all: bool = False

    @model_validator(mode="after")
    def validate_selection(self) -> "CopySystemItems":
        if self.all == bool(self.instrument_ids):
            raise ValueError("Select instrument_ids or all, but not both")
        return self


class ImportItems(Contract):
    csv: str = Field(min_length=1, max_length=32768)


class NoteInput(Contract):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class UniverseSnapshot(Contract):
    watchlist_id: UUID
    name: str | None = None
    revision: int
    captured_at: datetime
    ownership_kind: Literal["USER", "SYSTEM"] = "USER"
    system_code: str | None = None
    source_reference: str | None = None
    source_updated_at: datetime | None = None
    instruments: tuple[InstrumentIdentity, ...]
