from backend.workers.handlers.aggregating import run_aggregating
from backend.workers.handlers.chem_modeling import run_chem_modeling
from backend.workers.handlers.distributed_compiling import run_distributed_compiling
from backend.workers.handlers.quantum_encoding import run_quantum_encoding
from backend.workers.handlers.scoring import run_scoring
from backend.workers.handlers.screening import run_screening
from backend.workers.handlers.simulation_evaluating import run_simulation_evaluating

HANDLERS = {
    "screening": run_screening,
    "chem_modeling": run_chem_modeling,
    "quantum_encoding": run_quantum_encoding,
    "distributed_compiling": run_distributed_compiling,
    "simulation_evaluating": run_simulation_evaluating,
    "scoring": run_scoring,
    "aggregating": run_aggregating,
}


def run_stage(stage_name: str, payload: dict) -> dict:
    return HANDLERS[stage_name](payload)
