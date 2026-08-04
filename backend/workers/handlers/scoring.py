from backend.services.scoring.service import ScoringService


def run_scoring(payload: dict) -> dict:
    service = ScoringService()
    score = service.score(
        chemistry_model=payload["chemistry_model"],
        compiled_result=payload["compiled_result"],
        evaluation=payload["evaluation"],
        candidate_context=payload["candidate_context"],
    )
    return {
        "status": "success",
        "candidate_context": payload["candidate_context"],
        "chemistry_model": payload["chemistry_model"],
        "quantum_problem": payload["quantum_problem"],
        "compiled_result": payload["compiled_result"],
        "evaluation": payload["evaluation"],
        "score": score,
    }
