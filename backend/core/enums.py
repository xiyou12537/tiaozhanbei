from enum import Enum


class WorkflowStatus(str, Enum):
    CREATED = "created"
    VALIDATED = "validated"
    SCREENING = "screening"
    CHEM_MODELING = "chem_modeling"
    QUANTUM_ENCODING = "quantum_encoding"
    DISTRIBUTED_COMPILING = "distributed_compiling"
    SIMULATION_EVALUATING = "simulation_evaluating"
    SCORING = "scoring"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_COMPLETED = "partial_completed"
    CANCELLED = "cancelled"


class StageName(str, Enum):
    SCREENING = "screening"
    CHEM_MODELING = "chem_modeling"
    QUANTUM_ENCODING = "quantum_encoding"
    DISTRIBUTED_COMPILING = "distributed_compiling"
    SIMULATION_EVALUATING = "simulation_evaluating"
    SCORING = "scoring"
    AGGREGATING = "aggregating"


class StageRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
