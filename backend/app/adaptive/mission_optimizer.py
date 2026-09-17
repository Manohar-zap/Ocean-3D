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

        # Prioritize evaluation of the most competitive platforms
        if preferred_platform and preferred_platform.lower() not in ("all", "any", "none", "*"):
            pref = preferred_platform.lower().strip()
            matching = [c for c in feasible_candidates if pref in c["platform_type"].lower()]
            eval_candidates = matching[:15] if matching else feasible_candidates[:15]
        else:
            eval_candidates = feasible_candidates[:20]

        ranked_candidates = []
        current_field = None

        for inst in eval_candidates:
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
                inst_copy["feasible"] = False
                inst_copy["rejection_reason"] = energy["rejection_reason"]
                inst_copy["failed_criteria"] = inst_copy.get("failed_criteria", []) + ["energy"]
                rejected_candidates.append(inst_copy)
                for c in all_candidates:
                    if c["instrument_id"] == pid:
                        c["feasible"] = False
                        c["rejection_reason"] = energy["rejection_reason"]
                        c["failed_criteria"] = list(set(c.get("failed_criteria", []) + ["energy"]))
                        c["feasibility_checks"] = inst_eval["feasibility_checks"]
                continue

            for c in all_candidates:
                if c["instrument_id"] == pid:
                    c["feasibility_checks"] = inst_eval["feasibility_checks"]

            eig = information_gain_engine.compute_expected_information_gain(p_score, ptype, target_depth_m=depth_m)

            sens_match = 1.0 if instrument_registry._matches_sensor(variable, inst.get("sensors", [])) else 0.5
            energy_margin_factor = energy["safety_reserve_percent"] / 100.0
            feasibility_score = 0.60 if route["direct_distance_km"] < inst["remaining_range_km"] * 0.5 else 0.40

            distance_penalty = (route["direct_distance_km"] / 1000.0) * 6.0
            simulation_penalty = 4.0 if inst.get("is_simulated", True) else 0.0

            # Transit Freshness: penalize long multi-week transits (temporal staleness)
            # AUVs (1.5 m/s) and UUVs (2.2 m/s) arrive days faster than slow buoyancy gliders (0.35 m/s)
            transit_days = route["estimated_duration_hours"] / 24.0
            speed_freshness_bonus = max(0.0, 14.0 - transit_days * 1.4)

            mission_score = round(
                (eig["expected_information_gain_percent"] * 0.45)
                + (feasibility_score * 25.0)
                + (sens_match * 10.0)
                + (energy_margin_factor * 10.0)
                + speed_freshness_bonus
                - distance_penalty
                - simulation_penalty,
                1,
            )

            decision = "RECOMMEND" if mission_score >= 18.0 and p_score >= 15.0 else "MONITOR"

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
                    "duration_label": f"{route['estimated_duration_hours']:.1f} hrs ({transit_days:.1f} days) [SIMULATED ESTIMATE]",
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

        if preferred_platform and preferred_platform.lower() not in ("all", "any", "none", "*"):
            ranked_candidates.sort(
                key=lambda c: (c["platform_type"].lower() == preferred_platform.lower(), c["mission_score"]),
                reverse=True
            )
        else:
            ranked_candidates.sort(key=lambda c: c["mission_score"], reverse=True)
        selected_winner = ranked_candidates[0] if ranked_candidates else None
        overall_decision = selected_winner["decision"] if selected_winner else "NO_FEASIBLE_PLATFORM"

        if selected_winner and current_field is None:
            current_field = selected_winner["route_details"].get("current_field", [])

        if selected_winner and overall_decision == "RECOMMEND":
            action_msg = f"Deploy/route {selected_winner['name']} toward target ({latitude:.2f}°, {longitude:.2f}°) at {depth_m:.0f}m depth [SIMULATED MISSION PLAN]"
        elif not selected_winner:
            action_msg = (
                f"NO FEASIBLE IN-SITU PLATFORM: All fleet assets exceed range limits, depth rating, or energy constraints "
                f"for target ({latitude:.2f}°, {longitude:.2f}°). Recommend rapid air-deployment or expedition vessel dispatch."
            )
        else:
            action_msg = "Continue monitoring; candidate platforms do not meet the required information gain and energy margin."

        # Alternatives for remote information gaps when in-situ platforms are sparse or distant
        air_drop_alternative = {
            "method": "AIR_DEPLOYED_PROFILING_FLOAT",
            "name": "Air-Drop Autonomous Profiling Float (C-130 / Cargo Drone Air-Drop)",
            "estimated_deployment_hours": 1.5,
            "target_depth_m": min(2000.0, max(200.0, depth_m)),
            "expected_information_gain": 34.0,
            "sensors": ["temperature", "salinity", "pressure", "oxygen"],
            "status": "READY_FOR_DEPLOYMENT",
            "description": "Rapid parachute air-drop directly over target void; begins deep CTD profiling within 30 minutes of splashdown.",
        }
        vessel_alternative = {
            "method": "EXPEDITION_RESEARCH_VESSEL",
            "name": "ORV Sagar Kanya (Expedition Rosette Cast)",
            "transit_speed_knots": 12.0,
            "max_depth_m": 6000.0,
            "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll", "adcp"],
            "status": "AVAILABLE_FOR_DISPATCH",
            "description": "Deep-water oceanographic vessel equipped with 24-bottle CTD rosette and underway ADCP.",
        }

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
            "air_drop_alternative": air_drop_alternative,
            "vessel_alternative": vessel_alternative,
            "scoring_formula": "mission_score = (EIG * 0.45) + (Feasibility * 25) + (SensorMatch * 10) + (EnergyMargin * 10) + SpeedFreshnessBonus - DistPenalty",
            "provenance": "SIMULATED_MISSION_DECISION_SUPPORT",
            "planning_mode_notice": "ALL PLATFORM ASSIGNMENTS, TRAJECTORIES, AND ENERGY FIGURES ARE SIMULATED FOR MISSION PLANNING ONLY",
        }


mission_optimizer = MissionOptimizerEngine()
