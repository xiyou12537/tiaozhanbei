from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AtomGeometry(BaseModel):
    element: str = Field(..., min_length=1, max_length=2, pattern=r"^[A-Z][a-z]?$")
    coordinates_angstrom: tuple[float, float, float]

    @field_validator("coordinates_angstrom")
    @classmethod
    def coordinates_must_be_finite(cls, value: tuple[float, float, float]) -> tuple[float, float, float]:
        if any(not math.isfinite(coordinate) for coordinate in value):
            raise ValueError("原子坐标必须是有限数值。")
        return value


class VqeOptions(BaseModel):
    ansatz_layers: int = Field(default=1, ge=1, le=4)
    max_iterations: int = Field(default=80, ge=1, le=500)
    convergence_tolerance: float = Field(default=0.0001, gt=0)
    shots: int = Field(default=1024, ge=1, le=1_000_000)


class TopologyEdge(BaseModel):
    source: int = Field(..., ge=0, le=2)
    target: int = Field(..., ge=0, le=2)

    @model_validator(mode="after")
    def reject_self_loop(self):
        if self.source == self.target:
            raise ValueError("虚拟节点拓扑不允许自环。")
        return self


class PartitionOptions(BaseModel):
    partition_count: int = Field(default=2, ge=2, le=3)
    partition_strategy: Literal["sequential_greedy"] = "sequential_greedy"
    inter_qpu_topology: list[TopologyEdge] | None = Field(default=None, min_length=1, max_length=3)
    topology_edges: list[TopologyEdge] | None = Field(default=None, min_length=1, max_length=3)
    virtual_qpus: list["VirtualQpuRequest"] | None = Field(default=None, min_length=2, max_length=3)
    initial_layout: Literal["identity"] = "identity"
    routing_method: Literal["shortest_path_swap"] = "shortest_path_swap"


class PhysicalCouplingEdge(BaseModel):
    source: int = Field(..., ge=0, le=11)
    target: int = Field(..., ge=0, le=11)

    @model_validator(mode="after")
    def reject_self_loop(self):
        if self.source == self.target:
            raise ValueError("物理耦合拓扑不允许自环。")
        return self


class VirtualQpuRequest(BaseModel):
    virtual_qpu_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    physical_qubit_count: int = Field(..., ge=1, le=12)
    physical_coupling_map: list[PhysicalCouplingEdge] = Field(default_factory=list, max_length=66)


class MoleculeWorkflowRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "molecule_name": "H2",
                    "geometry": [
                        {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.0]},
                        {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.735]},
                    ],
                    "charge": 0,
                    "spin_multiplicity": 1,
                    "basis_set": "sto-3g",
                    "mapping_method": "jordan_wigner",
                    "active_space_orbitals": 2,
                    "pauli_coefficient_cutoff": 0.000001,
                    "vqe": {
                        "ansatz_layers": 1,
                        "max_iterations": 80,
                        "convergence_tolerance": 0.0001,
                        "shots": 1024,
                    },
                    "partition": {
                        "partition_count": 2,
                        "partition_strategy": "sequential_greedy",
                        "inter_qpu_topology": [{"source": 0, "target": 1}],
                        "virtual_qpus": [
                            {"virtual_qpu_id": "T1", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
                            {"virtual_qpu_id": "T2", "physical_qubit_count": 4, "physical_coupling_map": [{"source": 2, "target": 3}]},
                        ],
                        "initial_layout": "identity",
                        "routing_method": "shortest_path_swap",
                    },
                    "execution_mode": "logical_virtual_qpu",
                }
            ]
        }
    )

    molecule_name: str = Field(..., min_length=1, max_length=120)
    geometry: list[AtomGeometry] = Field(..., min_length=1, max_length=10)
    charge: int = Field(default=0, ge=-10, le=10)
    spin_multiplicity: int = Field(default=1, ge=1, le=11)
    basis_set: str = Field(default="sto-3g", min_length=2, max_length=64, pattern=r"^[A-Za-z0-9+*(),._-]+$")
    mapping_method: Literal["jordan_wigner"] = "jordan_wigner"
    active_space_orbitals: int | None = Field(default=None, ge=1, le=6)
    pauli_coefficient_cutoff: float = Field(default=0.000001, gt=0, le=0.01)
    vqe: VqeOptions = Field(default_factory=VqeOptions)
    partition: PartitionOptions = Field(default_factory=PartitionOptions)
    execution_mode: Literal["logical_virtual_qpu"] = "logical_virtual_qpu"


