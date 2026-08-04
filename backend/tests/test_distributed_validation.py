from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.db.migrations.legacy_sqlite.migrate import upgrade_database
from backend.db.migrations.legacy_sqlite.molecular_m_b import (
    migrate_staging_database as migrate_molecular_m_b_staging,
)
from backend.db.repositories.distributed_validation_repository import (
    DistributedStateConflictError,
    DistributedValidationRepository,
)
from backend.models_db import DistributedCompilationRecord
from backend.services.distributed_validation.artifact_store import (
    NoClobberArtifactStore,
)
from backend.services.distributed_validation.canonical import (
    CanonicalizationError,
    canonical_artifact_bytes,
    canonical_artifact_path,
    decode_canonical_artifact_value,
    ordered_pauli_payload_bytes,
    parameter_vector_sha256,
    parse_bound_qasm2_strict,
    sha256_bytes,
    sha256_file,
)
from backend.services.distributed_validation.compiler import (
    build_compilation_settings,
    compile_distributed_v1,
)
from backend.services.distributed_validation.protocol import build_protocol_payload
from backend.services.distributed_validation.protocol import TOPOLOGY_4Q_SHA256
from backend.services.distributed_validation.registration import (
    FROZEN_ROLES,
    OWNER_USER_ID,
    register_frozen_history,
)
from backend.services.distributed_validation.simulator import (
    DistributedSimulationError,
    simulate_statevector_v1,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = WORKSPACE_ROOT / "data" / "structure_artifacts"
BACKUP_DATABASE = (
    WORKSPACE_ROOT
    / "data"
    / "backups"
    / "partitioning.pre-stage-b.20260728T102950095.db"
)


def _session_factory(database_path: Path):
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA busy_timeout=30000")

    return engine, sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture()
def migrated_database(tmp_path: Path) -> tuple[Path, sessionmaker]:
    database_path = tmp_path / "partitioning.db"
    shutil.copy2(BACKUP_DATABASE, database_path)
    result = upgrade_database(database_path)
    assert result["applied"] is True
    molecular_result = migrate_molecular_m_b_staging(database_path)
    assert molecular_result["migration_id"] == "20260730_01_molecular_m_b"
    engine, factory = _session_factory(database_path)
    try:
        yield database_path, factory
    finally:
        engine.dispose()


def _register(factory: sessionmaker) -> dict[str, dict[str, str]]:
    with factory() as session, session.begin():
        return register_frozen_history(session, ARTIFACT_ROOT)


def _compilation_values(ids: dict[str, str], compilation_id: str) -> dict:
    role = FROZEN_ROLES[0]
    return {
        "compilation_id": compilation_id,
        "owner_user_id": OWNER_USER_ID,
        "vqe_execution_id": ids["vqe_execution_id"],
        "qubit_hamiltonian_id": ids["qubit_hamiltonian_id"],
        "closure_benchmark_id": ids["closure_benchmark_id"],
        "benchmark_level": "level_a_4q",
        "execution_stage": "stage_b",
        "protocol_id": "distributed_molecular_circuit_validation",
        "protocol_version": "1.0.0",
        "protocol_artifact_path": str(
            ARTIFACT_ROOT
            / "distributed_molecular_circuit_validation_protocol_v1.json"
        ),
        "protocol_sha256": (
            "4f06fbb9bda3c433ba952641f4848601bb1f3dbf4da7bc8c89f63e0b9d916888"
        ),
        "topology_name": "linear-2-capacity-2",
        "topology_sha256": TOPOLOGY_4Q_SHA256,
        "raw_qasm_sha256": role.raw_qasm_sha256,
        "canonical_circuit_sha256": role.canonical_circuit_sha256,
        "parameter_sha256": role.parameter_sha256,
        "hamiltonian_artifact_sha256": role.hamiltonian_sha256,
        "ordered_pauli_payload_sha256": role.ordered_pauli_sha256,
        "execution_semantics_strategy": (
            "topology_aware_remote_swap_route_and_restore"
        ),
        "partition_count": 2,
        "status": "compilation_created",
        "baseline_metrics": {},
        "optimized_metrics": {},
        "resource_estimate": {},
        "authorization_mode": "test_only",
        "authorization_reference": "synthetic_database_test",
        "formal_attempt_limit": 1,
        "formal_attempts_started": 0,
        "actual_distributed_hardware_execution": False,
        "row_version": 0,
    }


def test_frozen_input_hashes_and_hash_schemes_are_reproducible() -> None:
    for role in FROZEN_ROLES:
        vqe_path = ARTIFACT_ROOT / role.vqe_filename
        hamiltonian_path = ARTIFACT_ROOT / role.hamiltonian_filename
        qasm_path = ARTIFACT_ROOT / role.qasm_source_filename
        assert sha256_file(vqe_path) == role.vqe_sha256
        assert sha256_file(hamiltonian_path) == role.hamiltonian_sha256
        assert sha256_file(qasm_path) == role.qasm_source_sha256

        vqe = json.loads(vqe_path.read_text(encoding="utf-8"))
        qasm_source = json.loads(qasm_path.read_text(encoding="utf-8"))
        hamiltonian = json.loads(hamiltonian_path.read_text(encoding="utf-8"))
        result = vqe["acceptance"] if role.qubit_count == 4 else vqe["result"]
        qasm_text = (
            result["qasm_content"]
            if role.qubit_count == 4
            else qasm_source["remediation"]["qasm_content"]
        )
        parsed = parse_bound_qasm2_strict(qasm_text)
        assert parsed.raw_qasm_sha256 == role.raw_qasm_sha256
        assert parsed.canonical_sha256 == role.canonical_circuit_sha256
        assert (
            parameter_vector_sha256(result["final_measurement"]["parameters"])
            == role.parameter_sha256
        )
        jordan_wigner = hamiltonian["jordan_wigner_pauli"]
        preimage = ordered_pauli_payload_bytes(
            jordan_wigner["mapping"],
            jordan_wigner["constant_energy_offset_hartree"],
        )
        assert sha256_bytes(preimage) == role.ordered_pauli_sha256
        assert len(preimage) == (2695 if role.qubit_count == 4 else 33792)


def test_artifact_canonical_json_round_trip_and_path_rules() -> None:
    payload = {
        "enum": "ready",
        "float": 0.1,
        "items": [None, True, "Li\u2082S\u2084"],
        "path": "nested/report.json",
    }
    encoded = canonical_artifact_bytes(payload)
    decoded = decode_canonical_artifact_value(
        json.loads(encoded.decode("utf-8"))
    )
    assert decoded == payload
    assert canonical_artifact_path("nested/report.json") == "nested/report.json"
    with pytest.raises(CanonicalizationError):
        canonical_artifact_path("nested/../report.json")
    with pytest.raises(CanonicalizationError):
        canonical_artifact_bytes({"bad": "\ud800"})


def test_no_clobber_store_allows_exactly_one_concurrent_publisher(
    tmp_path: Path,
) -> None:
    store = NoClobberArtifactStore(tmp_path)
    payloads = [{"writer": 0}, {"writer": 1}]

    def publish(payload: dict) -> str:
        try:
            return store.publish_json(
                "concurrent/result.json",
                payload,
                max_size_bytes=1024,
            ).sha256
        except FileExistsError:
            return "exists"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, payloads))
    assert outcomes.count("exists") == 1
    assert sum(outcome != "exists" for outcome in outcomes) == 1
    stored = (tmp_path / "concurrent" / "result.json").read_bytes()
    assert sha256_bytes(stored) in outcomes


