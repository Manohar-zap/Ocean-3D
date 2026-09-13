"""
Unit & Integration Tests for Real Argo GDAC NetCDF Adapter & Ingestion Pipeline.
"""
import os
import unittest
import numpy as np
import netCDF4 as nc
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.adapters import ArgoGliderAdapter
from app.argo_netcdf_parser import parse_argo_netcdf_file, unesco_pressure_to_depth, juld_to_iso


class TestRealArgoAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.fixture_dir = Path("backend/data/argo_cache")
        cls.fixture_dir.mkdir(parents=True, exist_ok=True)
        cls.fixture_file = cls.fixture_dir / "5906203_prof.nc"
        cls._create_sample_nc_fixture(cls.fixture_file)

    @classmethod
    def _create_sample_nc_fixture(cls, filepath: Path):
        ds = nc.Dataset(str(filepath), "w", format="NETCDF4")
        ds.createDimension("N_PROF", 1)
        ds.createDimension("N_LEVELS", 10)
        ds.createDimension("STRING8", 8)

        p_num = ds.createVariable("PLATFORM_NUMBER", "c", ("N_PROF", "STRING8"))
        p_num[0] = list("5906203 ")

        juld = ds.createVariable("JULD", "f8", ("N_PROF",))
        juld[0] = 27820.25  # ~2026-03-01

        lat = ds.createVariable("LATITUDE", "f4", ("N_PROF",))
        lat[0] = 9.805

        lon = ds.createVariable("LONGITUDE", "f4", ("N_PROF",))
        lon[0] = 75.812

        pres = ds.createVariable("PRES", "f4", ("N_PROF", "N_LEVELS"))
        pres[0, :] = [10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 800.0, 1000.0, 1500.0, 2000.0]

        temp = ds.createVariable("TEMP", "f4", ("N_PROF", "N_LEVELS"), fill_value=99999.0)
        temp[0, :] = [28.4, 28.1, 27.2, 23.5, 18.2, 10.1, 6.5, 4.8, 99999.0, 2.5]  # level 8 is fill_value

        psal = ds.createVariable("PSAL", "f4", ("N_PROF", "N_LEVELS"), fill_value=99999.0)
        psal[0, :] = [35.2, 35.2, 35.3, 35.1, 34.9, 34.7, 34.6, 34.6, 34.7, 34.7]

        temp_qc = ds.createVariable("TEMP_QC", "c", ("N_PROF", "N_LEVELS"))
        temp_qc[0, :] = list("1111111141")  # level 8 has bad QC '4'

        psal_qc = ds.createVariable("PSAL_QC", "c", ("N_PROF", "N_LEVELS"))
        psal_qc[0, :] = list("1111111111")

        ds.close()

    def test_unesco_pressure_to_depth(self):
        """Test UNESCO 1983 hydrostatic pressure-to-depth conversion."""
        depth_10dbar = unesco_pressure_to_depth(10.0, 10.0)
        self.assertGreater(depth_10dbar, 9.8)
        self.assertLess(depth_10dbar, 10.2)

        depth_2000dbar = unesco_pressure_to_depth(2000.0, 10.0)
        self.assertGreater(depth_2000dbar, 1950.0)
        self.assertLess(depth_2000dbar, 2000.0)

    def test_juld_to_iso(self):
        """Test JULD conversion to ISO 8601 UTC timestamp string."""
        iso_str = juld_to_iso(27820.25)
        self.assertTrue(iso_str.startswith("2026-03-03"))

    def test_parse_real_argo_netcdf_file(self):
        """Test parsing valid Argo NetCDF profile file (Test A, B, C, F)."""
        recs = parse_argo_netcdf_file(self.fixture_file, data_status="CACHED REAL DATA")
        self.assertGreater(len(recs), 0)

        r0 = recs[0]
        self.assertEqual(r0.kind, "observation")
        self.assertEqual(r0.dataset_id, "argo_gdac")
        self.assertEqual(r0.platform_id, "ARGO-5906203")
        self.assertEqual(r0.platform_type, "argo")
        self.assertEqual(r0.data_status, "CACHED REAL DATA")
        self.assertEqual(r0.quality_flag, "good")
        self.assertEqual(r0.latitude, 9.805)
        self.assertEqual(r0.longitude, 75.812)

        # Confirm level 8 (bad QC / fill value) was filtered out
        temps = [r.value for r in recs if r.variable == "temperature"]
        self.assertNotIn(99999.0, temps)

    def test_malformed_file_graceful_handling(self):
        """Test graceful handling of malformed / corrupted NetCDF files (Test D)."""
        malformed_file = self.fixture_dir / "corrupted_test.nc"
        with open(malformed_file, "w") as f:
            f.write("not a netcdf file content")

        try:
            recs = parse_argo_netcdf_file(malformed_file)
            self.assertEqual(len(recs), 0)
        finally:
            if malformed_file.exists():
                malformed_file.unlink()

    def test_argo_adapter_parse_and_metadata(self):
        """Test ArgoGliderAdapter metadata & parse pipeline."""
        adapter = ArgoGliderAdapter()
        meta = adapter.metadata()
        self.assertIn("data_status", meta)
        self.assertIn("source_organization", meta)

        recs = adapter.parse("argo_gdac")
        self.assertGreater(len(recs), 0)
        self.assertIn(recs[0].data_status, ["REAL DATA", "CACHED REAL DATA", "DEMONSTRATION DATA"])

    def test_api_compatibility(self):
        """Test GET /api/observations and profile endpoints (Test E)."""
        response = self.client.get("/api/observations?platform_type=argo")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("markers", data)
        self.assertGreater(data["count"], 0)

        # Check platform profile endpoint
        sample_pid = data["markers"][0]["platform_id"]
        res_prof = self.client.get(f"/api/observations/{sample_pid}/profile")
        self.assertEqual(res_prof.status_code, 200)
        prof_data = res_prof.json()
        self.assertEqual(prof_data["platform_id"], sample_pid)
        self.assertIn("profile", prof_data)


if __name__ == "__main__":
    unittest.main()
