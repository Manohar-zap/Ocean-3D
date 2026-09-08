import unittest
import os
from fastapi.testclient import TestClient
from app.main import app
from app.adapters import get_data_mode

class TestMigrationAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_datamode_logic(self):
        # Default is auto
        self.assertEqual(get_data_mode(), "auto")

        # Test env override
        os.environ["DATA_MODE"] = "real"
        self.assertEqual(get_data_mode(), "real")
        os.environ["DATA_MODE"] = "auto" # reset

    def test_optional_dataset_id(self):
        # /api/model should default to copernicus_cmems
        response = self.client.get("/api/model?variable=temperature&min_depth=0&max_depth=0")
        self.assertEqual(response.status_code, 200)

    def test_observation_track(self):
        res_obs = self.client.get("/api/observations?platform_type=argo")
        data = res_obs.json()
        markers = data["markers"]
        self.assertGreater(len(markers), 0)
        pid = markers[0]["platform_id"]

        response = self.client.get(f"/api/observations/{pid}/track")
        self.assertEqual(response.status_code, 200)
        track = response.json()
        self.assertIsInstance(track, list)
        self.assertGreater(len(track), 0)
        # Verify sorted by time
        times = [t["time"] for t in track]
        self.assertEqual(times, sorted(times))

    def test_stale_dataset_ids(self):
        # Check catalog for only allowed dataset IDs
        res_cat = self.client.get("/api/catalog")
        ds_ids = [d["dataset_id"] for d in res_cat.json()["datasets"]]
        for ds_id in ds_ids:
            # Should start with authorized prefixes
            self.assertTrue(ds_id.startswith(("copernicus", "insitu", "argo", "ioos", "synthetic", "gebco")))
            self.assertNotIn("incois_las_model", ds_id)
            self.assertNotIn("bgc_model", ds_id)

if __name__ == "__main__":
    unittest.main()
