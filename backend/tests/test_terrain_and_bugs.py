"""
Regression tests for terrain endpoints, profile lat/lon inclusion, and compare dataset_id parameter.
"""
import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestTerrainAndBugs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_terrain_endpoints(self):
        # 1. Heightmap binary smoke test
        res_hm = self.client.get("/api/terrain/heightmap")
        self.assertEqual(res_hm.status_code, 200)
        self.assertEqual(res_hm.headers["content-type"], "application/octet-stream")
        # 2048 * 1024 * 4 bytes = 8,388,608 bytes
        self.assertEqual(len(res_hm.content), 2048 * 1024 * 4)

        # 2. Heightmap meta smoke test
        res_meta = self.client.get("/api/terrain/heightmap-meta")
        self.assertEqual(res_meta.status_code, 200)
        self.assertEqual(res_meta.headers["content-type"], "application/json")
        meta = res_meta.json()
        self.assertEqual(meta["width"], 2048)
        self.assertEqual(meta["height"], 1024)
        self.assertEqual(meta["dtype"], "float32-le")

    def test_profile_lat_lon(self):
        res_obs = self.client.get("/api/observations?platform_type=argo")
        self.assertEqual(res_obs.status_code, 200)
        markers = res_obs.json()["markers"]
        self.assertGreater(len(markers), 0)
        pid = markers[0]["platform_id"]

        res_prof = self.client.get(f"/api/observations/{pid}/profile")
        self.assertEqual(res_prof.status_code, 200)
        data = res_prof.json()
        self.assertGreater(len(data["profile"]), 0)

        # Assert each profile item has latitude and longitude
        for item in data["profile"]:
            self.assertIn("latitude", item)
            self.assertIn("longitude", item)
            self.assertIsInstance(item["latitude"], float)
            self.assertIsInstance(item["longitude"], float)

    def test_compare_with_dataset_id(self):
        res_obs = self.client.get("/api/observations?platform_type=argo")
        markers = res_obs.json()["markers"]
        pid = markers[0]["platform_id"]

        res_prof = self.client.get(f"/api/observations/{pid}/profile")
        profile = res_prof.json()["profile"]
        sample = profile[0]

        # Test compare with explicit dataset_id parameter
        url = f"/api/compare?platform_id={pid}&variable={sample['variable']}&depth={sample['depth']}&time={sample['time']}&dataset_id=incois_las_model"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["observation_id"].startswith(pid))
        self.assertIn("difference", data)


if __name__ == "__main__":
    unittest.main()
