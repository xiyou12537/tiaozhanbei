from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event

from backend.services.distributed_validation.remediation_simulator import (
    StructuredSimulationResult,
)
from backend.services.distributed_validation.canonical import (
    canonical_artifact_path,
)

MIGRATION_ID = "20260728_02_distributed_validation_remediation_v2"


class RemediationMigrationError(RuntimeError):
    """Raised when a remediation migration is not safely scoped to a copy."""


def _temporary_engine(database_path: Path):
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _validate_temporary_database(
    database_path: Path,
    temporary_root: Path,
) -> Path:
    resolved_database = database_path.resolve()
    resolved_root = temporary_root.resolve()
    if not resolved_database.exists():
        raise RemediationMigrationError(
            f"Temporary database does not exist: {resolved_database}"
        )
    if resolved_database == resolved_root or resolved_root not in resolved_database.parents:
        raise RemediationMigrationError(
            "Remediation migration requires a database below temporary_root."
        )
    workspace_data = Path(__file__).resolve().parents[4] / "data"
    if resolved_database == (workspace_data / "partitioning.db").resolve():
        raise RemediationMigrationError("Formal partitioning.db is immutable.")
    if (workspace_data / "backups").resolve() in resolved_database.parents:
        raise RemediationMigrationError("Formal database backups are immutable.")
    return resolved_database


def upgrade_remediation_copy(
    database_path: Path,
    *,
    temporary_root: Path,
) -> dict[str, Any]:
    """Install V2 observation storage and reconcile only a temporary DB copy."""
    resolved = _validate_temporary_database(database_path, temporary_root)
    engine = _temporary_engine(resolved)
    with engine.begin() as connection:
        v1 = connection.exec_driver_sql(
            "SELECT 1 FROM legacy_schema_migrations "
            "WHERE migration_id='20260728_01_distributed_validation_v1'"
        ).scalar_one_or_none()
        if v1 is None:
            raise RemediationMigrationError(
                "The temporary copy must first contain the audited V1 migration."
            )
        already_applied = connection.exec_driver_sql(
            "SELECT 1 FROM legacy_schema_migrations WHERE migration_id=?",
            (MIGRATION_ID,),
        ).scalar_one_or_none()
        if already_applied is not None:
            count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM distributed_simulation_observations_v2"
            ).scalar_one()
            guarded_lineages = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM distributed_formal_attempt_lineage_v2"
            ).scalar_one()
            return {
                "migration_id": MIGRATION_ID,
                "applied": False,
                "database": str(resolved),
                "reconciled_rows": count,
                "guarded_lineages": guarded_lineages,
            }
        _create_global_attempt_guard(connection)
        connection.exec_driver_sql(
            """
            CREATE TABLE distributed_simulation_observations_v2 (
                simulation_id VARCHAR(64) PRIMARY KEY,
                owner_user_id INTEGER NOT NULL,
                protocol_fixture_version VARCHAR(64) NOT NULL,
                observations_json JSON NOT NULL,
                assessment_json JSON NOT NULL,
                milestones_json JSON NOT NULL,
                partial BOOLEAN NOT NULL,
                missing_metrics_json JSON NOT NULL,
                logical_statevector_completed BOOLEAN NOT NULL,
                distributed_statevector_completed BOOLEAN NOT NULL,
                observable_evaluation_completed BOOLEAN NOT NULL,
                sector_observation_completed BOOLEAN NOT NULL,
                assessment_completed BOOLEAN NOT NULL,
                result_artifact_published BOOLEAN NOT NULL,
                validation_report_published BOOLEAN NOT NULL,
                result_artifact_path VARCHAR(500),
                result_artifact_sha256 VARCHAR(64),
                validation_report_path VARCHAR(500),
                validation_report_sha256 VARCHAR(64),
                reconciliation_status VARCHAR(96) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(simulation_id)
                    REFERENCES distributed_simulations(simulation_id),
                FOREIGN KEY(owner_user_id) REFERENCES users(id),
                CHECK (
                    logical_statevector_completed IN (0,1) AND
                    distributed_statevector_completed IN (0,1) AND
                    observable_evaluation_completed IN (0,1) AND
                    sector_observation_completed IN (0,1) AND
                    assessment_completed IN (0,1) AND
                    result_artifact_published IN (0,1) AND
                    validation_report_published IN (0,1)
                )
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER trg_simulation_observations_v2_milestones_monotonic
            BEFORE UPDATE ON distributed_simulation_observations_v2
            WHEN
                NEW.logical_statevector_completed <
                    OLD.logical_statevector_completed OR
                NEW.distributed_statevector_completed <
                    OLD.distributed_statevector_completed OR
                NEW.observable_evaluation_completed <
                    OLD.observable_evaluation_completed OR
                NEW.sector_observation_completed <
                    OLD.sector_observation_completed OR
                NEW.assessment_completed < OLD.assessment_completed OR
                NEW.result_artifact_published <
                    OLD.result_artifact_published OR
                NEW.validation_report_published <
                    OLD.validation_report_published
            BEGIN
                SELECT RAISE(ABORT, 'execution_milestone_regression');
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE INDEX ix_simulation_observations_v2_owner
            ON distributed_simulation_observations_v2(owner_user_id)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE INDEX ix_simulation_observations_v2_reconciliation_status
            ON distributed_simulation_observations_v2(reconciliation_status)
            """
        )
        reconciled = _reconcile_existing_rows(connection)
        guarded_lineages = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM distributed_formal_attempt_lineage_v2"
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO legacy_schema_migrations(migration_id) VALUES (?)",
            (MIGRATION_ID,),
        )
    engine.dispose()
    return {
        "migration_id": MIGRATION_ID,
        "applied": True,
        "database": str(resolved),
        "reconciled_rows": reconciled,
        "guarded_lineages": guarded_lineages,
    }


