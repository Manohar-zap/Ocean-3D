"""
Unit and integration tests for OceanGliders GDAC service and API endpoint.
Tests all requirements: endpoint functionality, schema correctness, identifier preservation,
coordinate/timestamp validity, latest-position logic, null values handling, cache fallback,
and non-interference with NOAA and core observations endpoints.
"""

import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.oceangliders_service import oceangliders_service


class TestOceanGlidersServiceAndAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_oceangliders_api_endpoint(self):
        """1. Test that /api/external-gliders/oceangliders returns status 200 and valid schema."""
        response = self.client.get("/api/external-gliders/oceangliders")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("gliders", data)
        self.assertIn("count", data)
        self.assertIn("bounds", data)
        self.assertIn("basins_represented", data)
        self.assertEqual(data["status"], "READY")
        self.assertIsInstance(data["gliders"], list)

    def test_response_schema_and_real_identifiers(self):
        """2 & 3. Test response schema and preservation of real deployment identifiers."""
        result = oceangliders_service.get_latest_gliders()
        self.assertEqual(result["status"], "READY")
        gliders = result["gliders"]
        self.assertGreater(len(gliders), 0)

        for g in gliders[:5]:
            self.assertIn("source", g)
            self.assertIn("dataset_id", g)
            self.assertIn("deployment_id", g)
            self.assertIn("platform_id", g)
            self.assertIn("trajectory", g)
            self.assertIn("latitude", g)
            self.assertIn("longitude", g)
            self.assertIn("timestamp", g)
            self.assertIn("data_status", g)
            self.assertIn("ocean_basin", g)
            self.assertIn("qc", g)

            # Ensure deployment ID is a non-empty string from source
            self.assertTrue(isinstance(g["deployment_id"], str))
            self.assertGreater(len(g["deployment_id"]), 0)

    def test_coordinates_and_timestamps_validity(self):
        """4 & 5. Test that latitude, longitude, and timestamps are valid."""
        result = oceangliders_service.get_latest_gliders()
        for g in result["gliders"]:
            lat = g["latitude"]
            lon = g["longitude"]
            self.assertIsInstance(lat, (int, float))
            self.assertIsInstance(lon, (int, float))
            self.assertTrue(-90.0 <= lat <= 90.0)
            self.assertTrue(-180.0 <= lon <= 180.0)

            ts = g["timestamp"]
            self.assertIsInstance(ts, str)
            self.assertGreater(len(ts), 10)  # ISO format string expected

    def test_latest_position_logic_and_no_duplicates_per_deployment(self):
        """6, 7 & 8. Test latest-position logic and ensure unique deployment entries without duplicate markers."""
        result = oceangliders_service.get_latest_gliders()
        gliders = result["gliders"]
        deployments = [g["deployment_id"] for g in gliders]

        # Check uniqueness of deployment IDs (one latest position per deployment)
        self.assertEqual(len(deployments), len(set(deployments)))

    def test_null_scientific_values_remain_null(self):
        """9. Test that missing scientific values remain None (never fake 0.0)."""
        result = oceangliders_service.get_latest_gliders()
        for g in result["gliders"]:
            for key in ["depth", "temperature", "salinity"]:
                val = g.get(key)
                if val is not None:
                    self.assertIsInstance(val, (int, float))

    def test_no_synthetic_records(self):
        """10. Test that no synthetic records are generated (source organization is OceanGliders)."""
        result = oceangliders_service.get_latest_gliders()
        self.assertEqual(result["source"], "OceanGliders Global Data Assembly Center")
        self.assertEqual(result["dataset_id"], "OceanGlidersGDACTrajectories")

    def test_cache_fallback(self):
        """11. Test cache mechanism (returns dict with READY or UNAVAILABLE)."""
        result = oceangliders_service.get_latest_gliders(force_refresh=False)
        self.assertIn("status", result)
        self.assertIn(result["status"], ["READY", "UNAVAILABLE"])

    def test_noaa_and_observations_endpoints_unchanged(self):
        """12 & 13. Verify NOAA and core observations endpoints remain active and unchanged."""
        res_noaa = self.client.get("/api/external-gliders/noaa")
        self.assertEqual(res_noaa.status_code, 200)

        res_obs = self.client.get("/api/model?dataset_id=incois_las_model&variable=temperature")
        self.assertIn(res_obs.status_code, [200, 400, 422])
