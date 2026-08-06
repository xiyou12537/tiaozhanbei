from backend.services.chemistry.service import ChemistryModelingService


def run_chem_modeling(payload: dict) -> dict:
    service = ChemistryModelingService()
    chemistry_model = service.build_model(payload["candidate_context"])
    return {
        "status": "success",
        "candidate_context": payload["candidate_context"],
        "chemistry_model": chemistry_model,
    }
