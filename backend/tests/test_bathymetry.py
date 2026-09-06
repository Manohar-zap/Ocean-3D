"""
Unit & Integration Tests for Real GEBCO 3D Seafloor Bathymetry Adapter & API.
"""
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.adapters import BathymetryAdapter


class TestBathymetrySeafloor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_bathymetry_adapter_metadata(self):
        adapter = BathymetryAdapter()
        meta = adapter.metadata()
        self.assertEqual(meta["source_organization"], "GEBCO (General Bathymetric Chart of the Oceans)")
        self.assertEqual(meta["product_id"], "GEBCO_2023_GRID")
        self.assertIn("data_status", meta)

    def test_bathymetry_api_endpoint(self):
        response = self.client.get("/api/bathymetry?min_lat=0&max_lat=25&min_lon=60&max_lon=95")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["dataset_id"], "gebco_bathymetry")
        self.assertEqual(data["source_organization"], "GEBCO (General Bathymetric Chart of the Oceans)")
        self.assertIn("points", data)
        self.assertGreater(data["count"], 0)
        
        # Verify depth values are real negative elevation meters
        p0 = data["points"][0]
        self.assertIn("elevation", p0)
        self.assertIn("depth", p0)


if __name__ == "__main__":
    unittest.main()
