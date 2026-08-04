"""
数据库 ORM 模型 —— 用户、电路、任务、映射结果。

四个表：
  - User: 注册用户
  - Circuit: 上传的 QASM 电路
  - Task: 分区计算任务
  - Mapping: 芯片拓扑映射结果
"""

import datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
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


class StructureFileRecord(Base):
    """Persist a user-owned source structure file and its parse lifecycle."""

    __tablename__ = "structure_files"
    __table_args__ = (
        CheckConstraint(
            "input_purpose IN ('legacy_screening', 'molecular_logical_circuit')",
            name="ck_structure_file_input_purpose",
        ),
        UniqueConstraint(
            "file_id",
            "owner_user_id",
            "input_purpose",
            name="uq_structure_file_owner_purpose",
        ),
    )

    file_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    material_name = Column(String(100), nullable=False)
    material_family = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    original_filename = Column(String(255), nullable=False)
    normalized_filename = Column(String(128), nullable=False)
    file_type = Column(String(32), nullable=False, index=True)
    input_purpose = Column(String(32), nullable=False, index=True)
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
    __table_args__ = (
        UniqueConstraint(
            "structure_id",
            "file_id",
            "owner_user_id",
            name="uq_parsed_structure_source_owner",
        ),
    )

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
    workflow_id = Column(String(64), nullable=True, unique=True, index=True)
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
    __table_args__ = (
        CheckConstraint(
            "("
            "source_type = 'adsorption_model' "
            "AND adsorption_model_id IS NOT NULL "
            "AND molecular_model_id IS NULL"
            ") OR ("
            "source_type = 'molecular_model' "
            "AND adsorption_model_id IS NULL "
            "AND molecular_model_id IS NOT NULL"
            ")",
            name="ck_quantum_region_exactly_one_source",
        ),
    )

    quantum_region_id = Column(String(64), primary_key=True)
    source_type = Column(String(32), nullable=False, index=True)
    adsorption_model_id = Column(String(64), ForeignKey("adsorption_models.adsorption_model_id"), nullable=True, index=True)
    molecular_model_id = Column(String(64), ForeignKey("molecular_models.molecular_model_id"), nullable=True, index=True)
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
    source_geometry_artifact_path = Column(String(500), nullable=True)
    source_geometry_sha256 = Column(String(64), nullable=True)
    region_atom_count = Column(Integer, nullable=True)
    region_indices_sha256 = Column(String(64), nullable=True)
    preflight_artifact_path = Column(String(500), nullable=True)
    status = Column(String(32), nullable=False, index=True)
    warnings = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class MolecularModelRecord(Base):
    """Immutable confirmed molecular input, versioned by structure and owner."""

    __tablename__ = "molecular_models"
    __table_args__ = (
        CheckConstraint(
            "source_input_purpose = 'molecular_logical_circuit'",
            name="ck_molecular_model_input_purpose",
        ),
        CheckConstraint(
            "source_format = 'xyz'",
            name="ck_molecular_model_source_format",
        ),
        CheckConstraint(
            "coordinate_unit = 'angstrom'",
            name="ck_molecular_model_coordinate_unit",
        ),
        CheckConstraint(
            "confirmation_status IN ('pending_confirmation', 'confirmed')",
            name="ck_molecular_model_confirmation_status",
        ),
        CheckConstraint(
            "model_version >= 1 AND atom_count BETWEEN 1 AND 32",
            name="ck_molecular_model_resource_shape",
        ),
        CheckConstraint(
            "("
            "confirmation_status = 'pending_confirmation' "
            "AND total_charge IS NULL "
            "AND spin_multiplicity IS NULL "
            "AND electron_count IS NULL "
            "AND confirmed_by_user_id IS NULL "
            "AND confirmed_at IS NULL "
            "AND frozen_input_sha256 IS NULL"
            ") OR ("
            "confirmation_status = 'confirmed' "
            "AND total_charge IS NOT NULL "
            "AND spin_multiplicity = 1 "
            "AND electron_count BETWEEN 2 AND 128 "
            "AND electron_count % 2 = 0 "
            "AND confirmed_by_user_id = owner_user_id "
            "AND confirmed_at IS NOT NULL "
            "AND frozen_input_sha256 IS NOT NULL"
            ")",
            name="ck_molecular_model_confirmation_fields",
        ),
        ForeignKeyConstraint(
            ["structure_id", "source_file_id", "owner_user_id"],
            [
                "parsed_structures.structure_id",
                "parsed_structures.file_id",
                "parsed_structures.owner_user_id",
            ],
            name="fk_molecular_model_parsed_source_owner",
        ),
        ForeignKeyConstraint(
            ["source_file_id", "owner_user_id", "source_input_purpose"],
            [
                "structure_files.file_id",
                "structure_files.owner_user_id",
                "structure_files.input_purpose",
            ],
            name="fk_molecular_model_file_owner_purpose",
        ),
        ForeignKeyConstraint(
            ["supersedes_molecular_model_id", "owner_user_id", "structure_id"],
            [
                "molecular_models.molecular_model_id",
                "molecular_models.owner_user_id",
                "molecular_models.structure_id",
            ],
            name="fk_molecular_model_predecessor_owner_structure",
        ),
        UniqueConstraint(
            "owner_user_id",
            "structure_id",
            "model_version",
            name="uq_molecular_model_structure_version",
        ),
        UniqueConstraint(
            "molecular_model_id",
            "owner_user_id",
            "structure_id",
            name="uq_molecular_model_owner_structure",
        ),
        UniqueConstraint(
            "molecular_model_id",
            "owner_user_id",
            name="uq_molecular_model_owner",
        ),
        UniqueConstraint(
            "supersedes_molecular_model_id",
            name="uq_molecular_model_direct_successor",
        ),
    )

    molecular_model_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    structure_id = Column(String(64), nullable=False, index=True)
    source_file_id = Column(String(64), nullable=False, index=True)
    source_input_purpose = Column(String(32), nullable=False)
    model_version = Column(Integer, nullable=False)
    supersedes_molecular_model_id = Column(String(64), nullable=True, index=True)
    source_format = Column(String(16), nullable=False)
    source_file_sha256 = Column(String(64), nullable=False)
    canonical_geometry_sha256 = Column(String(64), nullable=False, index=True)
    canonical_geometry_payload = Column(JSON, nullable=False)
    canonical_geometry_artifact_path = Column(String(500), nullable=True)
    input_manifest_artifact_path = Column(String(500), nullable=True)
    coordinate_unit = Column(String(16), nullable=False)
    total_charge = Column(Integer, nullable=True)
    spin_multiplicity = Column(Integer, nullable=True)
    atom_count = Column(Integer, nullable=False)
    electron_count = Column(Integer, nullable=True)
    formula = Column(String(255), nullable=False)
    element_set = Column(JSON, nullable=False, default=list)
    dimensionality = Column(String(32), nullable=False)
    confirmation_status = Column(String(32), nullable=False, index=True)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    frozen_input_sha256 = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )


