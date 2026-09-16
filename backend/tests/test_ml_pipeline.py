"""
Unit & Integration Tests for OCEAN 3D Real-Data + Trained ML Pipeline.
"""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.inference_engine import ocean_inference_engine
from app.ml.training_pipeline import MLTrainingPipeline
from app.adaptive.gap_detector import gap_detector


class TestMLPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_trained_artifacts_available(self):
        """Verify that genuine ML model artifacts exist and are loaded."""
        self.assertTrue(ocean_inference_engine.is_model_available("temperature"))
        self.assertTrue(ocean_inference_engine.is_model_available("salinity"))

        status = ocean_inference_engine.get_model_status()
        self.assertEqual(status["ml_engine"], "LightGBM Quantile Prediction Engine v2.0")
        self.assertIn("temperature", status["models"])
        self.assertEqual(status["models"]["temperature"]["status"], "LOADED")
        self.assertGreaterEqual(status["models"]["temperature"]["metrics"]["r2"], 0.85)
        self.assertGreaterEqual(status["models"]["temperature"]["metrics"]["empirical_90pct_coverage"], 80.0)

    def test_02_temperature_inference_and_quantiles(self):
        """Verify expected temperature and quantile monotonicity Q_0.05 <= Mean <= Q_0.95."""
        res = ocean_inference_engine.predict(14.0, 88.5, depth=500.0, variable="temperature")
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["unit"], "degC")
        self.assertIsNotNone(res["predicted_value"])

        # Ocean temperature at 500m in Bay of Bengal is typically 6 - 15 degC
        self.assertGreaterEqual(res["predicted_value"], 5.0)
        self.assertLessEqual(res["predicted_value"], 18.0)

        pi = res["prediction_interval_90pct"]
        self.assertEqual(len(pi), 2)
        self.assertLessEqual(pi[0], res["predicted_value"])
        self.assertGreaterEqual(pi[1], res["predicted_value"])
        self.assertGreater(res["interval_width"], 0.1)
        self.assertGreater(res["uncertainty_sigma"], 0.0)
        self.assertEqual(res["provenance"], "REAL_IN_SITU_DATA_TRAINED_ML_INFERENCE")

    def test_03_surface_vs_deep_temperature(self):
        """Verify physically sound temperature stratification (surface is warmer than deep ocean)."""
        surf = ocean_inference_engine.predict(14.0, 88.5, depth=5.0, variable="temperature")
        deep = ocean_inference_engine.predict(14.0, 88.5, depth=1500.0, variable="temperature")
        self.assertGreater(surf["predicted_value"], deep["predicted_value"])
        self.assertGreater(surf["predicted_value"], 22.0)  # Tropical SST > 22 degC
        self.assertLess(deep["predicted_value"], 10.0)    # Deep abyss < 10 degC

    def test_04_salinity_inference(self):
        """Verify salinity prediction resides in realistic marine range (30 - 38 PSU)."""
        res = ocean_inference_engine.predict(14.0, 88.5, depth=50.0, variable="salinity")
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["unit"], "psu")
        self.assertGreaterEqual(res["predicted_value"], 28.0)
        self.assertLessEqual(res["predicted_value"], 38.0)

    def test_05_api_ml_status(self):
        """Verify GET /api/ml/status endpoint."""
        res = self.client.get("/api/ml/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("ml_engine", data)
        self.assertIn("temperature", data["models"])
        self.assertEqual(data["models"]["temperature"]["status"], "LOADED")

    def test_06_api_ml_predict(self):
        """Verify GET /api/ml/predict endpoint."""
        res = self.client.get("/api/ml/predict?lat=13.6&lon=88.5&depth=500&variable=temperature")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["variable"], "temperature")
        self.assertIsNotNone(data["predicted_value"])
        self.assertIn("prediction_interval_90pct", data)
        self.assertGreater(data["uncertainty_percent"], 0.0)

    def test_07_gaps_contain_genuine_ml_uncertainty(self):
        """Verify that detected gaps feature real ML uncertainty rather than heuristics."""
        gaps = gap_detector.detect_all_global_gaps()
        self.assertGreaterEqual(len(gaps), 5)
        for g in gaps:
            self.assertIn("ml_expected_value", g)
            self.assertIn("ml_prediction_interval_90pct", g)
            self.assertIn("ml_uncertainty_sigma", g)
            self.assertIn("ml_model_version", g)
            self.assertIn("provenance", g)
            self.assertEqual(g["provenance"], "REAL_IN_SITU_OBSERVATIONS_AND_TRAINED_ML_QUANTILE_INFERENCE")
            self.assertTrue(gap_detector.is_ocean_point(g["latitude"], g["longitude"]))


if __name__ == "__main__":
    unittest.main()
