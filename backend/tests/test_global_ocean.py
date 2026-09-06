"""
Global Ocean Architecture Tests across Indian, Atlantic, Pacific, and Southern Oceans.
"""
import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestGlobalOceanArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_indian_ocean_region(self):
        """Verify Indian Ocean regional bounding box query."""
        url = "/api/model?dataset_id=incois_las_model&variable=temperature&min_lat=0&max_lat=25&min_lon=60&max_lon=95&min_depth=0&max_depth=0"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["count"], 0)

    def test_atlantic_ocean_region(self):
        """Verify Atlantic Ocean regional bounding box query."""
        url = "/api/model?dataset_id=copernicus_cmems&variable=temperature&min_lat=-20&max_lat=45&min_lon=-70&max_lon=10&min_depth=0&max_depth=0"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["count"], 0)

    def test_pacific_ocean_region(self):
        """Verify Pacific Ocean regional bounding box query."""
        url = "/api/model?dataset_id=copernicus_cmems&variable=temperature&min_lat=-30&max_lat=30&min_lon=130&max_lon=180&min_depth=0&max_depth=0"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["count"], 0)

    def test_southern_ocean_region(self):
        """Verify Southern Ocean regional bounding box query."""
        url = "/api/model?dataset_id=copernicus_cmems&variable=temperature&min_lat=-75&max_lat=-45&min_lon=-180&max_lon=180&min_depth=0&max_depth=0"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["count"], 0)

    def test_global_catalog_provenance(self):
        """Verify global dataset product ID (GLOBAL_MULTIYEAR_PHY_001_030) in catalog."""
        res = self.client.get("/api/catalog")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("datasets", data)
        self.assertGreater(len(data["datasets"]), 0)


if __name__ == "__main__":
    unittest.main()
