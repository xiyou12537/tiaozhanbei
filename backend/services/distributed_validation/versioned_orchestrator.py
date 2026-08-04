from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from qiskit import QuantumCircuit

from .artifact_store import NoClobberArtifactStore, PublishedArtifact
from .remediation_protocol import VersionedValidationProtocol
from .versioned_simulation import (
    FaultInjector,
    StructuredSimulationResult,
    simulate_statevector_versioned_v2,
)


class VersionedOrchestrationError(RuntimeError):
    """Raised when a V2 execution violates authorization or Artifact rules."""


@dataclass(frozen=True)
class VersionedSimulationRequest:
    """Inputs shared by synthetic validation and a future formal V2 attempt."""

    run_id: str
    owner_user_id: int
    artifact_directory: str
    execution_scope: Literal["synthetic", "formal_v2"]
    formal_evidence: bool
    logical_circuit: QuantumCircuit
    distributed_executable: dict[str, Any]
    pauli_mapping: dict[str, Any]
    e_classical_exact: float
    e_exact_pauli: float
    upstream_logical_energy: float
    hf_energy: float
    target_alpha: int
    target_beta: int
    parent_artifact: PublishedArtifact
    parent_artifact_id: str
    parent_role: str


@dataclass(frozen=True)
class VersionedSimulationRun:
    """Structured terminal result plus its mandatory result/report Artifacts."""

    structured_result: StructuredSimulationResult
    result_artifact: PublishedArtifact
    validation_report_artifact: PublishedArtifact
    final_execution_milestones: dict[str, dict[str, Any]]
    persistence_result: dict[str, Any] | None


VersionedPersistenceCallback = Callable[
    [
        VersionedSimulationRequest,
        StructuredSimulationResult,
        dict[str, dict[str, Any]],
        PublishedArtifact,
        PublishedArtifact,
    ],
    dict[str, Any],
]