class DeploymentArchitecture(BaseModel):
    architecture_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    architecture_name: str | None = Field(default=None, min_length=1, max_length=120)
    partition: PartitionOptions


class MolecularStudyRequest(MoleculeWorkflowRequest):
    architectures: list[DeploymentArchitecture] = Field(..., min_length=3, max_length=12)

    @model_validator(mode="after")
    def distinct_architecture_ids(self):
        identifiers = [item.architecture_id for item in self.architectures]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("architecture_id must be unique within a study.")
        return self


class CalculationStage(BaseModel):
    stage: str
    status: Literal["running", "completed", "failed"]
    started_at: str
    completed_at: str | None
    duration_ms: float | None
    details: dict


class MoleculeSummary(BaseModel):
    molecule_name: str
    geometry: list[AtomGeometry]
    atom_count: int
    charge: int
    spin_multiplicity: int
    basis_set: str
    geometry_optimization_performed: bool


class ActiveSpaceResult(BaseModel):
    active_electrons: int
    active_orbitals: int
    orbital_indices: list[int]
    orbital_energies_hartree: list[float]
    selection_method: str


class PauliTerm(BaseModel):
    pauli_string: str
    coefficient: float


class HamiltonianResult(BaseModel):
    mapping_method: str
    fallback_reason: str | None
    qubit_count: int
    qubit_count_before_tapering: int
    z2_tapering_applied: bool
    pauli_term_count: int
    pauli_terms: list[PauliTerm]
    coefficient_cutoff: float
    truncation_error_estimate: float


class VqeIteration(BaseModel):
    iteration: int
    parameters: list[float]
    energy_hartree: float
    energy_uncertainty_hartree: float


class VqeOptimizerDiagnostics(BaseModel):
    scipy_success: bool
    scipy_status: int
    scipy_message: str
    nfev: int
    termination_reason: str
    best_iteration: int
    initial_energy_hartree: float
    final_energy_hartree: float
    recent_energy_changes_hartree: list[float]


class VqeResult(BaseModel):
    ansatz: str
    ansatz_version: str | None = None
    simulator_version: str | None = None
    optimizer: str
    initial_state: str
    initial_occupied_qubits: list[int]
    qasm: str
    converged: bool
    optimizer_diagnostics: VqeOptimizerDiagnostics
    best_parameters: list[float]
    iteration_count: int
    iteration_history: list[VqeIteration]


class PartitionAssignment(BaseModel):
    partition_id: str
    qubits: list[int]


class PartitionSchemeResult(BaseModel):
    method: str
    strategy: Literal["sequential_greedy"] | None = None
    partition_count: int
    partitions: list[PartitionAssignment]
    teleportations: int
    global_gate_count: int
    parameters: dict


class VirtualNodeAssignment(BaseModel):
    virtual_node_id: str
    partition_id: str
    qubits: list[int]


class LogicalPhysicalLayout(BaseModel):
    logical_qubit: int
    physical_qubit: int


class RoutedGate(BaseModel):
    gate: Literal["x", "h", "s", "sdg", "ry", "rz", "cx", "swap"]
    physical_qubits: list[int]


class TwoQubitRoutingEvidence(BaseModel):
    partition_id: str
    virtual_qpu_id: str
    gate_index: int
    gate: Literal["cx"]
    logical_qubits: list[int]
    initial_physical_qubits: list[int]
    final_physical_qubits: list[int]
    routing_status: Literal["direct", "routed"]
    path: list[int]
    swap_positions: list[int]
    swap_path: list[list[int]]


class PartitionChipRouting(BaseModel):
    partition_id: str
    virtual_qpu_id: str
    logical_qubits: list[int]
    physical_qubit_count: int
    physical_coupling_map: list[PhysicalCouplingEdge]
    logical_to_physical_initial: list[LogicalPhysicalLayout]
    logical_to_physical_final: list[LogicalPhysicalLayout]
    original_operation_count: int
    routed_operation_count: int
    original_two_qubit_operation_count: int
    routed_two_qubit_operation_count: int
    routed_gate_sequence: list[RoutedGate]
    two_qubit_routing_evidence: list[TwoQubitRoutingEvidence]


