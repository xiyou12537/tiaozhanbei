from backend.services.candidate.service import CandidateService


def run_screening(payload: dict) -> dict:
    service = CandidateService()
    context = service.build_context(
        candidate_material=payload["candidate_material"],
        case_id=payload.get("case_id"),
    )
    return {
        "status": "success",
        "screening_passed": context["screening_passed"],
        "candidate_context": context,
    }
