"""Idempotent SQLite migration for the molecular Workflow P1.2 release.

P1/P1.1 scientific diagnostics are additive JSON fields in persisted result
documents, so the migration intentionally never rewrites historical results.
Older records retain null/legacy values when read through the typed API.
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
from backend.models_db import (
    DeploymentEvaluationRecord,
    DeploymentStudyRecord,
    MolecularBondScanPointRecord,
    MolecularBondScanRecord,
    MolecularProblemRecord,
)

MIGRATION_VERSION = "20260813_p12_molecular_release"
MIGRATION_DESCRIPTION = (
    "Additive molecular Study/Bond Scan persistence; scientific diagnostics remain in JSON result documents."
)
MIGRATION_CHECKSUM = hashlib.sha256(MIGRATION_DESCRIPTION.encode("utf-8")).hexdigest()

_TABLES = (
    MolecularProblemRecord.__table__,
    DeploymentStudyRecord.__table__,
    DeploymentEvaluationRecord.__table__,
    MolecularBondScanRecord.__table__,
    MolecularBondScanPointRecord.__table__,
)

# SQLite ADD COLUMN cannot safely add NOT NULL fields to a populated legacy
# table.  These additive definitions keep historical values NULL, which is the
# frozen API's explicit legacy representation.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "molecular_problems": {
        "molecule_name": "VARCHAR(120)", "status": "VARCHAR(32) DEFAULT 'queued'",
        "request_json": "JSON", "result_json": "JSON", "error_json": "JSON",
        "created_at": "DATETIME", "updated_at": "DATETIME",
    },
    "deployment_studies": {
        "user_id": "INTEGER", "problem_id": "VARCHAR(64)", "status": "VARCHAR(32) DEFAULT 'queued'",
        "request_json": "JSON", "result_json": "JSON", "error_json": "JSON",
        "created_at": "DATETIME", "updated_at": "DATETIME",
    },
    "deployment_evaluations": {
        "study_id": "VARCHAR(64)", "architecture_id": "VARCHAR(64)", "status": "VARCHAR(32) DEFAULT 'queued'",
        "request_json": "JSON", "result_json": "JSON", "error_json": "JSON",
        "created_at": "DATETIME", "updated_at": "DATETIME",
    },
    "molecular_bond_scans": {
        "user_id": "INTEGER", "idempotency_key": "VARCHAR(128)", "request_json": "JSON",
        "status": "VARCHAR(32) DEFAULT 'queued'", "current_stage": "VARCHAR(64) DEFAULT 'input_validation'",
        "result_json": "JSON", "error_json": "JSON", "created_at": "DATETIME",
        "started_at": "DATETIME", "completed_at": "DATETIME",
    },
    "molecular_bond_scan_points": {
        "scan_id": "VARCHAR(64)", "point_index": "INTEGER", "distance_angstrom": "FLOAT",
        "molecular_problem_id": "VARCHAR(64)", "status": "VARCHAR(32) DEFAULT 'queued'",
        "validation_status": "VARCHAR(32)", "result_json": "JSON", "error_json": "JSON",
        "started_at": "DATETIME", "completed_at": "DATETIME",
    },
}

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_molecular_problems_user_id ON molecular_problems (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_deployment_studies_user_id ON deployment_studies (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_deployment_evaluations_study_id ON deployment_evaluations (study_id)",
    "CREATE INDEX IF NOT EXISTS ix_molecular_bond_scans_user_id ON molecular_bond_scans (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_molecular_bond_scan_points_scan_id ON molecular_bond_scan_points (scan_id)",
)


@dataclass(frozen=True)
class MigrationResult:
    applied: bool
    backup_path: str | None
    changes: tuple[str, ...]


def _sqlite_path(database_url: str) -> Path:
    engine = create_engine(database_url)
    if engine.dialect.name != "sqlite":
        raise ValueError("This release migration supports the documented SQLite production database only.")
    path = engine.url.database
    if not path or path == ":memory:":
        raise ValueError("A file-backed SQLite DATABASE_URL is required for auditable backup.")
    return Path(path).resolve()


def _backup_database(database_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{database_path.stem}.{MIGRATION_VERSION}.{timestamp}.sqlite3"
    source = sqlite3.connect(database_path)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_path


def apply_molecular_release_migration(database_url: str = DATABASE_URL, *, backup_dir: Path | None = None) -> MigrationResult:
    """Back up then apply the additive P1.2 schema migration once."""
    database_path = _sqlite_path(database_url)
    if not database_path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {database_path}")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        inspector = inspect(connection)
        existing = None
        if "schema_migrations" in inspector.get_table_names():
            existing = connection.execute(
                text("SELECT checksum FROM schema_migrations WHERE version = :version"),
                {"version": MIGRATION_VERSION},
            ).scalar_one_or_none()
    if existing is not None:
        if existing != MIGRATION_CHECKSUM:
            raise RuntimeError("Recorded migration checksum does not match the release script.")
        return MigrationResult(applied=False, backup_path=None, changes=())

    backup_path = _backup_database(database_path, backup_dir or database_path.parent / "backups")
    changes: list[str] = []
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(128) PRIMARY KEY, checksum VARCHAR(64) NOT NULL, description TEXT NOT NULL, applied_at DATETIME NOT NULL)"))
        Base.metadata.create_all(bind=connection, tables=list(_TABLES))
        inspector = inspect(connection)
        for table_name, columns in _ADDITIVE_COLUMNS.items():
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}'))
                    changes.append(f"{table_name}.{column_name}")
        for statement in _INDEXES:
            connection.execute(text(statement))
        connection.execute(text("INSERT INTO schema_migrations (version, checksum, description, applied_at) VALUES (:version, :checksum, :description, :applied_at)"), {
            "version": MIGRATION_VERSION, "checksum": MIGRATION_CHECKSUM,
            "description": MIGRATION_DESCRIPTION, "applied_at": datetime.now(timezone.utc),
        })
    return MigrationResult(applied=True, backup_path=str(backup_path), changes=tuple(changes))


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up and apply the P1.2 molecular release migration.")
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--backup-dir", type=Path, default=None)
    args = parser.parse_args()
    result = apply_molecular_release_migration(args.database_url, backup_dir=args.backup_dir)
    print({"applied": result.applied, "backup_path": result.backup_path, "changes": result.changes})


if __name__ == "__main__":
    main()
