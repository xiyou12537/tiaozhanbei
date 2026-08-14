"""
数据库 ORM 模型 —— 用户、电路、任务、映射结果。

四个表：
  - User: 注册用户
  - Circuit: 上传的 QASM 电路
  - Task: 分区计算任务
  - Mapping: 芯片拓扑映射结果
"""

import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # 关联
    circuits = relationship("Circuit", back_populates="owner", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="owner", cascade="all, delete-orphan")
    mappings = relationship("Mapping", back_populates="owner", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="owner", cascade="all, delete-orphan")
    structure_files = relationship("StructureFileRecord", back_populates="owner", cascade="all, delete-orphan")


class Circuit(Base):
    """电路表 —— 存储用户上传的 QASM 电路"""
    __tablename__ = "circuits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), default="未命名电路")
    qasm_content = Column(Text, nullable=False)
    num_qubits = Column(Integer, default=0)
    total_gates = Column(Integer, default=0)
    multi_qubit_gates = Column(Integer, default=0)
    qubit_list = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="circuits")
    tasks = relationship("Task", back_populates="circuit", cascade="all, delete-orphan")


class Task(Base):
    """任务表 —— 记录每次分区计算的状态和结果"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    circuit_id = Column(Integer, ForeignKey("circuits.id"), nullable=False)
    task_id = Column(String(20), unique=True, nullable=False, index=True)
    status = Column(String(20), default="queued")  # queued / running / completed / failed
    params_json = Column(JSON, default={})
    result_json = Column(JSON, default=None)
    error_message = Column(Text, default=None)
    elapsed_seconds = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="tasks")
    circuit = relationship("Circuit", back_populates="tasks")


class Mapping(Base):
    """映射表 —— 记录芯片拓扑映射结果"""
    __tablename__ = "mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    topology_name = Column(String(100), default="自定义拓扑")
    topology_json = Column(JSON, default=[])
    mapping_json = Column(JSON, default={})
    subgraph_cost = Column(Float, default=0.0)
    epr_cost = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="mappings")


class ChatMessage(Base):
    """聊天消息表 —— 记录 AI 对话历史"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="chat_messages")
    references = relationship("ChatReference", back_populates="chat_message", cascade="all, delete-orphan")


class KnowledgeDocument(Base):
    """知识库文档表"""
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)  # system_doc / paper
    source_path = Column(String(500), nullable=False)
    status = Column(String(50), default="uploaded", index=True)  # uploaded / indexed / failed
    summary = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")
    references = relationship("ChatReference", back_populates="document")


class KnowledgeChunk(Base):
    """知识库切块表"""
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    section_title = Column(String(255), default="")
    content = Column(Text, nullable=False)
    token_length = Column(Integer, default=0)
    embedding_json = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    document = relationship("KnowledgeDocument", back_populates="chunks")
    references = relationship("ChatReference", back_populates="chunk")


class ChatReference(Base):
    """聊天命中知识片段引用表"""
    __tablename__ = "chat_references"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=False, index=True)
    chunk_id = Column(Integer, ForeignKey("knowledge_chunks.id"), nullable=False, index=True)
    rank = Column(Integer, default=0)
    score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    chat_message = relationship("ChatMessage", back_populates="references")
    document = relationship("KnowledgeDocument", back_populates="references")
    chunk = relationship("KnowledgeChunk", back_populates="references")


class ScreeningWorkflowRecord(Base):
    """Persisted multi-material screening workflow payload."""
    __tablename__ = "screening_workflows"

    workflow_id = Column(String(64), primary_key=True)
    case_id = Column(String(100), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    candidate_count = Column(Integer, nullable=False, default=0)
    recommended_material = Column(String(255), nullable=False, default="")
    workflow_payload = Column(JSON, nullable=False, default={})
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class MoleculeWorkflowRecord(Base):
    """Persist a complete small-molecule quantum workflow request and result."""

    __tablename__ = "molecule_workflows"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_molecule_workflow_user_idempotency"),
    )

    workflow_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=True)
    molecule_name = Column(String(120), nullable=False, index=True)
    execution_mode = Column(String(32), nullable=False, default="logical_virtual_qpu")
    status = Column(String(32), nullable=False, index=True, default="running")
    current_stage = Column(String(64), nullable=False, default="input_validation")
    request_json = Column(JSON, nullable=False, default=dict)
    stages_json = Column(JSON, nullable=False, default=list)
    result_json = Column(JSON, nullable=True)
    error_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )


