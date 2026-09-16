"""Tests for Argo Gap ML Model & Platform Exclusion Verification."""

import unittest
from matplotlib.path import Path as MplPath
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.ml.gap_model import argo_gap_pipeline
from app.adaptive.gap_detector import gap_detector
from app.storage import store


class TestArgoGapModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        gap_detector._init_indices()

    def test_01_model_loaded_and_metadata(self):
        """Verifies ArgoGapMLPipeline artifact exists and has trained metrics."""
        self.assertTrue(argo_gap_pipeline.is_loaded() or argo_gap_pipeline.load())
        meta = argo_gap_pipeline.metadata
        self.assertIn("metrics", meta)
        acc = meta["metrics"].get("test_accuracy", 0)
        self.assertGreaterEqual(acc, 95.0, f"Model test accuracy {acc}% should be >= 95%")

    def test_02_sampled_point_near_float(self):
        """Points within 100km of an active float must be classified as SAMPLED (no gap)."""
        pred = argo_gap_pipeline.predict(
            lat=10.0,
            lon=65.0,
            dist_nearest_km=80.0,
            density_250km=5,
            density_500km=12,
            directional_sparsity=0.2,
            bathy_depth=-3500.0,
        )
        self.assertEqual(pred.category, "SAMPLED")
        self.assertEqual(pred.color, "none")
        self.assertLessEqual(pred.severity_score, 45.0)

    def test_03_elevated_yellow_gap(self):
        """Points in moderate void (200 - 320km) must be classified as ELEVATED (Yellow)."""
        pred = argo_gap_pipeline.predict(
            lat=15.0,
            lon=88.0,
            dist_nearest_km=250.0,
            density_250km=1,
            density_500km=4,
            directional_sparsity=0.6,
            bathy_depth=-3000.0,
        )
        self.assertEqual(pred.category, "ELEVATED")
        self.assertEqual(pred.color, "yellow")
        self.assertGreaterEqual(pred.severity_score, 45.0)

    def test_04_critical_red_void(self):
        """Points in large void (>= 350km) must be classified as CRITICAL (Red)."""
        pred = argo_gap_pipeline.predict(
            lat=-10.0,
            lon=95.0,
            dist_nearest_km=480.0,
            density_250km=0,
            density_500km=0,
            directional_sparsity=1.0,
            bathy_depth=-4500.0,
        )
        self.assertEqual(pred.category, "CRITICAL")
        self.assertEqual(pred.color, "red")
        self.assertGreaterEqual(pred.severity_score, 75.0)

    def test_05_gap_detector_returns_red_and_yellow_gaps(self):
        """Global gap detection must return both Red and Yellow classified gaps."""
        gaps = gap_detector.detect_all_global_gaps()
        self.assertGreaterEqual(len(gaps), 8)

        colors = {g.get("color") for g in gaps}
        self.assertIn("red", colors, "Must have Red (Critical) gaps")
        self.assertIn("yellow", colors, "Must have Yellow (Elevated) gaps")

        for g in gaps:
            self.assertIn(g["color"], ["red", "yellow"])
            self.assertIn(g["priority_level"], ["CRITICAL", "ELEVATED", "HIGH", "MODERATE"])
            self.assertGreater(g["nearest_observation_km"], 150.0, "Centroid must be >= 150km from floats")

    def test_06_zero_active_platforms_inside_any_gap_polygon(self):
        """STRICT INVARIANT: No active in-situ platform should EVER be enclosed in a gap zone."""
        platforms = {r.platform_id: (r.latitude, r.longitude) for r in store.observation_records if r.platform_id}
        plat_coords = np.array(list(platforms.values()))
        self.assertGreater(len(plat_coords), 1000)

        gaps = gap_detector.detect_all_global_gaps()
        enclosed_count = 0
        enclosed_details = []

        for g in gaps:
            poly = g.get("polygon_coordinates", [])
            if len(poly) >= 4:
                mpl_p = MplPath(np.array(poly))
                in_mask = mpl_p.contains_points(plat_coords[:, [1, 0]])
                cnt = int(np.sum(in_mask))
                if cnt > 0:
                    enclosed_count += cnt
                    enclosed_details.append(f"{g['id']} has {cnt} platforms inside")

        self.assertEqual(
            enclosed_count,
            0,
            f"Active platforms found inside gap polygons: {', '.join(enclosed_details)}",
        )

    def test_07_api_gaps_endpoint_includes_color_and_nearest(self):
        """API endpoint /api/adaptive/gaps must serve gap color and nearest distance."""
        res = self.client.get("/api/adaptive/gaps")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("gaps", data)
        self.assertGreaterEqual(len(data["gaps"]), 8)

        first_gap = data["gaps"][0]
        self.assertIn("color", first_gap)
        self.assertIn("nearest_observation_km", first_gap)
        self.assertIn(first_gap["color"], ["red", "yellow"])
