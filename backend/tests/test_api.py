"""
Unit tests for OCEAN 3D FastAPI backend endpoints.
"""
import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestOCEAN3DAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertGreater(data["model_records"], 0)
        self.assertGreater(data["observation_records"], 0)
        self.assertGreater(len(data["datasets"]), 0)

    def test_catalog(self):
        response = self.client.get("/api/catalog")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("datasets", data)
        self.assertGreaterEqual(len(data["datasets"]), 2)
        ds_ids = [d["dataset_id"] for d in data["datasets"]]
        self.assertIn("incois_las_model", ds_ids)

    def test_model_query(self):
        response = self.client.get("/api/model?dataset_id=incois_las_model&variable=temperature&min_depth=0&max_depth=0")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["count"], 0)
        self.assertEqual(len(data["points"]), data["count"])
        self.assertIn("unit", data)
        self.assertIn("time", data)

    def test_model_query_validation(self):
        # Invalid lat range
        response = self.client.get("/api/model?dataset_id=incois_las_model&variable=temperature&min_lat=10&max_lat=5")
        self.assertEqual(response.status_code, 400)

        # Non-existent variable/depth range -> 404
        response = self.client.get("/api/model?dataset_id=incois_las_model&variable=nonexistent&min_depth=0&max_depth=0")
        self.assertEqual(response.status_code, 404)

    def test_model_times(self):
        response = self.client.get("/api/model/times?dataset_id=incois_las_model")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["dataset_id"], "incois_las_model")
        self.assertGreater(len(data["times"]), 0)

        # Unknown dataset
        res_err = self.client.get("/api/model/times?dataset_id=unknown_ds")
        self.assertEqual(res_err.status_code, 404)

    def test_observations(self):
        response = self.client.get("/api/observations?platform_type=argo")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["count"], 0)
        self.assertEqual(len(data["markers"]), data["count"])

    def test_observation_profile(self):
        res_obs = self.client.get("/api/observations?platform_type=argo")
        markers = res_obs.json()["markers"]
        self.assertGreater(len(markers), 0)
        pid = markers[0]["platform_id"]

        response = self.client.get(f"/api/observations/{pid}/profile")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["platform_id"], pid)
        self.assertGreater(len(data["profile"]), 0)

    def test_compare(self):
        res_obs = self.client.get("/api/observations?platform_type=argo")
        markers = res_obs.json()["markers"]
        pid = markers[0]["platform_id"]

        res_prof = self.client.get(f"/api/observations/{pid}/profile")
        profile = res_prof.json()["profile"]
        sample = profile[0]

        url = f"/api/compare?platform_id={pid}&variable={sample['variable']}&depth={sample['depth']}&time={sample['time']}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["observation_id"].startswith(pid))
        self.assertIn("difference", data)
        self.assertIn("model_value", data)
        self.assertIn("observation_value", data)

    def test_export(self):
        response = self.client.get("/api/export?kind=model&dataset_id=incois_las_model&variable=temperature&min_depth=0&max_depth=0")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        lines = response.text.strip().split("\n")
        self.assertGreater(len(lines), 1)
        self.assertTrue(lines[0].startswith("kind,dataset_id,variable"))


if __name__ == "__main__":
    unittest.main()
