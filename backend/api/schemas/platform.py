from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkflowCreateRequest(BaseModel):
    case_id: str | None = None
    candidate_material: str = Field(..., min_length=1)
    qasm_content: str | None = None
    execution_mode: str | None = None


class ScreeningWorkflowCreateRequest(BaseModel):
    case_id: str = Field(default="li-s-demo", min_length=1)
    candidate_materials: list[str] = Field(..., min_length=3)


class WorkflowCreateResponse(BaseModel):
    workflow_id: str
    overall_status: str
    current_stage: str


class WorkflowDetailResponse(BaseModel):
    workflow_id: str
    overall_status: str
    current_stage: str
    candidate_material: str
    completed_stage_count: int
    total_stage_count: int


class WorkflowStageResponse(BaseModel):
    stage_name: str
    stage_status: str
    attempt_no: int
    service_name: str
    output: dict[str, Any] | None = None


class WorkflowEventResponse(BaseModel):
    event_index: int
    event_type: str
    stage_name: str | None = None
    payload: dict[str, Any]


class WorkflowResultResponse(BaseModel):
    workflow_id: str
    overall_status: str
    candidate_material: str
    result_view: dict[str, Any]


class WorkflowSummaryResponse(BaseModel):
    workflow_id: str
    current_stage: str
    overall_status: str
    summary: dict[str, Any]


class WorkflowArtifactsResponse(BaseModel):
    workflow_id: str
    artifacts: dict[str, Any]


class WorkflowCancelResponse(BaseModel):
    workflow_id: str
    overall_status: str
    message: str


class CandidateCatalogResponse(BaseModel):
    candidate_name: str
    family: str
    adsorption_strength: float
    material_id: str | None = None
    material_name: str | None = None
    material_family: str | None = None
    active_site: str | None = None
    adsorption_energy_li2s6: float | None = None
    adsorption_energy_li2s4: float | None = None
    reaction_barrier_proxy: float | None = None
    conductivity_score: float | None = None
    stability_score: float | None = None
    synthesis_feasibility_score: float | None = None
    source_type: str | None = None
    source_reference: str | None = None


class ScreeningWorkflowCreateResponse(BaseModel):
    workflow_id: str
    case_id: str
    status: str
    candidate_count: int
    recommended_material: str
    created_at: str = ""
    updated_at: str = ""


class ScreeningWorkflowPayloadResponse(BaseModel):
    workflow_id: str
    case_id: str
    status: str
    candidate_count: int
    candidate_results: list[dict[str, Any]]
    classical_screening: list[dict[str, Any]]
    quantum_refinement: list[dict[str, Any]]
    explanations: dict[str, dict[str, Any]]
    leaderboard: list[dict[str, Any]]
    recommended_material: str
    created_at: str = ""
    updated_at: str = ""


class ScreeningWorkflowListItemResponse(BaseModel):
    workflow_id: str
    case_id: str
    status: str
    candidate_count: int
    recommended_material: str
    created_at: str
    updated_at: str


class ScreeningStageResponse(BaseModel):
    workflow_id: str
    results: list[dict[str, Any]]


class ScreeningLeaderboardResponse(BaseModel):
    workflow_id: str
    candidate_count: int
    recommended_material: str
    leaderboard: list[dict[str, Any]]


class CandidateExplanationResponse(BaseModel):
    workflow_id: str
    candidate_material: str
    explanation: dict[str, Any]


class CaseCatalogResponse(BaseModel):
    case_id: str
    title: str
    candidate_material: str


class ActiveSiteConfirmRequest(BaseModel):
    site_source: str = Field(default="suggested", pattern="^(suggested|manual)$")
    site_id: str | None = None
    center_atom_indices: list[int] = Field(..., min_length=1, max_length=8)
    neighbor_atom_indices: list[int] = Field(default_factory=list, max_length=16)
    site_label: str = Field(..., min_length=1, max_length=120)
    user_note: str | None = Field(default=None, max_length=1000)


class AdsorptionModelCreateRequest(BaseModel):
    polysulfide_species: list[str] = Field(..., min_length=1, max_length=2)
    max_conformations_per_species: int = Field(default=6, ge=3, le=6)
    initial_distance_angstrom: float = Field(default=2.6, ge=2.0, le=3.5)


