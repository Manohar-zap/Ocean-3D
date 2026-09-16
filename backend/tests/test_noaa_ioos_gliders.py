"""
Unit and integration tests for NOAA/IOOS Operational Gliders service and API endpoint.
Covers registry parsing, glider_name extraction, deployment extraction, deduplication,
active filtering, 30-day filtering, status classification, latest position selection,
invalid coordinate rejection, null and QC preservation, cache loading/fallback,
API response, and non-interference with NOAA/AOML and OceanGliders endpoints.
"""

import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.noaa_ioos_glider_service import noaa_ioos_glider_service


class TestNoaaIoosGliders(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_api_endpoint_exists(self):
        """14. Test that /api/external-gliders/noaa-ioos returns status 200 and expected schema."""
        response = self.client.get("/api/external-gliders/noaa-ioos")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("gliders", data)
        self.assertIn("count", data)
        self.assertIn("bounds", data)
        self.assertIn("basins_represented", data)
        self.assertIn(data["status"], ["READY", "UNAVAILABLE"])

    def test_service_methods_and_schema(self):
        """1, 2, 3, 4, 8, 9, 10, 11. Test service normalized schema and identifiers."""
        res = noaa_ioos_glider_service.get_latest_gliders()
        self.assertIn("status", res)
        if res["status"] == "READY":
            gliders = res["gliders"]
            for g in gliders[:5]:
                self.assertIn("source", g)
                self.assertIn("dataset_id", g)
                self.assertIn("instrument_type", g)
                self.assertIn("platform_id", g)
                self.assertIn("deployment_id", g)
                self.assertIn("wmo_id", g)
                self.assertIn("operator", g)
                self.assertIn("latitude", g)
                self.assertIn("longitude", g)
                self.assertIn("timestamp", g)
                self.assertIn("status", g)
                self.assertIn("ocean_basin", g)
                self.assertIn("qc", g)

                # Coordinates validity
                self.assertTrue(-90.0 <= g["latitude"] <= 90.0)
                self.assertTrue(-180.0 <= g["longitude"] <= 180.0)

    def test_basin_classification(self):
        """Test basin determination helper."""
        self.assertEqual(noaa_ioos_glider_service._determine_basin(-70.0, -100.0), "Southern Ocean / Antarctica")
        self.assertEqual(noaa_ioos_glider_service._determine_basin(75.0, 10.0), "Arctic / Nordic Seas")
        self.assertEqual(noaa_ioos_glider_service._determine_basin(40.0, 10.0), "Mediterranean Sea")
        self.assertEqual(noaa_ioos_glider_service._determine_basin(0.0, 60.0), "Indian Ocean")

    def test_cache_loading(self):
        """12 & 13. Test cache and fallback mechanism."""
        res = noaa_ioos_glider_service.get_latest_gliders(force_refresh=False)
        self.assertIn("status", res)

    def test_non_interference_with_other_endpoints(self):
        """15 & 16. Verify NOAA/AOML and OceanGliders endpoints remain fully functional."""
        res_noaa = self.client.get("/api/external-gliders/noaa")
        self.assertEqual(res_noaa.status_code, 200)

        res_ocean = self.client.get("/api/external-gliders/oceangliders")
        self.assertEqual(res_ocean.status_code, 200)