class MolecularWorkflowRecord(Base):
    """Persist the non-computational M-B molecular lineage and stage status."""

    __tablename__ = "molecular_workflows"
    __table_args__ = (
        UniqueConstraint(
            "molecular_model_id",
            "protocol_id",
            "protocol_version",
            name="uq_molecular_workflow_protocol",
        ),
        CheckConstraint(
            "partial IN (0, 1) AND qualification_granted IN (0, 1)",
            name="ck_molecular_workflow_boolean_flags",
        ),
    )

    molecular_workflow_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    molecular_model_id = Column(String(64), ForeignKey("molecular_models.molecular_model_id"), nullable=False, index=True)
    quantum_region_id = Column(String(64), ForeignKey("quantum_region_models.quantum_region_id"), nullable=False, unique=True, index=True)
    protocol_id = Column(String(128), nullable=False)
    protocol_version = Column(String(32), nullable=False)
    protocol_payload_sha256 = Column(String(64), nullable=False)
    current_stage = Column(String(64), nullable=False, index=True)
    workflow_status = Column(String(64), nullable=False, index=True)
    qualification_status = Column(String(64), nullable=False, default="not_assessed")
    qualification_granted = Column(Integer, nullable=False, default=0)
    partial = Column(Integer, nullable=False, default=0)
    terminal_failure_code = Column(String(96), nullable=True)
    terminal_failure_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class MolecularElectronicStructureCalculationRecord(Base):
    """A future M-C RHF request; M-B creates the schema but never runs it."""

    __tablename__ = "molecular_electronic_structure_calculations"
    __table_args__ = (
        UniqueConstraint(
            "molecular_workflow_id",
            "protocol_id",
            "protocol_version",
            name="uq_molecular_electronic_calculation_protocol",
        ),
    )

    calculation_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    molecular_workflow_id = Column(String(64), ForeignKey("molecular_workflows.molecular_workflow_id"), nullable=False, index=True)
    molecular_model_id = Column(String(64), ForeignKey("molecular_models.molecular_model_id"), nullable=False, index=True)
    quantum_region_id = Column(String(64), ForeignKey("quantum_region_models.quantum_region_id"), nullable=False, index=True)
    stage_attempt_id = Column(
        String(64),
        ForeignKey("molecular_stage_attempts.stage_attempt_id"),
        nullable=True,
        unique=True,
    )
    protocol_id = Column(String(128), nullable=False)
    protocol_version = Column(String(32), nullable=False)
    input_payload_sha256 = Column(String(64), nullable=False)
    frozen_request = Column(JSON, nullable=False, default=dict)
    status = Column(String(64), nullable=False, index=True)
    converged = Column(Integer, nullable=False, default=0)
    total_energy_hartree = Column(Float, nullable=True)
    failure_code = Column(String(96), nullable=True)
    failure_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class MolecularStageAttemptRecord(Base):
    """Write-once admission fact for one molecular workflow stage."""

    __tablename__ = "molecular_stage_attempts"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "molecular_workflow_id",
            "stage_name",
            "attempt_number",
            name="uq_molecular_stage_attempt",
        ),
        CheckConstraint(
            "attempt_number = 1",
            name="ck_molecular_stage_attempt_one",
        ),
        CheckConstraint(
            "qualification_granted IN (0, 1)",
            name="ck_molecular_stage_attempt_qualification",
        ),
    )

    stage_attempt_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    molecular_workflow_id = Column(String(64), ForeignKey("molecular_workflows.molecular_workflow_id"), nullable=False, index=True)
    stage_name = Column(String(64), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    input_payload_sha256 = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    status = Column(String(64), nullable=False, index=True)
    produced_fact_flags = Column(JSON, nullable=False, default=dict)
    qualification_granted = Column(Integer, nullable=False, default=0)
    failure_code = Column(String(96), nullable=True)
    failure_stage = Column(String(96), nullable=True)
    failure_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class MolecularObservationRecord(Base):
    """Append-only observation from a molecular stage attempt."""

    __tablename__ = "molecular_observations"
    __table_args__ = (
        UniqueConstraint(
            "stage_attempt_id",
            "sequence_number",
            name="uq_molecular_observation_sequence",
        ),
        CheckConstraint("partial IN (0, 1)", name="ck_molecular_observation_partial"),
    )

    observation_id = Column(String(64), primary_key=True)
    stage_attempt_id = Column(String(64), ForeignKey("molecular_stage_attempts.stage_attempt_id"), nullable=False, index=True)
    molecular_workflow_id = Column(String(64), ForeignKey("molecular_workflows.molecular_workflow_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    stage_name = Column(String(64), nullable=False)
    observation_name = Column(String(96), nullable=False)
    value_json = Column(JSON, nullable=True)
    unit = Column(String(64), nullable=True)
    raw_value_json = Column(JSON, nullable=True)
    normalized_value_json = Column(JSON, nullable=True)
    algorithm_version = Column(String(64), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    partial = Column(Integer, nullable=False, default=0)
    missing_reason = Column(String(160), nullable=True)
    payload_sha256 = Column(String(64), nullable=False)
    observed_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)


class MolecularArtifactPublicationRecord(Base):
    """No-clobber publication journal for molecular workflow Artifacts."""

    __tablename__ = "molecular_artifact_publication_journal"
    __table_args__ = (
        UniqueConstraint(
            "molecular_workflow_id",
            "artifact_role",
            "schema_version",
            name="uq_molecular_artifact_role_version",
        ),
        UniqueConstraint("target_relative_path", name="uq_molecular_artifact_target"),
        CheckConstraint(
            "status IN ('pending', 'published', 'failed', 'reconciled')",
            name="ck_molecular_artifact_publication_status",
        ),
    )

    publication_id = Column(String(64), primary_key=True)
    stage_attempt_id = Column(String(64), ForeignKey("molecular_stage_attempts.stage_attempt_id"), nullable=True, index=True)
    molecular_workflow_id = Column(String(64), ForeignKey("molecular_workflows.molecular_workflow_id"), nullable=False, index=True)
    molecular_model_id = Column(String(64), ForeignKey("molecular_models.molecular_model_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    artifact_role = Column(String(96), nullable=False)
    filename = Column(String(160), nullable=False)
    schema_id = Column(String(128), nullable=False)
    schema_version = Column(String(32), nullable=False)
    target_relative_path = Column(String(500), nullable=False)
    expected_payload_sha256 = Column(String(64), nullable=False)
    expected_file_sha256 = Column(String(64), nullable=False)
    actual_file_sha256 = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, index=True)
    failure_stage = Column(String(96), nullable=True)
    failure_code = Column(String(96), nullable=True)
    failure_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    published_at = Column(DateTime, nullable=True)
    reconciled_at = Column(DateTime, nullable=True)


class MolecularLogicalValidationRecord(Base):
    """Future M-C validation schema; no row is created during M-B."""

    __tablename__ = "molecular_logical_validations"
    __table_args__ = (
        CheckConstraint(
            "partial IN (0, 1)",
            name="ck_molecular_logical_validation_partial",
        ),
    )

    validation_id = Column(String(64), primary_key=True)
    stage_attempt_id = Column(String(64), ForeignKey("molecular_stage_attempts.stage_attempt_id"), nullable=False, unique=True)
    molecular_workflow_id = Column(String(64), ForeignKey("molecular_workflows.molecular_workflow_id"), nullable=False, index=True)
    vqe_circuit_id = Column(String(64), ForeignKey("vqe_circuits.vqe_circuit_id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    observations_json = Column(JSON, nullable=False, default=dict)
    acceptance_checks_json = Column(JSON, nullable=False, default=dict)
    partial = Column(Integer, nullable=False, default=0)
    qualification_status = Column(String(96), nullable=False)
    failure_code = Column(String(96), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)


class MolecularIdempotencyRecord(Base):
    """Owner- and route-scoped canonical request/result binding."""

    __tablename__ = "molecular_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "route_scope",
            "idempotency_key_hash",
            name="uq_molecular_idempotency_scope",
        ),
    )

    idempotency_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    route_scope = Column(String(160), nullable=False)
    parent_resource_id = Column(String(64), nullable=False)
    idempotency_key_hash = Column(String(64), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    response_resource_type = Column(String(64), nullable=True)
    response_resource_id = Column(String(64), nullable=True)
    response_status_code = Column(Integer, nullable=True)
    response_payload = Column(JSON, nullable=True)
    terminal = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)


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
    record_origin = Column(String(64), nullable=False, default="native_workflow")
    source_artifact_id = Column(String(160), nullable=True)
    source_artifact_path = Column(String(500), nullable=True)
    source_artifact_sha256 = Column(String(64), nullable=True)
    registration_scheme = Column(String(64), nullable=True)
    registration_key = Column(String(64), nullable=True, index=True)
    registered_at = Column(DateTime, nullable=True)
    registration_manifest = Column(JSON, nullable=True)


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
    record_origin = Column(String(64), nullable=False, default="native_workflow")
    source_artifact_id = Column(String(160), nullable=True)
    source_artifact_path = Column(String(500), nullable=True)
    source_artifact_sha256 = Column(String(64), nullable=True)
    registration_scheme = Column(String(64), nullable=True)
    registration_key = Column(String(64), nullable=True, index=True)
    registered_at = Column(DateTime, nullable=True)
    registration_manifest = Column(JSON, nullable=True)


class QubitHamiltonianRecord(Base):
    __tablename__ = "structure_qubit_hamiltonians"
    __table_args__ = (
        UniqueConstraint(
            "qubit_hamiltonian_id",
            "owner_user_id",
            name="uq_qubit_hamiltonian_owner",
        ),
    )
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
    ordered_pauli_payload_sha256 = Column(String(64), nullable=True, index=True)
    record_origin = Column(String(64), nullable=False, default="native_workflow")
    source_artifact_id = Column(String(160), nullable=True)
    source_artifact_path = Column(String(500), nullable=True)
    source_artifact_sha256 = Column(String(64), nullable=True)
    registration_scheme = Column(String(64), nullable=True)
    registration_key = Column(String(64), nullable=True, index=True)
    registered_at = Column(DateTime, nullable=True)
    registration_manifest = Column(JSON, nullable=True)
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
    measurement_plan_artifact_path = Column(String(500), nullable=True)
    status = Column(String(32), nullable=False)
    raw_qasm_sha256 = Column(String(64), nullable=True, index=True)
    canonical_circuit_sha256 = Column(String(64), nullable=True, index=True)
    parameter_sha256 = Column(String(64), nullable=True, index=True)
    parameter_hash_scheme = Column(String(64), nullable=True)
    parameters_bound = Column(Boolean, nullable=False, default=False)
    record_origin = Column(String(64), nullable=False, default="native_workflow")
    source_artifact_id = Column(String(160), nullable=True)
    source_artifact_path = Column(String(500), nullable=True)
    source_artifact_sha256 = Column(String(64), nullable=True)
    registration_scheme = Column(String(64), nullable=True)
    registration_key = Column(String(64), nullable=True, index=True)
    registered_at = Column(DateTime, nullable=True)
    registration_manifest = Column(JSON, nullable=True)


class VqeExecutionRecord(Base):
    __tablename__ = "vqe_executions"
    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "owner_user_id",
            name="uq_vqe_execution_owner",
        ),
    )
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
    record_origin = Column(String(64), nullable=False, default="native_workflow")
    source_artifact_id = Column(String(160), nullable=True)
    source_artifact_path = Column(String(500), nullable=True)
    source_artifact_sha256 = Column(String(64), nullable=True)
    registration_scheme = Column(String(64), nullable=True)
    registration_key = Column(String(64), nullable=True, index=True)
    registered_at = Column(DateTime, nullable=True)
    registration_manifest = Column(JSON, nullable=True)


class QuantumClosureBenchmarkRecord(Base):
    """Immutable audit record for one FCI/Pauli/VQE closure comparison."""

    __tablename__ = "quantum_closure_benchmarks"

    closure_benchmark_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    research_benchmark_id = Column(String(64), ForeignKey("research_benchmarks.benchmark_id"), nullable=False, index=True)
    research_candidate_id = Column(String(64), ForeignKey("research_benchmark_candidates.candidate_id"), nullable=False, index=True)
    workflow_id = Column(String(64), ForeignKey("structure_screening_workflows.workflow_id"), nullable=False, index=True)
    quantum_region_id = Column(String(64), ForeignKey("quantum_region_models.quantum_region_id"), nullable=False, index=True)
    active_space_id = Column(String(64), ForeignKey("active_spaces.active_space_id"), nullable=False, index=True)
    fermionic_hamiltonian_id = Column(String(64), ForeignKey("fermionic_hamiltonians.hamiltonian_id"), nullable=False, index=True)
    qubit_hamiltonian_id = Column(String(64), ForeignKey("structure_qubit_hamiltonians.qubit_hamiltonian_id"), nullable=True, index=True)
    classical_reference_id = Column(String(64), ForeignKey("classical_references.reference_id"), nullable=True, index=True)
    vqe_execution_id = Column(String(64), ForeignKey("vqe_executions.execution_id"), nullable=True, index=True)
    source_candidate_sha256 = Column(String(64), nullable=False)
    fermionic_hamiltonian_sha256 = Column(String(64), nullable=False)
    pauli_hamiltonian_sha256 = Column(String(64), nullable=True)
    mapping_method = Column(String(32), nullable=False)
    qubit_count = Column(Integer, nullable=True)
    active_electrons = Column(Integer, nullable=False)
    active_orbitals = Column(Integer, nullable=False)
    spin_multiplicity = Column(Integer, nullable=False)
    basis_set = Column(String(64), nullable=False)
    fci_energy_hartree = Column(Float, nullable=True)
    exact_pauli_energy_hartree = Column(Float, nullable=True)
    vqe_energy_hartree = Column(Float, nullable=True)
    mapping_error_hartree = Column(Float, nullable=True)
    vqe_error_hartree = Column(Float, nullable=True)
    mapping_tolerance_hartree = Column(Float, nullable=False)
    vqe_target_tolerance_hartree = Column(Float, nullable=False)
    status = Column(String(64), nullable=False, index=True)
    result_qualification = Column(String(64), nullable=False)
    failure_code = Column(String(64), nullable=True)
    artifact_manifest = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    benchmark_role = Column(String(32), nullable=True)
    qualification_protocol_id = Column(String(128), nullable=True)
    qualification_protocol_version = Column(String(32), nullable=True)
    qualification_status = Column(String(96), nullable=True)
    qualification_recomputed = Column(Boolean, nullable=True)
    source_vqe_artifact_id = Column(String(160), nullable=True)
    source_vqe_artifact_path = Column(String(500), nullable=True)
    source_vqe_artifact_sha256 = Column(String(64), nullable=True)
    remediation_artifact_id = Column(String(160), nullable=True)
    remediation_artifact_path = Column(String(500), nullable=True)
    remediation_artifact_sha256 = Column(String(64), nullable=True)
    qualification_protocol_artifact_path = Column(String(500), nullable=True)
    qualification_protocol_artifact_sha256 = Column(String(64), nullable=True)
    scientific_adsorption_validation = Column(Boolean, nullable=False, default=False)
    ground_state_assessed = Column(Boolean, nullable=False, default=False)
    record_origin = Column(String(64), nullable=False, default="native_workflow")
    source_artifact_id = Column(String(160), nullable=True)
    source_artifact_path = Column(String(500), nullable=True)
    source_artifact_sha256 = Column(String(64), nullable=True)
    registration_scheme = Column(String(64), nullable=True)
    registration_key = Column(String(64), nullable=True, index=True)
    registered_at = Column(DateTime, nullable=True)
    registration_manifest = Column(JSON, nullable=True)


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
    record_origin = Column(String(64), nullable=False, default="native_workflow")
    source_artifact_id = Column(String(160), nullable=True)
    source_artifact_path = Column(String(500), nullable=True)
    source_artifact_sha256 = Column(String(64), nullable=True)
    registration_scheme = Column(String(64), nullable=True)
    registration_key = Column(String(64), nullable=True, index=True)
    registered_at = Column(DateTime, nullable=True)
    registration_manifest = Column(JSON, nullable=True)


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


class DistributedCompilationRecord(Base):
    """Persist one immutable distributed compilation input and its eight artifacts."""

    __tablename__ = "distributed_compilations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["vqe_execution_id", "owner_user_id"],
            ["vqe_executions.execution_id", "vqe_executions.owner_user_id"],
        ),
        ForeignKeyConstraint(
            ["qubit_hamiltonian_id", "owner_user_id"],
            [
                "structure_qubit_hamiltonians.qubit_hamiltonian_id",
                "structure_qubit_hamiltonians.owner_user_id",
            ],
        ),
        CheckConstraint(
            "actual_distributed_hardware_execution = 0",
            name="ck_distributed_compilation_not_hardware",
        ),
        CheckConstraint(
            "formal_attempts_started >= 0 AND formal_attempts_started <= formal_attempt_limit",
            name="ck_distributed_compilation_attempts",
        ),
        CheckConstraint(
            "status IN ("
            "'compilation_created',"
            "'distributed_executable_ready',"
            "'formal_attempt_consumed',"
            "'blocked_by_resource_guardrail',"
            "'compilation_failed'"
            ")",
            name="ck_distributed_compilation_status",
        ),
        UniqueConstraint(
            "compilation_id",
            "owner_user_id",
            name="uq_distributed_compilation_owner",
        ),
    )

    compilation_id = Column(String(64), primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    vqe_execution_id = Column(String(64), nullable=False, index=True)
    qubit_hamiltonian_id = Column(String(64), nullable=False, index=True)
    closure_benchmark_id = Column(
        String(64),
        ForeignKey("quantum_closure_benchmarks.closure_benchmark_id"),
        nullable=False,
        index=True,
    )
    benchmark_level = Column(String(32), nullable=False)
    execution_stage = Column(String(16), nullable=False)
    protocol_id = Column(String(128), nullable=False)
    protocol_version = Column(String(32), nullable=False)
    protocol_artifact_path = Column(String(500), nullable=False)
    protocol_sha256 = Column(String(64), nullable=False)
    topology_name = Column(String(64), nullable=False)
    topology_sha256 = Column(String(64), nullable=False)
    raw_qasm_sha256 = Column(String(64), nullable=False)
    canonical_circuit_sha256 = Column(String(64), nullable=False)
    parameter_sha256 = Column(String(64), nullable=False)
    hamiltonian_artifact_sha256 = Column(String(64), nullable=False)
    ordered_pauli_payload_sha256 = Column(String(64), nullable=False)
    execution_semantics_strategy = Column(String(96), nullable=False)
    partition_count = Column(Integer, nullable=False)
    status = Column(String(64), nullable=False, index=True)
    failure_code = Column(String(96), nullable=True)
    failure_stage = Column(String(64), nullable=True)
    failure_detail = Column(Text, nullable=True)
    input_manifest_path = Column(String(500), nullable=True)
    input_manifest_sha256 = Column(String(64), nullable=True)
    logical_snapshot_path = Column(String(500), nullable=True)
    logical_snapshot_sha256 = Column(String(64), nullable=True)
    partition_plan_path = Column(String(500), nullable=True)
    partition_plan_sha256 = Column(String(64), nullable=True)
    optimized_gate_order_path = Column(String(500), nullable=True)
    optimized_gate_order_sha256 = Column(String(64), nullable=True)
    target_topology_path = Column(String(500), nullable=True)
    target_topology_sha256 = Column(String(64), nullable=True)
    chip_mapping_path = Column(String(500), nullable=True)
    chip_mapping_sha256 = Column(String(64), nullable=True)
    communication_route_plan_path = Column(String(500), nullable=True)
    communication_route_plan_sha256 = Column(String(64), nullable=True)
    distributed_executable_path = Column(String(500), nullable=True)
    distributed_executable_sha256 = Column(String(64), nullable=True)
    baseline_metrics = Column(JSON, nullable=False, default=dict)
    optimized_metrics = Column(JSON, nullable=False, default=dict)
    resource_estimate = Column(JSON, nullable=False, default=dict)
    authorization_mode = Column(String(64), nullable=False)
    authorization_reference = Column(String(160), nullable=False)
    formal_attempt_limit = Column(Integer, nullable=False, default=1)
    formal_attempts_started = Column(Integer, nullable=False, default=0)
    actual_distributed_hardware_execution = Column(Boolean, nullable=False, default=False)
    row_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)


