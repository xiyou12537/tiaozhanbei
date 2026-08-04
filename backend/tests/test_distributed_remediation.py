from __future__ import annotations

import copy
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.api.routers import platform
from backend.db.migrations.legacy_sqlite.remediation_v2 import (
    MIGRATION_ID,
    RemediationMigrationError,
    persist_synthetic_observations,
    upgrade_remediation_copy,
)
from backend.db.repositories.distributed_validation_repository import (
    DistributedNotFoundError,
    DistributedValidationRepository,
)
from backend.main import app
from backend.middleware import get_current_user
from backend.models_db import User
from backend.services.distributed_validation.canonical import (
    canonical_artifact_sha256,
    decode_canonical_artifact_value,
    parse_bound_qasm2_strict,
    sha256_file,
)
from backend.services.distributed_validation.artifact_store import (
    NoClobberArtifactStore,
)
from backend.services.distributed_validation.compiler import (
    build_compilation_settings,
    compile_distributed_v1,
)
from backend.services.distributed_validation.remediation_protocol import (
    FUTURE_ARTIFACT_FILENAMES,
    build_synthetic_protocol_fixture,
    remediation_protocol_json_schema,
    validate_synthetic_protocol_fixture,
)
from backend.services.distributed_validation.remediation_service import (
    SyntheticRemediationService,
    SyntheticValidationInput,
)
from backend.services.distributed_validation.service import (
    DistributedValidationService,
    DistributedValidationServiceError,
)
from backend.services.distributed_validation.versioned_orchestrator import (
    VersionedSimulationRequest,
)
from backend.services.distributed_validation import versioned_simulation


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
FORMAL_DATABASE = WORKSPACE_ROOT / "data" / "partitioning.db"
FORMAL_ARTIFACT_ROOT = WORKSPACE_ROOT / "data" / "structure_artifacts"
FORMAL_COMPILATION_ID = "dmc_a728180ea4944d36a83ee4dde1762f04"
SYNTHETIC_QASM = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[4];
u3(pi,0,pi) q[0];
u3(pi,0,pi) q[1];
cx q[0],q[1];
cx q[0],q[1];
cx q[0],q[2];
cx q[0],q[2];
cx q[0],q[3];
cx q[0],q[3];
cx q[1],q[2];
cx q[1],q[2];
cx q[1],q[3];
cx q[1],q[3];
cx q[2],q[3];
cx q[2],q[3];
"""
SYNTHETIC_PAULI = {
    "qubit_count": 4,
    "pauli_terms": [{"pauli_string": "I", "coefficient": -1.0}],
}


def _synthetic_input(
    run_id: str,
    *,
    target_alpha: int = 1,
    target_beta: int = 1,
    upstream_logical_energy: float = -1.0,
) -> SyntheticValidationInput:
    return SyntheticValidationInput(
        run_id=run_id,
        owner_user_id=183,
        qasm_text=SYNTHETIC_QASM,
        pauli_mapping=copy.deepcopy(SYNTHETIC_PAULI),
        e_classical_exact=-1.0,
        e_exact_pauli=-1.0,
        upstream_logical_energy=upstream_logical_energy,
        hf_energy=0.0,
        target_alpha=target_alpha,
        target_beta=target_beta,
    )


def _service(tmp_path: Path) -> SyntheticRemediationService:
    return SyntheticRemediationService(
        artifact_root=tmp_path / "synthetic-artifacts",
        protocol_payload=build_synthetic_protocol_fixture(),
        formal_artifact_root=FORMAL_ARTIFACT_ROOT,
    )


def _versioned_request(
    service: DistributedValidationService,
    *,
    run_id: str,
    target_alpha: int = 1,
    target_beta: int = 1,
    upstream_logical_energy: float = -1.0,
) -> tuple[object, str, VersionedSimulationRequest]:
    protocol = validate_synthetic_protocol_fixture(
        build_synthetic_protocol_fixture()
    )
    parsed = parse_bound_qasm2_strict(SYNTHETIC_QASM)
    settings = build_compilation_settings(
        partitioning=protocol.partitioning.model_dump(mode="python"),
        gate_ordering=protocol.gate_ordering.model_dump(mode="python"),
        mapping=protocol.mapping.model_dump(mode="python"),
        routing=protocol.routing.model_dump(mode="python"),
        qubit_count=parsed.circuit.num_qubits,
    )
    topology = {
        "schema": "distributed-topology-v1",
        "topology_name": protocol.topology.name,
        "directed": False,
        "nodes": [
            {
                "id": node_id,
                "qubit_capacity": protocol.topology.capacity_per_node,
            }
            for node_id in range(protocol.topology.node_count)
        ],
        "edges": [
            {"source": 0, "target": 1, "weight_hex": "3ff0000000000000"}
        ],
    }
    compiled = compile_distributed_v1(
        parsed,
        settings=settings,
        maximum_expanded_gate_count=(
            protocol.resource_guardrails.maximum_expanded_gate_count
        ),
        topology_payload=topology,
        topology_sha256=protocol.topology.topology_sha256,
    )
    parent = service.store.publish_json(
        f"versioned_inputs/{run_id}/distributed_executable.json",
        compiled.distributed_executable,
        max_size_bytes=protocol.resource_guardrails.maximum_artifact_size_bytes,
    )
    request = VersionedSimulationRequest(
        run_id=run_id,
        owner_user_id=183,
        artifact_directory=f"versioned_execution/{run_id}",
        execution_scope="synthetic",
        formal_evidence=False,
        logical_circuit=parsed.circuit,
        distributed_executable=compiled.distributed_executable,
        pauli_mapping=copy.deepcopy(SYNTHETIC_PAULI),
        e_classical_exact=-1.0,
        e_exact_pauli=-1.0,
        upstream_logical_energy=upstream_logical_energy,
        hf_energy=0.0,
        target_alpha=target_alpha,
        target_beta=target_beta,
        parent_artifact=parent,
        parent_artifact_id=f"{run_id}:distributed_executable",
        parent_role="distributed_executable",
    )
    return protocol, canonical_artifact_sha256(
        protocol.model_dump(mode="python")
    ), request


def _decoded_json(path: Path) -> dict:
    return decode_canonical_artifact_value(
        json.loads(path.read_text(encoding="utf-8"))
    )


def _temporary_session_factory(database_path: Path):
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine, sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def _copy_and_upgrade(tmp_path: Path) -> Path:
    database_path = tmp_path / "database-copy" / "partitioning.db"
    database_path.parent.mkdir(parents=True)
    shutil.copy2(FORMAL_DATABASE, database_path)
    result = upgrade_remediation_copy(
        database_path,
        temporary_root=tmp_path,
    )
    assert result["applied"] is True
    return database_path


def _insert_synthetic_simulation_parent(
    database_path: Path,
    *,
    compilation_id: str = "synthetic_compilation_persistence",
    simulation_id: str = "synthetic_simulation_persistence",
) -> None:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        source = dict(
            connection.execute(
                "SELECT * FROM distributed_compilations WHERE compilation_id=?",
                (FORMAL_COMPILATION_ID,),
            ).fetchone()
        )
        source.update(
            {
                "compilation_id": compilation_id,
                "status": "formal_attempt_consumed",
                "formal_attempts_started": 1,
                "authorization_mode": "test_only",
                "authorization_reference": "temporary_remediation_test",
                "failure_code": None,
                "failure_stage": None,
                "failure_detail": None,
                "row_version": 1,
            }
        )
        compilation_columns = list(source)
        connection.execute(
            f"INSERT INTO distributed_compilations "
            f"({','.join(compilation_columns)}) VALUES "
            f"({','.join('?' for _ in compilation_columns)})",
            tuple(source[column] for column in compilation_columns),
        )
        connection.execute(
            """
            INSERT INTO distributed_simulations (
                simulation_id,
                compilation_id,
                owner_user_id,
                formal_attempt_number,
                execution_backend_type,
                execution_backend_detail,
                shots,
                status,
                qualification_status,
                acceptance_checks,
                resource_telemetry,
                distributed_semantics_simulated,
                actual_distributed_hardware_execution,
                row_version,
                created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """,
            (
                simulation_id,
                compilation_id,
                183,
                1,
                "statevector_simulator",
                "synthetic_remediation_test",
                0,
                "simulation_failed",
                "not_validated",
                "{}",
                "{}",
                0,
                0,
                0,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _attempt_formal_compilation_clone(
    database_path: Path,
    compilation_id: str,
) -> str:
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        source = dict(
            connection.execute(
                "SELECT * FROM distributed_compilations WHERE compilation_id=?",
                (FORMAL_COMPILATION_ID,),
            ).fetchone()
        )
        source.update(
            {
                "compilation_id": compilation_id,
                "status": "compilation_created",
                "formal_attempts_started": 0,
                "row_version": 0,
                "created_at": "2026-07-28 00:00:00",
                "completed_at": None,
            }
        )
        columns = list(source)
        connection.execute(
            f"INSERT INTO distributed_compilations "
            f"({','.join(columns)}) VALUES "
            f"({','.join('?' for _ in columns)})",
            tuple(source[column] for column in columns),
        )
        connection.commit()
        return "created"
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        return str(exc)
    finally:
        connection.close()


def test_complete_protocol_schema_fixture_and_frozen_artifact_names() -> None:
    payload = build_synthetic_protocol_fixture()
    validated = validate_synthetic_protocol_fixture(payload)
    schema = remediation_protocol_json_schema()
    assert validated.authorization.formal_protocol_artifact_creation_allowed is False
    assert validated.authorization.formal_4q_attempt_authorized is False
    assert validated.authorization.stage_c_authorized is False
    assert validated.failure_partial_schema.validation_failure_is_exception is False
    assert tuple(
        artifact.filename for artifact in validated.artifact_contract.artifacts
    ) == FUTURE_ARTIFACT_FILENAMES
    assert FUTURE_ARTIFACT_FILENAMES[0] == "distributed_input_manifest.json"
    for required in (
        "qualifying_inputs",
        "circuit_requirements",
        "reference_energies",
        "lifecycle",
        "ownership",
        "artifact_contract",
        "failure_partial_schema",
        "execution_milestones",
        "numerical_algorithms",
        "partitioning",
        "gate_ordering",
        "mapping",
        "routing",
    ):
        assert required in schema["required"]

    invalid = copy.deepcopy(payload)
    del invalid["numerical_algorithms"]["particle_variance_negative_roundoff_tolerance"]
    with pytest.raises(ValidationError):
        validate_synthetic_protocol_fixture(invalid)


def test_synthetic_success_publishes_ten_no_clobber_artifacts_and_lineage(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    run = service.run(_synthetic_input("synthetic_success"))
    assert run.structured_result.assessment.accepted is True
    assert run.structured_result.observations.partial is False
    assert run.structured_result.observations.distributed_semantics_simulated is True
    assert [artifact.absolute_path.name for artifact in run.artifacts] == list(
        FUTURE_ARTIFACT_FILENAMES
    )
    assert len(run.artifacts) == 10

    previous = None
    for artifact in run.artifacts:
        assert sha256_file(artifact.absolute_path) == artifact.sha256
        payload = _decoded_json(artifact.absolute_path)
        assert payload["actual_distributed_hardware_execution"] is False
        assert payload["synthetic_only"] is True
        if previous is not None:
            parent = payload["parents"][0]
            assert parent["relative_path"] == previous.relative_path
            assert parent["sha256"] == previous.sha256
            assert set(parent) == {
                "artifact_id",
                "role",
                "relative_path",
                "sha256",
                "schema_version",
            }
        previous = artifact

    manifest = _decoded_json(run.artifacts[0].absolute_path)
    for parent in manifest["parents"]:
        parent_path = service.artifact_root / parent["relative_path"]
        assert parent_path.is_file()
        assert sha256_file(parent_path) == parent["sha256"]

    report = _decoded_json(run.artifacts[-1].absolute_path)
    route_plan = _decoded_json(run.artifacts[6].absolute_path)
    executable = _decoded_json(run.artifacts[7].absolute_path)
    assert len(route_plan["routes"]) > 0
    assert route_plan["mapping_restored"] is True
    assert executable["final_logical_to_execution_mapping"] == [
        [0, 0],
        [1, 1],
        [2, 2],
        [3, 3],
    ]
    assert report["execution_milestones"]["result_artifact_published"][
        "completed"
    ] is True
    assert report["execution_milestones"]["validation_report_published"][
        "completed"
    ] is True


@pytest.mark.parametrize(
    ("run_id", "input_overrides", "expected_code"),
    (
        (
            "synthetic_sector_failure",
            {"target_alpha": 2, "target_beta": 2},
            "synthetic_particle_sector_validation_failed",
        ),
        (
            "synthetic_energy_failure",
            {"upstream_logical_energy": -0.5},
            "synthetic_energy_validation_failed",
        ),
    ),
)
def test_synthetic_validation_failures_are_terminal_results_with_ten_artifacts(
    tmp_path: Path,
    run_id: str,
    input_overrides: dict,
    expected_code: str,
) -> None:
    run = _service(tmp_path).run(
        _synthetic_input(run_id, **input_overrides)
    )
    assert run.structured_result.assessment.terminal_status == (
        "synthetic_acceptance_not_met"
    )
    assert run.structured_result.assessment.failure_code == expected_code
    assert run.structured_result.observations.partial is False
    assert run.structured_result.observations.distributed_semantics_simulated is True
    assert len(run.artifacts) == 10
    assert run.artifacts[-2].absolute_path.name == (
        "distributed_simulation_result.json"
    )
    assert run.artifacts[-1].absolute_path.name == (
        "distributed_validation_report.json"
    )


def test_infrastructure_failure_preserves_partial_observations_and_execution_fact(
    tmp_path: Path,
) -> None:
    def fail_after_distributed(stage: str) -> None:
        if stage == "after_distributed_statevector":
            raise RuntimeError("injected telemetry-stage failure")

    run = _service(tmp_path).run(
        _synthetic_input("synthetic_partial_failure"),
        fault_injector=fail_after_distributed,
    )
    observations = run.structured_result.observations
    assert observations.partial is True
    assert observations.distributed_semantics_simulated is True
    assert observations.infrastructure_error is not None
    assert run.structured_result.assessment.failure_code == (
        "synthetic_infrastructure_failure"
    )
    assert {item.name for item in observations.missing_metrics} >= {
        "e_logical_vqe",
        "e_distributed",
        "statevector_fidelity",
    }
    assert len(run.artifacts) == 10
    result = _decoded_json(run.artifacts[-2].absolute_path)
    assert result["partial"] is True
    assert result["observations"]["distributed_semantics_simulated"] is True


@pytest.mark.parametrize(
    ("raw_variance", "should_pass"),
    ((-5e-14, True), (-2e-13, False)),
)
def test_raw_variance_roundoff_uses_versioned_fixture_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_variance: float,
    should_pass: bool,
) -> None:
    original = versioned_simulation._centered_sector_metrics

    def synthetic_roundoff(*args, **kwargs) -> dict[str, float]:
        metrics = original(*args, **kwargs)
        metrics["n_alpha_variance_raw_difference"] = raw_variance
        metrics["n_beta_variance_raw_difference"] = raw_variance
        return metrics

    monkeypatch.setattr(
        versioned_simulation,
        "_centered_sector_metrics",
        synthetic_roundoff,
    )
    run = _service(tmp_path).run(
        _synthetic_input(f"synthetic_roundoff_{should_pass}")
    )
    assert run.structured_result.assessment.acceptance_checks[
        "raw_variance_roundoff_consistent"
    ] is should_pass
    assert run.structured_result.assessment.accepted is should_pass
    if not should_pass:
        assert run.structured_result.assessment.failure_code == (
            "synthetic_numerical_validation_failed"
        )


def test_no_clobber_prevents_synthetic_rerun_with_same_run_id(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    synthetic_input = _synthetic_input("synthetic_no_clobber")
    first = service.run(synthetic_input)
    hashes_before = {
        artifact.relative_path: artifact.sha256 for artifact in first.artifacts
    }
    with pytest.raises(FileExistsError):
        service.run(synthetic_input)
    assert {
        artifact.relative_path: sha256_file(artifact.absolute_path)
        for artifact in first.artifacts
    } == hashes_before


def test_remediation_migration_reconciles_without_inference_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = _copy_and_upgrade(tmp_path)
    second = upgrade_remediation_copy(
        database_path,
        temporary_root=tmp_path,
    )
    assert second["applied"] is False
    assert second["guarded_lineages"] == 1

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT
                partial,
                distributed_statevector_completed,
                reconciliation_status
            FROM distributed_simulation_observations_v2
            WHERE simulation_id='dms_4723e9828a4b426c9c22dc4d00d00cc3'
            """
        ).fetchone()
        assert row == (
            1,
            0,
            "legacy_audit_gap_preserved_without_inference",
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM legacy_schema_migrations "
                "WHERE migration_id=?",
                (MIGRATION_ID,),
            ).fetchone()[0]
            == 1
        )
    finally:
        connection.close()


