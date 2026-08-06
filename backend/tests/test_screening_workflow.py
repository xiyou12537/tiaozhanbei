from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api.routers import platform
from backend.main import create_app


class ScreeningWorkflowTests(unittest.TestCase):
    def setUp(self):
        platform.SCREENING_WORKFLOWS.clear()
        self.client = TestClient(create_app(legacy_enabled=True))
        self.created_workflow_ids: list[str] = []

    def tearDown(self):
        platform.SCREENING_WORKFLOWS.clear()
        for workflow_id in self.created_workflow_ids:
            platform.screening_workflow_repository.delete_workflow(workflow_id)

    def test_screening_workflow_builds_multi_material_leaderboard(self):
        response = self.client.post(
            "/api/platform/screening-workflows",
            json={
                "case_id": "li-s-demo",
                "candidate_materials": ["Fe-N4/C", "Co-N4/C", "MoS2"],
            },
        )

        self.assertEqual(response.status_code, 200)
        created = response.json()
        workflow_id = created["workflow_id"]
        self.created_workflow_ids.append(workflow_id)
        self.assertEqual(created["candidate_count"], 3)
        self.assertTrue(created["recommended_material"])
        self.assertTrue(created["created_at"])
        self.assertTrue(created["updated_at"])

        aggregate_response = self.client.get(f"/api/platform/screening-workflows/{workflow_id}")
        self.assertEqual(aggregate_response.status_code, 200)
        aggregate = aggregate_response.json()
        self.assertEqual(len(aggregate["candidate_results"]), 3)
        self.assertEqual(len(aggregate["classical_screening"]), 3)
        self.assertGreaterEqual(len(aggregate["quantum_refinement"]), 2)
        self.assertTrue(aggregate["explanations"])
        self.assertTrue(aggregate["created_at"])
        self.assertTrue(aggregate["updated_at"])

        platform.SCREENING_WORKFLOWS.clear()
        persisted_response = self.client.get(f"/api/platform/screening-workflows/{workflow_id}")
        self.assertEqual(persisted_response.status_code, 200)
        self.assertEqual(persisted_response.json()["workflow_id"], workflow_id)

        history_response = self.client.get("/api/platform/screening-workflows")
        self.assertEqual(history_response.status_code, 200)
        history = history_response.json()
        self.assertTrue(any(item["workflow_id"] == workflow_id for item in history))

        screening_response = self.client.get(f"/api/platform/workflows/{workflow_id}/classical-screening")
        self.assertEqual(screening_response.status_code, 200)
        screening_results = screening_response.json()["results"]
        self.assertEqual(len(screening_results), 3)
        screening_scores = {
            item["screening"]["classical_screening_score"]
            for item in screening_results
        }
        self.assertGreaterEqual(len(screening_scores), 3)

        refinement_response = self.client.get(f"/api/platform/workflows/{workflow_id}/quantum-refinement")
        self.assertEqual(refinement_response.status_code, 200)
        refinement_results = refinement_response.json()["results"]
        self.assertGreaterEqual(len(refinement_results), 2)
        for item in refinement_results:
            self.assertIn("hamiltonian_terms", item["quantum_problem"])
            self.assertIn("refined_adsorption_energy", item["quantum_refinement"])
            self.assertIn("execution_quality", item["distributed_execution"])

        leaderboard_response = self.client.get(f"/api/platform/workflows/{workflow_id}/leaderboard")
        self.assertEqual(leaderboard_response.status_code, 200)
        leaderboard = leaderboard_response.json()["leaderboard"]
        self.assertEqual(len(leaderboard), 3)
        final_scores = [item["score"]["final_score"] for item in leaderboard]
        rank_positions = [item["score"]["rank_position"] for item in leaderboard]
        self.assertEqual(final_scores, sorted(final_scores, reverse=True))
        self.assertEqual(rank_positions, [1, 2, 3])
        self.assertEqual(len(set(final_scores)), 3)
        self.assertEqual(leaderboard_response.json()["recommended_material"], leaderboard[0]["candidate_material"])

        material_id = screening_results[0]["material_profile"]["material_id"]
        explanation_response = self.client.get(
            f"/api/platform/workflows/{workflow_id}/candidate-explanations/{material_id}"
        )
        self.assertEqual(explanation_response.status_code, 200)
        explanation = explanation_response.json()["explanation"]
        self.assertTrue(explanation["recommendation_reason"])
        self.assertTrue(explanation["risk_notes"])

    def test_screening_workflow_requires_three_unique_materials(self):
        response = self.client.post(
            "/api/platform/screening-workflows",
            json={
                "case_id": "li-s-demo",
                "candidate_materials": ["Fe-N4/C", "Co-N4/C", "Co-N4/C"],
            },
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
