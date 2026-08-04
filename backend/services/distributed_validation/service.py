from __future__ import annotations

import json
import os
import logging
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import psutil

from backend.db.repositories.distributed_validation_repository import (
    DistributedNotFoundError,
    DistributedStateConflictError,
    DistributedValidationRepository,
)

from .artifact_store import NoClobberArtifactStore, PublishedArtifact
from .canonical import (
    canonical_artifact_sha256,
    decode_canonical_artifact_value,
    ordered_pauli_payload_bytes,
    parameter_vector_sha256,
    parse_bound_qasm2_strict,
    sha256_bytes,
    sha256_file,
)
from .compiler import build_compilation_settings, compile_distributed_v1
from .protocol import (
    PROTOCOL_FILENAME,
    PROTOCOL_ID,
    PROTOCOL_VERSION,
    TOPOLOGY_4Q_SHA256,
)
from .registration import FROZEN_ROLES, OWNER_USER_ID
from .remediation_protocol import VersionedValidationProtocol
from .simulator import simulate_statevector_v1
from .versioned_orchestrator import (
    VersionedDistributedSimulationOrchestrator,
    VersionedPersistenceCallback,
    VersionedSimulationRequest,
    VersionedSimulationRun,
)
from .versioned_simulation import FaultInjector

PROTOCOL_SHA256 = "4f06fbb9bda3c433ba952641f4848601bb1f3dbf4da7bc8c89f63e0b9d916888"
FORMAL_4Q_ROLE = next(role for role in FROZEN_ROLES if role.role == "minimum_pipeline")
ARTIFACT_FILENAMES = (
    "input_manifest.json",
    "logical_circuit_snapshot.json",
    "partition_plan.json",
    "optimized_gate_order.json",
    "target_topology.json",
    "chip_mapping.json",
    "communication_route_plan.json",
    "distributed_executable.json",
    "distributed_simulation_result.json",
    "distributed_validation_report.json",
)
logger = logging.getLogger(__name__)
CURRENT_FORMAL_AUTHORIZATION = {
    "stage_b_formal_attempt": "consumed_failed",
    "stage_b_remediation": "accepted",
    "new_formal_4q_attempt_authorized": False,
    "stage_c_authorized": False,
    "v1_write_entrypoint_sealed": True,
}


