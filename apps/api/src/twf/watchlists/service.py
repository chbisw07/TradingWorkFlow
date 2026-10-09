"""Owner-scoped collection persistence. All I/O is outside short DB scopes."""

import csv
import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from twf.discovery.domain import InstrumentIdentity
from twf.infrastructure.identity import User
from twf.infrastructure.watchlists import (
    WatchlistActivityRow,
    WatchlistItemRow,
    WatchlistNoteRow,
    WatchlistRow,
)
from twf.instrument_metadata.service import InstrumentMetadataService
from twf.watchlists.catalog import kind
from twf.watchlists.contracts import (
    CreateWatchlist,
    SourceMetadata,
    UniverseSnapshot,
    UpdateWatchlist,
)

_MAX_WATCHLIST_ITEMS = 600


class WatchlistFailure(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        self.code, self.status = code, status
        super().__init__(code)


def now() -> datetime:
    return datetime.now(UTC)


def stamp(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()


class WatchlistService:
    def __init__(self, factory: sessionmaker[Session], owner: UUID) -> None:
        self.factory, self.owner = factory, owner

    def _get(self, db: Session, key: UUID, *, write: bool = False) -> WatchlistRow:
        if write:
            # UPDATE is the shared SQLite/PostgreSQL serialization point. No provider I/O here.
            result = db.execute(
                update(WatchlistRow)
                .where(WatchlistRow.id == key, WatchlistRow.owner_id == self.owner)
                .values(revision=WatchlistRow.revision + 1, updated_at=now())
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                raise WatchlistFailure("WATCHLIST_NOT_FOUND", 404)
        row = db.scalar(
            select(WatchlistRow).where(WatchlistRow.id == key, WatchlistRow.owner_id == self.owner)
        )
        if row is None:
            raise WatchlistFailure("WATCHLIST_NOT_FOUND", 404)
        return row

    @staticmethod
    def _active(row: WatchlistRow) -> None:
        if row.archived:
            raise WatchlistFailure("WATCHLIST_ARCHIVED")

    @staticmethod
    def _activity(db: Session, key: UUID, action: str, symbol: str = "") -> None:
        db.add(
            WatchlistActivityRow(
                id=uuid4(), watchlist_id=key, action=action, symbol=symbol, created_at=now()
            )
        )

    @staticmethod
    def _summary(db: Session, row: WatchlistRow) -> dict[str, Any]:
        item_rows = list(
            db.scalars(select(WatchlistItemRow).where(WatchlistItemRow.watchlist_id == row.id))
        )
        type_order = {"EQUITY": 0, "INDEX": 1, "FUTURE": 2, "OPTION": 3}
        type_summary = sorted(
            {kind(InstrumentIdentity.model_validate(item.instrument)) for item in item_rows},
            key=type_order.__getitem__,
        )
        return dict(
            id=str(row.id),
            name=row.name,
            description=row.description,
            favorite=row.favorite,
            pinned=row.favorite,
            archived=row.archived,
            ordering=row.ordering,
            revision=row.revision,
            created_at=stamp(row.created_at),
            updated_at=stamp(row.updated_at),
            count=len(item_rows),
            ownership_kind="USER",
            read_only=False,
            system_code=None,
            enabled=True,
            availability="READY",
            pending_reason=None,
            expected_count=None,
            instrument_type_summary=type_summary,
            source_reference=None,
            source_received_at=None,
            freshness="CURRENT",
        )

    def list(self) -> list[dict[str, Any]]:
        with self.factory() as db:
            rows = db.scalars(
                select(WatchlistRow)
                .where(WatchlistRow.owner_id == self.owner)
                .order_by(
                    WatchlistRow.favorite.desc(), WatchlistRow.ordering, WatchlistRow.created_at
                )
            )
            return [self._summary(db, row) for row in rows]

    def create(self, payload: CreateWatchlist) -> dict[str, Any]:
        with self.factory.begin() as db:
            db.execute(update(User).where(User.id == self.owner).values(id=User.id))
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(WatchlistRow)
                    .where(WatchlistRow.owner_id == self.owner)
                )
                or 0
            )
            if count >= 100:
                raise WatchlistFailure("WATCHLIST_LIMIT")
            row = WatchlistRow(
                id=uuid4(),
                owner_id=self.owner,
                name=payload.name,
                description=payload.description,
                favorite=False,
                archived=False,
                ordering=count,
                revision=0,
                created_at=now(),
                updated_at=now(),
            )
            db.add(row)
            db.flush()
            self._activity(db, row.id, "CREATED")
            return self._summary(db, row)

    def update(self, key: UUID, payload: UpdateWatchlist) -> dict[str, Any]:
        with self.factory.begin() as db:
            row = self._get(db, key, write=True)
            for field, value in payload.model_dump(exclude_none=True).items():
                setattr(row, field, value)
            self._activity(db, key, "UPDATED")
            return self._summary(db, row)

    def restore_many(self, keys: tuple[UUID, ...]) -> dict[str, int]:
        with self.factory.begin() as db:
            rows = [self._get(db, key, write=True) for key in sorted(set(keys), key=str)]
            restored = 0
            for row in rows:
                if row.archived:
                    row.archived = False
                    self._activity(db, row.id, "RESTORED")
                    restored += 1
            return {"restored": restored}

    def delete_many(self, keys: tuple[UUID, ...]) -> dict[str, int]:
        with self.factory.begin() as db:
            rows = [self._get(db, key, write=True) for key in sorted(set(keys), key=str)]
            if any(not row.archived for row in rows):
                raise WatchlistFailure("WATCHLIST_NOT_ARCHIVED")
            ids = [row.id for row in rows]
            for model in (WatchlistActivityRow, WatchlistNoteRow, WatchlistItemRow):
                db.execute(delete(model).where(model.watchlist_id.in_(ids)))
            for row in rows:
                db.delete(row)
            return {"deleted": len(rows)}

    @staticmethod
    def _metadata_target(
        instrument: InstrumentIdentity, instrument_kind: str
    ) -> tuple[tuple[str, str], Literal["DIRECT", "UNDERLYING"]] | None:
        if instrument_kind == "EQUITY":
            return (instrument.exchange.upper(), instrument.symbol.upper()), "DIRECT"
        if instrument_kind not in {"FUTURE", "OPTION"}:
            return None
        source = instrument.underlying.source
        if instrument.underlying.ambiguous or source.namespace != "dhan-symbol":
            return None
        exchange, separator, symbol = source.native_id.upper().partition(":")
        if not separator or exchange not in {"NSE", "BSE"} or not symbol:
            return None
        return (exchange, symbol), "UNDERLYING"

    @classmethod
    def _enrich_items(cls, db: Session, items: Sequence[dict[str, Any]]) -> None:
        targets: dict[str, tuple[tuple[str, str], Literal["DIRECT", "UNDERLYING"]]] = {}
        for item in items:
            instrument = InstrumentIdentity.model_validate(item["instrument"])
            target = cls._metadata_target(instrument, str(item["kind"]))
            if target is not None:
                targets[str(instrument.instrument_id)] = target
        service = InstrumentMetadataService(db)
        metadata = service.get_many_by_exchange_symbols(
            tuple(target[0] for target in targets.values())
        )
        for item in items:
            instrument = InstrumentIdentity.model_validate(item["instrument"])
            target = targets.get(str(instrument.instrument_id))
            found = metadata.get(target[0]) if target is not None else None
            item["instrument_metadata"] = (
                service.summary(
                    found,
                    applies_to_symbol=instrument.symbol,
                    resolution_basis=target[1],
                ).model_dump(mode="json")
                if found is not None and target is not None
                else None
            )

    def enrich_detail(self, detail: dict[str, Any]) -> dict[str, Any]:
        """Enrich an already-resolved built-in universe without provider I/O."""

        items = [dict(item) for item in detail["items"]]
        with self.factory() as db:
            self._enrich_items(db, items)
        return {**detail, "items": items}

    def detail(self, key: UUID) -> dict[str, Any]:
        with self.factory() as db:
            row = self._get(db, key)
            items = list(
                db.scalars(
                    select(WatchlistItemRow)
                    .where(WatchlistItemRow.watchlist_id == key)
                    .order_by(WatchlistItemRow.ordering)
                )
            )
            notes = db.scalars(
                select(WatchlistNoteRow)
                .where(WatchlistNoteRow.watchlist_id == key)
                .order_by(WatchlistNoteRow.created_at.desc())
                .limit(50)
            )
            activity = db.scalars(
                select(WatchlistActivityRow)
                .where(WatchlistActivityRow.watchlist_id == key)
                .order_by(WatchlistActivityRow.created_at.desc())
                .limit(30)
            )
            public_items = [
                dict(
                    instrument=item.instrument,
                    kind=kind(InstrumentIdentity.model_validate(item.instrument)),
                    added_at=stamp(item.added_at),
                    ordering=item.ordering,
                    source=item.source,
                )
                for item in items
            ]
            self._enrich_items(db, public_items)
            return {
                **self._summary(db, row),
                "items": public_items,
                "notes": [
                    dict(
                        id=str(n.id),
                        text=n.text,
                        created_at=stamp(n.created_at),
                        author=str(self.owner),
                    )
                    for n in notes
                ],
                "activity": [
                    dict(
                        id=str(a.id),
                        action=a.action,
                        symbol=a.symbol,
                        created_at=stamp(a.created_at),
                    )
                    for a in activity
                ],
            }

    def snapshot(self, key: UUID) -> UniverseSnapshot:
        detail = self.detail(key)
        if detail["archived"]:
            raise WatchlistFailure("WATCHLIST_ARCHIVED")
        return UniverseSnapshot(
            watchlist_id=key,
            name=detail["name"],
            revision=detail["revision"],
            captured_at=now(),
            ownership_kind="USER",
            instruments=tuple(
                InstrumentIdentity.model_validate(i["instrument"]) for i in detail["items"]
            ),
        )

    def add(
        self, key: UUID, instruments: tuple[InstrumentIdentity, ...], source: SourceMetadata
    ) -> dict[str, Any]:
        with self.factory.begin() as db:
            row = self._get(db, key, write=True)
            self._active(row)
            return self._add(db, key, instruments, source)

    def _add(
        self,
        db: Session,
        key: UUID,
        instruments: tuple[InstrumentIdentity, ...],
        source: SourceMetadata,
    ) -> dict[str, Any]:
        rows = list(
            db.scalars(select(WatchlistItemRow).where(WatchlistItemRow.watchlist_id == key))
        )
        known = {i.instrument_id for i in rows}
        order = max((i.ordering for i in rows), default=-1) + 1
        added = duplicates = 0
        for item in instruments:
            if item.instrument_id in known:
                duplicates += 1
                continue
            if len(known) >= _MAX_WATCHLIST_ITEMS:
                raise WatchlistFailure("WATCHLIST_FULL")
            db.add(
                WatchlistItemRow(
                    id=uuid4(),
                    watchlist_id=key,
                    instrument_id=item.instrument_id,
                    instrument=item.model_dump(mode="json"),
                    source=source.model_dump(mode="json"),
                    ordering=order,
                    added_at=now(),
                )
            )
            self._activity(db, key, "ADDED", item.symbol)
            known.add(item.instrument_id)
            order += 1
            added += 1
        if source.source == "import":
            self._activity(db, key, "IMPORT")
        return {"added": added, "duplicates": duplicates}

    def remove(self, key: UUID, ids: tuple[UUID, ...]) -> None:
        with self.factory.begin() as db:
            self._active(self._get(db, key, write=True))
            rows = list(
                db.scalars(
                    select(WatchlistItemRow).where(
                        WatchlistItemRow.watchlist_id == key,
                        WatchlistItemRow.instrument_id.in_(ids),
                    )
                )
            )
            for row in rows:
                self._activity(db, key, "REMOVED", str(row.instrument["symbol"]))
                db.delete(row)

    def transfer(
        self, key: UUID, target: UUID, ids: tuple[UUID, ...], move: bool
    ) -> dict[str, Any]:
        if key == target:
            raise WatchlistFailure("SAME_WATCHLIST")
        with self.factory.begin() as db:
            for lock in sorted((key, target), key=str):
                self._active(self._get(db, lock, write=True))
            rows = list(
                db.scalars(
                    select(WatchlistItemRow)
                    .where(
                        WatchlistItemRow.watchlist_id == key,
                        WatchlistItemRow.instrument_id.in_(ids),
                    )
                    .order_by(WatchlistItemRow.ordering)
                )
            )
            result = {"added": 0, "duplicates": 0}
            for original in rows:
                added = self._add(
                    db,
                    target,
                    (InstrumentIdentity.model_validate(original.instrument),),
                    SourceMetadata.model_validate(original.source),
                )
                result["added"] += added["added"]
                result["duplicates"] += added["duplicates"]
                db.flush()  # Explicit sessions do not autoflush; preserve destination ordering.
            for row in rows:
                self._activity(
                    db, key, "MOVED" if move else "COPIED", str(row.instrument["symbol"])
                )
                if move:
                    db.delete(row)
            return result

    def note(self, key: UUID, text: str) -> None:
        with self.factory.begin() as db:
            self._active(self._get(db, key, write=True))
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(WatchlistNoteRow)
                    .where(WatchlistNoteRow.watchlist_id == key)
                )
                or 0
            )
            if count >= 200:
                raise WatchlistFailure("NOTE_LIMIT")
            db.add(WatchlistNoteRow(id=uuid4(), watchlist_id=key, text=text, created_at=now()))

    def export(self, key: UUID) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["canonical_symbol", "exchange", "instrument_type", "trading_symbol"])
        for row in self.detail(key)["items"]:
            item = row["instrument"]
            values = [
                f"{item['exchange']}:{item['symbol']}",
                item["exchange"],
                row["kind"],
                item["symbol"],
            ]
            writer.writerow(
                ["'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values]
            )
        return out.getvalue()