class IntraChipRoutingCost(BaseModel):
    abstract_swap_count: int
    routed_two_qubit_operation_count: int
    native_two_qubit_gate_equivalent_count: int


class RoutedExecutionPlanStep(BaseModel):
    execution_index: int
    original_gate_index: int
    operation: Literal["x", "h", "s", "sdg", "ry", "rz", "cx", "swap"]
    scope: Literal["intra_qpu", "inter_qpu"]
    partition_ids: list[str]
    virtual_qpu_ids: list[str]
    logical_qubits: list[int]
    physical_qubits: list[int]
    physical_edge_is_valid: bool | None
    logical_to_physical_layout_before: dict[str, list[LogicalPhysicalLayout]]
    logical_to_physical_layout_after: dict[str, list[LogicalPhysicalLayout]]
    angle: float | None = None


class CommunicationEvent(BaseModel):
    gate_index: int
    gate: str
    control_qubit: int
    target_qubit: int
    source_partition_id: str
    target_partition_id: str
    source_virtual_node_id: str
    target_virtual_node_id: str


class DistributionResult(BaseModel):
    backend_type: Literal["simulator"]
    capability_level: Literal["logical_virtual_qpu"]
    is_real_qpu: Literal[False]
    partition_scheme: PartitionSchemeResult
    virtual_node_mapping: list[VirtualNodeAssignment]
    topology_edges: list[TopologyEdge]
    mapping_cost: float
    inter_qpu_topology: list[TopologyEdge] | None = None
    partition_chip_routing: list[PartitionChipRouting] | None = None
    two_qubit_routing_evidence: list[TwoQubitRoutingEvidence] | None = None
    routed_execution_plan: list[RoutedExecutionPlanStep] | None = None
    original_two_qubit_operation_count: int | None = None
    routed_two_qubit_operation_count: int | None = None
    intra_chip_routing_cost: IntraChipRoutingCost | None = None
    cross_partition_communication_count: int
    communication_events: list[CommunicationEvent]
    actual_partition_consumption: Literal[True]
    actual_routed_plan_consumption: bool | None = None
    final_logical_to_physical_layout: dict[str, list[LogicalPhysicalLayout]] | None = None
    simulation_strategy: str
    state_norm: float


class EnergyComparison(BaseModel):
    unpartitioned_benchmark_energy_hartree: float
    distributed_simulation_energy_hartree: float
    absolute_error_hartree: float


class ValidationIssue(BaseModel):
    code: Literal["vqe_not_converged"]
    stage: Literal["vqe_optimization"]
    iteration_count: int
    message: str


class OptimizerValidation(BaseModel):
    status: Literal["passed", "needs_review"]
    optimizer: str
    success: bool
    termination_reason: str
    nfev: int


class ScientificValidationIssue(BaseModel):
    code: str
    message: str


class ScientificValidation(BaseModel):
    status: Literal["passed", "needs_review", "failed"]
    target_electron_count: int
    particle_number_expectation: float | None = None
    particle_number_variance: float | None = None
    hf_reference_energy_hartree: float | None = None
    hf_determinant_energy_hartree: float | None = None
    zero_parameter_energy_hartree: float | None = None
    first_objective_energy_hartree: float | None = None
    hf_reference_error_hartree: float | None = None
    fci_reference_energy_hartree: float | None = None
    exact_qubit_ground_energy_hartree: float | None = None
    vqe_fci_error_hartree: float | None = None
    chemical_accuracy_threshold_hartree: float
    chemical_accuracy_reached: bool | None = None
    variational_bound_satisfied: bool | None = None
    minimum_consistency_status: Literal["passed", "needs_review"] | None = None
    core_energy_hartree: float | None = None
    active_electrons: int
    active_orbitals: list[int]
    qubit_ordering: str
    spin_square: float | None = None
    expected_spin_square: float | None = None
    spin_contamination: float | None = None
    issues: list[ScientificValidationIssue] = Field(default_factory=list)


class DeploymentValidation(BaseModel):
    status: Literal["passed", "needs_review"]
    distributed_execution_error_hartree: float | None = None
    actual_routed_plan_consumption: bool | None = None
    state_norm: float | None = None


