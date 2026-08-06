"""
Pydantic models for the quantum circuit partitioning API.

All request/response schemas are defined here so the FastAPI routers
and the React frontend share a single source of truth.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Circuit
# ---------------------------------------------------------------------------

class QasmUploadRequest(BaseModel):
    """Upload a circuit as raw QASM 2.0 text."""
    qasm_content: str = Field(
        ..., min_length=1, max_length=10_000_000,
        description="Raw OpenQASM 2.0 source text.",
    )


class CircuitInfo(BaseModel):
    """Summary info returned after parsing a QASM circuit."""
    circuit_id: str
    num_qubits: int
    total_gates: int
    single_qubit_gates: int
    multi_qubit_gates: int
    qubit_list: List[int]


# ---------------------------------------------------------------------------
# Partitioning
# ---------------------------------------------------------------------------

class PartitionRequest(BaseModel):
    """Parameters for a partitioning run."""
    circuit_id: str
    num_partitions: int = Field(default=2, ge=1, le=50)
    max_imbalance: int = Field(default=1, ge=0, le=20)
    b1: float = Field(default=10.0, ge=0.1, le=100.0)
    b2: float = Field(default=2.0, ge=0.1, le=100.0)
    alpha: float = Field(default=3.0, ge=0.1, le=20.0)
    beta: float = Field(default=1.0, ge=0.1, le=20.0)
    search: bool = Field(
        default=False,
        description="Enable grid search over (b1, b2)."
    )


class GridSearchRequest(BaseModel):
    """Parameters for a grid-search partitioning run."""
    circuit_id: str
    num_partitions: int = Field(default=2, ge=1, le=50)
    max_imbalance: int = Field(default=1, ge=0, le=20)
    alpha: float = Field(default=3.0, ge=0.1, le=20.0)
    beta: float = Field(default=1.0, ge=0.1, le=20.0)
    b1_list: List[float] = Field(default_factory=lambda: list(range(1, 21)))
    b2_list: List[float] = Field(default_factory=lambda: list(range(1, 21)))


class PartitionInfo(BaseModel):
    """Details of a single partition."""
    index: int
    qubits: List[int]
    size: int


class PartitionResultResponse(BaseModel):
    """Full result of a partitioning run."""
    task_id: str
    num_partitions: int
    partitions: List[PartitionInfo]
    teleportations: int
    global_gates: int
    optimized_gate_count: int
    params_used: Dict[str, float]
    elapsed_seconds: float
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Task status
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    message: str = ""
    result: Optional[Any] = None


# ---------------------------------------------------------------------------
# Chip mapping
# ---------------------------------------------------------------------------

class TopologyEdge(BaseModel):
    source: int
    target: int


class MappingRequest(BaseModel):
    """Find optimal chip mapping for a partition result."""
    task_id: str  # reference to a completed partition task
    topology_edges: List[TopologyEdge]


class MappingResultResponse(BaseModel):
    """Result of a chip-mapping computation."""
    mapping: Dict[str, str]  # {chip_id: partition_id}
    subgraph_cost: float
    total_epr_cost: int
    topology_edges: List[TopologyEdge]
    valid: bool


class TopologyCompareRequest(BaseModel):
    """Compare EPR costs across multiple topologies."""
    task_id: str
    topologies: Dict[str, List[TopologyEdge]]  # {name: edges}


class TopologyCompareResponse(BaseModel):
    task_id: str
    comparisons: List[MappingResultResponse]


# ---------------------------------------------------------------------------
# Topology presets
# ---------------------------------------------------------------------------

class TopologyPreset(BaseModel):
    name: str
    label: str
    description: str
    edges: List[TopologyEdge]


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

class GraphDataResponse(BaseModel):
    """JSON-serialisable graph for frontend rendering."""
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    extra: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# AI Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Send a message to the AI assistant."""
    message: str = Field(..., min_length=1, max_length=5000)


class ChatMessageResponse(BaseModel):
    """A single chat message in the history."""
    role: str
    content: str
    created_at: str


class ChatHistoryResponse(BaseModel):
    """Paginated chat history for the current user."""
    messages: List[ChatMessageResponse]


class KnowledgeDocumentCreateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    document_type: str = Field(default="system_doc", pattern="^(system_doc|paper)$")
    source_path: Optional[str] = Field(default=None, min_length=1, max_length=500)
    content: Optional[str] = Field(default=None, min_length=1)
    summary: Optional[str] = Field(default="")


class KnowledgeDocumentResponse(BaseModel):
    id: int
    name: str
    document_type: str
    source_path: str
    status: str
    summary: str
    chunk_count: int = 0
    created_at: str
    updated_at: str


class KnowledgeImportDirectoryRequest(BaseModel):
    directory_path: str = Field(..., min_length=1, max_length=500)
    document_type: str = Field(default="paper", pattern="^(system_doc|paper)$")
    recursive: bool = True


class KnowledgeImportDirectoryResponse(BaseModel):
    status: str
    directory_path: str
    document_type: str
    processed_count: int
    created_count: int
    indexed_count: int
    failed_count: int


class KnowledgeIndexResponse(BaseModel):
    document_id: int
    status: str
    chunk_count: int


class KnowledgeRebuildRequest(BaseModel):
    document_type: Optional[str] = Field(default=None, pattern="^(system_doc|paper)$")


class KnowledgeRebuildResponse(BaseModel):
    status: str
    document_count: int
    chunk_count: int
    document_type: Optional[str] = None


class KnowledgeStatsResponse(BaseModel):
    document_count: int
    chunk_count: int
    indexed_document_count: int
    uploaded_document_count: int
    failed_document_count: int
    system_doc_count: int
    paper_count: int


class KnowledgeDiagnosticIssueResponse(BaseModel):
    issue_type: str
    severity: str
    document_id: int
    document_name: str
    document_type: str
    status: str
    chunk_count: int
    source_path: str
    message: str


class KnowledgeDiagnosticsResponse(BaseModel):
    pdf_backend: str
    issue_count: int
    issues: List[KnowledgeDiagnosticIssueResponse]


class KnowledgeAnalyticsDocumentResponse(BaseModel):
    document_id: int
    document_name: str
    document_type: str
    reference_count: int
    avg_score: float
    last_referenced_at: str


class KnowledgeAnalyticsResponse(BaseModel):
    total_reference_count: int
    referenced_document_count: int
    unreferenced_indexed_document_count: int
    top_documents: List[KnowledgeAnalyticsDocumentResponse]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_type: Optional[str] = Field(default=None, pattern="^(system_doc|paper)$")


class KnowledgeSearchHitResponse(BaseModel):
    chunk_id: int
    document_id: int
    document_name: str
    document_type: str
    section_title: str
    content: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    query: str
    hits: List[KnowledgeSearchHitResponse]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    """Request to export a full result report."""
    task_id: str
    format: str = Field(default="json", pattern="^(json|zip)$")


class ExportResponse(BaseModel):
    task_id: str
    download_url: str
    filename: str
