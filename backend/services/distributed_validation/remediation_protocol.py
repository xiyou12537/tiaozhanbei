from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SYNTHETIC_PROTOCOL_ID = "distributed_molecular_circuit_validation_synthetic"
SYNTHETIC_PROTOCOL_VERSION = "2.0.0-test-fixture"

FUTURE_ARTIFACT_FILENAMES = (
    "distributed_input_manifest.json",
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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HashSchemes(StrictModel):
    artifact: str
    qasm: str
    parameters: str
    ordered_pauli: str
    digest: Literal["sha256"]


class QualifyingInputs(StrictModel):
    owner_bound_lineage_required: bool
    immutable_qualification_required: bool
    qualification_recomputed_allowed: bool
    source_file_sha256_required: bool
    raw_qasm_sha256_required: bool
    canonical_circuit_sha256_required: bool
    parameter_sha256_required: bool
    ordered_pauli_payload_sha256_required: bool
    parameters_must_be_bound: bool


class CircuitRequirements(StrictModel):
    qasm_version: Literal["2.0"]
    gate_set: list[Literal["u3", "cx"]]
    classical_bits_allowed: bool
    measurements_allowed: bool
    conditions_allowed: bool
    global_phase_fidelity_invariant: bool
    qiskit_qubit_endian: Literal["little_endian"]
    pauli_label_qubit_zero_position: Literal["rightmost"]
    parameters_must_not_be_rebound: bool


class Partitioning(StrictModel):
    algorithm: Literal["deterministic_greedy_multistart_grid_v1"]
    partition_count: Literal[2]
    partition_ids: list[Literal[0, 1]]
    partition_numbering: Literal[
        "minimum_logical_qubit_ascending_then_zero_based"
    ]
    seed: int
    stochastic_behavior_allowed: bool
    num_starts_rule: Literal["min(15,qubit_count)"]
    b1_grid: list[int]
    b2_grid: list[int]
    alpha: float
    beta: float
    maximum_imbalance: int = Field(ge=0)
    candidate_tie_break: list[str]


class GateOrdering(StrictModel):
    scheme: Literal["disjoint-support-only-v1"]
    equivalence_infidelity_maximum: float = Field(gt=0)
    unsupported_commutation_fallback: Literal["fail"]


class Mapping(StrictModel):
    algorithm: Literal["minimum_cost_then_lexicographic_mapping_v1"]
    equal_cost_tie_break: Literal[
        "lexicographically_smallest_sorted_integer_partition_node_pairs"
    ]
    frozen_equal_cost_mapping: list[list[int]]
    networkx_iteration_order_is_semantic: bool


class Routing(StrictModel):
    route_first_operand_to_second_operand_node: bool
    carrier_type: Literal["existing_data_qubit"]
    carrier_order: Literal["execution_qubit_index_ascending"]
    carrier_must_not_be_gate_operand: bool
    carrier_must_be_unreserved: bool
    additional_ancilla_allowed: bool
    swap_decomposition: list[str]
    inverse_route_required: bool
    final_mapping_required: Literal["identity"]


class ReferenceEnergies(StrictModel):
    required_names: list[
        Literal[
            "e_classical_exact",
            "e_exact_pauli",
            "e_logical_vqe",
            "e_distributed",
        ]
    ]
    runtime_logical_energy_must_be_recomputed: bool
    optimizer_execution_allowed: bool
    identity_term_contains_energy_offset: bool
    add_constant_offset_at_runtime: bool


class Lifecycle(StrictModel):
    compilation_states: list[str]
    simulation_states: list[str]
    formal_attempt_limit: int = Field(ge=1)
    automatic_retry_allowed: bool
    result_artifacts_required_for_success: bool
    result_artifacts_required_for_failure: bool


class Ownership(StrictModel):
    owner_required_on_all_database_records: bool
    owner_required_on_all_artifacts: bool
    client_may_set_hardware_execution: bool
    actual_distributed_hardware_execution: bool
    cross_owner_reads_allowed: bool


class ArtifactContractEntry(StrictModel):
    order: int = Field(ge=1)
    role: str
    filename: str
    schema_version: int = Field(ge=1)
    owner: Literal["compilation", "simulation"]


class ArtifactContract(StrictModel):
    canonicalization_scheme: Literal["artifact-canonical-json-v1"]
    publish_mode: Literal["no_clobber"]
    full_parent_lineage_required: bool
    lineage_fields: list[
        Literal["artifact_id", "role", "relative_path", "sha256", "schema_version"]
    ]
    artifacts: list[ArtifactContractEntry]

    @model_validator(mode="after")
    def validate_frozen_artifacts(self) -> "ArtifactContract":
        expected_roles = (
            "distributed_input_manifest",
            "logical_circuit_snapshot",
            "partition_plan",
            "optimized_gate_order",
            "target_topology",
            "chip_mapping",
            "communication_route_plan",
            "distributed_executable",
            "distributed_simulation_result",
            "distributed_validation_report",
        )
        ordered = sorted(self.artifacts, key=lambda item: item.order)
        if tuple(item.order for item in ordered) != tuple(range(1, 11)):
            raise ValueError("Artifact order must be exactly 1..10.")
        if tuple(item.role for item in ordered) != expected_roles:
            raise ValueError("Artifact roles do not match the frozen contract.")
        if tuple(item.filename for item in ordered) != FUTURE_ARTIFACT_FILENAMES:
            raise ValueError("Artifact filenames do not match the frozen contract.")
        return self


class FailurePartialSchema(StrictModel):
    observations_always_returned: bool
    assessment_always_returned: bool
    missing_metrics_must_include_reason: bool
    infrastructure_failure_preserves_partial_observations: bool
    validation_failure_is_exception: bool
    failure_result_artifact_required: bool
    failure_report_artifact_required: bool
    partial_observations_may_grant_qualification: bool


class ExecutionMilestones(StrictModel):
    ordered_names: list[str]
    monotonic_true_only: bool
    timestamp_each_transition: bool
    distributed_execution_fact_milestone: str


class NumericalAlgorithms(StrictModel):
    particle_variance_algorithm: Literal["centered_second_moment_v1"]
    particle_variance_negative_roundoff_tolerance: float = Field(ge=0)
    fci_vs_exact_pauli_hartree: float = Field(gt=0)
    runtime_logical_vs_upstream_hartree: float = Field(gt=0)
    variational_lower_bound_hartree: float = Field(gt=0)
    logical_vs_exact_pauli_hartree: float = Field(gt=0)
    distributed_vs_exact_pauli_hartree: float = Field(gt=0)
    distributed_vs_logical_hartree: float = Field(gt=0)
    statevector_infidelity: float = Field(gt=0)
    statevector_normalization_error: float = Field(gt=0)
    energy_imaginary_absolute_hartree: float = Field(gt=0)
    particle_sector_expectation_error: float = Field(gt=0)
    particle_sector_variance: float = Field(gt=0)
    correlation_recovery_ratio_minimum: float = Field(ge=0, le=1)
    nonfinite_values_allowed: bool


class ExecutionSemantics(StrictModel):
    strategy: Literal["topology_aware_remote_swap_route_and_restore"]
    backend: Literal["qiskit.quantum_info.Statevector"]
    shots: Literal[0]
    statevector_dtype: Literal["complex128"]
    custom_remote_gate_allowed: bool
    additional_ancilla_allowed: bool
    inverse_route_required: bool
    final_mapping_required: Literal["identity"]


class Topology(StrictModel):
    name: str
    node_count: int = Field(ge=2)
    capacity_per_node: int = Field(ge=1)
    topology_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    client_override_allowed: bool


class ResourceGuardrails(StrictModel):
    maximum_expanded_gate_count: int = Field(gt=0)
    maximum_circuit_depth: int = Field(gt=0)
    maximum_artifact_size_bytes: int = Field(gt=0)
    maximum_artifact_total_bytes: int = Field(gt=0)
    maximum_qasm_size_bytes: int = Field(gt=0)
    minimum_available_disk_bytes: int = Field(gt=0)
    minimum_available_memory_bytes: int = Field(gt=0)
    compilation_wall_seconds: int = Field(gt=0)
    simulation_wall_seconds: int = Field(gt=0)
    total_wall_seconds: int = Field(gt=0)
    rss_limit_bytes: int = Field(gt=0)


class SoftwareEnvironment(StrictModel):
    python: str
    python_distribution: str
    qiskit: str
    qiskit_terra: str
    numpy: str
    networkx: str
    sqlalchemy: str
    alembic: str
    fastapi: str
    pydantic: str


class ProtocolAuthorization(StrictModel):
    fixture_only: bool
    formal_protocol_artifact_creation_allowed: bool
    formal_4q_attempt_authorized: bool
    stage_c_authorized: bool
    synthetic_statevector_authorized: bool
    temporary_database_only: bool
    temporary_artifact_root_only: bool


class RemediationProtocol(StrictModel):
    schema_name: Literal["distributed-molecular-circuit-validation-protocol-v2"]
    schema_version: Literal[2]
    protocol_id: str = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    authorization: ProtocolAuthorization
    hash_schemes: HashSchemes
    qualifying_inputs: QualifyingInputs
    circuit_requirements: CircuitRequirements
    partitioning: Partitioning
    gate_ordering: GateOrdering
    mapping: Mapping
    routing: Routing
    reference_energies: ReferenceEnergies
    lifecycle: Lifecycle
    ownership: Ownership
    artifact_contract: ArtifactContract
    failure_partial_schema: FailurePartialSchema
    execution_milestones: ExecutionMilestones
    numerical_algorithms: NumericalAlgorithms
    execution_semantics: ExecutionSemantics
    topology: Topology
    resource_guardrails: ResourceGuardrails
    software_environment: SoftwareEnvironment
    scientific_limits: dict[str, bool | int]


VersionedValidationProtocol = RemediationProtocol


def build_synthetic_protocol_fixture() -> dict[str, Any]:
    """Build the complete fixture-only protocol; this never writes an Artifact."""
    artifact_roles = (
        "distributed_input_manifest",
        "logical_circuit_snapshot",
        "partition_plan",
        "optimized_gate_order",
        "target_topology",
        "chip_mapping",
        "communication_route_plan",
        "distributed_executable",
        "distributed_simulation_result",
        "distributed_validation_report",
    )
    payload: dict[str, Any] = {
        "schema_name": "distributed-molecular-circuit-validation-protocol-v2",
        "schema_version": 2,
        "protocol_id": SYNTHETIC_PROTOCOL_ID,
        "protocol_version": SYNTHETIC_PROTOCOL_VERSION,
        "authorization": {
            "fixture_only": True,
            "formal_protocol_artifact_creation_allowed": False,
            "formal_4q_attempt_authorized": False,
            "stage_c_authorized": False,
            "synthetic_statevector_authorized": True,
            "temporary_database_only": True,
            "temporary_artifact_root_only": True,
        },
        "hash_schemes": {
            "artifact": "artifact-canonical-json-v1",
            "qasm": "qasm2-canonical-circuit-v1",
            "parameters": "parameter-ieee754-f64-le-c-v1",
            "ordered_pauli": "ordered-pauli-payload-v1",
            "digest": "sha256",
        },
        "qualifying_inputs": {
            "owner_bound_lineage_required": True,
            "immutable_qualification_required": True,
            "qualification_recomputed_allowed": False,
            "source_file_sha256_required": True,
            "raw_qasm_sha256_required": True,
            "canonical_circuit_sha256_required": True,
            "parameter_sha256_required": True,
            "ordered_pauli_payload_sha256_required": True,
            "parameters_must_be_bound": True,
        },
        "circuit_requirements": {
            "qasm_version": "2.0",
            "gate_set": ["u3", "cx"],
            "classical_bits_allowed": False,
            "measurements_allowed": False,
            "conditions_allowed": False,
            "global_phase_fidelity_invariant": True,
            "qiskit_qubit_endian": "little_endian",
            "pauli_label_qubit_zero_position": "rightmost",
            "parameters_must_not_be_rebound": True,
        },
        "partitioning": {
            "algorithm": "deterministic_greedy_multistart_grid_v1",
            "partition_count": 2,
            "partition_ids": [0, 1],
            "partition_numbering": (
                "minimum_logical_qubit_ascending_then_zero_based"
            ),
            "seed": 20260728,
            "stochastic_behavior_allowed": False,
            "num_starts_rule": "min(15,qubit_count)",
            "b1_grid": list(range(1, 21)),
            "b2_grid": list(range(1, 21)),
            "alpha": 3.0,
            "beta": 1.0,
            "maximum_imbalance": 1,
            "candidate_tie_break": [
                "estimated_teleportations",
                "global_gate_count",
                "cross_partition_gate_count",
                "load_difference",
                "partition_signature",
                "b1",
                "b2",
                "seed_qubit",
            ],
        },
        "gate_ordering": {
            "scheme": "disjoint-support-only-v1",
            "equivalence_infidelity_maximum": 1e-12,
            "unsupported_commutation_fallback": "fail",
        },
        "mapping": {
            "algorithm": "minimum_cost_then_lexicographic_mapping_v1",
            "equal_cost_tie_break": (
                "lexicographically_smallest_sorted_integer_partition_node_pairs"
            ),
            "frozen_equal_cost_mapping": [[0, 0], [1, 1]],
            "networkx_iteration_order_is_semantic": False,
        },
        "routing": {
            "route_first_operand_to_second_operand_node": True,
            "carrier_type": "existing_data_qubit",
            "carrier_order": "execution_qubit_index_ascending",
            "carrier_must_not_be_gate_operand": True,
            "carrier_must_be_unreserved": True,
            "additional_ancilla_allowed": False,
            "swap_decomposition": ["cx(a,b)", "cx(b,a)", "cx(a,b)"],
            "inverse_route_required": True,
            "final_mapping_required": "identity",
        },
        "reference_energies": {
            "required_names": [
                "e_classical_exact",
                "e_exact_pauli",
                "e_logical_vqe",
                "e_distributed",
            ],
            "runtime_logical_energy_must_be_recomputed": True,
            "optimizer_execution_allowed": False,
            "identity_term_contains_energy_offset": True,
            "add_constant_offset_at_runtime": False,
        },
        "lifecycle": {
            "compilation_states": [
                "synthetic_compilation_created",
                "distributed_executable_ready",
                "synthetic_compilation_failed",
            ],
            "simulation_states": [
                "synthetic_simulation_running",
                "synthetic_completed",
                "synthetic_acceptance_not_met",
                "synthetic_simulation_failed",
            ],
            "formal_attempt_limit": 1,
            "automatic_retry_allowed": False,
            "result_artifacts_required_for_success": True,
            "result_artifacts_required_for_failure": True,
        },
        "ownership": {
            "owner_required_on_all_database_records": True,
            "owner_required_on_all_artifacts": True,
            "client_may_set_hardware_execution": False,
            "actual_distributed_hardware_execution": False,
            "cross_owner_reads_allowed": False,
        },
        "artifact_contract": {
            "canonicalization_scheme": "artifact-canonical-json-v1",
            "publish_mode": "no_clobber",
            "full_parent_lineage_required": True,
            "lineage_fields": [
                "artifact_id",
                "role",
                "relative_path",
                "sha256",
                "schema_version",
            ],
            "artifacts": [
                {
                    "order": index,
                    "role": role,
                    "filename": filename,
                    "schema_version": 2,
                    "owner": "compilation" if index <= 8 else "simulation",
                }
                for index, (role, filename) in enumerate(
                    zip(artifact_roles, FUTURE_ARTIFACT_FILENAMES, strict=True),
                    start=1,
                )
            ],
        },
        "failure_partial_schema": {
            "observations_always_returned": True,
            "assessment_always_returned": True,
            "missing_metrics_must_include_reason": True,
            "infrastructure_failure_preserves_partial_observations": True,
            "validation_failure_is_exception": False,
            "failure_result_artifact_required": True,
            "failure_report_artifact_required": True,
            "partial_observations_may_grant_qualification": False,
        },
        "execution_milestones": {
            "ordered_names": [
                "simulation_started",
                "logical_statevector_started",
                "logical_statevector_completed",
                "distributed_statevector_started",
                "distributed_statevector_completed",
                "observable_evaluation_completed",
                "sector_observation_completed",
                "assessment_completed",
                "result_artifact_published",
                "validation_report_published",
            ],
            "monotonic_true_only": True,
            "timestamp_each_transition": True,
            "distributed_execution_fact_milestone": (
                "distributed_statevector_completed"
            ),
        },
        "numerical_algorithms": {
            "particle_variance_algorithm": "centered_second_moment_v1",
            "particle_variance_negative_roundoff_tolerance": 1e-13,
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
            "correlation_recovery_ratio_minimum": 0.90,
            "nonfinite_values_allowed": False,
        },
        "execution_semantics": {
            "strategy": "topology_aware_remote_swap_route_and_restore",
            "backend": "qiskit.quantum_info.Statevector",
            "shots": 0,
            "statevector_dtype": "complex128",
            "custom_remote_gate_allowed": False,
            "additional_ancilla_allowed": False,
            "inverse_route_required": True,
            "final_mapping_required": "identity",
        },
        "topology": {
            "name": "synthetic-linear-2-capacity-2",
            "node_count": 2,
            "capacity_per_node": 2,
            "topology_sha256": (
                "17643382379161456bb9fde6cbfe792798c1bd8485f9a828dede92b91c9d53cd"
            ),
            "client_override_allowed": False,
        },
        "resource_guardrails": {
            "maximum_expanded_gate_count": 600,
            "maximum_circuit_depth": 600,
            "maximum_artifact_size_bytes": 8 * 1024 * 1024,
            "maximum_artifact_total_bytes": 32 * 1024 * 1024,
            "maximum_qasm_size_bytes": 1024 * 1024,
            "minimum_available_disk_bytes": 2 * 1024 * 1024 * 1024,
            "minimum_available_memory_bytes": 2 * 1024 * 1024 * 1024,
            "compilation_wall_seconds": 60,
            "simulation_wall_seconds": 120,
            "total_wall_seconds": 180,
            "rss_limit_bytes": 1024 * 1024 * 1024,
        },
        "software_environment": {
            "python": "3.12.4",
            "python_distribution": "Anaconda",
            "qiskit": "0.46.3",
            "qiskit_terra": "0.46.3",
            "numpy": "2.4.6",
            "networkx": "3.6.1",
            "sqlalchemy": "2.0.50",
            "alembic": "1.18.5",
            "fastapi": "0.133.1",
            "pydantic": "2.13.4",
        },
        "scientific_limits": {
            "shots": 0,
            "ground_state_assessed": False,
            "scientific_adsorption_validation": False,
            "qpu_execution": False,
            "formal_evidence": False,
        },
    }
    return RemediationProtocol.model_validate(payload).model_dump(mode="python")


def validate_synthetic_protocol_fixture(payload: dict[str, Any]) -> RemediationProtocol:
    """Validate one complete fixture-only remediation protocol."""
    protocol = RemediationProtocol.model_validate(payload)
    if (
        protocol.protocol_id != SYNTHETIC_PROTOCOL_ID
        or protocol.protocol_version != SYNTHETIC_PROTOCOL_VERSION
        or not protocol.authorization.fixture_only
        or protocol.authorization.formal_protocol_artifact_creation_allowed
        or protocol.authorization.formal_4q_attempt_authorized
        or protocol.authorization.stage_c_authorized
        or not protocol.authorization.synthetic_statevector_authorized
        or not protocol.authorization.temporary_database_only
        or not protocol.authorization.temporary_artifact_root_only
    ):
        raise ValueError(
            "Synthetic fixture authorization does not match the B-R scope."
        )
    return protocol


def remediation_protocol_json_schema() -> dict[str, Any]:
    """Return the complete JSON Schema without creating a protocol Artifact."""
    return RemediationProtocol.model_json_schema()
