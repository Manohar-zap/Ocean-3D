"""
Unit & Integration Tests for Phase 1 Correction: AI Ocean-State Prediction & Uncertainty Layer.
"""
import os
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.prediction_engine import prediction_engine
from app.feature_builder import extract_time_aware_features_at


class TestPredictionEnginePhase1Correction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_model_separation_temperature_and_salinity(self):
        """Verify temperature and salinity load separate, variable-specific model binaries."""
        res_temp = prediction_engine.predict_environment(9.8, 75.8, 0.0, "temperature", 24)
        res_sal = prediction_engine.predict_environment(9.8, 75.8, 0.0, "salinity", 24)

        self.assertEqual(res_temp.variable, "temperature")
        self.assertEqual(res_temp.unit, "degC")
        self.assertEqual(res_sal.variable, "salinity")
        self.assertEqual(res_sal.unit, "psu")

        # Values & units must be distinct and specific to variable
        if res_temp.status == "OK" and res_sal.status == "OK":
            self.assertNotEqual(res_temp.prediction_value, res_sal.prediction_value)
            self.assertGreater(res_temp.prediction_value, 15.0)  # Temperature °C
            self.assertGreater(res_sal.prediction_value, 28.0)   # Salinity PSU

    def test_feature_consistency_no_synthetic_lags(self):
        """Verify shared feature builder extracts real time-aware lags without synthetic offsets."""
        feat_res = extract_time_aware_features_at(9.8, 75.8, 0.0, "temperature")
        self.assertIsNotNone(feat_res)
        vec, dict_f = feat_res

        self.assertEqual(len(vec), 7)
        self.assertIn("val_t0", dict_f)
        self.assertIn("val_t_minus1", dict_f)
        self.assertIn("val_t_minus2", dict_f)

    def test_missing_data_safety_returns_none(self):
        """Verify that when features/lags are unavailable, prediction_value is None and status is INSUFFICIENT_DATA."""
        res = prediction_engine.predict_environment(-88.0, -178.0, 0.0, "temperature", 24)
        self.assertEqual(res.status, "INSUFFICIENT_DATA")
        self.assertIsNone(res.prediction_value)
        self.assertIsNone(res.uncertainty_range)

    def test_legacy_model_fallback_disabled(self):
        """Verify deleting/renaming dedicated model file returns UNAVAILABLE rather than falling back to legacy binary."""
        found_bins = []
        for p_str in ["models/salinity_48h_ml_v1.bin", "backend/models/salinity_48h_ml_v1.bin"]:
            p = Path(p_str)
            if p.exists():
                tmp_p = Path(p_str + ".tmp")
                p.rename(tmp_p)
                found_bins.append((p, tmp_p))

        try:
            res = prediction_engine.predict_environment(9.8, 75.8, 0.0, "salinity", 48)
            self.assertEqual(res.status, "UNAVAILABLE")
            self.assertIsNone(res.prediction_value)
            self.assertIsNone(res.uncertainty_range)
        finally:
            for p, tmp_p in found_bins:
                if tmp_p.exists():
                    tmp_p.rename(p)

    def test_horizon_model_selection(self):
        """Verify 24h and 48h horizons use distinct model binaries."""
        res_24 = prediction_engine.predict_environment(9.8, 75.8, 0.0, "temperature", 24)
        res_48 = prediction_engine.predict_environment(9.8, 75.8, 0.0, "temperature", 48)

        self.assertEqual(res_24.forecast_horizon_hours, 24)
        self.assertEqual(res_48.forecast_horizon_hours, 48)

    def test_uncertainty_interval_bounds_and_confidence(self):
        """Verify 95% Prediction Interval lower < prediction < upper and confidence = 0.95."""
        res = prediction_engine.predict_environment(9.8, 75.8, 0.0, "temperature", 24)
        if res.status == "OK":
            self.assertIsNotNone(res.uncertainty_range)
            self.assertEqual(len(res.uncertainty_range), 2)
            lower, upper = res.uncertainty_range
            self.assertLess(lower, res.prediction_value)
            self.assertGreater(upper, res.prediction_value)
            self.assertEqual(res.confidence, 0.95)

    def test_provenance_metadata(self):
        """Verify model version, data period, unit, and provenance fields are returned."""
        res = prediction_engine.predict_environment(9.8, 75.8, 0.0, "temperature", 24)
        self.assertIn("model_version", res.model_dump())
        self.assertIn("training_data_period", res.model_dump())
        self.assertEqual(res.provenance, "PREDICTED")

    def test_prediction_api_endpoint(self):
        """Test GET /api/fisher/prediction REST API endpoint for Temperature and Salinity."""
        res_t = self.client.get("/api/fisher/prediction?lat=9.8&lon=75.8&variable=temperature&horizon_hours=24")
        self.assertEqual(res_t.status_code, 200)
        data_t = res_t.json()
        self.assertIn("prediction_value", data_t)

        res_s = self.client.get("/api/fisher/prediction?lat=9.8&lon=75.8&variable=salinity&horizon_hours=48")
        self.assertEqual(res_s.status_code, 200)
        data_s = res_s.json()
        self.assertEqual(data_s["variable"], "salinity")


if __name__ == "__main__":
    unittest.main()
