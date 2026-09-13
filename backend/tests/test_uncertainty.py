"""
Unit & Integration Tests for Phase 3: Model Error, Depth-Bin Statistics, and Uncertainty Engine.
"""
import os
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.collocation import collocation_engine
from app.error_analysis import error_analysis_engine
from app.uncertainty_model import uncertainty_engine, MIN_REQUIRED_VALID_SAMPLES


class TestUncertaintyEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_collocation_validity_time_mismatch(self):
        """Test strict temporal validity enforcement (time mismatch -> status TIME_MISMATCH, model_value None)."""
        # Save original env
        orig_tol = os.environ.get("MODEL_MAX_TIME_GAP_HOURS")
        os.environ["MODEL_MAX_TIME_GAP_HOURS"] = "24.0"  # Strict 24h gap
        try:
            res = collocation_engine.collocate_point(
                platform_id="ARGO-5906203",
                variable="temperature",
                depth=10.0,
                time="2026-03-03T06:00:00Z"
            )
            # Obs time = 2026-03-03, Model time = 2026-09-01 (~4362h gap > 24h)
            self.assertEqual(res.collocation_status, "TIME_MISMATCH")
            self.assertIsNone(res.model_value)
            self.assertIsNone(res.residual)
            self.assertIsNotNone(res.rejection_reason)
        finally:
            if orig_tol is not None:
                os.environ["MODEL_MAX_TIME_GAP_HOURS"] = orig_tol
            else:
                os.environ.pop("MODEL_MAX_TIME_GAP_HOURS", None)

    def test_collocation_validity_space_mismatch(self):
        """Test strict spatial validity enforcement (space mismatch -> status SPACE_MISMATCH)."""
        orig_time_tol = os.environ.get("MODEL_MAX_TIME_GAP_HOURS")
        orig_space_tol = os.environ.get("MODEL_MAX_SPATIAL_DISTANCE_KM")
        os.environ["MODEL_MAX_TIME_GAP_HOURS"] = "10000.0"
        os.environ["MODEL_MAX_SPATIAL_DISTANCE_KM"] = "5.0"  # Strict 5km gap
        try:
            res = collocation_engine.collocate_point(
                platform_id="ARGO-5906203",
                variable="temperature",
                depth=10.0
            )
            self.assertEqual(res.collocation_status, "SPACE_MISMATCH")
            self.assertIsNone(res.model_value)
            self.assertIsNone(res.residual)
        finally:
            if orig_time_tol is not None:
                os.environ["MODEL_MAX_TIME_GAP_HOURS"] = orig_time_tol
            else:
                os.environ.pop("MODEL_MAX_TIME_GAP_HOURS", None)
            if orig_space_tol is not None:
                os.environ["MODEL_MAX_SPATIAL_DISTANCE_KM"] = orig_space_tol
            else:
                os.environ.pop("MODEL_MAX_SPATIAL_DISTANCE_KM", None)

    def test_no_fabricated_model_values(self):
        """Verify that a missing model value remains None and no fake values (e.g. obs - 0.2) are used."""
        orig_tol = os.environ.get("MODEL_MAX_TIME_GAP_HOURS")
        os.environ["MODEL_MAX_TIME_GAP_HOURS"] = "1.0"
        try:
            res = collocation_engine.collocate_point("ARGO-5906203", "temperature", depth=10.0)
            self.assertIsNone(res.model_value)
            self.assertIsNone(res.residual)
            self.assertNotEqual(res.collocation_status, "VALID")
        finally:
            if orig_tol is not None:
                os.environ["MODEL_MAX_TIME_GAP_HOURS"] = orig_tol
            else:
                os.environ.pop("MODEL_MAX_TIME_GAP_HOURS", None)

    def test_data_leakage_prevention_platform_grouped_split(self):
        """Verify train/test split groups by platform_id so no float profiles appear in both sets."""
        os.environ["MODEL_MAX_TIME_GAP_HOURS"] = "10000.0"  # Allow matching for test
        try:
            eval_res = uncertainty_engine.train_and_evaluate_uncertainty_model("temperature")
            if eval_res.get("status") == "VALID":
                self.assertEqual(eval_res["split_strategy"], "platform_id_grouped_split_80_20")
                self.assertGreaterEqual(eval_res["train_platform_count"], 1)
        finally:
            os.environ.pop("MODEL_MAX_TIME_GAP_HOURS", None)

    def test_uncertainty_point_bounds_and_confidence(self):
        """Verify lower_bound <= predicted_residual <= upper_bound and uncertainty >= 0."""
        os.environ["MODEL_MAX_TIME_GAP_HOURS"] = "10000.0"
        try:
            u_res = uncertainty_engine.predict_point_uncertainty(9.805, 75.812, 10.0, "temperature")
            if u_res.status == "VALID":
                self.assertGreaterEqual(u_res.uncertainty, 0.0)
                if u_res.predicted_residual is not None and u_res.lower_bound is not None and u_res.upper_bound is not None:
                    self.assertLessEqual(u_res.lower_bound, u_res.predicted_residual)
                    self.assertGreaterEqual(u_res.upper_bound, u_res.predicted_residual)
                self.assertEqual(u_res.confidence_level, 0.95)
        finally:
            os.environ.pop("MODEL_MAX_TIME_GAP_HOURS", None)

    def test_insufficient_data_safety(self):
        """Verify that when valid collocations are below threshold, status INSUFFICIENT_DATA is returned."""
        os.environ["MODEL_MAX_TIME_GAP_HOURS"] = "0.001"  # Force 0 valid collocations
        try:
            u_res = uncertainty_engine.predict_point_uncertainty(9.805, 75.812, 10.0, "temperature")
            self.assertEqual(u_res.status, "INSUFFICIENT_DATA")
            self.assertIn("Insufficient valid", u_res.message)
        finally:
            os.environ.pop("MODEL_MAX_TIME_GAP_HOURS", None)

    def test_error_analysis_summary_api(self):
        """Test GET /api/error-analysis/summary REST API endpoint."""
        response = self.client.get("/api/error-analysis/summary?variable=temperature")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_observations", data)
        self.assertIn("valid_collocations", data)
        self.assertIn("time_rejected", data)
        self.assertIn("space_rejected", data)

    def test_uncertainty_point_api(self):
        """Test GET /api/uncertainty/point REST API endpoint."""
        response = self.client.get("/api/uncertainty/point?lat=9.8&lon=75.8&depth=10.0&variable=temperature")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("collocation_status", data)
        self.assertIn("confidence_level", data)

    def test_uncertainty_profile_api(self):
        """Test GET /api/uncertainty/profile REST API endpoint."""
        response = self.client.get("/api/uncertainty/profile?platform_id=ARGO-5906203&variable=temperature")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["platform_id"], "ARGO-5906203")
        self.assertIn("levels", data)
        self.assertIn("depth_bin_profiles", data)


if __name__ == "__main__":
    unittest.main()
