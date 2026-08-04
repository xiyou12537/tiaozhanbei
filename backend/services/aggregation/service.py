class ResultAggregationService:
    def build_result_view(self, payload: dict) -> dict:
        score = payload["score"]
        evaluation = payload["evaluation"]
        compiled_result = payload["compiled_result"]
        chemistry_model = payload["chemistry_model"]
        candidate_context = payload["candidate_context"]
        quantum_problem = payload["quantum_problem"]

        return {
            "workflow_id": payload["workflow_id"],
            "stage_name": "aggregating",
            "candidate_name": score["candidate_name"],
            "candidate_material": payload["candidate_material"],
            "overall_status": "completed",
            "summary": {
                "screening_passed": candidate_context["screening_passed"],
                "final_score": score["final_score"],
                "gatekeeping_passed": score["gatekeeping_passed"],
                "rank_position": score["rank_position"],
            },
            "scientific_snapshot": {
                "adsorption_energy": chemistry_model["adsorption_energy"],
                "qubit_count": quantum_problem["qubit_count"],
                "partition_count": compiled_result["partition_count"],
                "teleportations": compiled_result["teleportations"],
                "fidelity_score": evaluation["fidelity_score"],
                "energy_estimate": evaluation["energy_estimate"],
            },
            "artifacts": {
                "qasm_preview": quantum_problem["qasm_content"].splitlines()[:3],
                "topology_name": compiled_result["topology"]["name"],
            },
        }
