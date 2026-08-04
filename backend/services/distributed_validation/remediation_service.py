from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from .artifact_store import NoClobberArtifactStore, PublishedArtifact
from .canonical import (
    canonical_artifact_sha256,
    parse_bound_qasm2_strict,
    sha256_bytes,
)
from .compiler import build_compilation_settings, compile_distributed_v1
from .remediation_protocol import (
    FUTURE_ARTIFACT_FILENAMES,
    RemediationProtocol,
    validate_synthetic_protocol_fixture,
)
from .versioned_simulation import FaultInjector, StructuredSimulationResult
from .versioned_orchestrator import (
    VersionedDistributedSimulationOrchestrator,
    VersionedSimulationRequest,
)


@dataclass(frozen=True)
class SyntheticValidationInput:
    run_id: str
    owner_user_id: int
    qasm_text: str
    pauli_mapping: dict[str, Any]
    e_classical_exact: float
    e_exact_pauli: float
    upstream_logical_energy: float
    hf_energy: float
    target_alpha: int
    target_beta: int


@dataclass(frozen=True)
class SyntheticValidationRun:
    run_id: str
    structured_result: StructuredSimulationResult
    artifacts: tuple[PublishedArtifact, ...]
    final_execution_milestones: dict[str, dict[str, Any]]


class SyntheticRemediationError(RuntimeError):
    """Raised when fixture-only remediation could affect formal evidence."""