StudyStatus = Literal["queued", "running", "completed", "failed"]
EvaluationStatus = Literal["queued", "running", "completed", "failed"]


class MolecularStudyErrorDetail(BaseModel):
    """A stable business error payload for molecular-study endpoints."""

    code: str
    message: str
    stage: str | None = None
    study_id: str | None = None
    molecular_problem_id: str | None = None
    architecture_id: str | None = None


class MolecularStudyErrorResponse(BaseModel):
    detail: MolecularStudyErrorDetail


class MolecularProblemVqeResult(VqeResult):
    unpartitioned_energy_hartree: float | None = None


class FciReferenceResult(BaseModel):
    status: Literal["available", "unavailable", "not_configured"]
    method: str | None = None
    energy_hartree: float | None = None
    message: str | None = None


class MolecularProblemResult(BaseModel):
    """The reusable PySCF/Hamiltonian/VQE calculation of a molecular study.

    While a study is queued or running this retains its shape and uses null
    values for results that have not been produced yet.
    """

    molecular_problem_id: str
    status: StudyStatus
    stages: list[CalculationStage] = Field(default_factory=list)
    molecule: MoleculeSummary | None = None
    hf_energy_hartree: float | None = None
    active_space: ActiveSpaceResult | None = None
    hamiltonian: HamiltonianResult | None = None
    vqe: MolecularProblemVqeResult | None = None
    fci_reference: FciReferenceResult
    vqe_fci_scientific_error_hartree: float | None = None
    optimizer_validation: OptimizerValidation | None = None
    scientific_validation: ScientificValidation | None = None
    hamiltonian_builder_version: str | None = None
    scientific_validation_version: str | None = None


class DeploymentFailureReason(BaseModel):
    code: str
    message: str
    stage: str | None = None


class DeploymentPartitionSummary(BaseModel):
    partition_count: int
    partition_sizes: list[int]
    partitions: list[PartitionAssignment]


class DeploymentArchitectureResult(BaseModel):
    inter_qpu_topology: list[TopologyEdge]
    virtual_qpus: list[VirtualQpuRequest]
    initial_layout: Literal["identity"]
    routing_method: Literal["shortest_path_swap"]


class DeploymentMetrics(BaseModel):
    abstract_swap_count: int
    cross_partition_communication_count: int
    original_operation_count: int
    routed_operation_count: int
    original_two_qubit_operation_count: int
    routed_two_qubit_operation_count: int
    native_two_qubit_gate_equivalent_count: int


class DeploymentEnergyValidation(BaseModel):
    unpartitioned_vqe_energy_hartree: float
    distributed_simulation_energy_hartree: float
    distributed_execution_error_hartree: float


class DeploymentEvaluationResult(BaseModel):
    """One architecture's deployment outcome.

    A capacity/topology rejection is a completed evaluation with
    ``is_deployable=false``. A runtime error is ``failed`` with a null
    deployability decision. Neither outcome alone makes the parent study fail.
    """

    evaluation_id: str
    architecture_id: str
    architecture_name: str
    status: EvaluationStatus
    is_deployable: bool | None = None
    failure_reason: DeploymentFailureReason | None = None
    partition_summary: DeploymentPartitionSummary | None = None
    architecture: DeploymentArchitectureResult
    metrics: DeploymentMetrics | None = None
    energy_validation: DeploymentEnergyValidation | None = None
    distribution: DistributionResult | None = None


class MolecularStudySummary(BaseModel):
    total_evaluation_count: int
    completed_evaluation_count: int
    deployable_evaluation_count: int
    non_deployable_evaluation_count: int
    failed_evaluation_count: int


class MolecularStudyResult(BaseModel):
    molecular_problem: MolecularProblemResult
    deployment_evaluations: list[DeploymentEvaluationResult]
    summary: MolecularStudySummary


class MolecularStudyAcceptedResponse(BaseModel):
    study_id: str
    molecular_problem_id: str
    problem_id: str | None = Field(default=None, deprecated=True)
    status: Literal["queued"]
    current_stage: Literal["queued"]
    created_at: str
    started_at: None = None
    completed_at: None = None
    completed_evaluation_count: Literal[0]
    total_evaluation_count: int
    error: None = None


