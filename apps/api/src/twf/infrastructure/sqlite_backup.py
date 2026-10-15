"""Create and verify a new SQLite backup after stopping all TWF writers."""

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def backup(source: Path, directory: Path) -> Path:
    source = source.resolve(strict=True)
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    destination = directory / "twf-pre-postgres.sqlite"
    with destination.open("xb"):
        pass
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as reader:
        with sqlite3.connect(destination) as writer:
            reader.backup(writer)
            if writer.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("Backup failed integrity_check; do not migrate")
            if writer.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Backup has foreign-key anomalies; do not migrate")
            revision = writer.execute("SELECT version_num FROM alembic_version").fetchall()
    with destination.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    os.chmod(destination, 0o400)
    manifest = directory / "manifest.json"
    with manifest.open("x") as output:
        json.dump(
            {
                "source": str(source),
                "backup": str(destination.resolve()),
                "created_at": datetime.now(UTC).isoformat(),
                "bytes": destination.stat().st_size,
                "sha256": checksum,
                "integrity_check": "ok",
                "foreign_key_errors": 0,
                "revision": revision,
            },
            output,
            indent=2,
        )
        output.write("\n")
    manifest.chmod(0o400)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--directory", required=True, type=Path, help="New backup directory")
    parser.add_argument("--writers-stopped", required=True, action="store_true")
    args = parser.parse_args()
    manifest = backup(args.source, args.directory)
    print(f"Verified read-only backup: {manifest}")
    print("Apply filesystem immutability (chattr +i) or WORM retention before migrating.")


if __name__ == "__main__":
    main()