def _create_global_attempt_guard(connection: Any) -> None:
    connection.exec_driver_sql(
        """
        CREATE TABLE distributed_formal_attempt_lineage_v2 (
            owner_user_id INTEGER NOT NULL,
            vqe_execution_id VARCHAR(64) NOT NULL,
            qubit_hamiltonian_id VARCHAR(64) NOT NULL,
            closure_benchmark_id VARCHAR(64) NOT NULL,
            benchmark_level VARCHAR(32) NOT NULL,
            attempts_consumed INTEGER NOT NULL,
            terminal_status VARCHAR(64) NOT NULL,
            source_simulation_id VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (
                owner_user_id,
                vqe_execution_id,
                benchmark_level
            ),
            FOREIGN KEY(owner_user_id) REFERENCES users(id),
            FOREIGN KEY(vqe_execution_id)
                REFERENCES vqe_executions(execution_id),
            FOREIGN KEY(qubit_hamiltonian_id)
                REFERENCES structure_qubit_hamiltonians(qubit_hamiltonian_id),
            FOREIGN KEY(closure_benchmark_id)
                REFERENCES quantum_closure_benchmarks(closure_benchmark_id),
            FOREIGN KEY(source_simulation_id)
                REFERENCES distributed_simulations(simulation_id),
            CHECK (attempts_consumed >= 1)
        )
        """
    )
    connection.exec_driver_sql(
        """
        INSERT INTO distributed_formal_attempt_lineage_v2 (
            owner_user_id,
            vqe_execution_id,
            qubit_hamiltonian_id,
            closure_benchmark_id,
            benchmark_level,
            attempts_consumed,
            terminal_status,
            source_simulation_id
        )
        SELECT
            compilation.owner_user_id,
            compilation.vqe_execution_id,
            compilation.qubit_hamiltonian_id,
            compilation.closure_benchmark_id,
            compilation.benchmark_level,
            COUNT(simulation.simulation_id),
            'consumed_failed',
            MIN(simulation.simulation_id)
        FROM distributed_compilations AS compilation
        JOIN distributed_simulations AS simulation
          ON simulation.compilation_id = compilation.compilation_id
         AND simulation.owner_user_id = compilation.owner_user_id
        WHERE compilation.authorization_mode <> 'test_only'
        GROUP BY
            compilation.owner_user_id,
            compilation.vqe_execution_id,
            compilation.qubit_hamiltonian_id,
            compilation.closure_benchmark_id,
            compilation.benchmark_level
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TRIGGER trg_formal_lineage_blocks_new_compilation_v2
        BEFORE INSERT ON distributed_compilations
        WHEN NEW.authorization_mode <> 'test_only'
         AND EXISTS (
            SELECT 1
            FROM distributed_formal_attempt_lineage_v2 AS guard
            WHERE guard.owner_user_id = NEW.owner_user_id
              AND guard.vqe_execution_id = NEW.vqe_execution_id
              AND guard.benchmark_level = NEW.benchmark_level
              AND guard.attempts_consumed >= 1
         )
        BEGIN
            SELECT RAISE(ABORT, 'formal_lineage_attempt_consumed');
        END
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TRIGGER trg_formal_lineage_blocks_new_simulation_v2
        BEFORE INSERT ON distributed_simulations
        WHEN EXISTS (
            SELECT 1
            FROM distributed_compilations AS compilation
            JOIN distributed_formal_attempt_lineage_v2 AS guard
              ON guard.owner_user_id = compilation.owner_user_id
             AND guard.vqe_execution_id = compilation.vqe_execution_id
             AND guard.benchmark_level = compilation.benchmark_level
            WHERE compilation.compilation_id = NEW.compilation_id
              AND compilation.owner_user_id = NEW.owner_user_id
              AND compilation.authorization_mode <> 'test_only'
              AND guard.attempts_consumed >= 1
         )
        BEGIN
            SELECT RAISE(ABORT, 'formal_lineage_attempt_consumed');
        END
        """
    )