class MolecularStudyResponse(BaseModel):
    """Persisted state of an asynchronous molecular deployment study.

    Poll while status is queued or running; stop while completed or failed. A
    running study returns a stable partial ``result`` skeleton, and a completed
    study can contain both deployable and non-deployable architecture results.
    """

    study_id: str
    molecular_problem_id: str
    problem_id: str | None = Field(default=None, deprecated=True)
    status: StudyStatus
    current_stage: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    completed_evaluation_count: int
    total_evaluation_count: int
    result: MolecularStudyResult | None = Field(
        default=None,
        description="Stable partial skeleton while queued/running; complete result when completed."
    )
    error: MolecularStudyErrorDetail | None = None


class BondScanOptions(BaseModel):
    start_distance_angstrom: float = Field(..., ge=0.5, le=5.0)
    end_distance_angstrom: float = Field(..., ge=0.5, le=5.0)
    point_count: int = Field(..., ge=2, le=16)

    @model_validator(mode="after")
    def valid_scan_range(self):
        if self.end_distance_angstrom <= self.start_distance_angstrom:
            raise ValueError("end_distance_angstrom must be greater than start_distance_angstrom.")
        return self


class BondScanChemistryOptions(BaseModel):
    charge: int = Field(default=0, ge=-10, le=10)
    spin_multiplicity: int = Field(default=1, ge=1, le=11)
    basis_set: Literal["sto-3g"] = "sto-3g"
    active_space_orbitals: int = Field(default=2, ge=1, le=6)
    pauli_coefficient_cutoff: float = Field(default=0.000001, gt=0, le=0.01)
    vqe: VqeOptions = Field(default_factory=VqeOptions)


class MolecularBondScanRequest(BaseModel):
    molecule_type: Literal["LiH"] = "LiH"
    scan: BondScanOptions
    chemistry: BondScanChemistryOptions = Field(default_factory=BondScanChemistryOptions)
    deployment_architectures: list[DeploymentArchitecture] = Field(..., min_length=3, max_length=12)

    @model_validator(mode="after")
    def distinct_deployment_architecture_ids(self):
        identifiers = [item.architecture_id for item in self.deployment_architectures]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("architecture_id must be unique within a bond scan.")
        return self


class BondScanFciReference(BaseModel):
    status: Literal["available", "unavailable", "not_configured"]
    method: str | None = None
    energy_hartree: float | None = None
    message: str | None = None


class MolecularBondScanPoint(BaseModel):
    point_index: int
    distance_angstrom: float
    status: StudyStatus
    validation_status: Literal["passed", "needs_review"] | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    optimizer_validation: OptimizerValidation | None = None
    scientific_validation: ScientificValidation | None = None
    deployment_validation: DeploymentValidation | None = None
    molecular_problem_id: str | None = None
    hf_energy_hartree: float | None = None
    vqe_energy_hartree: float | None = None
    vqe_converged: bool | None = None
    optimizer_diagnostics: VqeOptimizerDiagnostics | None = None
    fci_reference: BondScanFciReference
    vqe_fci_scientific_error_hartree: float | None = None
    qubit_count: int | None = None
    pauli_term_count: int | None = None
    qasm: str | None = None
    stages: list[CalculationStage] = Field(default_factory=list)
    error: MolecularBondScanErrorDetail | None = None


class DiscreteEnergyMinimum(BaseModel):
    point_index: int
    distance_angstrom: float
    energy_hartree: float
    minimum_at_boundary: bool
    message: str | None = None


class MolecularBondScanSummary(BaseModel):
    issues: list[str] = Field(default_factory=list)
    minimum_at_boundary: bool = False


class MolecularBondScanResult(BaseModel):
    points: list[MolecularBondScanPoint]
    hf_discrete_minimum: DiscreteEnergyMinimum | None = None
    vqe_discrete_minimum: DiscreteEnergyMinimum | None = None
    scientific_vqe_discrete_minimum: DiscreteEnergyMinimum | None = None
    engineering_only_deployment: bool | None = Field(
        default=None,
        description="Null until deployment selection is known, including legacy results that predate this evidence.",
    )
    fci_discrete_minimum: DiscreteEnergyMinimum | None = None
    deployment_reference_point_index: int | None = None
    deployment_study_id: str | None = None
    deployment_result: list[DeploymentEvaluationResult] | None = None
    summary: MolecularBondScanSummary


