"""
Multi-Criteria Mission Optimizer & Candidate Ranking Module.

Ranks feasible mobile observing platforms using transparent scientific scoring:
mission_score = EIG * feasibility * sensor_match * energy_safety * urgency.
Provides explicit explainability for winner selection and rejection reasons.
"""
from __future__ import annotations
import math
import logging
from typing import Optional, Any

from .gap_detector import gap_detector
from .instrument_registry import instrument_registry
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
        preferred_platform: Optional[str] = None
    ) -> dict[str, Any]:
        # 1. Detect Target Information Gap
        gap = gap_detector.detect_information_gap(latitude, longitude, depth_m, variable)
        p_score = gap["priority_score"]

        # 2. Discover Candidate Fleet Platforms
        discovery = instrument_registry.discover_candidate_instruments(latitude, longitude, depth_m, variable)
        feasible_candidates = discovery["feasible_instruments"]
        rejected_candidates = discovery["rejected_instruments"]

        ranked_candidates = []

        # 3. Evaluate Feasibility, Energy, Current Routing, and EIG for each feasible candidate
        for inst in feasible_candidates:
            pid = inst["instrument_id"]
            ptype = inst["platform_type"]

            # Current-Aware Route
            route = current_router.plan_current_aware_trajectory(
                inst["latitude"], inst["longitude"], latitude, longitude, depth_m, inst["cruise_speed_mps"]
            )

            # Energy Evaluation
            energy = energy_engine.evaluate_energy_expenditure(
                ptype, inst["battery_percent"], route["direct_distance_km"],
                inst["cruise_speed_mps"], depth_m, route["current_headwind_mps"]
            )

            if not energy["feasible"]:
                inst_copy = dict(inst)
                inst_copy["rejection_reason"] = energy["rejection_reason"]
                rejected_candidates.append(inst_copy)
                continue

            # Expected Information Gain
            eig = information_gain_engine.compute_expected_information_gain(
                p_score, ptype, target_depth_m=depth_m
            )

            # Multi-Criteria Mission Score Calculation
            sens_match = 1.0 if variable in inst["sensors"] else 0.5
            energy_margin_factor = energy["safety_reserve_percent"] / 100.0
            feasibility_score = 0.60 if route["direct_distance_km"] < inst["remaining_range_km"] * 0.5 else 0.40

            mission_score = round(
                (eig["expected_information_gain_percent"] * 0.50) +
                (feasibility_score * 30.0) +
                (sens_match * 10.0) +
                (energy_margin_factor * 10.0), 1
            )

            decision = "RECOMMEND" if mission_score >= 45.0 and p_score >= 50.0 else "MONITOR"

            ranked_candidates.append({
                "instrument_id": pid,
                "name": inst["name"],
                "platform_type": ptype,
                "mission_score": mission_score,
                "decision": decision,
                "distance_km": route["direct_distance_km"],
                "estimated_duration_hours": route["estimated_duration_hours"],
                "energy_required_percent": energy["energy_required_percent"],
                "remaining_battery_after_mission": energy["energy_remaining_percent"],
                "expected_information_gain": eig["expected_information_gain_percent"],
                "route_details": route,
                "energy_details": energy,
                "information_gain_details": eig
            })

        # Sort ranked candidates descending by mission_score
        ranked_candidates.sort(key=lambda c: c["mission_score"], reverse=True)

        selected_winner = ranked_candidates[0] if ranked_candidates else None
        overall_decision = selected_winner["decision"] if selected_winner else "MONITOR"

        action_msg = (
            f"Deploy/route {selected_winner['name']} toward target ({latitude:.2f}°, {longitude:.2f}°) at {depth_m:.0f}m depth"
            if selected_winner and overall_decision == "RECOMMEND"
            else "Continue monitoring; no feasible candidate platform meets the required information gain and energy margin."
        )

        return {
            "decision": overall_decision,
            "target_gap": gap,
            "selected_winner": selected_winner,
            "ranked_candidates": ranked_candidates,
            "rejected_candidates": rejected_candidates,
            "recommended_action": action_msg,
            "scoring_formula": "mission_score = (EIG * 0.50) + (Feasibility * 30) + (SensorMatch * 10) + (EnergyMargin * 10)",
            "provenance": "DECISION_SUPPORT_SIMULATION"
        }


mission_optimizer = MissionOptimizerEngine()