class MolecularProblemRecord(Base):
    """One PySCF/Hamiltonian/VQE result reused by deployment evaluations."""

    __tablename__ = "molecular_problems"
    problem_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    molecule_name = Column(String(120), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    request_json = Column(JSON, nullable=False, default=dict)
    result_json = Column(JSON, nullable=True)
    error_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


class DeploymentStudyRecord(Base):
    """Async multi-architecture deployment assessment for one molecular problem."""

    __tablename__ = "deployment_studies"
    study_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    problem_id = Column(String(64), ForeignKey("molecular_problems.problem_id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    request_json = Column(JSON, nullable=False, default=dict)
    result_json = Column(JSON, nullable=True)
    error_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


class DeploymentEvaluationRecord(Base):
    """One independently routed/distributed execution for a proposed architecture."""

    __tablename__ = "deployment_evaluations"
    evaluation_id = Column(String(64), primary_key=True)
    study_id = Column(String(64), ForeignKey("deployment_studies.study_id"), nullable=False, index=True)
    architecture_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="queued", index=True)
    request_json = Column(JSON, nullable=False, default=dict)
    result_json = Column(JSON, nullable=True)
    error_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


class MolecularBondScanRecord(Base):
    """Persisted asynchronous LiH bond-length scan."""

    __tablename__ = "molecular_bond_scans"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_molecular_bond_scan_user_idempotency"),
    )

    scan_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=True)
    request_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="queued", index=True)
    current_stage = Column(String(64), nullable=False, default="input_validation")
    result_json = Column(JSON, nullable=True)
    error_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class MolecularBondScanPointRecord(Base):
    """Independently durable result for one deterministic LiH distance point."""

    __tablename__ = "molecular_bond_scan_points"
    __table_args__ = (UniqueConstraint("scan_id", "point_index", name="uq_molecular_bond_scan_point"),)

    point_id = Column(String(64), primary_key=True)
    scan_id = Column(String(64), ForeignKey("molecular_bond_scans.scan_id"), nullable=False, index=True)
    point_index = Column(Integer, nullable=False)
    distance_angstrom = Column(Float, nullable=False)
    molecular_problem_id = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    validation_status = Column(String(32), nullable=True)
    result_json = Column(JSON, nullable=True)
    error_json = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class AssistantSessionRecord(Base):
    """User-owned Molecular Copilot conversation metadata."""

    __tablename__ = "assistant_sessions"

    session_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(160), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