class DistributedValidationServiceError(RuntimeError):
    """Raised when Stage B cannot safely advance."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DistributedValidationService:
    """Expose read access to V1 and the shared versioned execution core."""

    def __init__(
        self,
        *,
        repository: DistributedValidationRepository | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        workspace_root = Path(__file__).resolve().parents[3]
        configured_data_root = Path(
            os.environ.get(
                "PLATFORM_DATA_ROOT",
                workspace_root / "data",
            )
        )
        self.artifact_root = (
            artifact_root or configured_data_root / "structure_artifacts"
        ).resolve()
        self.repository = repository or DistributedValidationRepository()
        self.store = NoClobberArtifactStore(self.artifact_root)
        self.protocol_path = self.artifact_root / PROTOCOL_FILENAME

    def execute_versioned_v2(
        self,
        *,
        protocol: VersionedValidationProtocol,
        protocol_sha256: str,
        request: VersionedSimulationRequest,
        persistence_callback: VersionedPersistenceCallback | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> VersionedSimulationRun:
        """Run the production V2 core under current authorization boundaries."""
        if request.execution_scope == "formal_v2":
            self._reject_sealed_formal_write("start_simulation")
        workspace_root = Path(__file__).resolve().parents[3]
        formal_root = (workspace_root / "data" / "structure_artifacts").resolve()
        temporary_roots = (
            Path(tempfile.gettempdir()).resolve(),
            (workspace_root / "tmp").resolve(),
        )
        is_temporary = any(
            self.artifact_root == root or root in self.artifact_root.parents
            for root in temporary_roots
        )
        if not is_temporary or (
            self.artifact_root == formal_root
            or formal_root in self.artifact_root.parents
        ):
            raise DistributedValidationServiceError(
                "remediation_artifact_root_not_temporary",
                "B-R versioned execution requires a temporary Artifact root.",
            )
        if (
            request.execution_scope != "synthetic"
            or request.formal_evidence
            or not request.run_id.startswith("synthetic_")
        ):
            raise DistributedValidationServiceError(
                "remediation_scope_violation",
                "B-R permits only non-formal synthetic V2 execution.",
            )
        orchestrator = VersionedDistributedSimulationOrchestrator(
            store=self.store,
            protocol=protocol,
            protocol_sha256=protocol_sha256,
            allow_formal_execution=False,
            persistence_callback=persistence_callback,
        )
        return orchestrator.execute(
            request,
            fault_injector=fault_injector,
        )

    def create_and_compile(
        self,
        *,
        owner_user_id: int,
        vqe_execution_id: str,
        idempotency_key: str,
    ) -> Any:
        """Reject new V1 compilations after the sole formal attempt was consumed."""
        if owner_user_id != OWNER_USER_ID:
            raise DistributedValidationServiceError(
                "owner_mismatch",
                "Stage B is frozen to owner_user_id=183.",
            )
        self._reject_sealed_formal_write("create_compilation")
        protocol = self._load_protocol()
        closure = self.repository.resolve_qualified_closure(
            owner_user_id=owner_user_id,
            vqe_execution_id=vqe_execution_id,
            benchmark_role="minimum_pipeline",
            qualification_protocol_id="minimum_fixed_sector_vqe_acceptance",
            qualification_protocol_version="1",
            qualification_status="minimum_fixed_sector_vqe_accepted",
        )
        execution, circuit, qubit_hamiltonian = (
            self.repository.resolve_compilation_inputs(
                owner_user_id=owner_user_id,
                vqe_execution_id=vqe_execution_id,
            )
        )
        if closure.qubit_count != 4 or qubit_hamiltonian.qubit_count != 4:
            raise DistributedValidationServiceError(
                "stage_c_not_authorized",
                "Stage B accepts only the frozen 4-qubit minimum CAS.",
            )
        frozen = self._validate_frozen_inputs(
            circuit=circuit,
            qubit_hamiltonian=qubit_hamiltonian,
            closure=closure,
        )
        request_payload = {
            "action": "create_compilation",
            "owner_user_id": owner_user_id,
            "vqe_execution_id": vqe_execution_id,
            "closure_benchmark_id": closure.closure_benchmark_id,
            "protocol_sha256": PROTOCOL_SHA256,
            "topology_sha256": TOPOLOGY_4Q_SHA256,
        }
        request_fingerprint = canonical_artifact_sha256(request_payload)
        compilation_id = f"dmc_{uuid4().hex}"
        resource_estimate = self._resource_preflight(
            protocol["resource_guardrails"]["level_a_4q"],
            len(frozen["qasm_text"].encode("utf-8")),
        )
        compilation = self.repository.create_compilation(
            values={
                "compilation_id": compilation_id,
                "owner_user_id": owner_user_id,
                "vqe_execution_id": execution.execution_id,
                "qubit_hamiltonian_id": qubit_hamiltonian.qubit_hamiltonian_id,
                "closure_benchmark_id": closure.closure_benchmark_id,
                "benchmark_level": "level_a_4q",
                "execution_stage": "stage_b",
                "protocol_id": PROTOCOL_ID,
                "protocol_version": PROTOCOL_VERSION,
                "protocol_artifact_path": str(self.protocol_path),
                "protocol_sha256": PROTOCOL_SHA256,
                "topology_name": "linear-2-capacity-2",
                "topology_sha256": TOPOLOGY_4Q_SHA256,
                "raw_qasm_sha256": FORMAL_4Q_ROLE.raw_qasm_sha256,
                "canonical_circuit_sha256": FORMAL_4Q_ROLE.canonical_circuit_sha256,
                "parameter_sha256": FORMAL_4Q_ROLE.parameter_sha256,
                "hamiltonian_artifact_sha256": FORMAL_4Q_ROLE.hamiltonian_sha256,
                "ordered_pauli_payload_sha256": FORMAL_4Q_ROLE.ordered_pauli_sha256,
                "execution_semantics_strategy": (
                    "topology_aware_remote_swap_route_and_restore"
                ),
                "partition_count": 2,
                "status": "compilation_created",
                "baseline_metrics": {},
                "optimized_metrics": {},
                "resource_estimate": resource_estimate,
                "authorization_mode": "product_stage_b_explicit_approval",
                "authorization_reference": "stage_b_authorized_2026-07-28",
                "formal_attempt_limit": 1,
                "formal_attempts_started": 0,
                "actual_distributed_hardware_execution": False,
                "row_version": 0,
            },
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if compilation.status != "compilation_created":
            return compilation

        started = time.perf_counter()
        try:
            parsed = parse_bound_qasm2_strict(frozen["qasm_text"])
            compilation_settings = build_compilation_settings(
                partitioning=protocol["partitioning"],
                gate_ordering=protocol["gate_ordering"],
                mapping=protocol["mapping"],
                routing=protocol["routing"],
                qubit_count=parsed.circuit.num_qubits,
            )
            compiled = compile_distributed_v1(
                parsed,
                settings=compilation_settings,
                maximum_expanded_gate_count=int(
                    protocol["resource_guardrails"]["level_a_4q"][
                        "maximum_expanded_gate_count"
                    ]
                ),
                topology_payload=protocol["topologies"]["level_a_4q"][
                    "canonical_preimage"
                ],
                topology_sha256=TOPOLOGY_4Q_SHA256,
            )
            elapsed = time.perf_counter() - started
            if elapsed > protocol["resource_guardrails"]["level_a_4q"][
                "compilation_wall_seconds"
            ]:
                raise DistributedValidationServiceError(
                    "blocked_by_resource_guardrail",
                    "Compilation exceeded its frozen wall-time guardrail.",
                )
            payloads = self._compilation_payloads(
                compilation_id=compilation.compilation_id,
                closure=closure,
                frozen=frozen,
                resource_estimate=resource_estimate,
                compiled=compiled,
            )
            published = self._publish_compilation_artifacts(
                compilation.compilation_id,
                payloads,
                int(
                    protocol["resource_guardrails"]["level_a_4q"][
                        "maximum_artifact_size_bytes"
                    ]
                ),
                int(
                    protocol["resource_guardrails"]["level_a_4q"][
                        "maximum_artifact_total_bytes"
                    ]
                ),
            )
            update_values = self._compilation_database_artifact_fields(published)
            update_values.update(
                {
                    "status": "distributed_executable_ready",
                    "baseline_metrics": compiled.baseline_metrics,
                    "optimized_metrics": compiled.optimized_metrics,
                    "completed_at": datetime.utcnow(),
                }
            )
            return self.repository.update_compilation(
                compilation.compilation_id,
                owner_user_id,
                expected_row_version=compilation.row_version,
                values=update_values,
            )
        except Exception as exc:
            self._persist_compilation_failure(compilation, owner_user_id, exc)
            raise

    def run_formal_simulation(
        self,
        *,
        owner_user_id: int,
        compilation_id: str,
        idempotency_key: str,
    ) -> Any:
        """Reject V1 simulation because its sole formal attempt was consumed."""
        if owner_user_id != OWNER_USER_ID:
            raise DistributedValidationServiceError(
                "owner_mismatch",
                "Stage B is frozen to owner_user_id=183.",
            )
        self._reject_sealed_formal_write("start_simulation")
        compilation = self.repository.get_compilation(compilation_id, owner_user_id)
        if compilation is None:
            raise DistributedNotFoundError("Compilation does not exist.")
        if compilation.execution_stage != "stage_b" or compilation.benchmark_level != "level_a_4q":
            raise DistributedValidationServiceError(
                "stage_c_not_authorized",
                "Only the Stage-B 4-qubit compilation may be simulated.",
            )
        if compilation.status != "distributed_executable_ready":
            raise DistributedStateConflictError(
                "Compilation is not ready for its formal attempt."
            )
        protocol = self._load_protocol()
        request_fingerprint = canonical_artifact_sha256(
            {
                "action": "start_formal_simulation",
                "owner_user_id": owner_user_id,
                "compilation_id": compilation_id,
                "protocol_sha256": compilation.protocol_sha256,
                "distributed_executable_sha256": compilation.distributed_executable_sha256,
            }
        )
        simulation_id = f"dms_{uuid4().hex}"
        simulation = self.repository.start_formal_simulation(
            compilation_id=compilation_id,
            owner_user_id=owner_user_id,
            simulation_values={
                "simulation_id": simulation_id,
                "compilation_id": compilation_id,
                "owner_user_id": owner_user_id,
                "formal_attempt_number": 1,
                "execution_backend_type": "statevector_simulator",
                "execution_backend_detail": "qiskit.quantum_info.Statevector",
                "shots": 0,
                "status": "simulation_running",
                "qualification_status": "pending",
                "acceptance_checks": {},
                "resource_telemetry": {},
                "distributed_semantics_simulated": False,
                "actual_distributed_hardware_execution": False,
                "row_version": 0,
                "started_at": datetime.utcnow(),
            },
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if simulation.status != "simulation_running":
            return simulation

        try:
            closure = self.repository.resolve_qualified_closure(
                owner_user_id=owner_user_id,
                vqe_execution_id=compilation.vqe_execution_id,
                benchmark_role="minimum_pipeline",
                qualification_protocol_id="minimum_fixed_sector_vqe_acceptance",
                qualification_protocol_version="1",
                qualification_status="minimum_fixed_sector_vqe_accepted",
            )
            _, circuit, qubit_hamiltonian = self.repository.resolve_compilation_inputs(
                owner_user_id=owner_user_id,
                vqe_execution_id=compilation.vqe_execution_id,
            )
            frozen = self._validate_frozen_inputs(
                circuit=circuit,
                qubit_hamiltonian=qubit_hamiltonian,
                closure=closure,
            )
            executable = self._read_canonical_artifact(
                Path(str(compilation.distributed_executable_path)),
                str(compilation.distributed_executable_sha256),
            )
            self._resource_preflight(
                protocol["resource_guardrails"]["level_a_4q"],
                len(frozen["qasm_text"].encode("utf-8")),
            )
            started = time.perf_counter()
            outcome = simulate_statevector_v1(
                logical_circuit=parse_bound_qasm2_strict(frozen["qasm_text"]).circuit,
                distributed_executable=executable,
                pauli_mapping=frozen["mapping"],
                e_classical_exact=float(closure.fci_energy_hartree),
                e_exact_pauli=float(closure.exact_pauli_energy_hartree),
                upstream_logical_energy=float(closure.vqe_energy_hartree),
                hf_energy=float(closure.artifact_manifest["hf_energy_hartree"]),
                target_alpha=1,
                target_beta=1,
                thresholds=protocol["acceptance_thresholds"],
            )
            if time.perf_counter() - started > protocol["resource_guardrails"][
                "level_a_4q"
            ]["simulation_wall_seconds"]:
                raise DistributedValidationServiceError(
                    "blocked_by_resource_guardrail",
                    "Simulation exceeded its frozen wall-time guardrail.",
                )
            result_payload, report_payload = self._simulation_payloads(
                simulation_id=simulation.simulation_id,
                compilation=compilation,
                outcome=outcome,
            )
            max_size = int(
                protocol["resource_guardrails"]["level_a_4q"][
                    "maximum_artifact_size_bytes"
                ]
            )
            run_dir = f"distributed_validation/{compilation_id}"
            result_artifact = self.store.publish_json(
                f"{run_dir}/{ARTIFACT_FILENAMES[8]}",
                result_payload,
                max_size_bytes=max_size,
            )
            report_artifact = self.store.publish_json(
                f"{run_dir}/{ARTIFACT_FILENAMES[9]}",
                report_payload,
                max_size_bytes=max_size,
            )
            metrics = outcome.metrics
            sector = metrics["distributed_sector"]
            return self.repository.update_simulation(
                simulation.simulation_id,
                owner_user_id,
                expected_row_version=simulation.row_version,
                values={
                    "status": (
                        "completed"
                        if outcome.qualification_status
                        == "distributed_closure_validated"
                        else "acceptance_not_met"
                    ),
                    "qualification_status": outcome.qualification_status,
                    "e_classical_exact": metrics["e_classical_exact"],
                    "e_exact_pauli": metrics["e_exact_pauli"],
                    "e_logical_vqe": metrics["e_logical_vqe"],
                    "e_distributed": metrics["e_distributed"],
                    "error_fci_vs_pauli": metrics["error_fci_vs_pauli"],
                    "error_logical_vs_pauli": metrics["error_logical_vs_pauli"],
                    "error_distributed_vs_logical": metrics[
                        "error_distributed_vs_logical"
                    ],
                    "error_distributed_vs_pauli": metrics[
                        "error_distributed_vs_pauli"
                    ],
                    "statevector_fidelity": metrics["statevector_fidelity"],
                    "statevector_infidelity": metrics["statevector_infidelity"],
                    "n_alpha_expectation": sector["n_alpha_expectation"],
                    "n_beta_expectation": sector["n_beta_expectation"],
                    "n_alpha_variance": sector["n_alpha_variance"],
                    "n_beta_variance": sector["n_beta_variance"],
                    "acceptance_checks": outcome.acceptance_checks,
                    "resource_telemetry": outcome.resource_telemetry,
                    "result_artifact_path": str(result_artifact.absolute_path),
                    "result_artifact_sha256": result_artifact.sha256,
                    "validation_report_path": str(report_artifact.absolute_path),
                    "validation_report_sha256": report_artifact.sha256,
                    "distributed_semantics_simulated": True,
                    "completed_at": datetime.utcnow(),
                },
            )
        except Exception as exc:
            self._persist_simulation_failure(simulation, owner_user_id, exc)
            raise

    def _load_protocol(self) -> dict[str, Any]:
        """Load archived V1 metadata without treating it as current authority."""
        if not self.protocol_path.exists():
            raise DistributedValidationServiceError(
                "protocol_missing",
                "The frozen protocol Artifact does not exist.",
            )
        if sha256_file(self.protocol_path) != PROTOCOL_SHA256:
            raise DistributedValidationServiceError(
                "protocol_hash_mismatch",
                "The frozen protocol Artifact hash does not match.",
            )
        payload = self._read_canonical_artifact(
            self.protocol_path,
            PROTOCOL_SHA256,
        )
        if (
            payload.get("protocol_id") != PROTOCOL_ID
            or payload.get("protocol_version") != PROTOCOL_VERSION
            or payload.get("stage_b_authorized") is not True
            or payload.get("stage_c_authorized") is not False
        ):
            raise DistributedValidationServiceError(
                "protocol_state_invalid",
                "The archived V1 protocol metadata does not match its frozen history.",
            )
        return payload

    @staticmethod
    def _reject_sealed_formal_write(action: str) -> None:
        if (
            CURRENT_FORMAL_AUTHORIZATION["new_formal_4q_attempt_authorized"]
            or not CURRENT_FORMAL_AUTHORIZATION["v1_write_entrypoint_sealed"]
        ):
            raise DistributedValidationServiceError(
                "authorization_state_invalid",
                "The immutable current authorization state is inconsistent.",
            )
        if action == "create_compilation":
            code = "new_formal_4q_attempt_not_authorized"
            detail = (
                "The historical V1 Stage-B authorization is not current "
                "authority; the sole formal 4q attempt was consumed and failed."
            )
        elif action == "start_simulation":
            code = "formal_attempt_consumed"
            detail = (
                "The sole formal 4q attempt is permanently consumed; "
                "simulation cannot be started again."
            )
        else:
            code = "formal_write_not_authorized"
            detail = "Formal distributed-validation writes are sealed."
        raise DistributedValidationServiceError(code, detail)

    def _validate_frozen_inputs(
        self,
        *,
        circuit: Any,
        qubit_hamiltonian: Any,
        closure: Any,
    ) -> dict[str, Any]:
        qasm_source_path = Path(str(circuit.qasm_artifact_path))
        hamiltonian_path = Path(str(qubit_hamiltonian.pauli_artifact_path))
        if sha256_file(qasm_source_path) != FORMAL_4Q_ROLE.qasm_source_sha256:
            raise DistributedValidationServiceError(
                "source_artifact_hash_mismatch",
                "Frozen 4q VQE Artifact hash mismatch.",
            )
        if sha256_file(hamiltonian_path) != FORMAL_4Q_ROLE.hamiltonian_sha256:
            raise DistributedValidationServiceError(
                "source_artifact_hash_mismatch",
                "Frozen 4q Hamiltonian Artifact hash mismatch.",
            )
        vqe = json.loads(qasm_source_path.read_text(encoding="utf-8"))
        hamiltonian = json.loads(hamiltonian_path.read_text(encoding="utf-8"))
        result = vqe["acceptance"]
        qasm_text = result["qasm_content"]
        parsed = parse_bound_qasm2_strict(qasm_text)
        parameters = result["final_measurement"]["parameters"]
        mapping = hamiltonian["jordan_wigner_pauli"]["mapping"]
        constant_offset = hamiltonian["jordan_wigner_pauli"][
            "constant_energy_offset_hartree"
        ]
        checks = {
            "raw_qasm": parsed.raw_qasm_sha256 == FORMAL_4Q_ROLE.raw_qasm_sha256,
            "canonical_circuit": (
                parsed.canonical_sha256 == FORMAL_4Q_ROLE.canonical_circuit_sha256
            ),
            "parameters": (
                parameter_vector_sha256(parameters)
                == FORMAL_4Q_ROLE.parameter_sha256
            ),
            "ordered_pauli": (
                sha256_bytes(ordered_pauli_payload_bytes(mapping, constant_offset))
                == FORMAL_4Q_ROLE.ordered_pauli_sha256
            ),
            "database_raw_qasm": (
                circuit.raw_qasm_sha256 == FORMAL_4Q_ROLE.raw_qasm_sha256
            ),
            "database_canonical": (
                circuit.canonical_circuit_sha256
                == FORMAL_4Q_ROLE.canonical_circuit_sha256
            ),
            "database_parameters": (
                circuit.parameter_sha256 == FORMAL_4Q_ROLE.parameter_sha256
            ),
            "database_pauli": (
                qubit_hamiltonian.ordered_pauli_payload_sha256
                == FORMAL_4Q_ROLE.ordered_pauli_sha256
            ),
            "database_qualification": (
                closure.qualification_status
                == "minimum_fixed_sector_vqe_accepted"
            ),
        }
        if not all(checks.values()):
            raise DistributedValidationServiceError(
                "frozen_input_hash_mismatch",
                f"Frozen input verification failed: {checks}",
            )
        return {
            "qasm_text": qasm_text,
            "parameters": parameters,
            "mapping": mapping,
            "constant_offset_hartree": constant_offset,
            "vqe_path": qasm_source_path,
            "hamiltonian_path": hamiltonian_path,
            "checks": checks,
        }

    @staticmethod
    def _resource_preflight(
        guardrails: dict[str, Any],
        qasm_size_bytes: int,
    ) -> dict[str, Any]:
        memory = psutil.virtual_memory()
        disk = shutil.disk_usage(Path.cwd())
        statevector_bytes = 2 ** int(guardrails["qubit_count"]) * 16
        checks = {
            "available_memory": memory.available
            >= int(guardrails["minimum_available_memory_bytes"]),
            "available_disk": disk.free
            >= int(guardrails["minimum_available_disk_bytes"]),
            "qasm_size": qasm_size_bytes
            <= int(guardrails["maximum_qasm_size_bytes"]),
            "statevector_rss_budget": statevector_bytes * 8
            <= int(guardrails["rss_limit_bytes"]),
        }
        result = {
            "checked_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "host_available_memory_bytes": int(memory.available),
            "host_available_disk_bytes": int(disk.free),
            "qasm_size_bytes": qasm_size_bytes,
            "data_qubits": int(guardrails["qubit_count"]),
            "routing_ancilla_qubits": 0,
            "total_qubits": int(guardrails["qubit_count"]),
            "statevector_bytes_each": statevector_bytes,
            "statevector_safety_multiplier": 8,
            "estimated_peak_bytes": statevector_bytes * 8,
            "rss_limit_bytes": int(guardrails["rss_limit_bytes"]),
            "checks": checks,
        }
        if not all(checks.values()):
            raise DistributedValidationServiceError(
                "blocked_by_resource_guardrail",
                f"Resource preflight failed: {checks}",
            )
        return result

    @staticmethod
    def _lineage(
        *,
        artifact_type: str,
        artifact_id: str,
        compilation_id: str,
        parent_artifact_ids: list[str],
    ) -> dict[str, Any]:
        return {
            "artifact_type": artifact_type,
            "schema_version": 1,
            "artifact_id": artifact_id,
            "compilation_id": compilation_id,
            "owner_user_id": OWNER_USER_ID,
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "protocol_sha256": PROTOCOL_SHA256,
            "parent_artifact_ids": parent_artifact_ids,
            "created_at": datetime.now(timezone.utc),
            "immutable": True,
            "actual_distributed_hardware_execution": False,
        }

    def _compilation_payloads(
        self,
        *,
        compilation_id: str,
        closure: Any,
        frozen: dict[str, Any],
        resource_estimate: dict[str, Any],
        compiled: Any,
    ) -> list[dict[str, Any]]:
        input_id = f"{compilation_id}:input_manifest"
        input_manifest = {
            **self._lineage(
                artifact_type="distributed_input_manifest",
                artifact_id=input_id,
                compilation_id=compilation_id,
                parent_artifact_ids=[
                    FORMAL_4Q_ROLE.vqe_id,
                    FORMAL_4Q_ROLE.hamiltonian_id,
                    PROTOCOL_ID,
                ],
            ),
            "benchmark_level": "level_a_4q",
            "closure_benchmark_id": closure.closure_benchmark_id,
            "source_vqe_execution_id": closure.vqe_execution_id,
            "source_files": [
                {
                    "role": "bound_logical_qasm",
                    "artifact_id": FORMAL_4Q_ROLE.vqe_id,
                    "path": str(frozen["vqe_path"]),
                    "file_sha256": FORMAL_4Q_ROLE.vqe_sha256,
                },
                {
                    "role": "active_space_hamiltonian",
                    "artifact_id": FORMAL_4Q_ROLE.hamiltonian_id,
                    "path": str(frozen["hamiltonian_path"]),
                    "file_sha256": FORMAL_4Q_ROLE.hamiltonian_sha256,
                },
                {
                    "role": "validation_protocol",
                    "artifact_id": PROTOCOL_ID,
                    "path": str(self.protocol_path),
                    "file_sha256": PROTOCOL_SHA256,
                },
            ],
            "raw_qasm_sha256": FORMAL_4Q_ROLE.raw_qasm_sha256,
            "canonical_circuit_sha256": FORMAL_4Q_ROLE.canonical_circuit_sha256,
            "parameter_sha256": FORMAL_4Q_ROLE.parameter_sha256,
            "ordered_pauli_payload_sha256": FORMAL_4Q_ROLE.ordered_pauli_sha256,
            "topology_sha256": TOPOLOGY_4Q_SHA256,
            "parameters_bound": True,
            "input_verification": frozen["checks"],
            "resource_preflight": resource_estimate,
            "scientific_adsorption_validation": False,
            "ground_state_assessed": False,
        }
        source_payloads = (
            compiled.logical_snapshot,
            compiled.partition_plan,
            compiled.optimized_gate_order,
            compiled.target_topology,
            compiled.chip_mapping,
            compiled.communication_route_plan,
            compiled.distributed_executable,
        )
        artifact_types = (
            "logical_circuit_snapshot",
            "partition_plan",
            "optimized_gate_order",
            "target_topology",
            "chip_mapping",
            "communication_route_plan",
            "distributed_executable",
        )
        payloads = [input_manifest]
        parent_id = input_id
        for artifact_type, payload in zip(artifact_types, source_payloads, strict=True):
            artifact_id = f"{compilation_id}:{artifact_type}"
            payloads.append(
                {
                    **self._lineage(
                        artifact_type=artifact_type,
                        artifact_id=artifact_id,
                        compilation_id=compilation_id,
                        parent_artifact_ids=[parent_id],
                    ),
                    **{
                        key: value
                        for key, value in payload.items()
                        if key not in {"artifact_type", "schema_version"}
                    },
                }
            )
            parent_id = artifact_id
        return payloads

    def _publish_compilation_artifacts(
        self,
        compilation_id: str,
        payloads: list[dict[str, Any]],
        max_size_bytes: int,
        max_total_bytes: int,
    ) -> list[PublishedArtifact]:
        published: list[PublishedArtifact] = []
        run_dir = f"distributed_validation/{compilation_id}"
        for filename, payload in zip(ARTIFACT_FILENAMES[:8], payloads, strict=True):
            artifact = self.store.publish_json(
                f"{run_dir}/{filename}",
                payload,
                max_size_bytes=max_size_bytes,
            )
            published.append(artifact)
            if sum(item.size_bytes for item in published) > max_total_bytes:
                raise DistributedValidationServiceError(
                    "blocked_by_resource_guardrail",
                    "Compilation Artifact total size exceeds the frozen limit.",
                )
        return published

    @staticmethod
    def _compilation_database_artifact_fields(
        published: list[PublishedArtifact],
    ) -> dict[str, Any]:
        prefixes = (
            "input_manifest",
            "logical_snapshot",
            "partition_plan",
            "optimized_gate_order",
            "target_topology",
            "chip_mapping",
            "communication_route_plan",
            "distributed_executable",
        )
        values: dict[str, Any] = {}
        for prefix, artifact in zip(prefixes, published, strict=True):
            values[f"{prefix}_path"] = str(artifact.absolute_path)
            values[f"{prefix}_sha256"] = artifact.sha256
        return values

    def _simulation_payloads(
        self,
        *,
        simulation_id: str,
        compilation: Any,
        outcome: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        result_id = f"{simulation_id}:distributed_simulation_result"
        result = {
            **self._lineage(
                artifact_type="distributed_simulation_result",
                artifact_id=result_id,
                compilation_id=compilation.compilation_id,
                parent_artifact_ids=[
                    f"{compilation.compilation_id}:distributed_executable"
                ],
            ),
            "simulation_id": simulation_id,
            "formal_attempt_number": 1,
            "backend": "qiskit.quantum_info.Statevector",
            "shots": 0,
            "distributed_semantics_simulated": True,
            "metrics": outcome.metrics,
            "acceptance_checks": outcome.acceptance_checks,
            "qualification_status": outcome.qualification_status,
            "resource_telemetry": outcome.resource_telemetry,
        }
        report = {
            **self._lineage(
                artifact_type="distributed_validation_report",
                artifact_id=f"{simulation_id}:distributed_validation_report",
                compilation_id=compilation.compilation_id,
                parent_artifact_ids=[result_id],
            ),
            "simulation_id": simulation_id,
            "formal_attempt_number": 1,
            "status": outcome.qualification_status,
            "four_energies_hartree": {
                "e_classical_exact": outcome.metrics["e_classical_exact"],
                "e_exact_pauli": outcome.metrics["e_exact_pauli"],
                "e_logical_vqe": outcome.metrics["e_logical_vqe"],
                "e_distributed": outcome.metrics["e_distributed"],
            },
            "errors_hartree": {
                key: value
                for key, value in outcome.metrics.items()
                if key.startswith("error_")
            },
            "statevector_fidelity": outcome.metrics["statevector_fidelity"],
            "statevector_infidelity": outcome.metrics["statevector_infidelity"],
            "fidelity_definition": (
                "abs(inner_product(native_logical,recovered_distributed))^2;"
                "global_phase_invariant;qiskit_little_endian"
            ),
            "particle_sector": outcome.metrics["distributed_sector"],
            "acceptance_checks": outcome.acceptance_checks,
            "resource_telemetry": {
                "compilation_preflight": compilation.resource_estimate,
                "simulation": outcome.resource_telemetry,
            },
            "compilation_metrics": {
                "baseline": compilation.baseline_metrics,
                "optimized": compilation.optimized_metrics,
            },
            "compilation_artifacts": self._compilation_artifact_manifest(
                compilation
            ),
            "hamiltonian_runtime_rule": {
                "identity_pauli_term_contains_energy_offset": True,
                "constant_offset_is_audit_only": True,
                "constant_offset_added_at_runtime": False,
                "exact_pauli_energy_regression_error_hartree": outcome.metrics[
                    "error_runtime_exact_regression"
                ],
            },
            "shots": 0,
            "ground_state_assessed": False,
            "scientific_adsorption_validation": False,
            "qpu_execution": False,
            "actual_distributed_hardware_execution": False,
        }
        return result, report

    @staticmethod
    def _compilation_artifact_manifest(compilation: Any) -> list[dict[str, str]]:
        prefixes = (
            "input_manifest",
            "logical_snapshot",
            "partition_plan",
            "optimized_gate_order",
            "target_topology",
            "chip_mapping",
            "communication_route_plan",
            "distributed_executable",
        )
        manifest: list[dict[str, str]] = []
        for prefix in prefixes:
            path = getattr(compilation, f"{prefix}_path")
            sha256 = getattr(compilation, f"{prefix}_sha256")
            if not path or not sha256:
                raise DistributedValidationServiceError(
                    "compilation_artifact_incomplete",
                    f"Compilation Artifact is incomplete: {prefix}",
                )
            manifest.append(
                {
                    "role": prefix,
                    "path": str(path),
                    "sha256": str(sha256),
                }
            )
        return manifest

    @staticmethod
    def _read_canonical_artifact(path: Path, expected_sha256: str) -> dict[str, Any]:
        if sha256_file(path) != expected_sha256:
            raise DistributedValidationServiceError(
                "artifact_hash_mismatch",
                f"Artifact hash mismatch: {path}",
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        decoded = decode_canonical_artifact_value(raw)
        if not isinstance(decoded, dict):
            raise DistributedValidationServiceError(
                "artifact_schema_invalid",
                "Canonical Artifact root must be an object.",
            )
        return decoded

    def _persist_compilation_failure(
        self,
        compilation: Any,
        owner_user_id: int,
        exc: Exception,
    ) -> None:
        code = getattr(exc, "code", "compilation_failed")
        try:
            self.repository.update_compilation(
                compilation.compilation_id,
                owner_user_id,
                expected_row_version=compilation.row_version,
                values={
                    "status": (
                        "blocked_by_resource_guardrail"
                        if code == "blocked_by_resource_guardrail"
                        else "compilation_failed"
                    ),
                    "failure_code": str(code),
                    "failure_stage": "compilation",
                    "failure_detail": str(exc),
                    "completed_at": datetime.utcnow(),
                },
            )
        except Exception:
            # Preserve the original exception; a database-level failure remains
            # visible through the incomplete compilation state.
            logger.exception(
                "Failed to enrich compilation %s with failure evidence.",
                compilation.compilation_id,
            )

    def _persist_simulation_failure(
        self,
        simulation: Any,
        owner_user_id: int,
        exc: Exception,
    ) -> None:
        code = getattr(exc, "code", "simulation_failed")
        try:
            self.repository.update_simulation(
                simulation.simulation_id,
                owner_user_id,
                expected_row_version=simulation.row_version,
                values={
                    "status": (
                        "blocked_by_resource_guardrail"
                        if code == "blocked_by_resource_guardrail"
                        else "simulation_failed"
                    ),
                    "qualification_status": "not_validated",
                    "failure_code": str(code),
                    "failure_stage": "simulation",
                    "failure_detail": str(exc),
                    "completed_at": datetime.utcnow(),
                },
            )
        except Exception:
            # The consumed attempt remains durable even if failure enrichment
            # itself cannot be committed.
            logger.exception(
                "Failed to enrich simulation %s with failure evidence.",
                simulation.simulation_id,
            )
