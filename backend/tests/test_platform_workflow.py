from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api.routers import platform
from backend.main import create_app


class PlatformWorkflowTests(unittest.TestCase):
    def setUp(self):
        platform.WORKFLOW_REPOSITORY.clear()
        self.client = TestClient(create_app(legacy_enabled=True))

    def test_legacy_platform_workflow_endpoints_remain_available(self):
        create_response = self.client.post(
            "/api/platform/workflows",
            json={
                "case_id": "case-li2s6-baseline",
                "candidate_material": "Li2S6",
                "execution_mode": "sync",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        workflow_id = created["workflow_id"]
        self.assertEqual(created["overall_status"], "completed")
        self.assertEqual(created["current_stage"], "aggregating")

        detail_response = self.client.get(f"/api/platform/workflows/{workflow_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["candidate_material"], "Li2S6")
        self.assertEqual(detail["completed_stage_count"], detail["total_stage_count"])

        stages_response = self.client.get(f"/api/platform/workflows/{workflow_id}/stages")
        self.assertEqual(stages_response.status_code, 200)
        stages = stages_response.json()
        self.assertEqual(len(stages), 7)
        self.assertEqual(stages[0]["stage_name"], "screening")
        self.assertEqual(stages[-1]["stage_name"], "aggregating")

        events_response = self.client.get(f"/api/platform/workflows/{workflow_id}/events")
        self.assertEqual(events_response.status_code, 200)
        events = events_response.json()
        self.assertTrue(any(item["event_type"] == "workflow_created" for item in events))
        self.assertTrue(any(item["event_type"] == "workflow_completed" for item in events))

        summary_response = self.client.get(f"/api/platform/workflows/{workflow_id}/summary")
        self.assertEqual(summary_response.status_code, 200)
        summary = summary_response.json()
        self.assertEqual(summary["overall_status"], "completed")
        self.assertIn("final_score", summary["summary"])

        result_response = self.client.get(f"/api/platform/workflows/{workflow_id}/result")
        self.assertEqual(result_response.status_code, 200)
        result = result_response.json()
        self.assertEqual(result["overall_status"], "completed")
        self.assertEqual(result["candidate_material"], "Li2S6")
        self.assertIn("summary", result["result_view"])
        self.assertIn("scientific_snapshot", result["result_view"])
        self.assertIn("artifacts", result["result_view"])

        artifacts_response = self.client.get(f"/api/platform/workflows/{workflow_id}/artifacts")
        self.assertEqual(artifacts_response.status_code, 200)
        artifacts = artifacts_response.json()
        self.assertIn("qasm_preview", artifacts["artifacts"])
        self.assertIn("topology_name", artifacts["artifacts"])

    def test_completed_legacy_workflow_cannot_be_cancelled(self):
        create_response = self.client.post(
            "/api/platform/workflows",
            json={
                "case_id": "case-li2s6-baseline",
                "candidate_material": "Li2S6",
                "execution_mode": "sync",
            },
        )
        workflow_id = create_response.json()["workflow_id"]

        cancel_response = self.client.post(f"/api/platform/workflows/{workflow_id}/cancel")
        self.assertEqual(cancel_response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