class VersionedDistributedSimulationOrchestrator:
    """Production execution core for versioned V2 simulation semantics."""

    def __init__(
        self,
        *,
        store: NoClobberArtifactStore,
        protocol: VersionedValidationProtocol,
        protocol_sha256: str,
        allow_formal_execution: bool = False,
        persistence_callback: VersionedPersistenceCallback | None = None,
    ) -> None:
        self.store = store
        self.protocol = protocol
        self.protocol_sha256 = protocol_sha256
        self.allow_formal_execution = allow_formal_execution
        self.persistence_callback = persistence_callback

    def execute(
        self,
        request: VersionedSimulationRequest,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> VersionedSimulationRun:
        """Execute once and publish terminal evidence for every simulation outcome."""
        self._validate_authorization(request)
        structured_result = simulate_statevector_versioned_v2(
            logical_circuit=request.logical_circuit,
            distributed_executable=request.distributed_executable,
            pauli_mapping=request.pauli_mapping,
            e_classical_exact=request.e_classical_exact,
            e_exact_pauli=request.e_exact_pauli,
            upstream_logical_energy=request.upstream_logical_energy,
            hf_energy=request.hf_energy,
            target_alpha=request.target_alpha,
            target_beta=request.target_beta,
            protocol=self.protocol,
            fault_injector=fault_injector,
        )
        if (
            structured_result.observations.partial
            and structured_result.assessment.accepted
        ):
            raise VersionedOrchestrationError(
                "Partial observations cannot grant qualification."
            )

        milestones = {
            name: dict(value)
            for name, value in (
                structured_result.observations.execution_milestones.items()
            )
        }
        result_created_at = _utc_now()
        milestones["result_artifact_published"] = {
            "completed": True,
            "completed_at": result_created_at,
        }
        result_payload = {
            **self._header(
                request,
                role="distributed_simulation_result",
                created_at=result_created_at,
                parents=[
                    self._parent(
                        request.parent_artifact,
                        artifact_id=request.parent_artifact_id,
                        role=request.parent_role,
                    )
                ],
            ),
            "formal_evidence": request.formal_evidence,
            "partial": structured_result.observations.partial,
            "observations": structured_result.observations.as_dict(),
            "assessment": structured_result.assessment.as_dict(),
            "execution_milestones": milestones,
        }
        result_artifact = self.store.publish_json(
            (
                f"{request.artifact_directory}/"
                "distributed_simulation_result.json"
            ),
            result_payload,
            max_size_bytes=(
                self.protocol.resource_guardrails.maximum_artifact_size_bytes
            ),
        )

        report_created_at = _utc_now()
        milestones["validation_report_published"] = {
            "completed": True,
            "completed_at": report_created_at,
        }
        report_payload = {
            **self._header(
                request,
                role="distributed_validation_report",
                created_at=report_created_at,
                parents=[
                    self._parent(
                        result_artifact,
                        artifact_id=(
                            f"{request.run_id}:"
                            "distributed_simulation_result"
                        ),
                        role="distributed_simulation_result",
                    )
                ],
            ),
            "formal_evidence": request.formal_evidence,
            "status": structured_result.assessment.terminal_status,
            "qualification_status": (
                structured_result.assessment.qualification_status
            ),
            "partial": structured_result.observations.partial,
            "missing_metrics": [
                item.as_dict()
                for item in structured_result.observations.missing_metrics
            ],
            "observations": structured_result.observations.as_dict(),
            "assessment": structured_result.assessment.as_dict(),
            "execution_milestones": milestones,
            "scientific_adsorption_validation": False,
            "ground_state_assessed": False,
            "qpu_execution": False,
        }
        report_artifact = self.store.publish_json(
            (
                f"{request.artifact_directory}/"
                "distributed_validation_report.json"
            ),
            report_payload,
            max_size_bytes=(
                self.protocol.resource_guardrails.maximum_artifact_size_bytes
            ),
        )
        persistence_result = (
            self.persistence_callback(
                request,
                structured_result,
                milestones,
                result_artifact,
                report_artifact,
            )
            if self.persistence_callback is not None
            else None
        )
        return VersionedSimulationRun(
            structured_result=structured_result,
            result_artifact=result_artifact,
            validation_report_artifact=report_artifact,
            final_execution_milestones=milestones,
            persistence_result=persistence_result,
        )

    def _validate_authorization(
        self,
        request: VersionedSimulationRequest,
    ) -> None:
        authorization = self.protocol.authorization
        if request.execution_scope == "synthetic":
            if request.formal_evidence:
                raise VersionedOrchestrationError(
                    "Synthetic execution cannot create formal evidence."
                )
            if not authorization.synthetic_statevector_authorized:
                raise VersionedOrchestrationError(
                    "The protocol does not authorize synthetic execution."
                )
            return
        if request.execution_scope == "formal_v2":
            if not request.formal_evidence:
                raise VersionedOrchestrationError(
                    "Formal V2 execution must identify formal evidence."
                )
            if (
                authorization.fixture_only
                or not authorization.formal_4q_attempt_authorized
                or not self.allow_formal_execution
            ):
                raise VersionedOrchestrationError(
                    "A current independent authorization is required for formal V2."
                )
            return
        raise VersionedOrchestrationError("Unsupported execution scope.")

    def _header(
        self,
        request: VersionedSimulationRequest,
        *,
        role: str,
        created_at: str,
        parents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        contract = next(
            item
            for item in self.protocol.artifact_contract.artifacts
            if item.role == role
        )
        return {
            "artifact_type": role,
            "schema_version": contract.schema_version,
            "artifact_id": f"{request.run_id}:{role}",
            "run_id": request.run_id,
            "owner_user_id": request.owner_user_id,
            "protocol_id": self.protocol.protocol_id,
            "protocol_version": self.protocol.protocol_version,
            "protocol_sha256": self.protocol_sha256,
            "protocol_fixture_sha256": (
                self.protocol_sha256
                if request.execution_scope == "synthetic"
                else None
            ),
            "parents": parents,
            "created_at": created_at,
            "immutable": True,
            "execution_scope": request.execution_scope,
            "synthetic_only": request.execution_scope == "synthetic",
            "actual_distributed_hardware_execution": False,
        }

    @staticmethod
    def _parent(
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
