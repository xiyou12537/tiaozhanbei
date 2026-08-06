from backend.services.evaluation.service import SimulationEvaluationService


def run_simulation_evaluating(payload: dict) -> dict:
    service = SimulationEvaluationService()
    evaluation = service.evaluate(payload)
    return {
        "status": "success",
        "candidate_context": payload.get("candidate_context"),
        "chemistry_model": payload.get("chemistry_model"),
        "quantum_problem": payload.get("quantum_problem"),
        "compiled_result": payload["compiled_result"],
        "evaluation": evaluation,
    }
