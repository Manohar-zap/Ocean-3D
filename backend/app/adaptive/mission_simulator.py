"""
Mission Simulator Engine — full 3D playback payload for frontend mission director.
"""
from __future__ import annotations

import math
import logging
from typing import Any, Optional

from app.storage import store
from app.schemas import QueryFilters

from .gap_detector import gap_detector
from .mission_optimizer import mission_optimizer
from .information_gain import information_gain_engine
from .energy_model import energy_engine
from .current_router import current_router
from .instrument_registry import FLEET_PROVENANCE

logger = logging.getLogger(__name__)

MISSION_PHASES = [
    {"id": 1, "key": "GAP_DETECTED", "label": "01 GAP DETECTED"},
    {"id": 2, "key": "FLEET_SEARCH", "label": "02 FLEET SEARCH"},
    {"id": 3, "key": "FEASIBILITY_CHECK", "label": "03 FEASIBILITY CHECK"},
    {"id": 4, "key": "INSTRUMENT_SELECTED", "label": "04 INSTRUMENT SELECTED"},
    {"id": 5, "key": "ROUTE_OPTIMIZED", "label": "05 ROUTE OPTIMIZED"},
    {"id": 6, "key": "DEPLOYMENT", "label": "06 DEPLOYMENT"},
    {"id": 7, "key": "TRANSIT", "label": "07 TRANSIT"},
    {"id": 8, "key": "CURRENT_ADJUSTMENT", "label": "08 CURRENT ADJUSTMENT"},
    {"id": 9, "key": "DESCENT", "label": "09 DESCENT"},
    {"id": 10, "key": "TARGET_APPROACH", "label": "10 TARGET APPROACH"},
    {"id": 11, "key": "TARGET_REACHED", "label": "11 TARGET REACHED"},
    {"id": 12, "key": "SENSOR_SAMPLING", "label": "12 SENSOR SAMPLING"},
    {"id": 13, "key": "DATA_ACQUIRED", "label": "13 DATA ACQUIRED"},
    {"id": 14, "key": "GAP_REASSESSED", "label": "14 INFORMATION GAP REASSESSED"},
]