class MolecularBondScanAcceptedResponse(BaseModel):
    scan_id: str
    status: StudyStatus
    current_stage: str
    created_at: str
    total_point_count: int


class MolecularBondScanResponse(BaseModel):
    scan_id: str
    molecule_type: Literal["LiH"]
    status: StudyStatus
    current_stage: str
    execution_mode: Literal["logical_virtual_qpu"]
    is_real_qpu: Literal[False]
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    total_point_count: int
    queued_point_count: int
    running_point_count: int
    completed_point_count: int
    failed_point_count: int
    needs_review_point_count: int
    current_point_index: int | None = None
    result: MolecularBondScanResult | None = None
    error: MolecularBondScanErrorDetail | None = None


class MolecularBondScanErrorDetail(BaseModel):
    """Stable non-sensitive business error payload for LiH bond scans."""

    code: str
    message: str
    stage: str | None = None
    scan_id: str | None = None
    point_index: int | None = None
    molecular_problem_id: str | None = None


class MolecularBondScanErrorResponse(BaseModel):
    detail: MolecularBondScanErrorDetail


class MolecularBondScanCapabilitiesResponse(BaseModel):
    supported_molecule_types: list[Literal["LiH"]]
    distance_range_angstrom: tuple[float, float]
    minimum_point_count: int
    maximum_point_count: int
    supported_basis_sets: list[Literal["sto-3g"]]
    active_space_orbital_range: tuple[int, int]
    fci_supported: bool
    deployment_architecture_count_range: tuple[int, int]
    execution_mode: Literal["logical_virtual_qpu"]
    is_real_qpu: Literal[False]


