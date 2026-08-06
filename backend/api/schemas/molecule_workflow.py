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
    gate: str
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
    operation: Literal["x", "ry", "cx", "swap"]
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
    validation_status: Literal["passed", "needs_review"]
    validation_issues: list[ValidationIssue]
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
