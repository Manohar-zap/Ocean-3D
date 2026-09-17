"""
Unit & API Integration Tests for AUV, UUV, and ROV Observation & Mission Planning.
"""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.vehicles.vehicle_service import vehicle_service, MissionPlanRequest, TelemetryPacket


class TestVehicleMissions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_vehicle_registry_roster(self):
        """Verify all 6 demo AUV, UUV, and ROV platforms exist with valid schemas."""
        vehicles = vehicle_service.get_all_vehicles()
        self.assertGreaterEqual(len(vehicles), 6)

        types = {v["type"] for v in vehicles}
        self.assertIn("AUV", types)
        self.assertIn("UUV", types)
        self.assertIn("ROV", types)

        for v in vehicles:
            self.assertIn("id", v)
            self.assertIn("name", v)
            self.assertIn("latitude", v)
            self.assertIn("longitude", v)
            self.assertIn("depth", v)
            self.assertIn("status", v)
            self.assertEqual(v["source"], "SIMULATED")
            self.assertGreater(len(v["sensors"]), 0)

    def test_filter_by_type(self):
        """Verify filtering by AUV, UUV, and ROV."""
        auvs = vehicle_service.get_all_vehicles("AUV")
        self.assertTrue(all(v["type"] == "AUV" for v in auvs))
        self.assertGreaterEqual(len(auvs), 2)

        uuvs = vehicle_service.get_all_vehicles("UUV")
        self.assertTrue(all(v["type"] == "UUV" for v in uuvs))

        rovs = vehicle_service.get_all_vehicles("ROV")
        self.assertTrue(all(v["type"] == "ROV" for v in rovs))

    def test_get_vehicle_by_id_and_track(self):
        """Verify fetching specific vehicle with historical track coordinates."""
        v = vehicle_service.get_vehicle_by_id("AUV-001")
        self.assertIsNotNone(v)
        self.assertEqual(v["id"], "AUV-001")
        self.assertEqual(v["type"], "AUV")
        self.assertIn("track", v)
        self.assertGreaterEqual(len(v["track"]), 4)

    def test_mission_planning_workflow(self):
        """Verify generating a 3D mission route with waypoint coordinates and depth descent."""
        req = MissionPlanRequest(
            vehicle_id="AUV-001",
            target_lat=14.850,
            target_lon=74.300,
            target_depth=850.0,
            sensors=["temperature", "salinity", "oxygen", "chlorophyll"]
        )
        plan = vehicle_service.plan_mission(req)
        self.assertIn("mission_id", plan)
        self.assertEqual(plan["status"], "MISSION_PLANNED")
        self.assertEqual(plan["source"], "SIMULATED")
        self.assertGreater(plan["direct_distance_km"], 0.0)
        self.assertGreater(len(plan["waypoints"]), 5)
        self.assertIn("depth_profile", plan)

        # Vehicle status should be updated
        updated_v = vehicle_service.get_vehicle_by_id("AUV-001")
        self.assertEqual(updated_v["status"], "MISSION_PLANNED")

    def test_mission_depth_rating_enforcement(self):
        """Ensure mission is rejected if target depth exceeds max depth rating."""
        req = MissionPlanRequest(
            vehicle_id="UUV-001",  # Max depth 600m
            target_lat=10.0,
            target_lon=76.0,
            target_depth=3500.0,
        )
        with self.assertRaises(ValueError):
            vehicle_service.plan_mission(req)

    def test_ocean_observation_sampling(self):
        """Verify target observation data collection with realistic physics and clear simulation labels."""
        sample = vehicle_service.sample_observation_at_target(
            lat=14.85, lon=74.30, depth=850.0, sensors=["temperature", "salinity", "oxygen", "chlorophyll"]
        )
        self.assertIn("measurements", sample)
        m = sample["measurements"]
        self.assertIn("temperature", m)
        self.assertIn("salinity", m)
        self.assertIn("oxygen", m)
        self.assertIn("chlorophyll", m)

        # Deep ocean thermocline validation at 850m
        self.assertLess(m["temperature"], 12.0)
        self.assertGreater(m["temperature"], 4.0)
        # Deep aphotic zone chlorophyll should be near zero
        self.assertLess(m["chlorophyll"], 0.1)
        self.assertEqual(sample["source"], "SIMULATED")

    def test_telemetry_ingestion_interface(self):
        """Verify telemetry ingestion interface accepts updates for future live feeds."""
        packet = TelemetryPacket(
            vehicleId="AUV-001",
            latitude=14.220,
            longitude=73.830,
            depth=660.0,
            heading=220.0,
            speed=1.6,
            status="EN_ROUTE",
            sensorData={"temperature": 12.1, "salinity": 34.9}
        )
        res = vehicle_service.ingest_telemetry(packet)
        self.assertEqual(res["status"], "TELEMETRY_ACCEPTED")

        updated_v = vehicle_service.get_vehicle_by_id("AUV-001")
        self.assertEqual(updated_v["latitude"], 14.220)
        self.assertEqual(updated_v["depth"], 660.0)

    def test_api_endpoints(self):
        """Verify HTTP endpoints for vehicles and missions."""
        res_list = self.client.get("/api/vehicles")
        self.assertEqual(res_list.status_code, 200)
        vehicles = res_list.json()
        self.assertGreaterEqual(len(vehicles), 6)

        res_single = self.client.get("/api/vehicles/AUV-001")
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(res_single.json()["id"], "AUV-001")

        res_plan = self.client.post("/api/missions/plan", json={
            "vehicle_id": "AUV-001",
            "target_lat": 14.60,
            "target_lon": 74.00,
            "target_depth": 700.0,
            "sensors": ["temperature", "salinity"]
        })
        self.assertEqual(res_plan.status_code, 200)
        self.assertIn("mission_id", res_plan.json())

        res_sample = self.client.get("/api/missions/sample?lat=14.60&lon=74.00&depth=700&sensors=temperature,salinity")
        self.assertEqual(res_sample.status_code, 200)
        self.assertEqual(res_sample.json()["source"], "SIMULATED")


if __name__ == "__main__":
    unittest.main()