class MissionSimulatorEngine:
    """Generates deterministic mission playback timeline with 3D trajectory frames."""

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
        )
        return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))

    @staticmethod
    def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
        x = (
            math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
            - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
        )
        return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    def _query_model_value(self, lat: float, lon: float, depth: float, variable: str) -> tuple[Optional[float], bool]:
        rows = store.query_model(
            QueryFilters(
                dataset_id="incois_las_model",
                variable=variable,
                min_lat=lat - 0.5,
                max_lat=lat + 0.5,
                min_lon=lon - 0.5,
                max_lon=lon + 0.5,
                min_depth=depth,
                max_depth=depth,
            )
        )
        if rows:
            return round(sum(r.value for r in rows) / len(rows), 3), False
        return None, True

    def _simulate_profile_sample(
        self, lat: float, lon: float, depth: float, base_temp: Optional[float]
    ) -> dict[str, Any]:
        temp, temp_sim = self._query_model_value(lat, lon, depth, "temperature")
        sal, sal_sim = self._query_model_value(lat, lon, depth, "salinity")
        simulated = temp_sim or sal_sim
        if temp is None:
            temp = round((base_temp or 28.0) - depth * 0.025, 2)
            simulated = True
        if sal is None:
            sal = round(35.0 + depth * 0.0002, 3)
            simulated = True
        pressure = round(depth * 0.101 + 10.0, 2)
        return {
            "depth_m": depth,
            "temperature_c": temp,
            "salinity_psu": sal,
            "pressure_dbar": pressure,
            "simulated": simulated,
            "provenance": "SIMULATED_MEASUREMENT" if simulated else "MODEL_DATA",
        }

    def _build_trajectory_frames(
        self,
        waypoints: list[dict[str, Any]],
        start_battery: float,
        energy_required: float,
        cruise_speed: float,
        target_depth: float,
        target_lat: float,
        target_lon: float,
        duration_hours: float,
    ) -> list[dict[str, Any]]:
        """Dense trajectory with depth, heading, ground track, battery per frame."""
        frames: list[dict[str, Any]] = []
        if not waypoints:
            return frames

        # Interpolate transit at surface (depth=0), then descent at target
        transit_wps = [w for w in waypoints if w.get("depth_m", 0) < target_depth * 0.5]
        if not transit_wps:
            transit_wps = waypoints[:-1] if len(waypoints) > 1 else waypoints

        total_dist = 0.0
        for i in range(1, len(transit_wps)):
            total_dist += self._haversine_km(
                transit_wps[i - 1]["latitude"],
                transit_wps[i - 1]["longitude"],
                transit_wps[i]["latitude"],
                transit_wps[i]["longitude"],
            )

        frame_idx = 0
        elapsed_h = 0.0
        dist_travelled = 0.0
        prev = transit_wps[0]

        for i in range(1, len(transit_wps)):
            curr = transit_wps[i]
            seg_km = self._haversine_km(prev["latitude"], prev["longitude"], curr["latitude"], curr["longitude"])
            steps = max(3, int(seg_km / 5.0))
            for s in range(1, steps + 1):
                ratio = s / steps
                lat = prev["latitude"] + ratio * (curr["latitude"] - prev["latitude"])
                lon = prev["longitude"] + ratio * (curr["longitude"] - prev["longitude"])
                heading = self._bearing(prev["latitude"], prev["longitude"], curr["latitude"], curr["longitude"])
                u, v = curr.get("current_u", 0.0), curr.get("current_v", 0.0)
                cr = math.radians(heading)
                gu = cruise_speed * math.cos(cr) + u
                gv = cruise_speed * math.sin(cr) + v
                ground_track = (math.degrees(math.atan2(gv, gu)) + 360.0) % 360.0
                seg_dist = seg_km * ratio
                dist_travelled += seg_km / steps
                elapsed_h += (duration_hours * 0.85) * (seg_km / steps) / max(0.1, total_dist)
                energy_ratio = dist_travelled / max(0.1, total_dist)
                battery = start_battery - energy_required * energy_ratio * 0.85
                phase = "TRANSIT" if energy_ratio < 0.7 else "CURRENT_ADJUSTMENT"
                frames.append(
                    {
                        "frame": frame_idx,
                        "latitude": round(lat, 5),
                        "longitude": round(lon, 5),
                        "depth_m": 0.0,
                        "heading_deg": round(heading, 1),
                        "ground_track_deg": round(ground_track, 1),
                        "pitch_deg": 0.0,
                        "current_u": u,
                        "current_v": v,
                        "current_speed_mps": curr.get("current_speed_mps", 0.0),
                        "current_direction_deg": curr.get("current_direction_deg", 0.0),
                        "battery_percent": round(max(15.0, battery), 1),
                        "phase": phase,
                        "elapsed_hours": round(elapsed_h, 2),
                    }
                )
                frame_idx += 1
            prev = curr

        # Descent at target
        descent_depths = [0, 50, 100, 200, 350, 500]
        if target_depth not in descent_depths:
            descent_depths.append(int(target_depth))
        descent_depths = sorted(set(d for d in descent_depths if d <= max(target_depth, 500)))
        if target_depth > 500:
            descent_depths.extend([750, 1000])
        descent_depths = sorted(set(d for d in descent_depths if d <= 1000))

        for d_idx, depth in enumerate(descent_depths):
            ratio = (d_idx + 1) / len(descent_depths)
            energy_ratio = 0.85 + ratio * 0.15
            battery = start_battery - energy_required * energy_ratio
            phase = "DESCENT" if depth < target_depth else ("TARGET_APPROACH" if depth == target_depth else "DESCENT")
            if depth >= target_depth:
                phase = "TARGET_REACHED" if depth == target_depth else "DESCENT"
            frames.append(
                {
                    "frame": frame_idx,
                    "latitude": round(target_lat, 5),
                    "longitude": round(target_lon, 5),
                    "depth_m": float(depth),
                    "heading_deg": frames[-1]["heading_deg"] if frames else 0.0,
                    "ground_track_deg": frames[-1]["ground_track_deg"] if frames else 0.0,
                    "pitch_deg": -15.0 if depth > 0 else 0.0,
                    "current_u": waypoints[-1].get("current_u", 0.0),
                    "current_v": waypoints[-1].get("current_v", 0.0),
                    "current_speed_mps": waypoints[-1].get("current_speed_mps", 0.0),
                    "current_direction_deg": waypoints[-1].get("current_direction_deg", 0.0),
                    "battery_percent": round(max(15.0, battery), 1),
                    "phase": phase,
                    "elapsed_hours": round(duration_hours * (0.85 + ratio * 0.15), 2),
                }
            )
            frame_idx += 1

        return frames

    def simulate_mission(
        self,
        latitude: float,
        longitude: float,
        depth_m: float = 100.0,
        variable: str = "temperature",
        preferred_platform: str = "glider",
    ) -> dict[str, Any]:
        plan = mission_optimizer.plan_optimal_mission(latitude, longitude, depth_m, variable, preferred_platform)
        winner = plan.get("selected_winner")
        target_gap = plan["target_gap"]
        before_uncertainty = target_gap["priority_score"]

        if not winner:
            return {
                "status": "NO_FEASIBLE_MISSION",
                "target_gap": target_gap,
                "all_candidates": plan.get("all_candidates", []),
                "provenance": "CLOSED_LOOP_DECISION_SUPPORT_SIMULATION",
            }

        ptype = winner["platform_type"]
        route = winner["route_details"]
        energy = winner["energy_details"]
        eig = information_gain_engine.compute_expected_information_gain(before_uncertainty, ptype, target_depth_m=depth_m)
        after_uncertainty = eig["posterior_uncertainty_percent"]
        info_gain = eig["expected_information_gain_percent"]

        waypoints = route.get("waypoints", [])
        frames = self._build_trajectory_frames(
            waypoints,
            winner.get("energy_details", {}).get("initial_battery_percent", 82.0),
            energy["energy_required_percent"],
            route.get("effective_speed_mps", 0.35),
            depth_m,
            latitude,
            longitude,
            route.get("estimated_duration_hours", 24.0),
        )

        base_temp = target_gap.get("model_value")
        sample_depths = [0, 100, 250, depth_m, 1000]
        sampling_sequence = [self._simulate_profile_sample(latitude, longitude, d, base_temp) for d in sample_depths]

        mission_id = f"MIS-{int(abs(latitude * 100))}-{int(abs(longitude * 100))}"

        return {
            "mission_id": mission_id,
            "status": "SIMULATION_COMPLETED",
            "fleet_provenance": FLEET_PROVENANCE,
            "mission_phases": MISSION_PHASES,
            "target": {
                "latitude": latitude,
                "longitude": longitude,
                "depth_m": depth_m,
                "variable": variable,
            },
            "target_gap": target_gap,
            "all_candidates": plan.get("all_candidates", []),
            "rejected_candidates": plan.get("rejected_candidates", []),
            "selected_platform": winner,
            "routing": {
                "direct_route": route.get("direct_route"),
                "candidate_routes": route.get("candidate_routes", []),
                "selected_route": route.get("selected_route"),
                "routing_algorithm": route.get("routing_algorithm"),
                "current_field": route.get("current_field", plan.get("current_field", [])),
                "current_data_provenance": route.get("current_data_provenance"),
            },
            "trajectory_frames": frames,
            "before_simulation": {
                "information_gap_percent": before_uncertainty,
                "confidence_percent": target_gap.get("confidence_percent", 18.0),
            },
            "after_simulation": {
                "information_gap_percent": after_uncertainty,
                "confidence_percent": round(100.0 - after_uncertainty, 1),
                "label": "SIMULATED WHAT-IF RESULT",
            },
            "scientific_payoff": {
                "expected_information_gain_percent": info_gain,
                "uncertainty_reduction_percent": round((1.0 - after_uncertainty / max(1.0, before_uncertainty)) * 100.0, 1),
                "bayesian_update_formula": eig["method"],
                "label": "SIMULATED WHAT-IF RESULT",
            },
            "depth_sampling_sequence": sampling_sequence,
            "energy_timeline": {
                "initial_battery_percent": energy["initial_battery_percent"],
                "final_battery_percent": energy["energy_remaining_percent"],
                "safety_reserve_percent": energy["safety_reserve_percent"],
                "energy_required_percent": energy["energy_required_percent"],
            },
            "provenance": "CLOSED_LOOP_DECISION_SUPPORT_SIMULATION",
        }


mission_simulator = MissionSimulatorEngine()