def test_global_formal_attempt_guard_blocks_new_keys_compilations_and_simulations(
    tmp_path: Path,
) -> None:
    database_path = _copy_and_upgrade(tmp_path)
    sequential = [
        _attempt_formal_compilation_clone(
            database_path,
            f"dmc_forbidden_new_key_{index}",
        )
        for index in range(2)
    ]
    assert all("formal_lineage_attempt_consumed" in item for item in sequential)

    with ThreadPoolExecutor(max_workers=4) as executor:
        concurrent = list(
            executor.map(
                lambda index: _attempt_formal_compilation_clone(
                    database_path,
                    f"dmc_forbidden_concurrent_{index}",
                ),
                range(4),
            )
        )
    assert all("formal_lineage_attempt_consumed" in item for item in concurrent)

    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM distributed_compilations"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT attempts_consumed FROM "
            "distributed_formal_attempt_lineage_v2"
        ).fetchone()[0] == 1
        with pytest.raises(
            sqlite3.IntegrityError,
            match="formal_lineage_attempt_consumed",
        ):
            connection.execute(
                """
                INSERT INTO distributed_simulations (
                    simulation_id,
                    compilation_id,
                    owner_user_id,
                    formal_attempt_number,
                    execution_backend_type,
                    execution_backend_detail,
                    shots,
                    status,
                    qualification_status,
                    acceptance_checks,
                    resource_telemetry,
                    distributed_semantics_simulated,
                    actual_distributed_hardware_execution,
                    row_version,
                    created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                """,
                (
                    "dms_forbidden_second_attempt",
                    FORMAL_COMPILATION_ID,
                    183,
                    1,
                    "statevector_simulator",
                    "forbidden_second_attempt",
                    0,
                    "simulation_running",
                    "pending",
                    "{}",
                    "{}",
                    0,
                    0,
                    0,
                ),
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("case_name", "upstream_logical_energy", "fault_stage", "expected_status"),
    (
        ("success", -1.0, None, "synthetic_completed"),
        (
            "acceptance_failure",
            -0.5,
            None,
            "synthetic_acceptance_not_met",
        ),
        (
            "infrastructure_partial",
            -1.0,
            "after_distributed_statevector",
            "synthetic_simulation_failed",
        ),
    ),
)
def test_production_versioned_orchestrator_persists_terminal_synthetic_outcomes(
    tmp_path: Path,
    case_name: str,
    upstream_logical_energy: float,
    fault_stage: str | None,
    expected_status: str,
) -> None:
    database_path = _copy_and_upgrade(tmp_path)
    run_id = f"synthetic_production_core_{case_name}"
    compilation_id = f"synthetic_compilation_core_{case_name}"
    _insert_synthetic_simulation_parent(
        database_path,
        compilation_id=compilation_id,
        simulation_id=run_id,
    )
    service = DistributedValidationService(
        artifact_root=tmp_path / "production-versioned-artifacts"
    )
    protocol, protocol_sha256, request = _versioned_request(
        service,
        run_id=run_id,
        upstream_logical_energy=upstream_logical_energy,
    )

    def persist(
        callback_request,
        structured_result,
        milestones,
        result_artifact,
        report_artifact,
    ) -> dict:
        return persist_synthetic_observations(
            database_path=database_path,
            temporary_root=tmp_path,
            simulation_id=callback_request.run_id,
            owner_user_id=callback_request.owner_user_id,
            protocol_fixture_version=protocol.protocol_version,
            structured_result=structured_result,
            final_milestones=milestones,
            result_artifact_path=result_artifact.relative_path,
            result_artifact_sha256=result_artifact.sha256,
            validation_report_path=report_artifact.relative_path,
            validation_report_sha256=report_artifact.sha256,
        )

    def inject(stage: str) -> None:
        if stage == fault_stage:
            raise RuntimeError("synthetic injected infrastructure failure")

    run = service.execute_versioned_v2(
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        request=request,
        persistence_callback=persist,
        fault_injector=inject if fault_stage else None,
    )
    observations = run.structured_result.observations
    assessment = run.structured_result.assessment
    assert assessment.terminal_status == expected_status
    assert observations.distributed_semantics_simulated is True
    assert assessment.partial_observations_may_grant_qualification is False
    assert not (observations.partial and assessment.accepted)
    assert run.persistence_result["action"] == "inserted"
    assert run.result_artifact.relative_path.endswith(
        "/distributed_simulation_result.json"
    )
    assert run.validation_report_artifact.relative_path.endswith(
        "/distributed_validation_report.json"
    )

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        persisted = connection.execute(
            """
            SELECT *
            FROM distributed_simulation_observations_v2
            WHERE simulation_id=?
            """,
            (run_id,),
        ).fetchone()
        assert persisted is not None
        assert persisted["distributed_statevector_completed"] == 1
        assert persisted["result_artifact_published"] == 1
        assert persisted["validation_report_published"] == 1
        assert persisted["partial"] == int(observations.partial)
        missing = json.loads(persisted["missing_metrics_json"])
        assert all(item["reason"] for item in missing)
    finally:
        connection.close()

    result_payload = _decoded_json(run.result_artifact.absolute_path)
    report_payload = _decoded_json(
        run.validation_report_artifact.absolute_path
    )
    assert result_payload["observations"][
        "distributed_semantics_simulated"
    ] is True
    assert report_payload["qualification_status"] == (
        assessment.qualification_status
    )
    assert report_payload["partial"] is observations.partial