class SyntheticRemediationService:
    """Compile and simulate synthetic inputs while always publishing ten Artifacts."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        protocol_payload: dict[str, Any],
        formal_artifact_root: Path | None = None,
    ) -> None:
        resolved_root = artifact_root.resolve()
        workspace_root = Path(__file__).resolve().parents[3]
        resolved_formal = (
            formal_artifact_root
            or workspace_root / "data" / "structure_artifacts"
        ).resolve()
        if resolved_root == resolved_formal or resolved_formal in resolved_root.parents:
            raise SyntheticRemediationError(
                "Synthetic Artifact root must not be inside the formal Artifact root."
            )
        self.artifact_root = resolved_root
        self.protocol = validate_synthetic_protocol_fixture(protocol_payload)
        if not self.protocol.authorization.temporary_artifact_root_only:
            raise SyntheticRemediationError(
                "The remediation protocol must require a temporary Artifact root."
            )
        self.protocol_payload = self.protocol.model_dump(mode="python")
        self.protocol_sha256 = canonical_artifact_sha256(self.protocol_payload)
        self.store = NoClobberArtifactStore(self.artifact_root)
        self.versioned_orchestrator = VersionedDistributedSimulationOrchestrator(
            store=self.store,
            protocol=self.protocol,
            protocol_sha256=self.protocol_sha256,
            allow_formal_execution=False,
        )
        self.protocol_fixture_file = self.store.publish_json(
            (
                "test_fixtures/"
                "distributed_validation_protocol_v2.synthetic.json"
            ),
            self.protocol_payload,
            max_size_bytes=(
                self.protocol.resource_guardrails.maximum_artifact_size_bytes
            ),
        )
        if self.protocol_fixture_file.sha256 != self.protocol_sha256:
            raise SyntheticRemediationError(
                "Published protocol fixture does not match its canonical SHA-256."
            )

    def run(
        self,
        synthetic_input: SyntheticValidationInput,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> SyntheticValidationRun:
        """Run one synthetic case; this method rejects formal-looking IDs."""
        self._validate_synthetic_input(synthetic_input)
        self._check_preflight_resources(synthetic_input)
        compilation_started = time.perf_counter()
        parsed = parse_bound_qasm2_strict(synthetic_input.qasm_text)
        topology_payload = {
            "schema": "distributed-topology-v1",
            "topology_name": self.protocol.topology.name,
            "directed": False,
            "nodes": [
                {
                    "id": node_id,
                    "qubit_capacity": self.protocol.topology.capacity_per_node,
                }
                for node_id in range(self.protocol.topology.node_count)
            ],
            "edges": [
                {
                    "source": 0,
                    "target": 1,
                    "weight_hex": "3ff0000000000000",
                }
            ],
        }
        topology_sha256 = canonical_artifact_sha256(topology_payload)
        if topology_sha256 != self.protocol.topology.topology_sha256:
            raise SyntheticRemediationError(
                "Synthetic topology does not match the versioned fixture hash."
            )
        compilation_settings = build_compilation_settings(
            partitioning=self.protocol.partitioning.model_dump(mode="python"),
            gate_ordering=self.protocol.gate_ordering.model_dump(mode="python"),
            mapping=self.protocol.mapping.model_dump(mode="python"),
            routing=self.protocol.routing.model_dump(mode="python"),
            qubit_count=parsed.circuit.num_qubits,
        )
        compiled = compile_distributed_v1(
            parsed,
            settings=compilation_settings,
            maximum_expanded_gate_count=(
                self.protocol.resource_guardrails.maximum_expanded_gate_count
            ),
            topology_payload=topology_payload,
            topology_sha256=topology_sha256,
        )
        compilation_elapsed = time.perf_counter() - compilation_started
        if (
            compilation_elapsed
            > self.protocol.resource_guardrails.compilation_wall_seconds
        ):
            raise SyntheticRemediationError(
                "Synthetic compilation exceeded the fixture wall-time guardrail."
            )
        if (
            compiled.optimized_metrics["circuit_depth"]
            > self.protocol.resource_guardrails.maximum_circuit_depth
        ):
            raise SyntheticRemediationError(
                "Synthetic circuit depth exceeds the fixture guardrail."
            )
        run_directory = f"synthetic_validation/{synthetic_input.run_id}"
        artifacts: list[PublishedArtifact] = []
        parent = self._publish_input_manifest(
            synthetic_input,
            parsed,
            run_directory,
        )
        artifacts.append(parent)
        parent_role = "distributed_input_manifest"
        parent_artifact_id = (
            f"{synthetic_input.run_id}:distributed_input_manifest"
        )

        compilation_payloads = (
            compiled.logical_snapshot,
            compiled.partition_plan,
            compiled.optimized_gate_order,
            compiled.target_topology,
            compiled.chip_mapping,
            compiled.communication_route_plan,
            compiled.distributed_executable,
        )
        compilation_roles = (
            "logical_circuit_snapshot",
            "partition_plan",
            "optimized_gate_order",
            "target_topology",
            "chip_mapping",
            "communication_route_plan",
            "distributed_executable",
        )
        for index, (role, source_payload) in enumerate(
            zip(compilation_roles, compilation_payloads, strict=True),
            start=1,
        ):
            payload = {
                **self._artifact_header(
                    synthetic_input,
                    role=role,
                    parent_artifacts=[
                        self._published_parent(
                            parent,
                            artifact_id=parent_artifact_id,
                            role=parent_role,
                        )
                    ],
                ),
                **{
                    key: value
                    for key, value in source_payload.items()
                    if key not in {"artifact_type", "schema_version"}
                },
            }
            parent = self._publish(
                run_directory,
                FUTURE_ARTIFACT_FILENAMES[index],
                payload,
            )
            artifacts.append(parent)
            parent_role = role
            parent_artifact_id = f"{synthetic_input.run_id}:{role}"

        versioned_run = self.versioned_orchestrator.execute(
            VersionedSimulationRequest(
                run_id=synthetic_input.run_id,
                owner_user_id=synthetic_input.owner_user_id,
                artifact_directory=run_directory,
                execution_scope="synthetic",
                formal_evidence=False,
                logical_circuit=parsed.circuit,
                distributed_executable=compiled.distributed_executable,
                pauli_mapping=synthetic_input.pauli_mapping,
                e_classical_exact=synthetic_input.e_classical_exact,
                e_exact_pauli=synthetic_input.e_exact_pauli,
                upstream_logical_energy=(
                    synthetic_input.upstream_logical_energy
                ),
                hf_energy=synthetic_input.hf_energy,
                target_alpha=synthetic_input.target_alpha,
                target_beta=synthetic_input.target_beta,
                parent_artifact=parent,
                parent_artifact_id=parent_artifact_id,
                parent_role=parent_role,
            ),
            fault_injector=fault_injector,
        )
        artifacts.extend(
            (
                versioned_run.result_artifact,
                versioned_run.validation_report_artifact,
            )
        )
        if len(artifacts) != len(FUTURE_ARTIFACT_FILENAMES):
            raise SyntheticRemediationError(
                "Synthetic validation did not publish exactly ten Artifacts."
            )
        total_size = sum(artifact.size_bytes for artifact in artifacts)
        if total_size > (
            self.protocol.resource_guardrails.maximum_artifact_total_bytes
        ):
            raise SyntheticRemediationError(
                "Synthetic Artifact set exceeds the fixture total-size guardrail."
            )
        return SyntheticValidationRun(
            run_id=synthetic_input.run_id,
            structured_result=versioned_run.structured_result,
            artifacts=tuple(artifacts),
            final_execution_milestones=(
                versioned_run.final_execution_milestones
            ),
        )

    def _publish_input_manifest(
        self,
        synthetic_input: SyntheticValidationInput,
        parsed: Any,
        run_directory: str,
    ) -> PublishedArtifact:
        pauli_sha256 = canonical_artifact_sha256(synthetic_input.pauli_mapping)
        qasm_fixture = self.store.publish_bytes(
            f"synthetic_inputs/{synthetic_input.run_id}/logical.qasm",
            synthetic_input.qasm_text.encode("utf-8"),
            max_size_bytes=(
                self.protocol.resource_guardrails.maximum_qasm_size_bytes
            ),
        )
        if qasm_fixture.sha256 != parsed.raw_qasm_sha256:
            raise SyntheticRemediationError(
                "Synthetic QASM fixture does not match its parsed raw SHA-256."
            )
        pauli_fixture = self.store.publish_json(
            f"synthetic_inputs/{synthetic_input.run_id}/pauli_mapping.json",
            synthetic_input.pauli_mapping,
            max_size_bytes=(
                self.protocol.resource_guardrails.maximum_artifact_size_bytes
            ),
        )
        if pauli_fixture.sha256 != pauli_sha256:
            raise SyntheticRemediationError(
                "Synthetic Pauli fixture does not match its canonical SHA-256."
            )
        payload = {
            **self._artifact_header(
                synthetic_input,
                role="distributed_input_manifest",
                parent_artifacts=[
                    {
                        "artifact_id": "synthetic_protocol_fixture",
                        "role": "validation_protocol_fixture",
                        "relative_path": self.protocol_fixture_file.relative_path,
                        "sha256": self.protocol_sha256,
                        "schema_version": 2,
                    },
                    {
                        "artifact_id": "synthetic_logical_qasm",
                        "role": "bound_logical_qasm",
                        "relative_path": qasm_fixture.relative_path,
                        "sha256": parsed.raw_qasm_sha256,
                        "schema_version": 1,
                    },
                    {
                        "artifact_id": "synthetic_pauli_mapping",
                        "role": "ordered_pauli_mapping",
                        "relative_path": pauli_fixture.relative_path,
                        "sha256": pauli_sha256,
                        "schema_version": 1,
                    },
                ],
            ),
            "formal_evidence": False,
            "raw_qasm_sha256": parsed.raw_qasm_sha256,
            "canonical_circuit_sha256": parsed.canonical_sha256,
            "pauli_mapping_sha256": pauli_sha256,
            "parameters_bound": True,
            "optimizer_executed": False,
            "actual_distributed_hardware_execution": False,
        }
        return self._publish(
            run_directory,
            FUTURE_ARTIFACT_FILENAMES[0],
            payload,
        )

    def _artifact_header(
        self,
        synthetic_input: SyntheticValidationInput,
        *,
        role: str,
        parent_artifacts: list[dict[str, Any]],
        created_at: str | None = None,
    ) -> dict[str, Any]:
        contract = next(
            item for item in self.protocol.artifact_contract.artifacts
            if item.role == role
        )
        return {
            "artifact_type": role,
            "schema_version": contract.schema_version,
            "artifact_id": f"{synthetic_input.run_id}:{role}",
            "run_id": synthetic_input.run_id,
            "owner_user_id": synthetic_input.owner_user_id,
            "protocol_id": self.protocol.protocol_id,
            "protocol_version": self.protocol.protocol_version,
            "protocol_fixture_sha256": self.protocol_sha256,
            "parents": parent_artifacts,
            "created_at": created_at or _utc_now(),
            "immutable": True,
            "synthetic_only": True,
            "actual_distributed_hardware_execution": False,
        }

    def _publish(
        self,
        run_directory: str,
        filename: str,
        payload: dict[str, Any],
    ) -> PublishedArtifact:
        artifact = self.store.publish_json(
            f"{run_directory}/{filename}",
            payload,
            max_size_bytes=(
                self.protocol.resource_guardrails.maximum_artifact_size_bytes
            ),
        )
        return artifact

    @staticmethod
    def _published_parent(
        artifact: PublishedArtifact,
        *,
        artifact_id: str,
        role: str,
    ) -> dict[str, Any]:
        return {
            "artifact_id": artifact_id,
            "role": role,
            "relative_path": artifact.relative_path,
            "sha256": artifact.sha256,
            "schema_version": 2,
        }

    @staticmethod
    def _validate_synthetic_input(
        synthetic_input: SyntheticValidationInput,
    ) -> None:
        if not synthetic_input.run_id.startswith("synthetic_"):
            raise SyntheticRemediationError(
                "Synthetic run IDs must start with 'synthetic_'."
            )
        forbidden_fragments = ("dmc_", "dms_", "formal")
        if any(fragment in synthetic_input.run_id for fragment in forbidden_fragments):
            raise SyntheticRemediationError(
                "Synthetic run ID resembles a formal evidence identifier."
            )

    def _check_preflight_resources(
        self,
        synthetic_input: SyntheticValidationInput,
    ) -> None:
        qasm_size = len(synthetic_input.qasm_text.encode("utf-8"))
        guardrails = self.protocol.resource_guardrails
        if qasm_size > guardrails.maximum_qasm_size_bytes:
            raise SyntheticRemediationError(
                "Synthetic QASM exceeds the fixture size guardrail."
            )
        available_memory = psutil.virtual_memory().available
        if available_memory < guardrails.minimum_available_memory_bytes:
            raise SyntheticRemediationError(
                "Synthetic run is blocked by the memory guardrail."
            )
        available_disk = shutil.disk_usage(self.artifact_root).free
        if available_disk < guardrails.minimum_available_disk_bytes:
            raise SyntheticRemediationError(
                "Synthetic run is blocked by the disk guardrail."
            )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
