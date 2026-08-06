from backend.services.compiler.service import DistributedCompilerService


def run_distributed_compiling(payload: dict) -> dict:
    service = DistributedCompilerService()
    compiled_result = service.compile(payload["quantum_problem"])
    return {
        "status": "success",
        "candidate_context": payload.get("candidate_context"),
        "chemistry_model": payload.get("chemistry_model"),
        "quantum_problem": payload["quantum_problem"],
        "compiled_result": compiled_result,
    }
