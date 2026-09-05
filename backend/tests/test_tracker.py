"""
Unit tests for Real Observation Tracker Map Architecture.
"""
import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestObservationTrackerMap(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_tracker_summary_and_latest_markers(self):
        res = self.client.get("/api/observations")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("summary", data)
        summary = data["summary"]
        self.assertGreater(summary["argo"], 0)
        self.assertGreater(summary["glider"], 0)
        self.assertGreater(summary["ctd"], 0)
        self.assertGreater(summary["bgc"], 0)
        self.assertIn("latest_update", summary)

        markers = data["markers"]
        self.assertEqual(data["count"], len(markers))
        self.assertEqual(data["total_available"], len(markers))

        # Verify platform deduplication: each platform_id appears exactly once in markers
        pids = [m["platform_id"] for m in markers]
        self.assertEqual(len(pids), len(set(pids)))

        # Verify no hardcoded common fallbacks
        has_fallback = any(m["lat"] == 18.0 and m["lon"] == 78.5 for m in markers)
        self.assertFalse(has_fallback)

        # Verify data status provenance and honest status reporting
        for m in markers:
            self.assertEqual(m["data_status"], "DEMONSTRATION DATA")
            self.assertIn("status", m)
            if m["data_status"] == "DEMONSTRATION DATA":
                self.assertEqual(m["status"], "DEMONSTRATION")
            else:
                self.assertIn(m["status"], ("ACTIVE", "RECENT", "STALE", "OFFLINE"))

    def test_latest_platforms_endpoint(self):
        res = self.client.get("/api/observations/platforms/latest")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("platforms", data)
        self.assertGreater(data["count"], 0)
        p = data["platforms"][0]
        self.assertIn("platform_id", p)
        self.assertIn("latitude", p)
        self.assertIn("longitude", p)
        self.assertIn("timestamp", p)
        self.assertIn("data_status", p)

    def test_platform_track_endpoint(self):
        # Pick ARGO-2900000
        res = self.client.get("/api/observations/ARGO-2900000/track")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["platform_id"], "ARGO-2900000")
        self.assertEqual(data["platform_type"], "argo")
        self.assertIn("track", data)

        track = data["track"]
        self.assertGreaterEqual(len(track), 2)

        # Verify track points are chronologically ordered
        timestamps = [pt["timestamp"] for pt in track]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_region_bounding_box_filtering(self):
        # Filter for small region lat 0-10, lon 60-70
        res = self.client.get("/api/observations?min_lat=0&max_lat=10&min_lon=60&max_lon=70")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        filtered_count = data["count"]
        self.assertLessEqual(filtered_count, data["total_available"])

        for m in data["markers"]:
            self.assertTrue(0 <= m["lat"] <= 10)
            self.assertTrue(60 <= m["lon"] <= 70)


if __name__ == "__main__":
    unittest.main()
