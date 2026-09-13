"""
Unit & Integration Tests for Adaptive Ocean Observation Mission Planner.
"""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.adaptive.gap_detector import gap_detector
from app.adaptive.instrument_registry import instrument_registry
from app.adaptive.energy_model import energy_engine
from app.adaptive.current_router import current_router
from app.adaptive.information_gain import information_gain_engine
from app.adaptive.feasibility import feasibility_engine
from app.adaptive.mission_optimizer import mission_optimizer
from app.adaptive.mission_simulator import mission_simulator


class TestAdaptiveMissionPlanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_information_gap_detector(self):
        """Test 3D ocean information gap priority score calculation."""
        gap = gap_detector.detect_information_gap(15.4, 88.7, 500.0, "temperature")
        self.assertIn("priority_score", gap)
        self.assertIn("components", gap)
        self.assertGreaterEqual(gap["priority_score"], 0.0)
        self.assertLessEqual(gap["priority_score"], 100.0)

    def test_instrument_discovery_and_rejection(self):
        """Test candidate fleet discovery and explicit rejection reasons."""
        discovery = instrument_registry.discover_candidate_instruments(15.4, 88.7, 500.0, "temperature")
        self.assertIn("feasible_instruments", discovery)
        self.assertIn("rejected_instruments", discovery)

        # Verify Argo is rejected because it is non-steerable
        rejected_pids = [r["instrument_id"] for r in discovery["rejected_instruments"]]
        self.assertIn("ARGO-5906203", rejected_pids)

    def test_energy_expenditure_evaluation(self):
        """Test battery energy calculation and safety reserve enforcement."""
        energy = energy_engine.evaluate_energy_expenditure(
            platform_type="glider",
            initial_battery_percent=82.0,
            distance_km=137.8,
            cruise_speed_mps=0.35,
            depth_m=500.0,
            current_drag_mps=0.05,
            safety_reserve_percent=15.0
        )
        self.assertTrue(energy["feasible"])
        self.assertGreater(energy["energy_remaining_percent"], 15.0)

        # Test infeasible energy case (excessive distance)
        infeasible_energy = energy_engine.evaluate_energy_expenditure(
            platform_type="glider",
            initial_battery_percent=20.0,
            distance_km=800.0,
            cruise_speed_mps=0.35,
            depth_m=1000.0,
            safety_reserve_percent=15.0
        )
        self.assertFalse(infeasible_energy["feasible"])
        self.assertIn("INSUFFICIENT ENERGY MARGIN", infeasible_energy["rejection_reason"])

    def test_current_aware_trajectory_routing(self):
        """Test current-aware trajectory planning with ocean vector drag."""
        route = current_router.plan_current_aware_trajectory(
            start_lat=14.2, start_lon=87.5,
            target_lat=15.4, target_lon=88.7,
            target_depth_m=500.0,
            cruise_speed_mps=0.35
        )
        self.assertIn("waypoints", route)
        self.assertGreaterEqual(len(route["waypoints"]), 3)
        self.assertIn("avg_current_speed_mps", route)

    def test_expected_information_gain(self):
        """Test Bayesian posterior variance reduction and expected information gain."""
        eig = information_gain_engine.compute_expected_information_gain(
            prior_uncertainty_percent=82.0, platform_type="glider", target_depth_m=500.0
        )
        self.assertIn("expected_information_gain_percent", eig)
        self.assertLess(eig["posterior_uncertainty_percent"], 82.0)
        self.assertGreater(eig["expected_information_gain_percent"], 0.0)

    def test_mission_optimization_ranking(self):
        """Test multi-criteria candidate ranking and winner selection."""
        plan = mission_optimizer.plan_optimal_mission(15.4, 88.7, 500.0, "temperature", "glider")
        self.assertIn("selected_winner", plan)
        self.assertIn("ranked_candidates", plan)
        if plan["selected_winner"]:
            self.assertEqual(plan["selected_winner"]["platform_type"], "glider")

    def test_mission_simulation_execution(self):
        """Test step-by-step mission simulation and what-if Bayesian update."""
        sim = mission_simulator.simulate_mission(15.4, 88.7, 500.0, "temperature", "glider")
        self.assertEqual(sim["status"], "SIMULATION_COMPLETED")
        self.assertIn("before_simulation", sim)
        self.assertIn("after_simulation", sim)
        self.assertIn("scientific_payoff", sim)
        self.assertLess(sim["after_simulation"]["information_gap_percent"], sim["before_simulation"]["information_gap_percent"])

    def test_adaptive_api_endpoints(self):
        """Test GET /api/adaptive/* REST API endpoints."""
        res_gaps = self.client.get("/api/adaptive/gaps?min_lat=-10&max_lat=30&min_lon=50&max_lon=100")
        self.assertEqual(res_gaps.status_code, 200)
        self.assertIn("gaps", res_gaps.json())

        res_inst = self.client.get("/api/adaptive/instruments?lat=15.4&lon=88.7&depth=500")
        self.assertEqual(res_inst.status_code, 200)

        res_plan = self.client.get("/api/adaptive/plan?lat=15.4&lon=88.7&depth=500&platform=glider")
        self.assertEqual(res_plan.status_code, 200)

        res_sim = self.client.get("/api/adaptive/simulate?lat=15.4&lon=88.7&depth=500&platform=glider")
        self.assertEqual(res_sim.status_code, 200)
        self.assertEqual(res_sim.json()["status"], "SIMULATION_COMPLETED")


if __name__ == "__main__":
    unittest.main()