def test_remediation_migration_rejects_formal_database() -> None:
    with pytest.raises(RemediationMigrationError):
        upgrade_remediation_copy(
            FORMAL_DATABASE,
            temporary_root=WORKSPACE_ROOT,
        )


def test_synthetic_observation_persistence_is_idempotent_and_milestones_monotonic(
    tmp_path: Path,
) -> None:
    database_path = _copy_and_upgrade(tmp_path)
    _insert_synthetic_simulation_parent(database_path)
    run = _service(tmp_path).run(_synthetic_input("synthetic_db_persistence"))
    kwargs = {
        "database_path": database_path,
        "temporary_root": tmp_path,
        "simulation_id": "synthetic_simulation_persistence",
        "owner_user_id": 183,
        "protocol_fixture_version": "2.0.0-test-fixture",
        "structured_result": run.structured_result,
        "final_milestones": run.final_execution_milestones,
        "result_artifact_path": run.artifacts[-2].relative_path,
        "result_artifact_sha256": run.artifacts[-2].sha256,
        "validation_report_path": run.artifacts[-1].relative_path,
        "validation_report_sha256": run.artifacts[-1].sha256,
    }
    assert persist_synthetic_observations(**kwargs)["action"] == "inserted"
    assert persist_synthetic_observations(**kwargs)["action"] == "verified"

    connection = sqlite3.connect(database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE distributed_simulation_observations_v2
                SET distributed_statevector_completed=0
                WHERE simulation_id='synthetic_simulation_persistence'
                """
            )
    finally:
        connection.close()


def test_repository_lists_only_owner_bound_execution_compilations(
    tmp_path: Path,
) -> None:
    database_path = _copy_and_upgrade(tmp_path)
    engine, factory = _temporary_session_factory(database_path)
    try:
        repository = DistributedValidationRepository(factory)
        rows = repository.list_compilations_for_execution(
            "ve_hist_b688e23a03e0e3174a389340c0c1a06a",
            183,
        )
        assert [row.compilation_id for row in rows] == [FORMAL_COMPILATION_ID]
        with pytest.raises(DistributedNotFoundError):
            repository.list_compilations_for_execution(
                "ve_hist_b688e23a03e0e3174a389340c0c1a06a",
                999999,
            )
    finally:
        engine.dispose()


def test_exact_compilation_list_api_is_present_without_global_list_apis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, int | str] = {}

    def list_for_execution(vqe_execution_id: str, owner_user_id: int) -> list:
        captured.update(
            {
                "vqe_execution_id": vqe_execution_id,
                "owner_user_id": owner_user_id,
            }
        )
        return []

    monkeypatch.setattr(
        platform.distributed_validation_service.repository,
        "list_compilations_for_execution",
        list_for_execution,
    )
    app.dependency_overrides[get_current_user] = lambda: User(
        id=183,
        username="stage-b-r-owner",
        password_hash="test-only",
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/platform/vqe-executions/vqexe_test/"
                "distributed-compilations"
            )
            assert response.status_code == 200
            assert response.json() == []
            assert captured == {
                "vqe_execution_id": "vqexe_test",
                "owner_user_id": 183,
            }
            openapi_paths = client.get("/openapi.json").json()["paths"]
            assert "/api/platform/distributed-compilations" not in openapi_paths
            assert "/api/platform/distributed-simulations" not in openapi_paths
    finally:
        app.dependency_overrides.clear()


def test_formal_post_endpoints_reject_new_attempt_while_get_remains_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_calls: list[str] = []

    def forbidden_repository_call(*_args, **_kwargs):
        repository_calls.append("called")
        raise AssertionError("A sealed formal POST reached repository I/O.")

    def list_for_execution(_vqe_execution_id: str, _owner_user_id: int) -> list:
        return []

    service = platform.distributed_validation_service
    monkeypatch.setattr(service, "_load_protocol", forbidden_repository_call)
    monkeypatch.setattr(
        service.repository,
        "resolve_qualified_closure",
        forbidden_repository_call,
    )
    monkeypatch.setattr(
        service.repository,
        "get_compilation",
        forbidden_repository_call,
    )
    monkeypatch.setattr(
        service.repository,
        "list_compilations_for_execution",
        list_for_execution,
    )
    app.dependency_overrides[get_current_user] = lambda: User(
        id=183,
        username="stage-b-r-owner",
        password_hash="test-only",
    )
    try:
        with TestClient(app) as client:
            for index in range(3):
                response = client.post(
                    "/api/platform/vqe-executions/vqexe_test/"
                    "distributed-compilations",
                    headers={
                        "Idempotency-Key": f"forbidden-compilation-{index}"
                    },
                    json={
                        "benchmark_level": "level_a_4q",
                        "protocol_version": "1.0.0",
                    },
                )
                assert response.status_code == 409
                assert response.json()["detail"]["code"] == (
                    "new_formal_4q_attempt_not_authorized"
                )

            simulation_response = client.post(
                f"/api/platform/distributed-compilations/"
                f"{FORMAL_COMPILATION_ID}/simulations",
                headers={"Idempotency-Key": "forbidden-simulation-retry"},
                json={
                    "shots": 0,
                    "backend": "qiskit.quantum_info.Statevector",
                },
            )
            assert simulation_response.status_code == 409
            assert simulation_response.json()["detail"]["code"] == (
                "formal_attempt_consumed"
            )

            get_response = client.get(
                "/api/platform/vqe-executions/vqexe_test/"
                "distributed-compilations"
            )
            assert get_response.status_code == 200
            assert get_response.json() == []
        assert repository_calls == []
    finally:
        app.dependency_overrides.clear()
