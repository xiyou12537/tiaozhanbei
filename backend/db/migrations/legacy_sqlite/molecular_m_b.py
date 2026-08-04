"""Explicit staging-only migration for frozen Stage M-B schema.

This module never selects the application database implicitly. Callers must
provide both an immutable source and a distinct staging target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.models_db import Base

MIGRATION_ID = "20260730_01_molecular_m_b"
REBUILT_TABLES = (
    "structure_files",
    "parsed_structures",
    "quantum_region_models",
)
NEW_TABLES_BEFORE_QUANTUM = ("molecular_models",)
NEW_TABLES_AFTER_QUANTUM = (
    "molecular_stage_attempts",
    "molecular_workflows",
    "molecular_electronic_structure_calculations",
    "molecular_observations",
    "molecular_artifact_publication_journal",
    "molecular_logical_validations",
    "molecular_idempotency_records",
)
FORMAL_EVIDENCE_RELATIVE_PATHS = (
    "data/partitioning.db",
    "data/backups/partitioning.pre-stage-b.20260728T102950095.db",
    "data/structure_artifacts/distributed_molecular_circuit_validation_protocol_v1.json",
    "data/structure_artifacts/distributed_validation/dmc_a728180ea4944d36a83ee4dde1762f04/chip_mapping.json",
    "data/structure_artifacts/distributed_validation/dmc_a728180ea4944d36a83ee4dde1762f04/communication_route_plan.json",
    "data/structure_artifacts/distributed_validation/dmc_a728180ea4944d36a83ee4dde1762f04/distributed_executable.json",
    "data/structure_artifacts/distributed_validation/dmc_a728180ea4944d36a83ee4dde1762f04/input_manifest.json",
    "data/structure_artifacts/distributed_validation/dmc_a728180ea4944d36a83ee4dde1762f04/logical_circuit_snapshot.json",
    "data/structure_artifacts/distributed_validation/dmc_a728180ea4944d36a83ee4dde1762f04/optimized_gate_order.json",
    "data/structure_artifacts/distributed_validation/dmc_a728180ea4944d36a83ee4dde1762f04/partition_plan.json",
    "data/structure_artifacts/distributed_validation/dmc_a728180ea4944d36a83ee4dde1762f04/target_topology.json",
)
OLD_COLUMNS = {
    "structure_files": (
        "file_id", "owner_user_id", "material_name", "material_family",
        "description", "original_filename", "normalized_filename", "file_type",
        "file_size_bytes", "file_hash", "storage_path", "parse_status",
        "parse_error_code", "parse_error_message", "structure_id", "created_at",
        "updated_at",
    ),
    "parsed_structures": (
        "structure_id", "file_id", "owner_user_id", "formula", "elements",
        "element_counts", "atom_count", "atomic_sites", "lattice",
        "structure_type", "charge", "spin_multiplicity", "dimensionality",
        "parse_warnings", "validation_status", "validation_errors",
        "validation_warnings", "validation_suggestions", "workflow_id",
        "created_at", "updated_at",
    ),
    "quantum_region_models": (
        "quantum_region_id", "adsorption_model_id", "owner_user_id",
        "region_atom_indices", "frozen_environment_atom_indices",
        "embedding_method", "total_charge", "spin_multiplicity",
        "geometry_source_type", "geometry_method", "geometry_artifact_path",
        "status", "warnings", "created_at", "geometry_optimization_id",
        "preflight_artifact_path",
    ),
}


class MigrationSafetyError(RuntimeError):
    """Raised when a target is not an isolated staging copy."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def formal_evidence_snapshot() -> dict[str, dict[str, str | int]]:
    """Hash the frozen evidence set without opening any file for writing."""
    workspace = _workspace_root()
    return {
        relative_path: {
            "sha256": sha256_file(workspace / relative_path),
            "size_bytes": (workspace / relative_path).stat().st_size,
        }
        for relative_path in FORMAL_EVIDENCE_RELATIVE_PATHS
    }


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _assert_staging_target(source: Path, staging: Path) -> None:
    workspace = _workspace_root()
    formal_root = (workspace / "data").resolve()
    source = source.resolve()
    staging = staging.resolve()
    if source == staging:
        raise MigrationSafetyError("Source and staging database must differ.")
    if staging == formal_root or formal_root in staging.parents:
        raise MigrationSafetyError("Staging database must remain outside data/.")
    if staging.exists():
        raise MigrationSafetyError("Staging target must not already exist.")