def test_migration_registration_triggers_and_idempotency(
    migrated_database: tuple[Path, sessionmaker],
) -> None:
    database_path, factory = migrated_database
    first = _register(factory)
    second = _register(factory)
    assert first == second

    with factory() as session:
        counts = {
            table: session.connection().exec_driver_sql(
                f"SELECT COUNT(*) FROM {table}"
            ).scalar_one()
            for table in (
                "active_spaces",
                "fermionic_hamiltonians",
                "structure_qubit_hamiltonians",
                "vqe_circuits",
                "vqe_executions",
                "classical_references",
                "quantum_closure_benchmarks",
            )
        }
        assert set(counts.values()) == {2}

    with factory() as session, pytest.raises(DatabaseError):
        session.connection().exec_driver_sql(
            "UPDATE vqe_executions SET status='forbidden' "
            "WHERE execution_id=?",
            (first["minimum_pipeline"]["vqe_execution_id"],),
        )

    with factory() as session, pytest.raises(IntegrityError):
        session.add(
            DistributedCompilationRecord(
                **{
                    **_compilation_values(
                        first["minimum_pipeline"],
                        "dmc_bad_owner_fk",
                    ),
                    "owner_user_id": 999999,
                }
            )
        )
        session.commit()

    assert upgrade_database(database_path)["applied"] is False