class QuantumRegionCreateRequest(BaseModel):
    geometry_optimization_id: str = Field(..., min_length=4, max_length=64)
    radius_angstrom: float = Field(default=5.0, ge=1.0, le=12.0)
    total_charge: int | None = Field(default=None, ge=-20, le=20)
    spin_multiplicity: int | None = Field(default=None, ge=1, le=20)


class GeometryOptimizationCreateRequest(BaseModel):
    calculation_mode: str = Field(..., pattern="^(geometry_only|imported_optimized|dft_optimized)$")
    imported_structure_id: str | None = Field(default=None, min_length=4, max_length=64)
    method_name: str | None = Field(default=None, min_length=2, max_length=120)
    calculation_metadata: dict[str, Any] = Field(default_factory=dict)


class ActiveSpaceConfirmRequest(BaseModel):
    active_space_id: str = Field(..., min_length=4, max_length=64)


class QubitMappingRequest(BaseModel):
    mapping_method: str = Field(default="parity", pattern="^(parity|jordan_wigner)$")
    enable_z2_tapering: bool = True
    z2_tapering_sectors: dict[int, int] | None = None
    pauli_coefficient_cutoff: float = Field(default=0.000001, gt=0)

    @field_validator("z2_tapering_sectors")
    @classmethod
    def validate_z2_tapering_sectors(cls, value: dict[int, int] | None) -> dict[int, int] | None:
        if value is None:
            return value
        if any(qubit_index < 0 or sector not in {-1, 1} for qubit_index, sector in value.items()):
            raise ValueError("Z2 裁剪扇区必须以非负量子比特索引指定，且本征值只能为 -1 或 1。")
        return value


class VqeCircuitCreateRequest(BaseModel):
    ansatz: str = Field(default="hardware_efficient_ry_cx", pattern="^hardware_efficient_ry_cx$")
    ansatz_layers: int = Field(default=1, ge=1, le=4)
    optimizer: str = Field(default="COBYLA", pattern="^COBYLA$")
    max_iterations: int = Field(default=200, ge=1, le=500)
    convergence_tolerance: float = Field(default=0.0001, gt=0)
    shots: int = Field(default=8192, ge=1)
    measurement_grouping: str = Field(default="qubit_wise_commuting")


class QuantumClosureBenchmarkCreateRequest(BaseModel):
    """Protocol-locked parameters for a simulator-only quantum closure benchmark."""

    mapping_method: str = Field(default="jordan_wigner", pattern="^(parity|jordan_wigner)$")
    ansatz: str = Field(default="ry_cx", pattern="^(ry_cx|hardware_efficient_ry_cx)$")
    ansatz_layers: int = Field(default=2, ge=1, le=4)
    optimizer: str = Field(default="COBYLA", pattern="^COBYLA$")
    max_iterations: int = Field(default=300, ge=1, le=500)
    convergence_tolerance: float = Field(default=0.00001, gt=0)
    shots: int = Field(default=0, ge=0)
    mapping_tolerance_hartree: float = Field(default=0.00000001, gt=0, le=0.000001)
    vqe_target_tolerance_hartree: float = Field(default=0.0016, gt=0, le=0.1)


class BenchmarkCaseCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    catalyst_model_type: str = Field(..., min_length=3, max_length=120)
    adsorbate_species: str = Field(default="Li2S4", pattern="^Li2S4$")
    structure_id: str = Field(..., min_length=4, max_length=64)
    structure_origin: str = Field(..., min_length=3, max_length=120)
    geometry_status: str = Field(..., pattern="^(initial|dft_optimized|imported_dft_optimized)$")
    total_charge: int = Field(..., ge=-20, le=20)
    spin_candidate_definitions: list[dict[str, Any]] = Field(..., min_length=1, max_length=12)
    dft_metadata: dict[str, Any] = Field(default_factory=dict)
    version: str = Field(..., min_length=1, max_length=64)


class ElectronicStructureCandidateCreateRequest(BaseModel):
    charge_candidates: list[int] = Field(..., min_length=1, max_length=5)
    spin_strategy: str = Field(default="transition_metal_auto_candidates", pattern="^(transition_metal_auto_candidates|explicit)$")
    spin_multiplicities: list[int] = Field(default_factory=list, max_length=8)
    requested_methods: list[str] = Field(default_factory=lambda: ["UHF", "ROHF"], min_length=1, max_length=2)
    basis_set: str = Field(default="def2-svp", min_length=2, max_length=64)
    max_scf_attempts: int = Field(default=3, ge=1, le=3)
    spin_contamination_threshold: float = Field(..., gt=0, le=5)
    benchmark_case_id: str | None = Field(default=None, min_length=4, max_length=64)

    @field_validator("requested_methods")
    @classmethod
    def validate_requested_methods(cls, value: list[str]) -> list[str]:
        allowed = {"RHF", "UHF", "ROHF"}
        if not set(value).issubset(allowed):
            raise ValueError("requested_methods 仅支持 RHF、UHF、ROHF。")
        return value


