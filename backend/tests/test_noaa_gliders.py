"""
Unit tests for NOAA AOML ERDDAP Gliders Test Integration.
"""
import unittest
import json
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.noaa_glider_service import NoaaGliderService


class TestNoaaGlidersAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_noaa_gliders_endpoint_structure(self):
        """Verify GET /api/external-gliders/noaa returns valid metadata and gliders list."""
        resp = self.client.get("/api/external-gliders/noaa")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("status", data)
        self.assertEqual(data["status"], "READY")
        self.assertIn("source", data)
        self.assertEqual(data["source"], "NOAA/AOML/IOOS ERDDAP")
        self.assertIn("dataset_id", data)
        self.assertEqual(data["dataset_id"], "GLIDERS_2025_01_03")
        self.assertEqual(data["data_status"], "HISTORICAL TEST DATA (2025)")
        self.assertIn("notice", data)
        self.assertIn("gliders", data)
        self.assertGreater(data["count"], 0)
        self.assertEqual(data["count"], len(data["gliders"]))

    def test_noaa_glider_record_fields(self):
        """Verify each glider record conforms strictly to the revised schema with no invented values."""
        resp = self.client.get("/api/external-gliders/noaa")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        gliders = data["gliders"]
        self.assertGreater(len(gliders), 0)

        required_fields = [
            "source", "dataset_id", "instrument_type", "platform_id", "trajectory",
            "latitude", "longitude", "depth", "timestamp",
            "temperature", "salinity", "total_fixes", "data_status"
        ]

        for g in gliders[:20]:
            for field in required_fields:
                self.assertIn(field, g, f"Missing required field '{field}' in glider record")
            self.assertEqual(g["source"], "NOAA/AOML/IOOS ERDDAP")
            self.assertEqual(g["instrument_type"], "NOAA/AOML Glider (Test)")
            # platform_id must be None (no fake splitting)
            self.assertIsNone(g["platform_id"], "platform_id must be None when not explicitly provided by NOAA")
            # depth, temperature, salinity must be None (not 0.0 or synthetic)
            self.assertIsNone(g["depth"], "depth must be None (not 0.0) for position-only queries")
            self.assertIsNone(g["temperature"], "temperature must be None when not measured")
            self.assertIsNone(g["salinity"], "salinity must be None when not measured")
            # coordinates and timestamp must be valid
            self.assertIsInstance(g["latitude"], (int, float))
            self.assertIsInstance(g["longitude"], (int, float))
            self.assertTrue(-90.0 <= g["latitude"] <= 90.0)
            self.assertTrue(-180.0 <= g["longitude"] <= 180.0)
            self.assertIsInstance(g["timestamp"], str)
            self.assertGreater(len(g["timestamp"]), 0)

    def test_unique_trajectory_constraint(self):
        """Verify strictly one latest observation per unique trajectory ID."""
        resp = self.client.get("/api/external-gliders/noaa")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        gliders = data["gliders"]

        trajectories = [g["trajectory"] for g in gliders]
        unique_trajectories = set(trajectories)
        self.assertEqual(len(trajectories), len(unique_trajectories), "Duplicate trajectory markers found!")

    def test_mock_network_failure_handling(self):
        """Verify graceful error response when network fails and no cache exists."""
        service = NoaaGliderService()
        service._memory_cache = None
        service.CACHE_FILE = "non_existent_cache_file.json"

        with patch("urllib.request.urlopen", side_effect=Exception("Connection timed out")):
            result = service.get_latest_gliders(force_refresh=True)
            self.assertEqual(result["status"], "UNAVAILABLE")
            self.assertEqual(result["count"], 0)
            self.assertEqual(len(result["gliders"]), 0)
            self.assertIn("Connection timed out", result["message"])

    def test_mock_trajectory_latest_selection(self):
        """Verify latest observation selection logic on mock multi-observation records."""
        service = NoaaGliderService()
        mock_raw = {
            "table": {
                "columnNames": ["trajectory", "time", "latitude", "longitude"],
                "rows": [
                    ["traj-alpha", "2025-03-01T10:00:00Z", 20.0, -80.0],
                    ["traj-alpha", "2025-03-05T12:00:00Z", 20.5, -80.5],
                    ["traj-alpha", "2025-03-02T11:00:00Z", 20.1, -80.1],
                    ["traj-beta", "2025-04-10T08:00:00Z", 35.0, -75.0],
                    ["traj-gamma-invalid", "2025-05-01T00:00:00Z", None, -70.0],  # Invalid lat
                ]
            }
        }
        with patch.object(service, "_get_ssl_context"):
            with patch("urllib.request.urlopen") as mock_open:
                mock_resp = unittest.mock.MagicMock()
                mock_resp.read.return_value = json.dumps(mock_raw).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_open.return_value = mock_resp

                res = service._fetch_from_erddap()
                self.assertEqual(res["status"], "READY")
                self.assertEqual(res["count"], 2)  # traj-alpha and traj-beta
                # Verify traj-alpha selected the latest timestamp (March 5)
                alpha = next(g for g in res["gliders"] if g["trajectory"] == "traj-alpha")
                self.assertEqual(alpha["timestamp"], "2025-03-05T12:00:00Z")
                self.assertEqual(alpha["latitude"], 20.5)
                self.assertEqual(alpha["longitude"], -80.5)
                self.assertEqual(alpha["total_fixes"], 3)
                self.assertIsNone(alpha["platform_id"])
                self.assertIsNone(alpha["depth"])

    def test_existing_observations_endpoint_untouched(self):
        """Regression test: verify /api/observations is completely untouched and functioning."""
        resp = self.client.get("/api/observations?platform_type=glider")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("markers", data)
        self.assertIn("summary", data)
        self.assertGreaterEqual(data["summary"]["glider"], 1)


if __name__ == "__main__":
    import json
    unittest.main()
