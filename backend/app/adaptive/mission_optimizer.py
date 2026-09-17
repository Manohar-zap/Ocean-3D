"""
Multi-Criteria Mission Optimizer & Candidate Ranking Module.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .gap_detector import gap_detector
from .instrument_registry import instrument_registry, FLEET_PROVENANCE
from .energy_model import energy_engine
from .current_router import current_router
from .information_gain import information_gain_engine

logger = logging.getLogger(__name__)


class MissionOptimizerEngine:
    """Ranks and optimizes candidate mobile platforms for a target information gap."""

    def plan_optimal_mission(
        self,
        latitude: float,
        longitude: float,
        depth_m: float = 100.0,
        variable: str = "temperature",
        preferred_platform: Optional[str] = None,
    ) -> dict[str, Any]:
        gap = gap_detector.detect_information_gap(latitude, longitude, depth_m, variable)
        p_score = gap["priority_score"]

        discovery = instrument_registry.discover_candidate_instruments(latitude, longitude, depth_m, variable)
        feasible_candidates = discovery["feasible_instruments"]
        rejected_candidates = list(discovery["rejected_instruments"])
        all_candidates = discovery["all_candidates"]

        ranked_candidates = []
        current_field = None

        for inst in feasible_candidates:
            pid = inst["instrument_id"]
            ptype = inst["platform_type"]

            route = current_router.plan_current_aware_trajectory(
                inst["latitude"], inst["longitude"], latitude, longitude, depth_m, inst["cruise_speed_mps"]
            )
            if current_field is None:
                current_field = route.get("current_field", [])

            energy = energy_engine.evaluate_energy_expenditure(
                ptype,
                inst["battery_percent"],
                route["direct_distance_km"],
                inst["cruise_speed_mps"],
                depth_m,
                route["current_headwind_mps"],
            )

            inst_eval = dict(inst)
            inst_eval["energy_details"] = energy
            inst_eval["estimated_mission_time_hours"] = route["estimated_duration_hours"]
            inst_eval["current_exposure_mps"] = route["avg_current_speed_mps"]
            inst_eval["feasibility_checks"]["energy"] = {
                "label": "ENERGY",
                "passed": energy["feasible"],
                "detail": f"Required: {energy['energy_required_percent']:.1f}% | Reserve: {energy['safety_reserve_percent']:.1f}%",
            }
            inst_eval["feasibility_checks"]["current"] = {
                "label": "CURRENT",
                "passed": route["current_headwind_mps"] < inst["cruise_speed_mps"],
                "detail": f"Exposure: {route['avg_current_speed_mps']:.2f} m/s",
            }

            if not energy["feasible"]:
                inst_copy = dict(inst_eval)
                inst_copy["rejection_reason"] = energy["rejection_reason"]
                inst_copy["failed_criteria"] = inst_copy.get("failed_criteria", []) + ["energy"]
                rejected_candidates.append(inst_copy)
                continue

            eig = information_gain_engine.compute_expected_information_gain(p_score, ptype, target_depth_m=depth_m)

            sens_match = 1.0 if variable in inst["sensors"] else 0.5
            energy_margin_factor = energy["safety_reserve_percent"] / 100.0
            feasibility_score = 0.60 if route["direct_distance_km"] < inst["remaining_range_km"] * 0.5 else 0.40

            distance_penalty = (route["direct_distance_km"] / 1000.0) * 5.0
            simulation_penalty = 15.0 if inst.get("is_simulated", True) else 0.0

            mission_score = round(
                (eig["expected_information_gain_percent"] * 0.50)
                + (feasibility_score * 30.0)
                + (sens_match * 10.0)
                + (energy_margin_factor * 10.0)
                - distance_penalty
                - simulation_penalty,
                1,
            )

            decision = "RECOMMEND" if mission_score >= 20.0 and p_score >= 20.0 else "MONITOR"

            ranked_candidates.append(
                {
                    "instrument_id": pid,
                    "name": inst["name"],
                    "platform_type": ptype,
                    "operational_status": inst.get("operational_status", "SIMULATED_PLANNING_ASSET"),
                    "is_simulated": inst.get("is_simulated", True),
                    "mission_score": mission_score,
                    "decision": decision,
                    "distance_km": route["direct_distance_km"],
                    "distance_label": f"{route['direct_distance_km']:.1f} km [SIMULATED ESTIMATE]",
                    "estimated_duration_hours": route["estimated_duration_hours"],
                    "duration_label": f"{route['estimated_duration_hours']:.1f} hrs [SIMULATED ESTIMATE]",
                    "energy_required_percent": energy["energy_required_percent"],
                    "energy_label": f"{energy['energy_required_percent']:.1f}% [SIMULATED DRAW]",
                    "remaining_battery_after_mission": energy["energy_remaining_percent"],
                    "expected_information_gain": eig["expected_information_gain_percent"],
                    "feasibility_checks": inst_eval["feasibility_checks"],
                    "route_details": route,
                    "energy_details": energy,
                    "information_gain_details": eig,
                    "fleet_provenance": FLEET_PROVENANCE,
                }
            )

        ranked_candidates.sort(key=lambda c: c["mission_score"], reverse=True)
        selected_winner = ranked_candidates[0] if ranked_candidates else None
        overall_decision = selected_winner["decision"] if selected_winner else "NO_FEASIBLE_PLATFORM"

        if selected_winner and current_field is None:
            current_field = selected_winner["route_details"].get("current_field", [])

        if selected_winner and overall_decision == "RECOMMEND":
            action_msg = f"Deploy/route {selected_winner['name']} toward target ({latitude:.2f}°, {longitude:.2f}°) at {depth_m:.0f}m depth [SIMULATED MISSION PLAN]"
        elif not selected_winner:
            action_msg = (
                f"NO FEASIBLE PLATFORM: All fleet assets exceed range limits, depth rating, or energy constraints "
                f"for target ({latitude:.2f}°, {longitude:.2f}°). Recommend vessel expedition or float air-deployment."
            )
        else:
            action_msg = "Continue monitoring; candidate platforms do not meet the required information gain and energy margin."

        return {
            "decision": overall_decision,
            "fleet_provenance": FLEET_PROVENANCE,
            "target_gap": gap,
            "all_candidates": all_candidates,
            "selected_winner": selected_winner,
            "ranked_candidates": ranked_candidates,
            "rejected_candidates": rejected_candidates,
            "current_field": current_field or [],
            "recommended_action": action_msg,
            "scoring_formula": "mission_score = (EIG * 0.50) + (Feasibility * 30) + (SensorMatch * 10) + (EnergyMargin * 10)",
            "provenance": "SIMULATED_MISSION_DECISION_SUPPORT",
            "planning_mode_notice": "ALL PLATFORM ASSIGNMENTS, TRAJECTORIES, AND ENERGY FIGURES ARE SIMULATED FOR MISSION PLANNING ONLY",
        }


mission_optimizer = MissionOptimizerEngine()