class DftImportCreateRequest(BaseModel):
    optimized_structure_id: str | None = Field(default=None, min_length=4, max_length=64)
    calculation_metadata: dict[str, Any] = Field(default_factory=dict)
    energy_bundle: dict[str, Any] = Field(default_factory=dict)


class DirectDftCalculationMetadata(BaseModel):
    """Scientifically relevant electronic-state inputs shared by direct DFT engines."""

    model_config = ConfigDict(extra="allow")

    software_version: str = Field(..., min_length=1, max_length=64)
    functional: str = Field(..., min_length=1, max_length=64)
    basis_or_pseudopotential: str = Field(..., min_length=1, max_length=255)
    dispersion: str = Field(..., min_length=1, max_length=64)
    spin_polarization: bool
    total_charge: int = Field(..., ge=-20, le=20)
    spin_multiplicity: int = Field(..., ge=1, le=20)
    initial_magnetization_by_element: dict[str, float] | None = None
    convergence: dict[str, Any]


class DirectDftCalculationCreateRequest(BaseModel):
    engine_name: str = Field(..., pattern="^(quantum_espresso|cp2k)$")
    calculation_type: str = Field(..., pattern="^(geometry_optimization|single_point|adsorption_energy)$")
    calculation_metadata: DirectDftCalculationMetadata
    engine_settings: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=1, ge=1, le=3)
    timeout_seconds: int = Field(default=1800, ge=30, le=3600)

    @model_validator(mode="after")
    def validate_spin_configuration(self):
        metadata = self.calculation_metadata
        if metadata.spin_multiplicity > 1 and not metadata.spin_polarization:
            raise ValueError("开壳层 DFT 任务必须启用 spin_polarization。")
        if self.engine_name == "quantum_espresso" and metadata.spin_polarization:
            magnetization = metadata.initial_magnetization_by_element
            if not magnetization or not any(abs(value) > 0 for value in magnetization.values()):
                raise ValueError("Quantum ESPRESSO 自旋极化任务必须提供至少一个非零元素初始磁化。")
        return self


class ResearchBenchmarkImportRequest(BaseModel):
    benchmark_key: str = Field(default="fe-n4-c66-li2s4-literature-v1", min_length=8, max_length=120)
    dataset_url: str = Field(default="https://archive.materialscloud.org/records/f5t2r-6qf35", min_length=20, max_length=500)
    source_license: str = Field(default="CC-BY-4.0", pattern="^CC-BY-4.0$")
    adsorbate: str = Field(default="Li2S4", pattern="^Li2S4$")
    retain_raw_artifacts: bool = True


class ElectronicStructureCandidateConfirmRequest(BaseModel):
    confirmation_note: str | None = Field(default=None, max_length=1000)


class StructureFileResponse(BaseModel):
    file_id: str
    material_name: str
    material_family: str | None = None
    description: str | None = None
    original_filename: str
    file_type: str
    input_purpose: str
    file_size_bytes: int
    file_hash: str
    parse_status: str
    parse_error: dict[str, str | None] | None = None
    structure_id: str | None = None
    created_at: str
    updated_at: str


class StructureFileListResponse(BaseModel):
    items: list[StructureFileResponse]
    page: int
    page_size: int
    total: int


class MolecularModelCreateRequest(BaseModel):
    """Bind a strict XYZ parse to expected source/canonical hashes."""

    schema_version: str = Field(
        default="molecular_model_create_v1",
        pattern="^molecular_model_create_v1$",
    )
    source_format: str = Field(default="xyz", pattern="^xyz$")
    coordinate_unit: str = Field(default="angstrom", pattern="^angstrom$")
    expected_source_file_id: str = Field(..., min_length=4, max_length=64)
    expected_source_file_sha256: str = Field(
        ...,
        pattern=r"^[0-9a-f]{64}$",
    )
    expected_canonical_geometry_sha256: str = Field(
        ...,
        pattern=r"^[0-9a-f]{64}$",
    )
    supersedes_molecular_model_id: str | None = Field(
        default=None,
        min_length=4,
        max_length=64,
    )


