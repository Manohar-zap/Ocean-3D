"""
Unit & Integration Tests for Adaptive Ocean Observation Mission Planner.
"""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.adaptive.gap_detector import gap_detector
from app.adaptive.instrument_registry import instrument_registry, FLEET_PROVENANCE
from app.adaptive.energy_model import energy_engine
from app.adaptive.current_router import current_router
from app.adaptive.information_gain import information_gain_engine
from app.adaptive.mission_optimizer import mission_optimizer
from app.adaptive.mission_simulator import mission_simulator, MISSION_PHASES


class TestAdaptiveMissionPlanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_information_gap_detector(self):
        gap = gap_detector.detect_information_gap(15.4, 88.7, 500.0, "temperature")
        self.assertIn("priority_score", gap)
        self.assertGreaterEqual(gap["priority_score"], 0.0)
        self.assertLessEqual(gap["priority_score"], 100.0)

    def test_instrument_discovery_and_rejection(self):
        discovery = instrument_registry.discover_candidate_instruments(15.4, 88.7, 500.0, "temperature")
        self.assertEqual(discovery["fleet_provenance"], FLEET_PROVENANCE)
        self.assertIn("all_candidates", discovery)
        self.assertIn("feasible_instruments", discovery)
        self.assertIn("rejected_instruments", discovery)

        rejected_pids = [r["instrument_id"] for r in discovery["rejected_instruments"]]
        self.assertIn("ARGO-5906203", rejected_pids)

        argo = next(c for c in discovery["all_candidates"] if c["instrument_id"] == "ARGO-5906203")
        self.assertFalse(argo["feasibility_checks"]["controllable"]["passed"])

    def test_energy_expenditure_evaluation(self):
        energy = energy_engine.evaluate_energy_expenditure(
            platform_type="glider",
            initial_battery_percent=82.0,
            distance_km=137.8,
            cruise_speed_mps=0.35,
            depth_m=500.0,
            current_drag_mps=0.05,
            safety_reserve_percent=15.0,
        )
        self.assertTrue(energy["feasible"])
        self.assertGreater(energy["energy_remaining_percent"], 15.0)

        infeasible_energy = energy_engine.evaluate_energy_expenditure(
            platform_type="glider",
            initial_battery_percent=20.0,
            distance_km=800.0,
            cruise_speed_mps=0.35,
            depth_m=1000.0,
            safety_reserve_percent=15.0,
        )
        self.assertFalse(infeasible_energy["feasible"])

    def test_current_aware_trajectory_routing(self):
        route = current_router.plan_current_aware_trajectory(
            start_lat=14.2, start_lon=87.5,
            target_lat=15.4, target_lon=88.7,
            target_depth_m=500.0,
            cruise_speed_mps=0.35,
        )
        self.assertIn("waypoints", route)
        self.assertGreaterEqual(len(route["waypoints"]), 3)
        self.assertIn("direct_route", route)
        self.assertIn("candidate_routes", route)
        self.assertIn("selected_route", route)
        self.assertIn("current_field", route)
        self.assertEqual(len(route["candidate_routes"]), 3)

        # Optimal route should differ from direct when currents present
        direct = route["direct_route"]["waypoints"]
        selected = route["selected_route"]["waypoints"]
        direct_mid = direct[len(direct) // 2]
        selected_mid = selected[len(selected) // 2]
        dist_diff = abs(direct_mid["latitude"] - selected_mid["latitude"]) + abs(
            direct_mid["longitude"] - selected_mid["longitude"]
        )
        self.assertGreater(dist_diff, 0.0)

    def test_expected_information_gain(self):
        eig = information_gain_engine.compute_expected_information_gain(
            prior_uncertainty_percent=82.0, platform_type="glider", target_depth_m=500.0
        )
        self.assertLess(eig["posterior_uncertainty_percent"], 82.0)
        self.assertGreater(eig["expected_information_gain_percent"], 0.0)

    def test_mission_optimization_ranking(self):
        plan = mission_optimizer.plan_optimal_mission(15.4, 88.7, 500.0, "temperature", "glider")
        self.assertEqual(plan["fleet_provenance"], FLEET_PROVENANCE)
        self.assertIn("all_candidates", plan)
        self.assertIn("selected_winner", plan)
        if plan["selected_winner"]:
            self.assertEqual(plan["selected_winner"]["platform_type"], "glider")
            self.assertIn("direct_route", plan["selected_winner"]["route_details"])

    def test_mission_simulation_execution(self):
        sim = mission_simulator.simulate_mission(15.4, 88.7, 500.0, "temperature", "glider")
        self.assertEqual(sim["status"], "SIMULATION_COMPLETED")
        self.assertIn("trajectory_frames", sim)
        self.assertGreater(len(sim["trajectory_frames"]), 5)
        self.assertIn("routing", sim)
        self.assertIn("mission_phases", sim)
        self.assertEqual(len(sim["mission_phases"]), 14)

        # Depth must use water-column values, not fake altitude
        for frame in sim["trajectory_frames"]:
            self.assertLessEqual(frame["depth_m"], 1000.0)
            self.assertIn("heading_deg", frame)
            self.assertIn("battery_percent", frame)

        self.assertLess(
            sim["after_simulation"]["information_gap_percent"],
            sim["before_simulation"]["information_gap_percent"],
        )

    def test_adaptive_api_endpoints(self):
        res_plan = self.client.get("/api/adaptive/plan?lat=15.4&lon=88.7&depth=500&platform=glider")
        self.assertEqual(res_plan.status_code, 200)
        plan = res_plan.json()
        self.assertIn("fleet_provenance", plan)
        self.assertIn("current_field", plan)

        res_sim = self.client.get("/api/adaptive/simulate?lat=15.4&lon=88.7&depth=500&platform=glider")
        self.assertEqual(res_sim.status_code, 200)
        sim = res_sim.json()
        self.assertEqual(sim["status"], "SIMULATION_COMPLETED")
        self.assertIn("trajectory_frames", sim)


if __name__ == "__main__":
    unittest.main()