class AssistantMessageRecord(Base):
    """Append-only user and assistant messages for one assistant session."""

    __tablename__ = "assistant_messages"

    message_id = Column(String(64), primary_key=True)
    session_id = Column(String(64), ForeignKey("assistant_sessions.session_id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)


class AssistantToolExecutionRecord(Base):
    """Durable controlled-tool audit, including confirmation state and result."""

    __tablename__ = "assistant_tool_executions"

    execution_id = Column(String(64), primary_key=True)
    session_id = Column(String(64), ForeignKey("assistant_sessions.session_id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tool_name = Column(String(80), nullable=False, index=True)
    tool_kind = Column(String(24), nullable=False)
    arguments_json = Column(JSON, nullable=False, default=dict)
    parameter_summary = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="completed", index=True)
    confirmation_id = Column(String(64), unique=True, nullable=True, index=True)
    confirmation_expires_at = Column(DateTime, nullable=True, index=True)
    confirmed_at = Column(DateTime, nullable=True)
    result_json = Column(JSON, nullable=True)
    error_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


class StructureFileRecord(Base):
    """Persist a user-owned source structure file and its parse lifecycle."""

    __tablename__ = "structure_files"

    file_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    material_name = Column(String(100), nullable=False)
    material_family = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    original_filename = Column(String(255), nullable=False)
    normalized_filename = Column(String(128), nullable=False)
    file_type = Column(String(32), nullable=False, index=True)
    file_size_bytes = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    storage_path = Column(String(500), nullable=False)
    parse_status = Column(String(32), nullable=False, index=True, default="uploaded")
    parse_error_code = Column(String(64), nullable=True)
    parse_error_message = Column(Text, nullable=True)
    structure_id = Column(String(64), nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="structure_files")


class ParsedStructureRecord(Base):
    """Normalized atoms and validation output derived from a source structure file."""

    __tablename__ = "parsed_structures"

    structure_id = Column(String(64), primary_key=True)
    file_id = Column(String(64), ForeignKey("structure_files.file_id"), nullable=False, unique=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    formula = Column(String(255), nullable=False)
    elements = Column(JSON, nullable=False, default=list)
    element_counts = Column(JSON, nullable=False, default=dict)
    atom_count = Column(Integer, nullable=False)
    atomic_sites = Column(JSON, nullable=False, default=list)
    lattice = Column(JSON, nullable=True)
    structure_type = Column(String(32), nullable=False)
    charge = Column(Integer, nullable=True)
    spin_multiplicity = Column(Integer, nullable=True)
    dimensionality = Column(String(32), nullable=True)
    parse_warnings = Column(JSON, nullable=False, default=list)
    validation_status = Column(String(32), nullable=False)
    validation_errors = Column(JSON, nullable=False, default=list)
    validation_warnings = Column(JSON, nullable=False, default=list)
    validation_suggestions = Column(JSON, nullable=False, default=list)
    workflow_id = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class ActiveSiteRecord(Base):
    """A suggested or user-confirmed active site frozen for a structure workflow."""

    __tablename__ = "active_sites"

    active_site_id = Column(String(64), primary_key=True)
    structure_id = Column(String(64), ForeignKey("parsed_structures.structure_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    center_atom_indices = Column(JSON, nullable=False, default=list)
    neighbor_atom_indices = Column(JSON, nullable=False, default=list)
    site_label = Column(String(120), nullable=False)
    site_type = Column(String(64), nullable=False)
    detection_method = Column(String(64), nullable=False)
    confidence = Column(Float, nullable=False)
    status = Column(String(32), nullable=False, default="suggested", index=True)
    selected_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    user_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class AdsorptionModelRecord(Base):
    """A filtered Li2Sx initial adsorption conformation."""

    __tablename__ = "adsorption_models"

    adsorption_model_id = Column(String(64), primary_key=True)
    active_site_id = Column(String(64), ForeignKey("active_sites.active_site_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    polysulfide_species = Column(String(16), nullable=False)
    placement_strategy = Column(String(64), nullable=False)
    initial_distance_angstrom = Column(Float, nullable=False)
    geometry_quality_score = Column(Float, nullable=False)
    geometry_artifact_path = Column(String(500), nullable=False)
    status = Column(String(32), nullable=False, default="generated", index=True)
    warnings = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class GeometryOptimizationRecord(Base):
    """A geometry-only relaxation or an imported optimized geometry with explicit provenance."""

    __tablename__ = "geometry_optimizations"

    geometry_optimization_id = Column(String(64), primary_key=True)
    adsorption_model_id = Column(String(64), ForeignKey("adsorption_models.adsorption_model_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    calculation_mode = Column(String(32), nullable=False)
    source_type = Column(String(64), nullable=False)
    method_name = Column(String(120), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    geometry_artifact_path = Column(String(500), nullable=True)
    imported_structure_id = Column(String(64), ForeignKey("parsed_structures.structure_id"), nullable=True)
    warnings = Column(JSON, nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)


class QuantumRegionRecord(Base):
    """A local quantum region with explicit frozen-environment provenance."""

    __tablename__ = "quantum_region_models"

    quantum_region_id = Column(String(64), primary_key=True)
    adsorption_model_id = Column(String(64), ForeignKey("adsorption_models.adsorption_model_id"), nullable=False, index=True)
    geometry_optimization_id = Column(String(64), ForeignKey("geometry_optimizations.geometry_optimization_id"), nullable=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    region_atom_indices = Column(JSON, nullable=False, default=list)
    frozen_environment_atom_indices = Column(JSON, nullable=False, default=list)
    embedding_method = Column(String(64), nullable=False, default="frozen_atoms")
    total_charge = Column(Integer, nullable=True)
    spin_multiplicity = Column(Integer, nullable=True)
    geometry_source_type = Column(String(64), nullable=False, default="geometry_only")
    geometry_method = Column(String(64), nullable=False, default="initial_conformation")
    geometry_artifact_path = Column(String(500), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    warnings = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class ActiveSpaceRecord(Base):
    """A PySCF-derived active-space candidate or a user-confirmed selection."""
    __tablename__ = "active_spaces"
    active_space_id = Column(String(64), primary_key=True)
    quantum_region_id = Column(String(64), ForeignKey("quantum_region_models.quantum_region_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    active_electrons = Column(Integer, nullable=False)
    active_orbitals = Column(Integer, nullable=False)
    orbital_indices = Column(JSON, nullable=False, default=list)
    orbital_metadata = Column(JSON, nullable=False, default=dict)
    selection_reason = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class FermionicHamiltonianRecord(Base):
    __tablename__ = "fermionic_hamiltonians"
    hamiltonian_id = Column(String(64), primary_key=True)
    active_space_id = Column(String(64), ForeignKey("active_spaces.active_space_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    method_name = Column(String(120), nullable=False)
    basis_set = Column(String(64), nullable=False)
    core_energy = Column(Float, nullable=False)
    spin_orbital_count = Column(Integer, nullable=False)
    electron_count = Column(Integer, nullable=False)
    artifact_path = Column(String(500), nullable=False)
    artifact_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class QubitHamiltonianRecord(Base):
    __tablename__ = "structure_qubit_hamiltonians"
    qubit_hamiltonian_id = Column(String(64), primary_key=True)
    fermionic_hamiltonian_id = Column(String(64), ForeignKey("fermionic_hamiltonians.hamiltonian_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mapping_method = Column(String(32), nullable=False)
    fallback_reason = Column(Text, nullable=True)
    qubit_count = Column(Integer, nullable=False)
    qubit_count_before_tapering = Column(Integer, nullable=True)
    symmetry_tapering_applied = Column(Integer, nullable=False, default=0)
    tapered_symmetries = Column(JSON, nullable=False, default=list)
    tapering_reason = Column(Text, nullable=True)
    truncation_error_estimate = Column(Float, nullable=False, default=0.0)
    pauli_term_count = Column(Integer, nullable=False)
    coefficient_cutoff = Column(Float, nullable=False)
    pauli_artifact_path = Column(String(500), nullable=False)
    status = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class VqeCircuitRecord(Base):
    __tablename__ = "vqe_circuits"
    vqe_circuit_id = Column(String(64), primary_key=True)
    qubit_hamiltonian_id = Column(String(64), ForeignKey("structure_qubit_hamiltonians.qubit_hamiltonian_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ansatz = Column(String(64), nullable=False)
    ansatz_layers = Column(Integer, nullable=False)
    parameter_count = Column(Integer, nullable=False)
    optimizer = Column(String(64), nullable=False)
    max_iterations = Column(Integer, nullable=False)
    convergence_tolerance = Column(Float, nullable=False)
    shots = Column(Integer, nullable=False)
    measurement_grouping = Column(String(64), nullable=False)
    qasm_artifact_path = Column(String(500), nullable=False)
    measurement_plan_artifact_path = Column(String(500), nullable=False)
    status = Column(String(32), nullable=False)


class VqeExecutionRecord(Base):
    __tablename__ = "vqe_executions"
    execution_id = Column(String(64), primary_key=True)
    vqe_circuit_id = Column(String(64), ForeignKey("vqe_circuits.vqe_circuit_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    execution_backend_type = Column(String(32), nullable=False)
    execution_backend_detail = Column(String(128), nullable=True)
    shots_total = Column(Integer, nullable=False)
    converged = Column(Integer, nullable=False)
    final_energy_hartree = Column(Float, nullable=False)
    energy_uncertainty_hartree = Column(Float, nullable=False)
    energy_uncertainty_method = Column(String(64), nullable=True)
    iteration_artifact_path = Column(String(500), nullable=False)
    status = Column(String(32), nullable=False)


class BenchmarkCaseRecord(Base):
    """Versioned research input package for reproducible structure-driven studies."""

    __tablename__ = "benchmark_cases"

    benchmark_case_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    catalyst_model_type = Column(String(120), nullable=False)
    adsorbate_species = Column(String(32), nullable=False)
    structure_artifact_path = Column(String(500), nullable=False)
    structure_origin = Column(String(120), nullable=False)
    geometry_status = Column(String(64), nullable=False)
    total_charge = Column(Integer, nullable=False)
    spin_candidate_definitions = Column(JSON, nullable=False, default=list)
    dft_metadata = Column(JSON, nullable=False, default=dict)
    accepted_reference_id = Column(String(64), nullable=True)
    version = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="draft", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class ElectronicStructureCandidateRecord(Base):
    """One auditable charge/spin/method solution for a quantum region."""

    __tablename__ = "electronic_structure_candidates"

    candidate_id = Column(String(64), primary_key=True)
    quantum_region_id = Column(String(64), ForeignKey("quantum_region_models.quantum_region_id"), nullable=False, index=True)
    benchmark_case_id = Column(String(64), ForeignKey("benchmark_cases.benchmark_case_id"), nullable=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    total_charge = Column(Integer, nullable=False)
    spin_multiplicity = Column(Integer, nullable=False)
    scf_method = Column(String(64), nullable=True)
    basis_set = Column(String(64), nullable=False)
    converged = Column(Integer, nullable=False, default=0)
    scf_iterations = Column(JSON, nullable=False, default=list)
    total_energy_hartree = Column(Float, nullable=True)
    spin_square_s2 = Column(Float, nullable=True)
    expected_spin_square_s2 = Column(Float, nullable=True)
    spin_contamination_delta = Column(Float, nullable=True)
    spin_contamination_threshold = Column(Float, nullable=False)
    quality_status = Column(String(32), nullable=False, index=True)
    warnings = Column(JSON, nullable=False, default=list)
    log_artifact_path = Column(String(500), nullable=True)
    result_artifact_path = Column(String(500), nullable=True)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    confirmed_at = Column(DateTime, nullable=True)


class DftImportRecord(Base):
    """External DFT result and metadata imported without claiming that the platform ran DFT."""

    __tablename__ = "dft_imports"

    dft_import_id = Column(String(64), primary_key=True)
    adsorption_model_id = Column(String(64), ForeignKey("adsorption_models.adsorption_model_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    optimized_structure_id = Column(String(64), ForeignKey("parsed_structures.structure_id"), nullable=True)
    status = Column(String(32), nullable=False, index=True)
    calculation_metadata = Column(JSON, nullable=False, default=dict)
    energy_bundle = Column(JSON, nullable=False, default=dict)
    adsorption_energy_hartree = Column(Float, nullable=True)
    comparability_warnings = Column(JSON, nullable=False, default=list)
    geometry_artifact_path = Column(String(500), nullable=True)
    source_artifact_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class DftCalculationRecord(Base):
    """A queued direct DFT engine run with immutable input/output provenance."""

    __tablename__ = "dft_calculations"

    dft_calculation_id = Column(String(64), primary_key=True)
    adsorption_model_id = Column(String(64), ForeignKey("adsorption_models.adsorption_model_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    engine_name = Column(String(32), nullable=False)
    calculation_type = Column(String(32), nullable=False)
    calculation_metadata = Column(JSON, nullable=False, default=dict)
    engine_settings = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, index=True)
    task_id = Column(String(32), nullable=True, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False)
    timeout_seconds = Column(Integer, nullable=False)
    cancellation_requested = Column(Integer, nullable=False, default=0)
    input_artifact_path = Column(String(500), nullable=True)
    output_artifact_path = Column(String(500), nullable=True)
    parsed_result = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)


class ResearchBenchmarkRecord(Base):
    """An immutable public literature baseline, explicitly separated from approved project research data."""

    __tablename__ = "research_benchmarks"

    benchmark_id = Column(String(64), primary_key=True)
    benchmark_key = Column(String(120), nullable=False, unique=True, index=True)
    imported_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    source_url = Column(String(500), nullable=False)
    source_doi = Column(String(128), nullable=False)
    source_license = Column(String(64), nullable=False)
    source_dataset_version = Column(String(64), nullable=False)
    material_model = Column(String(128), nullable=False)
    adsorbate = Column(String(32), nullable=False)
    scientific_validation_level = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    dft_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class ResearchBenchmarkArtifactRecord(Base):
    """A checksum-addressed raw or parsed artifact retained from a public literature dataset."""

    __tablename__ = "research_benchmark_artifacts"

    artifact_id = Column(String(64), primary_key=True)
    benchmark_id = Column(String(64), ForeignKey("research_benchmarks.benchmark_id"), nullable=False, index=True)
    artifact_role = Column(String(64), nullable=False)
    original_filename = Column(String(255), nullable=False)
    checksum_md5 = Column(String(32), nullable=False)
    checksum_sha256 = Column(String(64), nullable=False, index=True)
    storage_path = Column(String(500), nullable=False)
    artifact_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class ResearchBenchmarkCandidateRecord(Base):
    """One source configuration from the public FeN4C66-Li2S4 dataset without relabelling its energy semantics."""

    __tablename__ = "research_benchmark_candidates"

    candidate_id = Column(String(64), primary_key=True)
    benchmark_id = Column(String(64), ForeignKey("research_benchmarks.benchmark_id"), nullable=False, index=True)
    source_candidate_id = Column(String(64), nullable=False)
    source_energy = Column(Float, nullable=True)
    source_energy_unit = Column(String(64), nullable=False)
    coordinate_artifact_path = Column(String(500), nullable=False)
    source_metadata = Column(JSON, nullable=False, default=dict)
    priority_rank = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class ResearchBenchmarkSelectionRecord(Base):
    """A user's immutable copy of a literature candidate used as a reproduction workflow input."""

    __tablename__ = "research_benchmark_selections"

    selection_id = Column(String(64), primary_key=True)
    benchmark_id = Column(String(64), ForeignKey("research_benchmarks.benchmark_id"), nullable=False, index=True)
    candidate_id = Column(String(64), ForeignKey("research_benchmark_candidates.candidate_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    structure_id = Column(String(64), ForeignKey("parsed_structures.structure_id"), nullable=False, unique=True)
    workflow_id = Column(String(64), ForeignKey("structure_screening_workflows.workflow_id"), nullable=False, unique=True)
    status = Column(String(32), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class ClassicalReferenceRecord(Base):
    """Small-system CASCI/FCI reference used to qualify simulator VQE output."""

    __tablename__ = "classical_references"

    reference_id = Column(String(64), primary_key=True)
    fermionic_hamiltonian_id = Column(String(64), ForeignKey("fermionic_hamiltonians.hamiltonian_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    method = Column(String(64), nullable=False)
    energy_hartree = Column(Float, nullable=True)
    status = Column(String(32), nullable=False, index=True)
    artifact_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class StructureWorkflowRecord(Base):
    """State snapshot for the user-uploaded structure modeling workflow."""

    __tablename__ = "structure_screening_workflows"

    workflow_id = Column(String(64), primary_key=True)
    structure_id = Column(String(64), ForeignKey("parsed_structures.structure_id"), nullable=False, unique=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