class MolecularModelConfirmRequest(BaseModel):
    """Explicit user confirmation frozen by Stage M-B."""

    schema_version: str = Field(
        default="molecular_model_confirm_v1",
        pattern="^molecular_model_confirm_v1$",
    )
    coordinate_unit: str = Field(..., pattern="^angstrom$")
    total_charge: int = Field(..., ge=-20, le=20)
    spin_multiplicity: int = Field(..., ge=1, le=1)
    expected_source_file_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    expected_canonical_geometry_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    confirmation: bool = Field(...)
    confirmation_note: str | None = Field(default=None, max_length=1000)


class MolecularElectronicStructureCreateRequest(BaseModel):
    """Future M-C admission envelope; M-B always rejects it before persistence."""

    protocol_id: str = Field(
        default="molecular_logical_circuit_closed_shell_cas22",
        pattern="^molecular_logical_circuit_closed_shell_cas22$",
    )
    protocol_version: str = Field(
        default="1.0.0-design-frozen",
        pattern=r"^1\.0\.0-design-frozen$",
    )


class DistributedCompilationCreateRequest(BaseModel):
    """Request the protocol-frozen Stage-B compilation for one VQE execution."""

    benchmark_level: str = Field(default="level_a_4q", pattern="^level_a_4q$")
    protocol_version: str = Field(default="1.0.0", pattern=r"^1\.0\.0$")


class DistributedCompilationResponse(BaseModel):
    """Owner-scoped compilation state; planning alone never grants execution."""

    model_config = ConfigDict(from_attributes=True)

    compilation_id: str
    owner_user_id: int
    vqe_execution_id: str
    qubit_hamiltonian_id: str
    closure_benchmark_id: str
    benchmark_level: str
    execution_stage: str
    protocol_id: str
    protocol_version: str
    protocol_sha256: str
    topology_name: str
    topology_sha256: str
    status: str
    failure_code: str | None = None
    failure_stage: str | None = None
    failure_detail: str | None = None
    formal_attempt_limit: int
    formal_attempts_started: int
    actual_distributed_hardware_execution: bool
    baseline_metrics: dict[str, Any]
    optimized_metrics: dict[str, Any]
    resource_estimate: dict[str, Any]
    created_at: Any
    completed_at: Any | None = None


class DistributedSimulationStartRequest(BaseModel):
    """Start the single statevector attempt for an executable compilation."""

    shots: int = Field(default=0, ge=0, le=0)
    backend: str = Field(
        default="qiskit.quantum_info.Statevector",
        pattern=r"^qiskit\.quantum_info\.Statevector$",
    )


class DistributedSimulationResponse(BaseModel):
    """Owner-scoped simulation result and qualification facts."""

    model_config = ConfigDict(from_attributes=True)

    simulation_id: str
    compilation_id: str
    owner_user_id: int
    formal_attempt_number: int
    execution_backend_type: str
    execution_backend_detail: str
    shots: int
    status: str
    qualification_status: str
    failure_code: str | None = None
    failure_stage: str | None = None
    failure_detail: str | None = None
    e_classical_exact: float | None = None
    e_exact_pauli: float | None = None
    e_logical_vqe: float | None = None
    e_distributed: float | None = None
    error_fci_vs_pauli: float | None = None
    error_logical_vs_pauli: float | None = None
    error_distributed_vs_logical: float | None = None
    error_distributed_vs_pauli: float | None = None
    statevector_fidelity: float | None = None
    statevector_infidelity: float | None = None
    n_alpha_expectation: float | None = None
    n_beta_expectation: float | None = None
    n_alpha_variance: float | None = None
    n_beta_variance: float | None = None
    acceptance_checks: dict[str, Any]
    resource_telemetry: dict[str, Any]
    distributed_semantics_simulated: bool
    actual_distributed_hardware_execution: bool
    created_at: Any
    started_at: Any | None = None
    completed_at: Any | None = None


class DistributedValidationReportResponse(BaseModel):
    """Validated report metadata; the immutable Artifact remains authoritative."""

    simulation_id: str
    compilation_id: str
    qualification_status: str
    validation_report_path: str
    validation_report_sha256: str
    actual_distributed_hardware_execution: bool


class DistributedApiErrorDetail(BaseModel):
    code: str
    message: str


class DistributedApiErrorResponse(BaseModel):
    detail: DistributedApiErrorDetail
