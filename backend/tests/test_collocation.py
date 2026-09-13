"""
Unit & Integration Tests for Phase 2: Argo – Ocean Model Collocation Engine & API.
"""
import os
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.collocation import collocation_engine, haversine_distance_km


class TestCollocationEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_haversine_distance_km(self):
        """Test Haversine spherical distance calculation in kilometers."""
        # Distance between Kochi (9.80N, 75.80E) and Vizag (17.50N, 83.50E) ~1200 km
        dist = haversine_distance_km(9.80, 75.80, 17.50, 83.50)
        self.assertGreater(dist, 1000.0)
        self.assertLess(dist, 1400.0)

        # Same point distance should be 0.0 km
        dist_zero = haversine_distance_km(9.80, 75.80, 9.80, 75.80)
        self.assertEqual(dist_zero, 0.0)

    def test_collocate_point_residual_sign(self):
        """Test single point collocation, residual sign (residual = observed - model), and absolute error."""
        import os
        orig_gap = os.environ.get("MODEL_MAX_TIME_GAP_HOURS")
        os.environ["MODEL_MAX_TIME_GAP_HOURS"] = "10000.0"
        try:
            res = collocation_engine.collocate_point(
                platform_id="ARGO-5906203",
                variable="temperature",
                depth=10.0
            )
            self.assertEqual(res.platform_id, "ARGO-5906203")
            self.assertEqual(res.variable, "temperature")
            self.assertEqual(res.observation_unit, "degC")
            self.assertEqual(res.collocation_status, "VALID")

            # Explicit residual definition check: residual = observed_value - model_value
            expected_residual = round(res.observed_value - res.model_value, 4)
            self.assertEqual(res.residual, expected_residual)
            self.assertEqual(res.absolute_error, round(abs(expected_residual), 4))
            self.assertGreaterEqual(res.spatial_distance_km, 0.0)
        finally:
            if orig_gap: os.environ["MODEL_MAX_TIME_GAP_HOURS"] = orig_gap
            else: os.environ.pop("MODEL_MAX_TIME_GAP_HOURS", None)

    def test_collocate_profile_levels_and_metrics(self):
        """Test full vertical depth profile collocation and operational skill metrics (Bias, RMSE, R2, Willmott d)."""
        import os
        orig_gap = os.environ.get("MODEL_MAX_TIME_GAP_HOURS")
        os.environ["MODEL_MAX_TIME_GAP_HOURS"] = "10000.0"
        try:
            res = collocation_engine.collocate_profile(
                platform_id="ARGO-5906203",
                variable="temperature"
            )
            self.assertEqual(res.platform_id, "ARGO-5906203")
            self.assertGreater(res.collocation_count, 0)
            self.assertIn("bias", res.metrics)
            self.assertIn("rmse", res.metrics)
            self.assertIn("mae", res.metrics)
            self.assertIn("r2", res.metrics)
            self.assertIn("willmott_d", res.metrics)

            # Check residual sign across profile levels
            for level in res.levels:
                if level.collocation_status == "VALID" and level.model_value is not None:
                    self.assertEqual(level.residual, round(level.observed_value - level.model_value, 4))
        finally:
            if orig_gap: os.environ["MODEL_MAX_TIME_GAP_HOURS"] = orig_gap
            else: os.environ.pop("MODEL_MAX_TIME_GAP_HOURS", None)

    def test_invalid_platform_id_handling(self):
        """Test graceful exception handling when unknown platform ID is queried."""
        with self.assertRaises(ValueError):
            collocation_engine.collocate_point(platform_id="NON_EXISTENT_FLOAT_9999")

    def test_collocation_point_api_endpoint(self):
        """Test GET /api/collocation/point REST API endpoint."""
        response = self.client.get("/api/collocation/point?platform_id=ARGO-5906203&variable=temperature&depth=10.0")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["platform_id"], "ARGO-5906203")
        self.assertIn("residual", data)
        self.assertIn("observed_value", data)
        self.assertIn("model_value", data)
        self.assertIn("spatial_distance_km", data)

    def test_collocation_profile_api_endpoint(self):
        """Test GET /api/collocation/profile REST API endpoint."""
        response = self.client.get("/api/collocation/profile?platform_id=ARGO-5906203&variable=temperature")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["platform_id"], "ARGO-5906203")
        self.assertIn("levels", data)
        self.assertIn("metrics", data)
        self.assertGreater(data["collocation_count"], 0)


if __name__ == "__main__":
    unittest.main()
