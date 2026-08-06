from backend.services.quantum.service import QuantumProblemService


def run_quantum_encoding(payload: dict) -> dict:
    service = QuantumProblemService()
    quantum_problem = service.encode_problem(payload["chemistry_model"])
    return {
        "status": "success",
        "candidate_context": payload.get("candidate_context"),
        "chemistry_model": payload["chemistry_model"],
        "quantum_problem": quantum_problem,
    }
