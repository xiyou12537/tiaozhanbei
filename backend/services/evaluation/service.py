class SimulationEvaluationService:
    def evaluate(self, payload: dict) -> dict:
        compiled = payload["compiled_result"]
        qubit_count = payload["quantum_problem"]["qubit_count"]
        fidelity_score = round(max(0.72, 0.98 - compiled["teleportations"] * 0.03), 3)
        energy_estimate = round(-0.4 - qubit_count * 0.05, 3)
        return {
            "shot_count": 1024,
            "fidelity_score": fidelity_score,
            "energy_estimate": energy_estimate,
            "depth_delta": compiled["teleportations"],
            "counts": {"0000": 640, "1111": 384},
        }
