from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event, inspect

from backend.models_db import (
    DistributedCompilationRecord,
    DistributedIdempotencyRecord,
    DistributedSimulationRecord,
    VqeCircuitRecord,
    VqeExecutionRecord,
)

MIGRATION_ID = "20260728_01_distributed_validation_v1"
HISTORICAL_ORIGIN = "historical_artifact_registration"

PROVENANCE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("record_origin", "VARCHAR(64) NOT NULL DEFAULT 'native_workflow'"),
    ("source_artifact_id", "VARCHAR(160)"),
    ("source_artifact_path", "VARCHAR(500)"),
    ("source_artifact_sha256", "VARCHAR(64)"),
    ("registration_scheme", "VARCHAR(64)"),
    ("registration_key", "VARCHAR(64)"),
    ("registered_at", "DATETIME"),
    ("registration_manifest", "JSON"),
)

PROVENANCE_TABLES = (
    "active_spaces",
    "fermionic_hamiltonians",
    "structure_qubit_hamiltonians",
    "vqe_circuits",
    "vqe_executions",
    "classical_references",
    "quantum_closure_benchmarks",
)

QUBIT_HAMILTONIAN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("ordered_pauli_payload_sha256", "VARCHAR(64)"),
)

CLOSURE_QUALIFICATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("benchmark_role", "VARCHAR(32)"),
    ("qualification_protocol_id", "VARCHAR(128)"),
    ("qualification_protocol_version", "VARCHAR(32)"),
    ("qualification_status", "VARCHAR(96)"),
    ("qualification_recomputed", "BOOLEAN"),
    ("source_vqe_artifact_id", "VARCHAR(160)"),
    ("source_vqe_artifact_path", "VARCHAR(500)"),
    ("source_vqe_artifact_sha256", "VARCHAR(64)"),
    ("remediation_artifact_id", "VARCHAR(160)"),
    ("remediation_artifact_path", "VARCHAR(500)"),
    ("remediation_artifact_sha256", "VARCHAR(64)"),
    ("qualification_protocol_artifact_path", "VARCHAR(500)"),
    ("qualification_protocol_artifact_sha256", "VARCHAR(64)"),
    ("scientific_adsorption_validation", "BOOLEAN NOT NULL DEFAULT 0"),
    ("ground_state_assessed", "BOOLEAN NOT NULL DEFAULT 0"),
)


class MigrationError(RuntimeError):
    """Raised when the legacy database cannot be migrated safely."""


def _sqlite_engine(database_path: Path):
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _column_names(connection, table_name: str) -> set[str]:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({table_name})").mappings()
    return {str(row["name"]) for row in rows}


def _add_columns(connection, table_name: str, columns: tuple[tuple[str, str], ...]) -> None:
    existing = _column_names(connection, table_name)
    for name, definition in columns:
        if name not in existing:
            connection.exec_driver_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN "{name}" {definition}'
            )


def _rebuild_empty_vqe_tables_if_required(connection) -> None:
    columns = {
        row["name"]: row
        for row in connection.exec_driver_sql("PRAGMA table_info(vqe_circuits)").mappings()
    }
    measurement_column = columns.get("measurement_plan_artifact_path")
    requires_rebuild = (
        measurement_column is not None
        and int(measurement_column["notnull"]) == 1
    )
    if not requires_rebuild:
        return

    circuit_count = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM vqe_circuits"
    ).scalar_one()
    execution_count = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM vqe_executions"
    ).scalar_one()
    if circuit_count or execution_count:
        raise MigrationError(
            "vqe_circuits/vqe_executions must be empty before the nullable "
            "measurement-plan schema migration."
        )

    connection.exec_driver_sql("DROP TABLE vqe_executions")
    connection.exec_driver_sql("DROP TABLE vqe_circuits")
    VqeCircuitRecord.__table__.create(bind=connection)
    VqeExecutionRecord.__table__.create(bind=connection)


def _create_domain_tables(connection) -> None:
    DistributedCompilationRecord.__table__.create(bind=connection, checkfirst=True)
    DistributedSimulationRecord.__table__.create(bind=connection, checkfirst=True)
    DistributedIdempotencyRecord.__table__.create(bind=connection, checkfirst=True)