def create_verified_staging_copy(
    source: str | Path,
    staging: str | Path,
    expected_source_sha256: str,
) -> dict[str, Any]:
    """Create a consistent staging copy with SQLite's online backup API."""
    source_path = Path(source).resolve()
    staging_path = Path(staging).resolve()
    _assert_staging_target(source_path, staging_path)
    before = sha256_file(source_path)
    if before != expected_source_sha256:
        raise MigrationSafetyError("Source SHA-256 does not match frozen evidence.")
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(
        f"file:{source_path.as_posix()}?mode=ro",
        uri=True,
    )
    staging_connection = sqlite3.connect(staging_path)
    try:
        source_connection.backup(staging_connection)
        staging_connection.commit()
        if staging_connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise MigrationSafetyError("SQLite backup failed integrity_check.")
        source_digests = {
            table: _rows_digest(source_connection, table)
            for table in REBUILT_TABLES
        }
        staging_digests = {
            table: _rows_digest(staging_connection, table)
            for table in REBUILT_TABLES
        }
        if source_digests != staging_digests:
            raise MigrationSafetyError("SQLite backup historical row verification failed.")
    finally:
        staging_connection.close()
        source_connection.close()
    after = sha256_file(source_path)
    copy_sha = sha256_file(staging_path)
    if before != after:
        staging_path.unlink(missing_ok=True)
        raise MigrationSafetyError("Source changed while the staging backup was created.")
    return {
        "source_sha256_before_copy": before,
        "source_sha256_after_copy": after,
        "staging_sha256_before_migration": copy_sha,
        "copy_method": "sqlite_backup_api",
        "copy_historical_rows_verified": True,
    }