SUCCESS_RESPONSE_EXAMPLE = {
    "workflow_id": "molwf_8c1c4ceff69049aa9bc3d9f582a1a9c7",
    "status": "completed",
    "current_stage": "completed",
    "validation_status": "passed",
    "validation_issues": [],
    "execution_mode": "logical_virtual_qpu",
    "is_real_qpu": False,
    "molecule": {
        "molecule_name": "H2",
        "geometry": [
            {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.0]},
            {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.735]},
        ],
        "atom_count": 2,
        "charge": 0,
        "spin_multiplicity": 1,
        "basis_set": "sto-3g",
        "geometry_optimization_performed": False,
    },
    "stages": [
        {
            "stage": "input_validation",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00+00:00",
            "completed_at": "2026-08-05T01:00:00.001000+00:00",
            "duration_ms": 1.0,
            "details": {"atom_count": 2, "geometry_optimization_performed": False},
        },
        {
            "stage": "electronic_structure",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00.002000+00:00",
            "completed_at": "2026-08-05T01:00:00.102000+00:00",
            "duration_ms": 100.0,
            "details": {"method_name": "RHF/sto-3g", "hf_total_energy_hartree": -1.1167, "candidate_count": 1},
        },
        {
            "stage": "active_space_selection",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00.103000+00:00",
            "completed_at": "2026-08-05T01:00:00.104000+00:00",
            "duration_ms": 1.0,
            "details": {"active_electrons": 2, "active_orbitals": 2, "orbital_indices": [0, 1], "orbital_energies_hartree": [-0.58, 0.67], "selection_method": "requested_candidate"},
        },
        {
            "stage": "fermionic_hamiltonian",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00.105000+00:00",
            "completed_at": "2026-08-05T01:00:00.205000+00:00",
            "duration_ms": 100.0,
            "details": {"core_energy_hartree": 0.7199, "active_orbitals": 2},
        },
        {
            "stage": "qubit_mapping",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00.206000+00:00",
            "completed_at": "2026-08-05T01:00:00.216000+00:00",
            "duration_ms": 10.0,
            "details": {"mapping_method": "jordan_wigner", "qubit_count": 4, "pauli_term_count": 3},
        },
        {
            "stage": "vqe_optimization",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00.217000+00:00",
            "completed_at": "2026-08-05T01:00:00.317000+00:00",
            "duration_ms": 100.0,
            "details": {"iteration_count": 2, "converged": True, "unpartitioned_energy_hartree": -1.12},
        },
        {
            "stage": "circuit_partitioning",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00.318000+00:00",
            "completed_at": "2026-08-05T01:00:00.328000+00:00",
            "duration_ms": 10.0,
            "details": {"partition_count": 2, "teleportations": 1, "global_gates": 1},
        },
        {
            "stage": "virtual_node_mapping",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00.329000+00:00",
            "completed_at": "2026-08-05T01:00:00.339000+00:00",
            "duration_ms": 10.0,
            "details": {"virtual_node_count": 2, "mapping_cost": 1.0, "topology_edges": [{"source": 0, "target": 1}]},
        },
        {
            "stage": "logical_distributed_simulation",
            "status": "completed",
            "started_at": "2026-08-05T01:00:00.340000+00:00",
            "completed_at": "2026-08-05T01:00:00.350000+00:00",
            "duration_ms": 10.0,
            "details": {"energy_hartree": -1.12, "cross_partition_communication_count": 1, "actual_partition_consumption": True},
        },
    ],
    "hf_energy_hartree": -1.1167,
    "active_space": {"active_electrons": 2, "active_orbitals": 2, "orbital_indices": [0, 1], "orbital_energies_hartree": [-0.58, 0.67], "selection_method": "requested_candidate"},
    "hamiltonian": {
        "mapping_method": "jordan_wigner",
        "fallback_reason": None,
        "qubit_count": 4,
        "qubit_count_before_tapering": 4,
        "z2_tapering_applied": False,
        "pauli_term_count": 3,
        "pauli_terms": [{"pauli_string": "I", "coefficient": -1.05}, {"pauli_string": "Z0", "coefficient": 0.17}, {"pauli_string": "X0 X1", "coefficient": 0.04}],
        "coefficient_cutoff": 0.000001,
        "truncation_error_estimate": 0.0,
    },
    "vqe": {
        "ansatz": "hardware_efficient_ry_cx",
        "optimizer": "Powell",
        "initial_state": "hartree_fock_occupation",
        "initial_occupied_qubits": [0, 1],
        "qasm": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[4];\nx q[0];\nx q[1];\nry(0.1) q[0];\nry(0.2) q[1];\nry(0.0) q[2];\nry(0.0) q[3];\ncx q[0],q[1];\ncx q[1],q[2];\ncx q[2],q[3];\n",
        "converged": True,
        "optimizer_diagnostics": {
            "scipy_success": True,
            "scipy_status": 0,
            "scipy_message": "Optimization terminated successfully.",
            "nfev": 2,
            "termination_reason": "optimizer_reported_success",
            "best_iteration": 2,
            "initial_energy_hartree": -1.1,
            "final_energy_hartree": -1.12,
            "recent_energy_changes_hartree": [-0.02],
        },
        "best_parameters": [0.1, 0.2, 0.0, 0.0],
        "iteration_count": 2,
        "iteration_history": [{"iteration": 1, "parameters": [0.0, 0.0, 0.0, 0.0], "energy_hartree": -1.1, "energy_uncertainty_hartree": 0.0}, {"iteration": 2, "parameters": [0.1, 0.2, 0.0, 0.0], "energy_hartree": -1.12, "energy_uncertainty_hartree": 0.0}],
    },
    "distribution": {
        "backend_type": "simulator",
        "capability_level": "logical_virtual_qpu",
        "is_real_qpu": False,
        "partition_scheme": {"method": "existing_greedy_partitioning_pipeline", "partition_count": 2, "partitions": [{"partition_id": "P1", "qubits": [0, 1]}, {"partition_id": "P2", "qubits": [2, 3]}], "teleportations": 1, "global_gate_count": 1, "parameters": {"b1": 10.0, "b2": 2.0, "max_imbalance": 1}},
        "virtual_node_mapping": [{"virtual_node_id": "T1", "partition_id": "P1", "qubits": [0, 1]}, {"virtual_node_id": "T2", "partition_id": "P2", "qubits": [2, 3]}],
        "topology_edges": [{"source": 0, "target": 1}],
        "mapping_cost": 1.0,
        "cross_partition_communication_count": 1,
        "communication_events": [{"gate_index": 6, "gate": "cx", "control_qubit": 1, "target_qubit": 2, "source_partition_id": "P1", "target_partition_id": "P2", "source_virtual_node_id": "T1", "target_virtual_node_id": "T2"}],
        "actual_partition_consumption": True,
        "simulation_strategy": "mapped_partition_tensor_contraction",
        "state_norm": 1.0,
    },
    "energies": {"unpartitioned_benchmark_energy_hartree": -1.12, "distributed_simulation_energy_hartree": -1.12, "absolute_error_hartree": 0.0},
}


class MoleculeWorkflowResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [SUCCESS_RESPONSE_EXAMPLE]})

    workflow_id: str
    contract_version: str | None = None
    status: Literal["completed"]
    current_stage: Literal["completed"]
    validation_status: Literal["passed", "needs_review"] = Field(
        ..., deprecated=True, description="Legacy optimizer-only status. Use optimizer_validation, scientific_validation and deployment_validation."
    )
    validation_issues: list[ValidationIssue] = Field(default_factory=list, deprecated=True)
    execution_mode: Literal["logical_virtual_qpu"]
    is_real_qpu: Literal[False]
    molecule: MoleculeSummary
    stages: list[CalculationStage]
    hf_energy_hartree: float
    active_space: ActiveSpaceResult
    hamiltonian: HamiltonianResult
    vqe: VqeResult
    distribution: DistributionResult
    energies: EnergyComparison
    optimizer_validation: OptimizerValidation | None = None
    scientific_validation: ScientificValidation | None = None
    deployment_validation: DeploymentValidation | None = None
    fci_reference: FciReferenceResult | None = None
    hamiltonian_builder_version: str | None = None
    scientific_validation_version: str | None = None


CAPABILITIES_RESPONSE_EXAMPLE = {
    "contract_version": "2.0",
    "supported_elements": ["H", "Li", "O"],
    "supported_basis_sets": ["sto-3g"],
    "max_atom_count": 10,
    "max_mapped_qubits": 12,
    "partition_counts": [2, 3],
    "partition_strategies": ["sequential_greedy"],
    "inter_qpu_topologies": ["user_supplied_undirected_edge_list"],
    "physical_coupling_maps": ["user_supplied_undirected_edge_list"],
    "initial_layout_methods": ["identity"],
    "routing_methods": ["shortest_path_swap"],
    "execution_modes": ["logical_virtual_qpu"],
    "is_real_qpu": False,
}


class MoleculeWorkflowCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [CAPABILITIES_RESPONSE_EXAMPLE]})

    contract_version: Literal["2.0"]
    supported_elements: list[str]
    supported_basis_sets: list[str]
    max_atom_count: int
    max_mapped_qubits: int
    partition_counts: list[int]
    partition_strategies: list[str]
    inter_qpu_topologies: list[str]
    physical_coupling_maps: list[str]
    initial_layout_methods: list[str]
    routing_methods: list[str]
    execution_modes: list[Literal["logical_virtual_qpu"]]
    is_real_qpu: Literal[False]


class MoleculeWorkflowHistoryItem(BaseModel):
    workflow_id: str
    molecule_name: str
    created_at: str
    completed_at: str | None
    duration_ms: float | None
    status: Literal["running", "completed", "failed"]
    validation_status: Literal["passed", "needs_review"] | None
    optimizer_name: str | None
    qubit_count: int | None
    pauli_term_count: int | None
    vqe_energy_hartree: float | None
    distributed_energy_hartree: float | None
    absolute_error_hartree: float | None


WORKFLOW_HISTORY_RESPONSE_EXAMPLE = {
    "items": [
        {
            "workflow_id": "molwf_8c1c4ceff69049aa9bc3d9f582a1a9c7",
            "molecule_name": "H2",
            "created_at": "2026-08-06T02:00:00",
            "completed_at": "2026-08-06T02:00:01.200000+00:00",
            "duration_ms": 1200.0,
            "status": "completed",
            "validation_status": "passed",
            "optimizer_name": "Powell",
            "qubit_count": 4,
            "pauli_term_count": 15,
            "vqe_energy_hartree": -1.12,
            "distributed_energy_hartree": -1.12,
            "absolute_error_hartree": 0.0,
        }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1,
}


class MoleculeWorkflowHistoryResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [WORKFLOW_HISTORY_RESPONSE_EXAMPLE]})

    items: list[MoleculeWorkflowHistoryItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class MoleculeWorkflowErrorDetail(BaseModel):
    code: str
    message: str
    stage: str
    workflow_id: str | None


class MoleculeWorkflowErrorResponse(BaseModel):
    detail: MoleculeWorkflowErrorDetail