def _create_indexes(connection) -> None:
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_vqe_execution_owner "
        "ON vqe_executions(execution_id, owner_user_id)"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_qubit_hamiltonian_owner "
        "ON structure_qubit_hamiltonians(qubit_hamiltonian_id, owner_user_id)"
    )
    for table_name in PROVENANCE_TABLES:
        connection.exec_driver_sql(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{table_name}_registration "
            f"ON {table_name}(registration_scheme, registration_key) "
            "WHERE registration_key IS NOT NULL"
        )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_closure_protocol_qualification "
        "ON quantum_closure_benchmarks("
        "owner_user_id, vqe_execution_id, benchmark_role, "
        "qualification_protocol_id, qualification_protocol_version"
        ") WHERE qualification_protocol_id IS NOT NULL"
    )


def _create_provenance_triggers(connection) -> None:
    for table_name in PROVENANCE_TABLES:
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table_name}_historical_complete
            BEFORE INSERT ON {table_name}
            WHEN NEW.record_origin = '{HISTORICAL_ORIGIN}' AND (
                NEW.source_artifact_id IS NULL OR
                NEW.source_artifact_path IS NULL OR
                NEW.source_artifact_sha256 IS NULL OR
                NEW.registration_scheme IS NULL OR
                NEW.registration_key IS NULL OR
                NEW.registered_at IS NULL OR
                NEW.registration_manifest IS NULL
            )
            BEGIN
                SELECT RAISE(ABORT, 'historical_provenance_incomplete');
            END
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table_name}_historical_immutable
            BEFORE UPDATE ON {table_name}
            WHEN OLD.record_origin = '{HISTORICAL_ORIGIN}'
            BEGIN
                SELECT RAISE(ABORT, 'historical_record_immutable');
            END
            """
        )


def _create_distributed_triggers(connection) -> None:
    connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS trg_distributed_compilation_immutable_input
        BEFORE UPDATE ON distributed_compilations
        WHEN
            NEW.owner_user_id IS NOT OLD.owner_user_id OR
            NEW.vqe_execution_id IS NOT OLD.vqe_execution_id OR
            NEW.qubit_hamiltonian_id IS NOT OLD.qubit_hamiltonian_id OR
            NEW.closure_benchmark_id IS NOT OLD.closure_benchmark_id OR
            NEW.benchmark_level IS NOT OLD.benchmark_level OR
            NEW.execution_stage IS NOT OLD.execution_stage OR
            NEW.protocol_id IS NOT OLD.protocol_id OR
            NEW.protocol_version IS NOT OLD.protocol_version OR
            NEW.protocol_sha256 IS NOT OLD.protocol_sha256 OR
            NEW.topology_sha256 IS NOT OLD.topology_sha256 OR
            NEW.raw_qasm_sha256 IS NOT OLD.raw_qasm_sha256 OR
            NEW.canonical_circuit_sha256 IS NOT OLD.canonical_circuit_sha256 OR
            NEW.parameter_sha256 IS NOT OLD.parameter_sha256 OR
            NEW.hamiltonian_artifact_sha256 IS NOT OLD.hamiltonian_artifact_sha256 OR
            NEW.ordered_pauli_payload_sha256 IS NOT OLD.ordered_pauli_payload_sha256 OR
            NEW.execution_semantics_strategy IS NOT OLD.execution_semantics_strategy OR
            NEW.actual_distributed_hardware_execution != 0
        BEGIN
            SELECT RAISE(ABORT, 'distributed_compilation_input_immutable');
        END
        """
    )
    artifact_columns = (
        "input_manifest",
        "logical_snapshot",
        "partition_plan",
        "optimized_gate_order",
        "target_topology",
        "chip_mapping",
        "communication_route_plan",
        "distributed_executable",
    )
    for prefix in artifact_columns:
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_distributed_compilation_{prefix}_write_once
            BEFORE UPDATE ON distributed_compilations
            WHEN (
                OLD.{prefix}_path IS NOT NULL AND
                NEW.{prefix}_path IS NOT OLD.{prefix}_path
            ) OR (
                OLD.{prefix}_sha256 IS NOT NULL AND
                NEW.{prefix}_sha256 IS NOT OLD.{prefix}_sha256
            )
            BEGIN
                SELECT RAISE(ABORT, 'distributed_artifact_write_once');
            END
            """
        )
    connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS trg_distributed_compilation_attempt_cas
        BEFORE UPDATE OF formal_attempts_started ON distributed_compilations
        WHEN NOT (
            NEW.formal_attempts_started = OLD.formal_attempts_started OR
            (
                OLD.formal_attempts_started = 0 AND
                NEW.formal_attempts_started = 1 AND
                OLD.status = 'distributed_executable_ready'
            )
        )
        BEGIN
            SELECT RAISE(ABORT, 'formal_attempt_transition_invalid');
        END
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TRIGGER IF NOT EXISTS trg_distributed_simulation_immutable_input
        BEFORE UPDATE ON distributed_simulations
        WHEN
            NEW.compilation_id IS NOT OLD.compilation_id OR
            NEW.owner_user_id IS NOT OLD.owner_user_id OR
            NEW.formal_attempt_number IS NOT OLD.formal_attempt_number OR
            NEW.execution_backend_type IS NOT OLD.execution_backend_type OR
            NEW.execution_backend_detail IS NOT OLD.execution_backend_detail OR
            NEW.shots IS NOT OLD.shots OR
            NEW.actual_distributed_hardware_execution != 0
        BEGIN
            SELECT RAISE(ABORT, 'distributed_simulation_input_immutable');
        END
        """
    )
    for prefix in ("result_artifact", "validation_report"):
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_distributed_simulation_{prefix}_write_once
            BEFORE UPDATE ON distributed_simulations
            WHEN (
                OLD.{prefix}_path IS NOT NULL AND
                NEW.{prefix}_path IS NOT OLD.{prefix}_path
            ) OR (
                OLD.{prefix}_sha256 IS NOT NULL AND
                NEW.{prefix}_sha256 IS NOT OLD.{prefix}_sha256
            )
            BEGIN
                SELECT RAISE(ABORT, 'distributed_artifact_write_once');
            END
            """
        )


def upgrade_database(database_path: Path) -> dict[str, object]:
    """Apply the V1 distributed-validation migration to one SQLite database."""
    resolved = database_path.resolve()
    if not resolved.exists():
        raise MigrationError(f"Database does not exist: {resolved}")

    engine = _sqlite_engine(resolved)
    with engine.connect() as connection:
        existing_fk_violations = {
            tuple(row.values())
            for row in connection.exec_driver_sql("PRAGMA foreign_key_check").mappings()
        }
        already_applied = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='legacy_schema_migrations'"
        ).scalar_one_or_none()
        if already_applied:
            row = connection.exec_driver_sql(
                "SELECT 1 FROM legacy_schema_migrations WHERE migration_id=?",
                (MIGRATION_ID,),
            ).scalar_one_or_none()
            if row:
                return {"migration_id": MIGRATION_ID, "applied": False, "database": str(resolved)}

        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS legacy_schema_migrations ("
                "migration_id VARCHAR(96) PRIMARY KEY, "
                "applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            _rebuild_empty_vqe_tables_if_required(connection)
            for table_name in PROVENANCE_TABLES:
                _add_columns(connection, table_name, PROVENANCE_COLUMNS)
            _add_columns(
                connection,
                "structure_qubit_hamiltonians",
                QUBIT_HAMILTONIAN_COLUMNS,
            )
            _add_columns(
                connection,
                "quantum_closure_benchmarks",
                CLOSURE_QUALIFICATION_COLUMNS,
            )
            _create_domain_tables(connection)
            _create_indexes(connection)
            _create_provenance_triggers(connection)
            _create_distributed_triggers(connection)
            connection.exec_driver_sql(
                "INSERT INTO legacy_schema_migrations(migration_id) VALUES (?)",
                (MIGRATION_ID,),
            )
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
        finally:
            if connection.in_transaction():
                connection.rollback()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()

        fk_violations = {
            tuple(row.values())
            for row in connection.exec_driver_sql("PRAGMA foreign_key_check").mappings()
        }
        new_fk_violations = fk_violations - existing_fk_violations
        if new_fk_violations:
            raise MigrationError(
                f"New foreign-key violations after migration: {sorted(new_fk_violations)}"
            )

        table_names = set(inspect(connection).get_table_names())
        required_tables = {
            "distributed_compilations",
            "distributed_simulations",
            "distributed_idempotency_records",
        }
        if not required_tables.issubset(table_names):
            raise MigrationError("Distributed validation tables were not created.")

    engine.dispose()
    return {
        "migration_id": MIGRATION_ID,
        "applied": True,
        "database": str(resolved),
        "preexisting_fk_violations": len(existing_fk_violations),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    result = upgrade_database(args.database)
    print(result)


if __name__ == "__main__":
    main()