def test_formal_attempt_compare_and_swap_allows_one_winner(
    migrated_database: tuple[Path, sessionmaker],
) -> None:
    _, factory = migrated_database
    ids = _register(factory)["minimum_pipeline"]
    repository = DistributedValidationRepository(factory)
    compilation = repository.create_compilation(
        values=_compilation_values(ids, "dmc_concurrent_cas"),
        idempotency_key="compilation-test-key",
        request_fingerprint="a" * 64,
    )
    compilation = repository.update_compilation(
        compilation.compilation_id,
        OWNER_USER_ID,
        expected_row_version=0,
        values={"status": "distributed_executable_ready"},
    )

    def consume(index: int) -> str:
        try:
            record = repository.start_formal_simulation(
                compilation_id=compilation.compilation_id,
                owner_user_id=OWNER_USER_ID,
                simulation_values={
                    "simulation_id": f"dms_concurrent_{index}",
                    "compilation_id": compilation.compilation_id,
                    "owner_user_id": OWNER_USER_ID,
                    "formal_attempt_number": 1,
                    "execution_backend_type": "statevector_simulator",
                    "execution_backend_detail": "synthetic_test",
                    "shots": 0,
                    "status": "simulation_running",
                    "qualification_status": "pending",
                    "acceptance_checks": {},
                    "resource_telemetry": {},
                    "distributed_semantics_simulated": False,
                    "actual_distributed_hardware_execution": False,
                    "row_version": 0,
                },
                idempotency_key=f"simulation-test-key-{index}",
                request_fingerprint=str(index) * 64,
            )
            return record.simulation_id
        except DistributedStateConflictError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(consume, (1, 2)))
    assert outcomes.count("rejected") == 1
    assert sum(outcome != "rejected" for outcome in outcomes) == 1
    final = repository.get_compilation(compilation.compilation_id, OWNER_USER_ID)
    assert final is not None
    assert final.formal_attempts_started == 1


def test_synthetic_route_restore_compiles_but_v1_execution_is_sealed() -> None:
    qasm = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[4];
u3(pi,0,pi) q[0];
u3(pi,0,pi) q[1];
cx q[0],q[2];
cx q[1],q[3];
cx q[0],q[3];
cx q[1],q[2];
"""
    parsed = parse_bound_qasm2_strict(qasm)
    topology = {
        "schema": "distributed-topology-v1",
        "topology_name": "linear-2-capacity-2",
        "directed": False,
        "nodes": [
            {"id": 0, "qubit_capacity": 2},
            {"id": 1, "qubit_capacity": 2},
        ],
        "edges": [{"source": 0, "target": 1, "weight_hex": "3ff0000000000000"}],
    }
    first = compile_distributed_v1(
        parsed,
        settings=build_compilation_settings(
            partitioning=build_protocol_payload()["partitioning"],
            gate_ordering=build_protocol_payload()["gate_ordering"],
            mapping=build_protocol_payload()["mapping"],
            routing=build_protocol_payload()["routing"],
            qubit_count=parsed.circuit.num_qubits,
        ),
        maximum_expanded_gate_count=600,
        topology_payload=topology,
        topology_sha256=TOPOLOGY_4Q_SHA256,
    )
    second = compile_distributed_v1(
        parsed,
        settings=build_compilation_settings(
            partitioning=build_protocol_payload()["partitioning"],
            gate_ordering=build_protocol_payload()["gate_ordering"],
            mapping=build_protocol_payload()["mapping"],
            routing=build_protocol_payload()["routing"],
            qubit_count=parsed.circuit.num_qubits,
        ),
        maximum_expanded_gate_count=600,
        topology_payload=topology,
        topology_sha256=TOPOLOGY_4Q_SHA256,
    )
    assert first.partition_plan["selected"] == second.partition_plan["selected"]
    assert first.chip_mapping["partition_to_node"] == [[0, 0], [1, 1]]
    assert first.distributed_executable["final_logical_to_execution_mapping"] == [
        [0, 0],
        [1, 1],
        [2, 2],
        [3, 3],
    ]
    assert first.communication_route_plan["mapping_restored"] is True

    thresholds = {
        "fci_vs_exact_pauli_hartree": 1e-8,
        "runtime_logical_vs_upstream_hartree": 1e-9,
        "variational_lower_bound_hartree": 1e-8,
        "logical_vs_exact_pauli_hartree": 0.0016,
        "distributed_vs_exact_pauli_hartree": 0.0016,
        "distributed_vs_logical_hartree": 1e-9,
        "statevector_infidelity": 1e-12,
        "statevector_normalization_error": 1e-12,
        "energy_imaginary_absolute_hartree": 1e-12,
        "particle_sector_expectation_error": 1e-10,
        "particle_sector_variance": 1e-10,
        "correlation_recovery_ratio_minimum": 0.9,
    }
    with pytest.raises(DistributedSimulationError) as error:
        simulate_statevector_v1(
            logical_circuit=parsed.circuit,
            distributed_executable=first.distributed_executable,
            pauli_mapping={
                "qubit_count": 4,
                "pauli_terms": [{"pauli_string": "I", "coefficient": -1.0}],
            },
            e_classical_exact=-1.0,
            e_exact_pauli=-1.0,
            upstream_logical_energy=-1.0,
            hf_energy=0.0,
            target_alpha=1,
            target_beta=1,
            thresholds=thresholds,
        )
    assert error.value.code == "v1_execution_sealed"