def _reconcile_existing_rows(connection: Any) -> int:
    rows = connection.exec_driver_sql(
        """
        SELECT
            simulation_id,
            owner_user_id,
            status,
            qualification_status,
            failure_code,
            failure_stage,
            failure_detail,
            distributed_semantics_simulated,
            result_artifact_path,
            result_artifact_sha256,
            validation_report_path,
            validation_report_sha256
        FROM distributed_simulations
        """
    ).mappings()
    reconciled = 0
    for row in rows:
        distributed_completed = bool(row["distributed_semantics_simulated"])
        result_published = bool(
            row["result_artifact_path"] and row["result_artifact_sha256"]
        )
        report_published = bool(
            row["validation_report_path"]
            and row["validation_report_sha256"]
        )
        terminal = row["status"] != "simulation_running"
        missing = (
            []
            if result_published
            else [
                {
                    "name": "legacy_partial_observations",
                    "reason": "not persisted by V1",
                }
            ]
        )
        reconciliation_status = (
            "legacy_complete_evidence_reconciled"
            if result_published and report_published
            else "legacy_audit_gap_preserved_without_inference"
        )
        connection.exec_driver_sql(
            """
            INSERT INTO distributed_simulation_observations_v2 (
                simulation_id,
                owner_user_id,
                protocol_fixture_version,
                observations_json,
                assessment_json,
                milestones_json,
                partial,
                missing_metrics_json,
                logical_statevector_completed,
                distributed_statevector_completed,
                observable_evaluation_completed,
                sector_observation_completed,
                assessment_completed,
                result_artifact_published,
                validation_report_published,
                result_artifact_path,
                result_artifact_sha256,
                validation_report_path,
                validation_report_sha256,
                reconciliation_status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["simulation_id"],
                row["owner_user_id"],
                "legacy-v1-read-only-reconciliation",
                json.dumps({}, sort_keys=True),
                json.dumps(
                    {
                        "terminal_status": row["status"],
                        "qualification_status": row["qualification_status"],
                        "failure_code": row["failure_code"],
                        "failure_stage": row["failure_stage"],
                        "failure_detail": row["failure_detail"],
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "logical_statevector_completed": {
                            "completed": distributed_completed,
                            "source": "legacy_distributed_semantics_simulated",
                        },
                        "distributed_statevector_completed": {
                            "completed": distributed_completed,
                            "source": "legacy_distributed_semantics_simulated",
                        },
                        "assessment_completed": {
                            "completed": terminal,
                            "source": "legacy_terminal_status",
                        },
                        "result_artifact_published": {
                            "completed": result_published,
                            "source": "legacy_artifact_columns",
                        },
                        "validation_report_published": {
                            "completed": report_published,
                            "source": "legacy_artifact_columns",
                        },
                    },
                    sort_keys=True,
                ),
                int(bool(missing)),
                json.dumps(missing, sort_keys=True),
                int(distributed_completed),
                int(distributed_completed),
                int(result_published),
                int(result_published),
                int(terminal),
                int(result_published),
                int(report_published),
                row["result_artifact_path"],
                row["result_artifact_sha256"],
                row["validation_report_path"],
                row["validation_report_sha256"],
                reconciliation_status,
            ),
        )
        reconciled += 1
    return reconciled


def persist_synthetic_observations(
    database_path: Path,
    *,
    temporary_root: Path,
    simulation_id: str,
    owner_user_id: int,
    protocol_fixture_version: str,
    structured_result: StructuredSimulationResult,
    final_milestones: dict[str, dict[str, Any]],
    result_artifact_path: str,
    result_artifact_sha256: str,
    validation_report_path: str,
    validation_report_sha256: str,
) -> dict[str, Any]:
    """Persist one synthetic result without touching formal evidence."""
    resolved = _validate_temporary_database(database_path, temporary_root)
    if not simulation_id.startswith("synthetic_"):
        raise RemediationMigrationError(
            "Only synthetic simulation IDs may use remediation persistence."
        )
    result_path = canonical_artifact_path(result_artifact_path)
    report_path = canonical_artifact_path(validation_report_path)
    if not result_path.endswith("/distributed_simulation_result.json"):
        raise RemediationMigrationError(
            "Synthetic result path does not use the frozen filename."
        )
    if not report_path.endswith("/distributed_validation_report.json"):
        raise RemediationMigrationError(
            "Synthetic report path does not use the frozen filename."
        )
    digest_pattern = re.compile(r"^[0-9a-f]{64}$")
    if not digest_pattern.fullmatch(result_artifact_sha256):
        raise RemediationMigrationError("Synthetic result SHA-256 is invalid.")
    if not digest_pattern.fullmatch(validation_report_sha256):
        raise RemediationMigrationError("Synthetic report SHA-256 is invalid.")
    observations = structured_result.observations
    assessment = structured_result.assessment
    flags = {
        name: bool(payload.get("completed", False))
        for name, payload in final_milestones.items()
    }
    values = (
        simulation_id,
        owner_user_id,
        protocol_fixture_version,
        json.dumps(observations.as_dict(), sort_keys=True),
        json.dumps(assessment.as_dict(), sort_keys=True),
        json.dumps(final_milestones, sort_keys=True),
        int(observations.partial),
        json.dumps(
            [item.as_dict() for item in observations.missing_metrics],
            sort_keys=True,
        ),
        int(flags.get("logical_statevector_completed", False)),
        int(flags.get("distributed_statevector_completed", False)),
        int(flags.get("observable_evaluation_completed", False)),
        int(flags.get("sector_observation_completed", False)),
        int(flags.get("assessment_completed", False)),
        int(flags.get("result_artifact_published", False)),
        int(flags.get("validation_report_published", False)),
        result_path,
        result_artifact_sha256,
        report_path,
        validation_report_sha256,
        "synthetic_observations_persisted",
    )
    engine = _temporary_engine(resolved)
    with engine.begin() as connection:
        parent_owner = connection.exec_driver_sql(
            "SELECT owner_user_id FROM distributed_simulations "
            "WHERE simulation_id=?",
            (simulation_id,),
        ).scalar_one_or_none()
        if parent_owner is None:
            raise RemediationMigrationError(
                "Synthetic simulation parent does not exist."
            )
        if int(parent_owner) != owner_user_id:
            raise RemediationMigrationError(
                "Synthetic observation owner does not match its simulation."
            )
        existing = connection.exec_driver_sql(
            "SELECT * FROM distributed_simulation_observations_v2 "
            "WHERE simulation_id=?",
            (simulation_id,),
        ).mappings().one_or_none()
        if existing is None:
            connection.exec_driver_sql(
                """
                INSERT INTO distributed_simulation_observations_v2 (
                    simulation_id,
                    owner_user_id,
                    protocol_fixture_version,
                    observations_json,
                    assessment_json,
                    milestones_json,
                    partial,
                    missing_metrics_json,
                    logical_statevector_completed,
                    distributed_statevector_completed,
                    observable_evaluation_completed,
                    sector_observation_completed,
                    assessment_completed,
                    result_artifact_published,
                    validation_report_published,
                    result_artifact_path,
                    result_artifact_sha256,
                    validation_report_path,
                    validation_report_sha256,
                    reconciliation_status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                values,
            )
            action = "inserted"
        else:
            comparable = tuple(existing[key] for key in (
                "simulation_id",
                "owner_user_id",
                "protocol_fixture_version",
                "observations_json",
                "assessment_json",
                "milestones_json",
                "partial",
                "missing_metrics_json",
                "logical_statevector_completed",
                "distributed_statevector_completed",
                "observable_evaluation_completed",
                "sector_observation_completed",
                "assessment_completed",
                "result_artifact_published",
                "validation_report_published",
                "result_artifact_path",
                "result_artifact_sha256",
                "validation_report_path",
                "validation_report_sha256",
                "reconciliation_status",
            ))
            if comparable != values:
                raise RemediationMigrationError(
                    "Synthetic observation idempotency conflict."
                )
            action = "verified"
    engine.dispose()
    return {
        "simulation_id": simulation_id,
        "action": action,
        "database": str(resolved),
    }
