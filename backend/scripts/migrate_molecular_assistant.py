"""Idempotent additive migration for the P1.3A Molecular Copilot tables.

The script is intentionally not run during application startup. Operators must
back up a file-backed SQLite database and invoke it explicitly for a release.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from backend.database import Base, DATABASE_URL
from backend.models_db import AssistantMessageRecord, AssistantSessionRecord, AssistantToolExecutionRecord

MIGRATION_VERSION = "20260814_p13a_molecular_assistant_v2"
MIGRATION_DESCRIPTION = "Additive Molecular Copilot audit and atomic confirmation persistence."
MIGRATION_CHECKSUM = hashlib.sha256(MIGRATION_DESCRIPTION.encode("utf-8")).hexdigest()
_TABLES = (AssistantSessionRecord.__table__, AssistantMessageRecord.__table__, AssistantToolExecutionRecord.__table__)


@dataclass(frozen=True)
class MigrationResult:
    applied: bool
    backup_path: str | None


def _sqlite_path(database_url: str) -> Path:
    engine = create_engine(database_url)
    if engine.dialect.name != "sqlite":
        raise ValueError("This release migration supports the documented SQLite deployment database only.")
    if not engine.url.database or engine.url.database == ":memory:":
        raise ValueError("A file-backed SQLite DATABASE_URL is required for an auditable backup.")
    return Path(engine.url.database).resolve()


def _backup_database(path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.stem}.{MIGRATION_VERSION}.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
    source, destination = sqlite3.connect(path), sqlite3.connect(backup)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup


def apply_molecular_assistant_migration(database_url: str = DATABASE_URL, *, backup_dir: Path | None = None) -> MigrationResult:
    path = _sqlite_path(database_url)
    if not path.is_file():
        raise FileNotFoundError("SQLite database does not exist.")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        inspector = inspect(connection)
        existing = connection.execute(text("SELECT checksum FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_VERSION}).scalar_one_or_none() if "schema_migrations" in inspector.get_table_names() else None
    if existing is not None:
        if existing != MIGRATION_CHECKSUM:
            raise RuntimeError("Recorded migration checksum does not match the release script.")
        return MigrationResult(applied=False, backup_path=None)
    backup = _backup_database(path, backup_dir or path.parent / "backups")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(128) PRIMARY KEY, checksum VARCHAR(64) NOT NULL, description TEXT NOT NULL, applied_at DATETIME NOT NULL)"))
        Base.metadata.create_all(bind=connection, tables=list(_TABLES))
        connection.execute(text("INSERT INTO schema_migrations (version, checksum, description, applied_at) VALUES (:version, :checksum, :description, :applied_at)"), {"version": MIGRATION_VERSION, "checksum": MIGRATION_CHECKSUM, "description": MIGRATION_DESCRIPTION, "applied_at": datetime.now(timezone.utc)})
    return MigrationResult(applied=True, backup_path=str(backup))


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up and apply the P1.3A Molecular Copilot migration.")
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--backup-dir", type=Path, default=None)
    args = parser.parse_args()
    result = apply_molecular_assistant_migration(args.database_url, backup_dir=args.backup_dir)
    print({"applied": result.applied, "backup_path": result.backup_path})


if __name__ == "__main__":
    main()
