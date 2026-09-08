"""
Comprehensive Unit Tests for OCEAN 3D Backend Endpoints & Adapters.
"""
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.adapters import ModelNetCDFAdapter, run_ingestion


class TestOCEAN3DImprovements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_volume_endpoint(self):
        """Test multi-depth volume endpoint for stacked water column."""
        url = "/api/model/volume?variable=temperature&depths=0,100,500"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["dataset_id"], "copernicus_cmems")
        self.assertEqual(data["variable"], "temperature")
        self.assertIn("layers", data)
        self.assertIn("0.0", data["layers"])
        self.assertIn("100.0", data["layers"])
        self.assertIn("500.0", data["layers"])

    def test_adapter_ingestion(self):
        """Test ingestion worker & adapter framework consistency."""
        records, catalog = run_ingestion()
        self.assertGreater(len(records), 0)
        self.assertIn("copernicus_cmems", catalog)
        self.assertIn("argo_gdac", catalog)

    def test_netcdf_adapter_can_handle(self):
        adapter = ModelNetCDFAdapter()
        self.assertTrue(adapter.can_handle("incois_las_model"))
        self.assertTrue(adapter.can_handle("sample_data.nc"))
        self.assertFalse(adapter.can_handle("unknown_format.txt"))


if __name__ == "__main__":
    unittest.main()
