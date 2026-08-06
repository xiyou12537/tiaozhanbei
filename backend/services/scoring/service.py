class ScoringService:
    def score(
        self,
        chemistry_model: dict,
        compiled_result: dict,
        evaluation: dict,
        candidate_context: dict,
    ) -> dict:
        chem_score = round(abs(chemistry_model["adsorption_energy"]) * 100, 2)
        deploy_score = round(
            max(10.0, 100 - compiled_result["teleportations"] * 15 - compiled_result["partition_count"] * 5),
            2,
        )
        fidelity_component = round(evaluation["fidelity_score"] * 100, 2)
        final_score = round((chem_score * 0.4) + (deploy_score * 0.3) + (fidelity_component * 0.3), 2)
        return {
            "candidate_name": candidate_context["candidate_name"],
            "gatekeeping_passed": evaluation["fidelity_score"] >= 0.75,
            "chem_score": chem_score,
            "deploy_score": deploy_score,
            "final_score": final_score,
            "rank_position": 1,
        }
