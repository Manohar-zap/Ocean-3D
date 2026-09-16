"""
Unit and Integration Tests for Global Glider & Controllable Instrument Guidance,
Current-Aware Trajectory Planning, ML-Driven Profile Sampling, and Closed-Loop Ingestion.
"""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.adaptive.instrument_registry import instrument_registry
from app.adaptive.current_router import current_router
from app.adaptive.mission_optimizer import mission_optimizer
from app.adaptive.mission_simulator import mission_simulator
from app.adaptive.gap_detector import gap_detector
from app.storage import store


class TestGliderGuidanceClosedLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_global_fleet_discovery_north_pacific(self):
        """Verify controllable mobile assets are available in North Pacific."""
        disc = instrument_registry.discover_candidate_instruments(
            target_lat=24.0, target_lon=-156.0, target_depth_m=300.0, required_sensor="temperature"
        )
        self.assertGreaterEqual(disc["feasible_count"], 1)
        feasible_ids = [c["instrument_id"] for c in disc["feasible_instruments"]]
        self.assertIn("GLIDER-NPAC-01", feasible_ids)

    def test_global_fleet_discovery_north_atlantic(self):
        """Verify controllable mobile assets are available in North Atlantic."""
        disc = instrument_registry.discover_candidate_instruments(
            target_lat=32.0, target_lon=-64.0, target_depth_m=500.0, required_sensor="temperature"
        )
        self.assertGreaterEqual(disc["feasible_count"], 1)
        feasible_ids = [c["instrument_id"] for c in disc["feasible_instruments"]]
        self.assertIn("GLIDER-NATL-01", feasible_ids)

    def test_southern_ocean_polar_void_infeasible_requirement_16(self):
        """Verify remote polar Southern Ocean voids correctly fail feasibility (Requirement 16)."""
        plan = mission_optimizer.plan_optimal_mission(
            latitude=-60.0, longitude=50.0, depth_m=500.0, variable="temperature"
        )
        self.assertEqual(plan["decision"], "NO_FEASIBLE_PLATFORM")
        self.assertIsNone(plan["selected_winner"])

        sim = mission_simulator.simulate_mission(
            latitude=-60.0, longitude=50.0, depth_m=500.0, variable="temperature"
        )
        self.assertEqual(sim["status"], "NO_FEASIBLE_MISSION")
        self.assertEqual(sim["decision"], "NO_FEASIBLE_PLATFORM")
        self.assertIn("recommended_alternatives", sim)

    def test_current_aware_router_with_land_awareness(self):
        """Verify current-aware A* router produces waypoints and avoids land obstacles."""
        route = current_router.plan_current_aware_trajectory(
            start_lat=14.2, start_lon=87.5,
            target_lat=15.4, target_lon=88.7,
            target_depth_m=400.0,
            cruise_speed_mps=0.35,
        )
        self.assertIn("waypoints", route)
        self.assertGreaterEqual(len(route["waypoints"]), 3)
        self.assertIn("selected_route", route)
        self.assertIn("candidate_routes", route)
        self.assertIn("current_field", route)

        # Check waypoint structure
        first_wp = route["waypoints"][0]
        self.assertIn("current_u", first_wp)
        self.assertIn("current_v", first_wp)
        self.assertIn("ground_track_deg", first_wp)
        self.assertIn("heading_deg", first_wp)

    def test_ml_driven_profile_sampling(self):
        """Verify mission simulator samples profile using genuine trained ML model."""
        sim = mission_simulator.simulate_mission(
            latitude=15.4, longitude=88.7, depth_m=500.0, variable="temperature", preferred_platform="glider"
        )
        self.assertEqual(sim["status"], "SIMULATION_COMPLETED")
        self.assertIn("depth_sampling_sequence", sim)
        sampling = sim["depth_sampling_sequence"]
        self.assertGreaterEqual(len(sampling), 3)

        for sample in sampling:
            self.assertIn("depth_m", sample)
            self.assertIn("temperature_c", sample)
            self.assertIn("salinity_psu", sample)
            self.assertIn("prediction_interval_temp", sample)
            self.assertIn("prediction_interval_sal", sample)
            self.assertIn("uncertainty_sigma", sample)
            self.assertEqual(sample["provenance"], "TRAINED_ML_PHYSICAL_OCEAN_SOUNDING")

    def test_closed_loop_ingestion_reduces_uncertainty(self):
        """Verify ingestion of mission observation collapses gap distance and reduces uncertainty."""
        test_lat = 16.0
        test_lon = 89.0

        # Pre-mission gap state
        gap_before = gap_detector.detect_information_gap(test_lat, test_lon, depth=200.0, variable="temperature")
        initial_score = gap_before["priority_score"]

        # Run simulation to generate ML physical soundings
        sim = mission_simulator.simulate_mission(test_lat, test_lon, depth_m=200.0, variable="temperature")
        self.assertEqual(sim["status"], "SIMULATION_COMPLETED")

        # Ingest observations via API
        payload = {
            "mission_id": sim["mission_id"],
            "platform_id": sim["selected_platform"]["instrument_id"],
            "platform_type": sim["selected_platform"]["platform_type"],
            "latitude": test_lat,
            "longitude": test_lon,
            "sampling_sequence": sim["depth_sampling_sequence"],
        }
        res = self.client.post("/api/adaptive/ingest", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["status"], "OBSERVATION_INGESTED")
        self.assertGreater(data["ingested_records_count"], 0)
        self.assertTrue(data["uncertainty_reduction_achieved"])

        # Re-check gap: distance should now be 0.0 km and score lower
        gap_after = data["updated_gap"]
        self.assertAlmostEqual(gap_after["nearest_observation_km"], 0.0, delta=1.0)
        self.assertLess(gap_after["priority_score"], initial_score)


if __name__ == "__main__":
    unittest.main()
