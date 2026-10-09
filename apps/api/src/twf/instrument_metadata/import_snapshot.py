"""Explicit CLI: python -m twf.instrument_metadata.import_snapshot SNAPSHOT."""

import argparse
import json
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from twf.config.settings import Settings
from twf.infrastructure.database import create_database_engine, create_session_factory
from twf.instrument_metadata.importer import (
    ImportFailure,
    SnapshotImporter,
    SnapshotValidationError,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Validate and import instrument metadata.")
    value.add_argument("snapshot", type=Path)
    value.add_argument("--summary", type=Path)
    value.add_argument("--minimum-rows", type=int, default=2001)
    return value


def main() -> int:
    args = parser().parse_args()
    summary = args.summary
    if summary is None:
        candidate = args.snapshot.with_name("nse_instrument_metadata_summary.json")
        summary = candidate if candidate.exists() else None
    engine = create_database_engine(Settings())
    try:
        result = SnapshotImporter(
            create_session_factory(engine), minimum_rows=args.minimum_rows
        ).import_snapshot(args.snapshot, summary)
    except SnapshotValidationError as exc:
        print(json.dumps({"status": "FAILED", "error": exc.code}))
        return 2
    except (ImportFailure, SQLAlchemyError):
        print(json.dumps({"status": "FAILED", "error": "DATABASE_IMPORT_FAILED"}))
        return 3
    finally:
        engine.dispose()
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
