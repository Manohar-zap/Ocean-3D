"""
Unit and Integration Tests for Global Gap Detection and Requirement 16 Failure Case.
"""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.adaptive.gap_detector import gap_detector
from app.adaptive.instrument_registry import instrument_registry
from app.adaptive.mission_optimizer import mission_optimizer
from app.adaptive.mission_simulator import mission_simulator


class TestGlobalGapDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_detect_all_global_gaps(self):
        gaps = gap_detector.detect_all_global_gaps()
        self.assertGreaterEqual(len(gaps), 5)

        # Check required fields on every detected gap
        for g in gaps:
            self.assertIn("id", g)
            self.assertIn("name", g)
            self.assertIn("latitude", g)
            self.assertIn("longitude", g)
            self.assertIn("depth_m", g)
            self.assertIn("priority_score", g)
            self.assertIn("priority_level", g)
            self.assertIn("reason", g)
            self.assertIn("nearest_observation_km", g)
            self.assertIn("nearest_platform_id", g)
            self.assertIn("observation_age_days", g)
            self.assertIn("depth_coverage_status", g)
            self.assertIn("missing_variables", g)
            self.assertGreaterEqual(g["priority_score"], 0.0)
            self.assertLessEqual(g["priority_score"], 100.0)

    def test_gap_api_endpoint_global(self):
        res = self.client.get("/api/adaptive/gaps")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("gaps", data)
        self.assertGreaterEqual(data["count"], 5)

    def test_requirement_16_failure_case_southern_ocean(self):
        # Dynamically detected Southern Ocean Polar Void is remote with NO reachable glider platform
        gaps = gap_detector.detect_all_global_gaps()
        sou_gap = next((g for g in gaps if "SOU" in g["id"] or "Southern Ocean" in g["name"]), None)
        self.assertIsNotNone(sou_gap)
        plan = mission_optimizer.plan_optimal_mission(sou_gap["latitude"], sou_gap["longitude"], sou_gap["depth_m"], "temperature")
        self.assertEqual(plan["decision"], "NO_FEASIBLE_PLATFORM")
        self.assertIsNone(plan["selected_winner"])

        sim = mission_simulator.simulate_mission(sou_gap["latitude"], sou_gap["longitude"], sou_gap["depth_m"], "temperature")
        self.assertEqual(sim["status"], "NO_FEASIBLE_MISSION")
        self.assertEqual(sim["decision"], "NO_FEASIBLE_PLATFORM")
        self.assertIn("recommended_alternatives", sim)
        self.assertGreaterEqual(len(sim["recommended_alternatives"]), 3)
        self.assertTrue(sim["is_simulated"])


if __name__ == "__main__":
    unittest.main()
