"""
Integration & Provenance Tests for Real Ocean Dataset Adapters.
"""
import os
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.adapters import CopernicusMarineAdapter, ModelNetCDFAdapter, parse_netcdf_records, run_ingestion


class TestRealDataIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_copernicus_adapter_metadata(self):
        """Verify Copernicus Marine Service adapter metadata & provenance attributes."""
        adapter = CopernicusMarineAdapter()
        meta = adapter.metadata()
        self.assertEqual(meta["source_organization"], "Copernicus Marine Service")
        self.assertEqual(meta["product_id"], "cmems_mod_glo_phy_anfc_0.083deg_P1D-m")
        self.assertIn("data_status", meta)
        self.assertIn(meta["data_status"], ["REAL DATA", "CACHED REAL DATA"])

    def test_incois_netcdf_ingestion(self):
        """Verify real NetCDF sample ingestion and coordinate normalization."""
        sample_path = "sample_incois_model.nc"
        if not os.path.exists(sample_path) and os.path.exists("backend/sample_incois_model.nc"):
            sample_path = "backend/sample_incois_model.nc"

        records = parse_netcdf_records(sample_path, "incois_las_model", "CACHED REAL DATA", "INCOIS", "INCOIS-ROMS-IND-01")
        self.assertGreater(len(records), 0)

        r0 = records[0]
        self.assertEqual(r0.data_status, "CACHED REAL DATA")
        self.assertEqual(r0.source_organization, "INCOIS")
        self.assertEqual(r0.product_id, "INCOIS-ROMS-IND-01")
        self.assertGreaterEqual(r0.latitude, 0.0)
        self.assertLessEqual(r0.latitude, 25.0)

    def test_catalog_provenance_api(self):
        """Verify GET /api/catalog returns provenance metadata for frontend display."""
        response = self.client.get("/api/catalog")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("datasets", data)
        self.assertGreater(len(data["datasets"]), 0)

        ds0 = data["datasets"][0]
        self.assertIn("data_status", ds0)
        self.assertIn("source_organization", ds0)


if __name__ == "__main__":
    unittest.main()
