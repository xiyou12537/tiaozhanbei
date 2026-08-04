from backend.services.aggregation.service import ResultAggregationService


def run_aggregating(payload: dict) -> dict:
    service = ResultAggregationService()
    result_view = service.build_result_view(payload)
    return {
        "status": "success",
        "candidate_context": payload["candidate_context"],
        "chemistry_model": payload["chemistry_model"],
        "quantum_problem": payload["quantum_problem"],
        "compiled_result": payload["compiled_result"],
        "evaluation": payload["evaluation"],
        "score": payload["score"],
        "result_view": result_view,
    }