class DistributedSimulationRecord(Base):
    """Persist the sole formal statevector attempt and its two artifacts."""

    __tablename__ = "distributed_simulations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["compilation_id", "owner_user_id"],
            [
                "distributed_compilations.compilation_id",
                "distributed_compilations.owner_user_id",
            ],
        ),
        CheckConstraint(
            "actual_distributed_hardware_execution = 0",
            name="ck_distributed_simulation_not_hardware",
        ),
        CheckConstraint(
            "formal_attempt_number = 1",
            name="ck_distributed_simulation_attempt_number",
        ),
        CheckConstraint(
            "status IN ("
            "'simulation_running',"
            "'completed',"
            "'acceptance_not_met',"
            "'blocked_by_resource_guardrail',"
            "'simulation_failed'"
            ")",
            name="ck_distributed_simulation_status",
        ),
        UniqueConstraint(
            "compilation_id",
            "formal_attempt_number",
            name="uq_distributed_simulation_attempt",
        ),
    )

    simulation_id = Column(String(64), primary_key=True)
    compilation_id = Column(String(64), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    formal_attempt_number = Column(Integer, nullable=False, default=1)
    execution_backend_type = Column(String(64), nullable=False)
    execution_backend_detail = Column(String(160), nullable=False)
    shots = Column(Integer, nullable=False, default=0)
    status = Column(String(64), nullable=False, index=True)
    qualification_status = Column(String(96), nullable=False)
    failure_code = Column(String(96), nullable=True)
    failure_stage = Column(String(64), nullable=True)
    failure_detail = Column(Text, nullable=True)
    e_classical_exact = Column(Float, nullable=True)
    e_exact_pauli = Column(Float, nullable=True)
    e_logical_vqe = Column(Float, nullable=True)
    e_distributed = Column(Float, nullable=True)
    error_fci_vs_pauli = Column(Float, nullable=True)
    error_logical_vs_pauli = Column(Float, nullable=True)
    error_distributed_vs_logical = Column(Float, nullable=True)
    error_distributed_vs_pauli = Column(Float, nullable=True)
    statevector_fidelity = Column(Float, nullable=True)
    statevector_infidelity = Column(Float, nullable=True)
    n_alpha_expectation = Column(Float, nullable=True)
    n_beta_expectation = Column(Float, nullable=True)
    n_alpha_variance = Column(Float, nullable=True)
    n_beta_variance = Column(Float, nullable=True)
    acceptance_checks = Column(JSON, nullable=False, default=dict)
    resource_telemetry = Column(JSON, nullable=False, default=dict)
    result_artifact_path = Column(String(500), nullable=True)
    result_artifact_sha256 = Column(String(64), nullable=True)
    validation_report_path = Column(String(500), nullable=True)
    validation_report_sha256 = Column(String(64), nullable=True)
    distributed_semantics_simulated = Column(Boolean, nullable=False, default=False)
    actual_distributed_hardware_execution = Column(Boolean, nullable=False, default=False)
    row_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class DistributedIdempotencyRecord(Base):
    """Keep idempotency keys scoped by owner and action."""

    __tablename__ = "distributed_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "action_type",
            "idempotency_key",
            name="uq_distributed_idempotency_action",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(64), nullable=True)
    response_status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
