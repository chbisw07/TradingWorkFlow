"""Offline, all-or-nothing SQLite snapshot -> empty PostgreSQL import.

Run with python -m twf.infrastructure.sqlite_migration --help. This module does
not switch runtime configuration, quiesce applications, or disable constraints.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    cast,
    func,
    literal,
    null,
    select,
    text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from twf.config.settings import Settings
from twf.infrastructure.database import (
    DATABASE_SCHEMA_HEAD,
    create_database_engine,
    require_database_ready,
)


class MigrationFailure(RuntimeError):
    """Only sanitized table/key/status diagnostics are safe to display."""


class NumericMigrationFailure(MigrationFailure):
    """A numeric row cannot be certified; never include its value in diagnostics."""

    def __init__(self, table: Table, column: Any, key: str, reason: str) -> None:
        self.table = table.name
        self.column = column.name
        self.primary_key = key
        self.declared_type = str(column.type)
        self.reason = reason
        super().__init__(
            f"{self.table} column {self.column} key {key} "
            f"declared {self.declared_type}: {reason}; import refused"
        )


def _numeric_value(raw: Any, kind: Numeric[Any]) -> Decimal:
    # Decimal/text/integer only, including destination verification. A Python
    # float reaching this boundary is a bug, not an acceptable conversion path.
    if not isinstance(raw, (str, int, Decimal)) or isinstance(raw, bool):
        raise MigrationFailure("numeric input is not exact decimal text/integer/Decimal")
    number = Decimal(raw)
    if not number.is_finite():
        raise MigrationFailure("non-finite numeric value")
    if kind.precision is None or kind.scale is None or not 0 <= kind.scale <= kind.precision:
        raise MigrationFailure("explicit nonnegative NUMERIC precision/scale required")
    with localcontext() as context:
        context.prec = max(kind.precision + 2, len(number.as_tuple().digits) + 2)
        quantum = Decimal(1).scaleb(-kind.scale)
        if abs(number) >= Decimal(10) ** (kind.precision - kind.scale):
            raise MigrationFailure("value exceeds declared precision")
        if number != number.quantize(quantum):
            raise MigrationFailure("value exceeds declared scale")
    return number


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _hash_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _canonical(value: Any) -> Any:
    # Tag containers too: a JSON object resembling a scalar marker must never
    # hash like that scalar (for example {"decimal":"1"} versus the number 1).
    if isinstance(value, Decimal):
        number = format(value, "f")
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        return ["decimal", "0" if value == 0 else number]
    if isinstance(value, UUID):
        return ["uuid", value.hex]
    if isinstance(value, datetime):
        return ["timestamp", value.astimezone(UTC).isoformat(timespec="microseconds")]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, dict):
        return ["object", [[key, _canonical(item)] for key, item in sorted(value.items())]]
    if isinstance(value, (list, tuple)):
        return ["array", [_canonical(item) for item in value]]
    return value


def _serialize(value: Any) -> str:
    return json.dumps(
        _canonical(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _value(raw: Any, kind: Any) -> Any:
    if raw is None:
        return None
    if isinstance(kind, JSON):
        # SQL NULL remains distinct from JSON null in the verification hash.
        return {"json": json.loads(raw, parse_float=Decimal, parse_int=Decimal)}
    if isinstance(kind, Uuid):
        return UUID(str(raw))
    if isinstance(kind, Boolean):
        if raw not in (0, 1, False, True):
            raise MigrationFailure("Invalid boolean value")
        return bool(raw)
    if isinstance(kind, DateTime):
        result = raw if isinstance(raw, datetime) else datetime.fromisoformat(raw)
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    if isinstance(kind, Date):
        return raw if isinstance(raw, date) else date.fromisoformat(raw)
    if isinstance(kind, Numeric):
        return _numeric_value(raw, kind)
    if isinstance(kind, Integer):
        number = Decimal(str(raw))
        if not number.is_finite() or number != number.to_integral_value():
            raise MigrationFailure("Non-integral value in integer column")
        return int(number)
    if isinstance(kind, String):
        if not isinstance(raw, str):
            raise MigrationFailure("Non-string value in text column")
        return raw
    raise MigrationFailure(f"Unsupported column type: {type(kind).__name__}")


def _source_rows(source: sqlite3.Connection, table: Table) -> Iterator[dict[str, Any]]:
    numeric = [c for c in table.columns if isinstance(c.type, Numeric)]
    declarations = {
        row[1]: row[2] for row in source.execute(f"PRAGMA table_info({_quote(table.name)})")
    }
    columns = [
        # REAL formatting proposes a candidate only. Independent SQL probes of
        # the stored value below establish whether it is uniquely representable.
        f"CASE typeof({_quote(c.name)}) "
        f"WHEN 'real' THEN printf('%!.26g', {_quote(c.name)}) "
        f"WHEN 'integer' THEN CAST({_quote(c.name)} AS TEXT) "
        f"WHEN 'text' THEN {_quote(c.name)} ELSE NULL END"
        if isinstance(c.type, Numeric)
        else _quote(c.name)
        for c in table.columns
    ]
    columns.extend(f"typeof({_quote(c.name)})" for c in numeric)
    order = ",".join(_quote(c.name) for c in table.primary_key)
    if not order:
        raise MigrationFailure(f"{table.name}: missing primary key; deterministic import refused")
    cursor = source.execute(
        f"SELECT {','.join(columns)} FROM {_quote(table.name)} ORDER BY {order}"
    )
    for record in cursor:
        row = dict(zip(table.columns.keys(), record[: len(table.columns)], strict=True))
        key = _serialize([row[c.name] for c in table.primary_key])
        for column, storage in zip(numeric, record[len(table.columns) :], strict=True):
            try:
                declaration = re.fullmatch(
                    r"(?:NUMERIC|DECIMAL)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)",
                    declarations[column.name],
                    re.IGNORECASE,
                )
                kind = column.type
                assert isinstance(kind, Numeric)
                if declaration is None or tuple(map(int, declaration.groups())) != (
                    kind.precision,
                    kind.scale,
                ):
                    raise MigrationFailure("source and destination numeric declarations differ")
                if storage == "null":
                    continue
                if storage not in {"integer", "real", "text"}:
                    raise MigrationFailure("unsupported numeric storage class")
                raw = row[column.name]
                if storage == "real":
                    if kind.precision is None or kind.scale is None:
                        raise MigrationFailure("REAL requires declared precision and scale")
                    with localcontext() as context:
                        context.prec = max(kind.precision + 4, 32)
                        quantum = Decimal(1).scaleb(-kind.scale)
                        candidate = Decimal(raw).quantize(quantum, rounding=ROUND_HALF_EVEN)
                        _numeric_value(candidate, kind)
                        # Do not trust printf or hash the candidate into truth.
                        # Exactly one declared-scale decimal must map back to the
                        # stored REAL. Adjacent matches mean storage cannot resolve
                        # this scale, so refuse instead of choosing arbitrarily.
                        name = _quote(column.name)
                        where = " AND ".join(f"{_quote(c.name)} IS ?" for c in table.primary_key)
                        matches = source.execute(
                            f"SELECT CAST(? AS REAL) = {name}, "
                            f"CAST(? AS REAL) = {name}, CAST(? AS REAL) = {name} "
                            f"FROM {_quote(table.name)} WHERE {where}",
                            (
                                format(candidate, "f"),
                                format(candidate - quantum, "f"),
                                format(candidate + quantum, "f"),
                                *(row[c.name] for c in table.primary_key),
                            ),
                        ).fetchone()
                        if matches != (1, 0, 0):
                            raise MigrationFailure(
                                "REAL has no unique lossless decimal at declared scale"
                            )
                    raw = candidate
                row[column.name] = _numeric_value(raw, kind)
            except (MigrationFailure, ValueError, TypeError, ArithmeticError) as exc:
                reason = (
                    str(exc)
                    if isinstance(exc, MigrationFailure)
                    else "invalid numeric representation"
                )
                raise NumericMigrationFailure(table, column, key, reason) from None
        yield row


def _destination_rows(connection: Connection, table: Table) -> Iterator[dict[str, Any]]:
    # Read JSON as text so arbitrary JSON numbers survive verification exactly.
    columns = [
        cast(c, String).label(c.name) if isinstance(c.type, JSON) else c for c in table.columns
    ]
    for row in connection.execute(select(*columns)).mappings():
        yield dict(row)


def _inventory(rows: Iterator[dict[str, Any]], table: Table) -> dict[str, Any]:
    fingerprints: list[tuple[str, str]] = []
    owners: dict[str, int] = {}
    nulls = {c.name: 0 for c in table.columns}
    for row in rows:
        try:
            values = {c.name: _value(row[c.name], c.type) for c in table.columns}
        except (MigrationFailure, ValueError, TypeError, ArithmeticError) as exc:
            key = _serialize([row[c.name] for c in table.primary_key])
            raise MigrationFailure(
                f"{table.name} key {key}: invalid source/destination value ({type(exc).__name__})"
            ) from None
        key = _serialize([values[c.name] for c in table.primary_key])
        for c in table.columns:
            if values[c.name] is None:
                nulls[c.name] += 1
                if not c.nullable:
                    raise MigrationFailure(f"{table.name} key {key}: NULL in {c.name}")
        owner = values.get("owner_id", values.get("user_id"))
        if owner is not None:
            owners[str(owner)] = owners.get(str(owner), 0) + 1
        fingerprints.append((key, hashlib.sha256(_serialize(values).encode()).hexdigest()))
    fingerprints.sort()
    if len({key for key, _ in fingerprints}) != len(fingerprints):
        raise MigrationFailure(f"{table.name}: duplicate canonical primary key")
    return {
        "count": len(fingerprints),
        "sha256": hashlib.sha256(_serialize(fingerprints).encode()).hexdigest(),
        "first_key": fingerprints[0][0] if fingerprints else None,
        "last_key": fingerprints[-1][0] if fingerprints else None,
        "owners": owners,
        "null_counts": nulls,
    }


def _source_constraints(source: sqlite3.Connection, table: Table) -> None:
    # Reflect destination unique constraints as well as the source's indexes.
    unique_sets = {tuple(c.name for c in table.primary_key)}
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            unique_sets.add(tuple(c.name for c in constraint.columns))
    for index in table.indexes:
        if index.unique:
            unique_sets.add(tuple(c.name for c in index.columns))
    for names in unique_sets:
        cols = ",".join(_quote(n) for n in names)
        nonnull = " AND ".join(f"{_quote(n)} IS NOT NULL" for n in names)
        duplicate = source.execute(
            f"SELECT 1 FROM {_quote(table.name)} WHERE {nonnull} "
            f"GROUP BY {cols} HAVING COUNT(*)>1 LIMIT 1"
        ).fetchone()
        if duplicate:
            raise MigrationFailure(f"{table.name}: duplicate unique key ({cols})")


def migrate_snapshot(
    source_path: Path,
    manifest: Mapping[str, Any],
    destination_url: str,
    *,
    dry_run: bool = False,
    verify_only: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if dry_run and verify_only:
        raise MigrationFailure("Choose dry-run or verify-only, not both")
    source_path = source_path.resolve(strict=True)
    if source_path.stat().st_mode & 0o222:
        raise MigrationFailure(
            "Source must be a verified read-only snapshot, never the live database"
        )
    source_hash = _hash_file(source_path)
    if source_hash != manifest.get("sha256") or source_path.stat().st_size != manifest.get("bytes"):
        raise MigrationFailure("Snapshot checksum/size does not match its backup manifest")
    engine = create_database_engine(Settings(database_url=destination_url))
    if engine.dialect.name != "postgresql":
        engine.dispose()
        raise MigrationFailure("Destination must be PostgreSQL")
    source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
    report: dict[str, Any] = {
        "content_hash_format": "tagged-canonical-v1",
        "dry_run": dry_run,
        "source_sha256": source_hash,
        "tables": {},
        "sequences": [],
    }
    try:
        source.execute("BEGIN")
        if source.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise MigrationFailure("SQLite integrity_check failed")
        if source.execute("PRAGMA foreign_key_check").fetchall():
            raise MigrationFailure("SQLite foreign_key_check failed")
        if source.execute("SELECT version_num FROM alembic_version").fetchall() != [
            (DATABASE_SCHEMA_HEAD,)
        ]:
            raise MigrationFailure("SQLite snapshot must be at the supported Alembic head")
        require_database_ready(engine)
        with engine.begin() as target:
            if verify_only:
                target.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            metadata = MetaData()
            metadata.reflect(target)
            names = {
                r[0]
                for r in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if names != set(metadata.tables):
                raise MigrationFailure(
                    "Source and destination table sets differ; no table may be skipped"
                )
            tables = [t for t in metadata.sorted_tables if t.name != "alembic_version"]
            # Exclude concurrent writes to destination for the entire copy+verify.
            if not dry_run and not verify_only:
                target.execute(
                    text(
                        "LOCK TABLE "
                        + ",".join(_quote(t.name) for t in tables)
                        + " IN ACCESS EXCLUSIVE MODE"
                    )
                )
            for table in tables:
                if not verify_only and target.scalar(select(func.count()).select_from(table)):
                    raise MigrationFailure(f"{table.name}: destination must be empty")
                cols = {r[1] for r in source.execute(f"PRAGMA table_info({_quote(table.name)})")}
                if cols != set(table.columns.keys()):
                    raise MigrationFailure(f"{table.name}: source/destination columns differ")
                _source_constraints(source, table)
                before = _inventory(_source_rows(source, table), table)
                report["tables"][table.name] = {"source": before}
                if progress:
                    progress(f"{table.name}: {before['count']} source rows validated")
                if dry_run:
                    continue
                if verify_only:
                    after = _inventory(_destination_rows(target, table), table)
                    if before != after:
                        raise MigrationFailure(f"{table.name}: content verification failed")
                    report["tables"][table.name].update(destination=after, verified=True)
                    continue
                for raw in _source_rows(source, table):
                    key = _serialize([_value(raw[c.name], c.type) for c in table.primary_key])
                    try:
                        values = {}
                        for column in table.columns:
                            item = raw[column.name]
                            if isinstance(column.type, JSON):
                                values[column.name] = (
                                    null() if item is None else cast(literal(item), column.type)
                                )
                            else:
                                values[column.name] = _value(item, column.type)
                        target.execute(table.insert().values(**values))
                    except (SQLAlchemyError, ValueError, TypeError) as exc:
                        code = getattr(getattr(exc, "orig", None), "sqlstate", None)
                        raise MigrationFailure(
                            f"{table.name} key {key}: import failed "
                            f"({code or type(exc).__name__}); rolled back"
                        ) from None
                after = _inventory(_destination_rows(target, table), table)
                if before != after:
                    raise MigrationFailure(
                        f"{table.name}: content verification failed; rolled back"
                    )
                report["tables"][table.name]["destination"] = after
                report["tables"][table.name]["verified"] = True
            if not dry_run and not verify_only:
                # No constraints are disabled. Check every FK again in the imported snapshot.
                for table in tables:
                    for fk in table.foreign_key_constraints:
                        parent = next(iter(fk.elements)).column.table
                        child = table.alias("child")
                        other = parent.alias("parent")
                        pairs = [
                            (child.c[e.parent.name], other.c[e.column.name]) for e in fk.elements
                        ]
                        from sqlalchemy import and_

                        orphan = target.scalar(
                            select(func.count())
                            .select_from(child)
                            .where(
                                and_(*(a.is_not(None) for a, _ in pairs)),
                                ~select(1)
                                .select_from(other)
                                .where(and_(*(a == b for a, b in pairs)))
                                .exists(),
                            )
                        )
                        if orphan:
                            raise MigrationFailure(f"{table.name}: foreign key {fk.name} failed")
                for table in tables:
                    for col in table.primary_key:
                        if isinstance(col.type, Integer):
                            sequence = target.scalar(
                                text("SELECT pg_get_serial_sequence(:table, :column)"),
                                {"table": table.name, "column": col.name},
                            )
                            if sequence:
                                maximum = target.scalar(select(func.max(col)))
                                next_value = 1 if maximum is None else maximum + 1
                                # Transactional RESTART (setval itself is not rollback-safe).
                                quoted_sequence = ".".join(
                                    _quote(part) for part in sequence.split(".")
                                )
                                target.execute(
                                    text(
                                        f"ALTER SEQUENCE {quoted_sequence} "
                                        f"RESTART WITH {int(next_value)}"
                                    )
                                )
                                report["sequences"].append(
                                    {
                                        "table": table.name,
                                        "column": col.name,
                                        "next_value": next_value,
                                    }
                                )
                report["foreign_keys_valid"] = True
                report["unique_constraints_valid"] = True
                if _hash_file(source_path) != source_hash:
                    raise MigrationFailure("Source changed during migration; rolled back")
        report["status"] = (
            "VERIFIED_READ_ONLY"
            if verify_only
            else "DRY_RUN_VALIDATED"
            if dry_run
            else "IMPORTED_AND_VERIFIED"
        )
        return report
    finally:
        source.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--destination-env",
        default="TWF_DATABASE_URL",
        help="Environment variable holding the PostgreSQL URL; never pass a password in argv",
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Report already exists; use a new path")
    url = os.environ.get(args.destination_env)
    if not url:
        parser.error("Destination URL environment variable is missing")
    try:
        # Validate output access before any import writes; create it private from birth.
        descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            report = migrate_snapshot(
                args.source,
                json.loads(args.manifest.read_text()),
                url,
                dry_run=args.dry_run,
                verify_only=args.verify_only,
                progress=lambda message: print(message, flush=True),
            )
            json.dump(report, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        print(f"{report['status']}: {len(report['tables'])} tables; report: {args.report}")
    except OSError:
        raise SystemExit(
            "Snapshot/report I/O failed. If import committed, use --verify-only with "
            "a new report path; do not assume the destination is empty."
        ) from None
    except (MigrationFailure, SQLAlchemyError) as exc:
        # Never format a driver exception; it may include data/credentials.
        raise SystemExit(
            str(exc)
            if isinstance(exc, MigrationFailure)
            else "Database import failed; rolled back. Check connectivity/schema."
        ) from None


if __name__ == "__main__":
    main()