def _rows_digest(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    columns = OLD_COLUMNS[table]
    primary_key = columns[0]
    rows = connection.execute(
        f"SELECT {','.join(columns)} FROM {table} ORDER BY {primary_key}"
    ).fetchall()
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    primary_keys = [row[0] for row in rows]
    primary_key_payload = json.dumps(
        primary_keys,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "row_count": len(rows),
        "primary_key_sha256": hashlib.sha256(primary_key_payload).hexdigest(),
        "old_fields_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _schema_snapshot(
    connection: sqlite3.Connection,
    table: str,
) -> dict[str, Any]:
    table_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    table_sql = table_sql_row[0] if table_sql_row else ""
    index_rows = connection.execute(
        "SELECT name,COALESCE(sql,'') FROM sqlite_master "
        "WHERE type='index' AND tbl_name=? ORDER BY name",
        (table,),
    ).fetchall()
    trigger_rows = connection.execute(
        "SELECT name,COALESCE(sql,'') FROM sqlite_master "
        "WHERE type='trigger' AND tbl_name=? ORDER BY name",
        (table,),
    ).fetchall()
    foreign_keys = connection.execute(
        f"PRAGMA foreign_key_list({table})"
    ).fetchall()
    indexes_payload = json.dumps(
        index_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    triggers_payload = json.dumps(
        trigger_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "table_sql": table_sql,
        "table_sql_sha256": _text_sha256(table_sql),
        "indexes": [list(row) for row in index_rows],
        "indexes_sha256": _text_sha256(indexes_payload),
        "triggers": [list(row) for row in trigger_rows],
        "triggers_sha256": _text_sha256(triggers_payload),
        "foreign_keys": [list(row) for row in foreign_keys],
    }


def _ordered_column_sha256(
    connection: sqlite3.Connection,
    table: str,
    primary_key: str,
    column: str,
) -> str:
    rows = connection.execute(
        f"SELECT {primary_key},{column} FROM {table} ORDER BY {primary_key}"
    ).fetchall()
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _create_orm_table(connection: sqlite3.Connection, table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    dialect = sqlite.dialect()
    connection.execute(str(CreateTable(table).compile(dialect=dialect)))
    for index in sorted(table.indexes, key=lambda item: item.name or ""):
        connection.execute(str(CreateIndex(index).compile(dialect=dialect)))


def _execute_statements(connection: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script without sqlite3.executescript's implicit COMMIT."""
    statement = ""
    for line in script.splitlines():
        statement += line + "\n"
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("Incomplete migration SQL statement.")


def _rebuild_structure_files(connection: sqlite3.Connection) -> None:
    _execute_statements(
        connection,
        """
        CREATE TABLE structure_files_m_b (
            file_id VARCHAR(64) NOT NULL PRIMARY KEY,
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            material_name VARCHAR(100) NOT NULL,
            material_family VARCHAR(100),
            description TEXT,
            original_filename VARCHAR(255) NOT NULL,
            normalized_filename VARCHAR(128) NOT NULL,
            file_type VARCHAR(32) NOT NULL,
            input_purpose VARCHAR(32) NOT NULL
                CHECK(input_purpose IN ('legacy_screening','molecular_logical_circuit')),
            file_size_bytes INTEGER NOT NULL,
            file_hash VARCHAR(64) NOT NULL,
            storage_path VARCHAR(500) NOT NULL,
            parse_status VARCHAR(32) NOT NULL,
            parse_error_code VARCHAR(64),
            parse_error_message TEXT,
            structure_id VARCHAR(64),
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE(file_id, owner_user_id, input_purpose)
        );
        INSERT INTO structure_files_m_b (
            file_id,owner_user_id,material_name,material_family,description,
            original_filename,normalized_filename,file_type,input_purpose,
            file_size_bytes,file_hash,storage_path,parse_status,parse_error_code,
            parse_error_message,structure_id,created_at,updated_at
        )
        SELECT
            file_id,owner_user_id,material_name,material_family,description,
            original_filename,normalized_filename,file_type,'legacy_screening',
            file_size_bytes,file_hash,storage_path,parse_status,parse_error_code,
            parse_error_message,structure_id,created_at,updated_at
        FROM structure_files;
        DROP TABLE structure_files;
        ALTER TABLE structure_files_m_b RENAME TO structure_files;
        CREATE UNIQUE INDEX ix_structure_files_structure_id ON structure_files(structure_id);
        CREATE INDEX ix_structure_files_owner_user_id ON structure_files(owner_user_id);
        CREATE INDEX ix_structure_files_file_hash ON structure_files(file_hash);
        CREATE INDEX ix_structure_files_created_at ON structure_files(created_at);
        CREATE INDEX ix_structure_files_parse_status ON structure_files(parse_status);
        CREATE INDEX ix_structure_files_file_type ON structure_files(file_type);
        CREATE INDEX ix_structure_files_input_purpose ON structure_files(input_purpose);
        """
    )


def _rebuild_parsed_structures(connection: sqlite3.Connection) -> None:
    _execute_statements(
        connection,
        """
        CREATE TABLE parsed_structures_m_b (
            structure_id VARCHAR(64) NOT NULL PRIMARY KEY,
            file_id VARCHAR(64) NOT NULL UNIQUE REFERENCES structure_files(file_id),
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            formula VARCHAR(255) NOT NULL,
            elements JSON NOT NULL,
            element_counts JSON NOT NULL,
            atom_count INTEGER NOT NULL,
            atomic_sites JSON NOT NULL,
            lattice JSON,
            structure_type VARCHAR(32) NOT NULL,
            charge INTEGER,
            spin_multiplicity INTEGER,
            dimensionality VARCHAR(32),
            parse_warnings JSON NOT NULL,
            validation_status VARCHAR(32) NOT NULL,
            validation_errors JSON NOT NULL,
            validation_warnings JSON NOT NULL,
            validation_suggestions JSON NOT NULL,
            workflow_id VARCHAR(64) UNIQUE,
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE(structure_id,file_id,owner_user_id)
        );
        INSERT INTO parsed_structures_m_b
        SELECT structure_id,file_id,owner_user_id,formula,elements,element_counts,
               atom_count,atomic_sites,lattice,structure_type,charge,
               spin_multiplicity,dimensionality,parse_warnings,validation_status,
               validation_errors,validation_warnings,validation_suggestions,
               workflow_id,created_at,updated_at
        FROM parsed_structures;
        DROP TABLE parsed_structures;
        ALTER TABLE parsed_structures_m_b RENAME TO parsed_structures;
        CREATE INDEX ix_parsed_structures_owner_user_id ON parsed_structures(owner_user_id);
        CREATE INDEX ix_parsed_structures_created_at ON parsed_structures(created_at);
        """
    )


def _rebuild_quantum_regions(connection: sqlite3.Connection) -> None:
    _execute_statements(
        connection,
        """
        CREATE TABLE quantum_region_models_m_b (
            quantum_region_id VARCHAR(64) NOT NULL PRIMARY KEY,
            source_type VARCHAR(32) NOT NULL,
            adsorption_model_id VARCHAR(64) REFERENCES adsorption_models(adsorption_model_id),
            molecular_model_id VARCHAR(64) REFERENCES molecular_models(molecular_model_id),
            geometry_optimization_id VARCHAR(64) REFERENCES geometry_optimizations(geometry_optimization_id),
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            region_atom_indices JSON NOT NULL,
            frozen_environment_atom_indices JSON NOT NULL,
            embedding_method VARCHAR(64) NOT NULL,
            total_charge INTEGER,
            spin_multiplicity INTEGER,
            geometry_source_type VARCHAR(64) NOT NULL,
            geometry_method VARCHAR(64) NOT NULL,
            geometry_artifact_path VARCHAR(500) NOT NULL,
            source_geometry_artifact_path VARCHAR(500),
            source_geometry_sha256 VARCHAR(64),
            region_atom_count INTEGER,
            region_indices_sha256 VARCHAR(64),
            preflight_artifact_path VARCHAR(500),
            status VARCHAR(32) NOT NULL,
            warnings JSON NOT NULL,
            created_at DATETIME,
            CHECK (
                (source_type='adsorption_model' AND adsorption_model_id IS NOT NULL AND molecular_model_id IS NULL)
                OR
                (source_type='molecular_model' AND adsorption_model_id IS NULL AND molecular_model_id IS NOT NULL)
            )
        );
        INSERT INTO quantum_region_models_m_b (
            quantum_region_id,source_type,adsorption_model_id,molecular_model_id,
            geometry_optimization_id,owner_user_id,region_atom_indices,
            frozen_environment_atom_indices,embedding_method,total_charge,
            spin_multiplicity,geometry_source_type,geometry_method,
            geometry_artifact_path,source_geometry_artifact_path,
            source_geometry_sha256,region_atom_count,region_indices_sha256,
            preflight_artifact_path,status,warnings,created_at
        )
        SELECT
            quantum_region_id,'adsorption_model',adsorption_model_id,NULL,
            geometry_optimization_id,owner_user_id,region_atom_indices,
            frozen_environment_atom_indices,embedding_method,total_charge,
            spin_multiplicity,geometry_source_type,geometry_method,
            geometry_artifact_path,geometry_artifact_path,NULL,
            json_array_length(region_atom_indices),NULL,preflight_artifact_path,
            status,warnings,created_at
        FROM quantum_region_models;
        DROP TABLE quantum_region_models;
        ALTER TABLE quantum_region_models_m_b RENAME TO quantum_region_models;
        CREATE INDEX ix_quantum_region_models_owner_user_id ON quantum_region_models(owner_user_id);
        CREATE INDEX ix_quantum_region_models_created_at ON quantum_region_models(created_at);
        CREATE INDEX ix_quantum_region_models_status ON quantum_region_models(status);
        CREATE INDEX ix_quantum_region_models_source_type ON quantum_region_models(source_type);
        CREATE INDEX ix_quantum_region_models_adsorption_model_id ON quantum_region_models(adsorption_model_id);
        CREATE INDEX ix_quantum_region_models_molecular_model_id ON quantum_region_models(molecular_model_id);
        CREATE INDEX ix_quantum_region_models_geometry_optimization_id ON quantum_region_models(geometry_optimization_id);
        """
    )


def _create_triggers(connection: sqlite3.Connection) -> None:
    _execute_statements(
        connection,
        """
        CREATE TRIGGER trg_structure_file_purpose_immutable
        BEFORE UPDATE OF input_purpose ON structure_files
        WHEN NEW.input_purpose <> OLD.input_purpose
        BEGIN SELECT RAISE(ABORT,'input_purpose_immutable'); END;

        CREATE TRIGGER trg_parsed_structure_source_consistency_insert
        BEFORE INSERT ON parsed_structures
        BEGIN
          SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM structure_files f
            WHERE f.file_id=NEW.file_id AND f.owner_user_id=NEW.owner_user_id
              AND ((f.input_purpose='legacy_screening' AND NEW.workflow_id IS NOT NULL)
                OR (f.input_purpose='molecular_logical_circuit' AND NEW.workflow_id IS NULL))
          ) THEN RAISE(ABORT,'parsed_structure_source_inconsistent') END;
        END;

        CREATE TRIGGER trg_parsed_structure_binding_immutable
        BEFORE UPDATE OF file_id,owner_user_id,workflow_id ON parsed_structures
        BEGIN SELECT RAISE(ABORT,'parsed_structure_binding_immutable'); END;

        CREATE TRIGGER trg_molecular_model_source_version_insert
        BEFORE INSERT ON molecular_models
        BEGIN
          SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM parsed_structures p JOIN structure_files f ON f.file_id=p.file_id
            WHERE p.structure_id=NEW.structure_id AND p.file_id=NEW.source_file_id
              AND p.owner_user_id=NEW.owner_user_id
              AND f.owner_user_id=NEW.owner_user_id
              AND f.input_purpose='molecular_logical_circuit'
          ) THEN RAISE(ABORT,'molecular_model_source_inconsistent') END;
          SELECT CASE
            WHEN NEW.supersedes_molecular_model_id IS NULL AND NEW.model_version<>1
              THEN RAISE(ABORT,'molecular_model_initial_version_invalid')
            WHEN NEW.supersedes_molecular_model_id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM molecular_models m
              WHERE m.molecular_model_id=NEW.supersedes_molecular_model_id
                AND m.owner_user_id=NEW.owner_user_id
                AND m.structure_id=NEW.structure_id
                AND m.confirmation_status='confirmed'
                AND NEW.model_version=m.model_version+1
            ) THEN RAISE(ABORT,'molecular_model_successor_invalid')
          END;
        END;

        CREATE TRIGGER trg_molecular_model_source_immutable
        BEFORE UPDATE OF owner_user_id,structure_id,source_file_id,
          source_input_purpose,model_version,supersedes_molecular_model_id,
          source_file_sha256,canonical_geometry_sha256,canonical_geometry_payload
        ON molecular_models
        BEGIN SELECT RAISE(ABORT,'molecular_model_source_immutable'); END;

        CREATE TRIGGER trg_molecular_model_confirmed_immutable
        BEFORE UPDATE OF coordinate_unit,total_charge,spin_multiplicity,
          atom_count,electron_count,formula,element_set,dimensionality,
          confirmation_status,confirmed_by_user_id,confirmed_at,frozen_input_sha256
        ON molecular_models
        WHEN OLD.confirmation_status='confirmed'
        BEGIN SELECT RAISE(ABORT,'confirmed_molecular_model_immutable'); END;

        CREATE TRIGGER trg_molecular_model_artifact_paths_write_once
        BEFORE UPDATE OF canonical_geometry_artifact_path,input_manifest_artifact_path
        ON molecular_models
        WHEN
          (OLD.canonical_geometry_artifact_path IS NOT NULL
            AND NEW.canonical_geometry_artifact_path IS NOT OLD.canonical_geometry_artifact_path)
          OR
          (OLD.input_manifest_artifact_path IS NOT NULL
            AND NEW.input_manifest_artifact_path IS NOT OLD.input_manifest_artifact_path)
        BEGIN SELECT RAISE(ABORT,'molecular_model_artifact_path_write_once'); END;

        CREATE TRIGGER trg_confirmed_molecular_model_delete_forbidden
        BEFORE DELETE ON molecular_models
        WHEN OLD.confirmation_status='confirmed'
        BEGIN SELECT RAISE(ABORT,'confirmed_molecular_model_delete_forbidden'); END;

        CREATE TRIGGER trg_quantum_region_source_consistency_insert
        BEFORE INSERT ON quantum_region_models
        BEGIN
          SELECT CASE
            WHEN NEW.source_type='adsorption_model' AND NOT EXISTS (
              SELECT 1 FROM adsorption_models a
              WHERE a.adsorption_model_id=NEW.adsorption_model_id
                AND a.owner_user_id=NEW.owner_user_id
            ) THEN RAISE(ABORT,'quantum_region_adsorption_owner_inconsistent')
            WHEN NEW.source_type='molecular_model' AND NOT EXISTS (
              SELECT 1 FROM molecular_models m
              WHERE m.molecular_model_id=NEW.molecular_model_id
                AND m.owner_user_id=NEW.owner_user_id
                AND m.confirmation_status='confirmed'
                AND json_array_length(NEW.region_atom_indices)=m.atom_count
                AND json_array_length(NEW.frozen_environment_atom_indices)=0
                AND NEW.embedding_method='none'
                AND NEW.total_charge=m.total_charge
                AND NEW.spin_multiplicity=m.spin_multiplicity
                AND NEW.region_atom_count=m.atom_count
                AND NEW.region_indices_sha256 IS NOT NULL
                AND NEW.geometry_artifact_path=NEW.source_geometry_artifact_path
                AND NEW.source_geometry_sha256=m.canonical_geometry_sha256
            ) THEN RAISE(ABORT,'quantum_region_molecular_source_inconsistent')
          END;
        END;

        CREATE TRIGGER trg_quantum_region_source_immutable
        BEFORE UPDATE OF source_type,adsorption_model_id,molecular_model_id,
          owner_user_id,region_atom_indices,frozen_environment_atom_indices,
          embedding_method,total_charge,spin_multiplicity,geometry_artifact_path,
          source_geometry_artifact_path,source_geometry_sha256,
          region_atom_count,region_indices_sha256
        ON quantum_region_models
        BEGIN SELECT RAISE(ABORT,'quantum_region_source_immutable'); END;

        CREATE TRIGGER trg_molecular_observation_append_only_update
        BEFORE UPDATE ON molecular_observations
        BEGIN SELECT RAISE(ABORT,'molecular_observation_append_only'); END;
        CREATE TRIGGER trg_molecular_observation_append_only_delete
        BEFORE DELETE ON molecular_observations
        BEGIN SELECT RAISE(ABORT,'molecular_observation_append_only'); END;

        CREATE TRIGGER trg_publication_identity_immutable
        BEFORE UPDATE OF molecular_workflow_id,molecular_model_id,owner_user_id,
          artifact_role,filename,schema_id,schema_version,target_relative_path,
          expected_payload_sha256,expected_file_sha256
        ON molecular_artifact_publication_journal
        BEGIN SELECT RAISE(ABORT,'publication_identity_immutable'); END;

        CREATE TRIGGER trg_publication_published_write_once
        BEFORE UPDATE ON molecular_artifact_publication_journal
        WHEN OLD.status='published'
        BEGIN SELECT RAISE(ABORT,'published_journal_write_once'); END;
        """
    )


def migrate_staging_database(staging: str | Path) -> dict[str, Any]:
    """Run the whole rebuild atomically against an isolated staging database."""
    staging_path = Path(staging).resolve()
    formal_root = (_workspace_root() / "data").resolve()
    if not staging_path.is_file() or formal_root in staging_path.parents:
        raise MigrationSafetyError("Migration accepts only an existing staging DB outside data/.")
    pre_sha = sha256_file(staging_path)
    connection = sqlite3.connect(staging_path)
    try:
        before = {table: _rows_digest(connection, table) for table in REBUILT_TABLES}
        schema_before = {
            table: _schema_snapshot(connection, table)
            for table in REBUILT_TABLES
        }
        workflow_id_sha256_before = _ordered_column_sha256(
            connection,
            "parsed_structures",
            "structure_id",
            "workflow_id",
        )
        baseline_foreign_key_check = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        _rebuild_structure_files(connection)
        _rebuild_parsed_structures(connection)
        for table in NEW_TABLES_BEFORE_QUANTUM:
            _create_orm_table(connection, table)
        _rebuild_quantum_regions(connection)
        for table in NEW_TABLES_AFTER_QUANTUM:
            _create_orm_table(connection, table)
        _create_triggers(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_schema_migrations (
                migration_id VARCHAR(128) PRIMARY KEY,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO legacy_schema_migrations(migration_id) VALUES (?)",
            (MIGRATION_ID,),
        )
        after = {table: _rows_digest(connection, table) for table in REBUILT_TABLES}
        schema_after = {
            table: _schema_snapshot(connection, table)
            for table in REBUILT_TABLES
        }
        workflow_id_sha256_after = _ordered_column_sha256(
            connection,
            "parsed_structures",
            "structure_id",
            "workflow_id",
        )
        if before != after:
            raise RuntimeError("Historical row/PK/old-field comparison failed.")
        if workflow_id_sha256_before != workflow_id_sha256_after:
            raise RuntimeError("Historical workflow_id comparison failed.")
        purpose_backfill = connection.execute(
            "SELECT input_purpose,count(*) FROM structure_files "
            "GROUP BY input_purpose ORDER BY input_purpose"
        ).fetchall()
        if purpose_backfill != [("legacy_screening", before["structure_files"]["row_count"])]:
            raise RuntimeError("Historical input_purpose backfill failed.")
        foreign_key_check = connection.execute("PRAGMA foreign_key_check").fetchall()
        integrity_check = connection.execute("PRAGMA integrity_check").fetchall()
        quick_check = connection.execute("PRAGMA quick_check").fetchall()
        all_trigger_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "ORDER BY name"
            ).fetchall()
        ]
        if (
            foreign_key_check != baseline_foreign_key_check
            or integrity_check != [("ok",)]
            or quick_check != [("ok",)]
        ):
            raise RuntimeError("Post-migration SQLite validation failed.")
        connection.commit()
        connection.execute("PRAGMA foreign_keys=ON")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "migration_id": MIGRATION_ID,
        "staging_database_path": str(staging_path),
        "staging_sha256_before_migration": pre_sha,
        "staging_sha256_after_migration": sha256_file(staging_path),
        "rebuilt_table_comparison": {
            table: {"before": before[table], "after": after[table], "equal": True}
            for table in REBUILT_TABLES
        },
        "rebuilt_table_schema": {
            table: {
                "before": schema_before[table],
                "after": schema_after[table],
            }
            for table in REBUILT_TABLES
        },
        "historical_workflow_id_sha256_before": workflow_id_sha256_before,
        "historical_workflow_id_sha256_after": workflow_id_sha256_after,
        "historical_workflow_id_unchanged": True,
        "historical_input_purpose_backfill": [
            {"input_purpose": purpose, "row_count": count}
            for purpose, count in purpose_backfill
        ],
        "restored_composite_unique_keys": [
            "structure_files(file_id,owner_user_id,input_purpose)",
            "parsed_structures(structure_id,file_id,owner_user_id)",
            "molecular_models(owner_user_id,structure_id,model_version)",
            "molecular_models(supersedes_molecular_model_id)",
        ],
        "required_trigger_names": all_trigger_names,
        "foreign_key_check_before": [list(row) for row in baseline_foreign_key_check],
        "foreign_key_check_after": [list(row) for row in foreign_key_check],
        "foreign_key_check_unchanged": True,
        "integrity_check": ["ok"],
        "quick_check": ["ok"],
        "historical_distributed_statevector_inferred": False,
        "runtime_promoted": False,
        "runtime_switch_pending": [
            "stage_m_b_runtime_promotion_authorized=true",
            "promote reviewed staging DB to data/runtime/molecular-v1/partitioning-runtime.db",
            "set LEGACY_DATABASE_PATH to the promoted runtime DB",
            "bind EXPECTED_RUNTIME_MIGRATION_ID and migration manifest SHA",
            "restart and pass startup gate before enabling molecular writes",
        ],
        "interruption_strategy": "single BEGIN IMMEDIATE transaction; rollback on any exception",
    }


def write_manifest_no_clobber(manifest: dict[str, Any], target: str | Path) -> str:
    """Write a staging migration manifest without replacing an existing file."""
    target_path = Path(target).resolve()
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--staging", required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    evidence_before = formal_evidence_snapshot()
    copy_evidence = create_verified_staging_copy(
        args.source,
        args.staging,
        args.expected_source_sha256,
    )
    migration_result = migrate_staging_database(args.staging)
    evidence_after = formal_evidence_snapshot()
    if evidence_before != evidence_after:
        raise MigrationSafetyError("Frozen evidence changed during staging migration.")
    manifest = {
        **copy_evidence,
        **migration_result,
        "formal_evidence_before": evidence_before,
        "formal_evidence_after": evidence_after,
        "formal_evidence_unchanged": True,
    }
    manifest["migration_source_sha256"] = sha256_file(Path(__file__))
    manifest_sha = write_manifest_no_clobber(manifest, args.manifest)
    print(json.dumps({"manifest": args.manifest, "manifest_sha256": manifest_sha}))


if __name__ == "__main__":
    main()
