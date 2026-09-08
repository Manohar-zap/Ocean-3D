import unittest
from fastapi.testclient import TestClient
from app.main import app

class TestSeaLevelSimulationAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_heightmap_meta_endpoint(self):
        response = self.client.get("/api/heightmap/meta")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["width"], 2048)
        self.assertEqual(data["height"], 1024)
        self.assertEqual(data["unit"], "meters")
        self.assertIn("min_elevation", data)
        self.assertIn("max_elevation", data)

    def test_heightmap_binary_endpoint(self):
        response = self.client.get("/api/heightmap")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/octet-stream")
        # 1024 * 2048 float32 = 2,097,152 float32s = 8,388,608 bytes
        self.assertEqual(len(response.content), 8388608)

if __name__ == "__main__":
    unittest.main()
