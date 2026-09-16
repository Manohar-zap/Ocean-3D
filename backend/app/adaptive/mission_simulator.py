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

    def query_seafloor_depth(self, lat: float, lon: float) -> tuple[Optional[float], str]:
        """Query GEBCO/ETOPO seafloor bathymetry depth in meters."""
        rows = store.query_model(
            QueryFilters(
                dataset_id="gebco_bathymetry",
                variable="elevation",
                min_lat=lat - 0.2,
                max_lat=lat + 0.2,
                min_lon=lon - 0.2,
                max_lon=lon + 0.2,
            )
        )
        if rows and rows[0].value < 0:
            seafloor_m = round(abs(rows[0].value), 1)
            return seafloor_m, "GEBCO 2023 Bathymetry"
        return None, "BATHYMETRY UNAVAILABLE — DEPTH LIMIT SIMULATION"

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
        platform_type: str,
        waypoints: list[dict[str, Any]],
        start_battery: float,
        cruise_speed: float,
        target_depth: float,
        target_lat: float,
        target_lon: float,
        duration_hours: float,
        safety_reserve_percent: float = 15.0,
    ) -> list[dict[str, Any]]:
        """Dense trajectory with state-based energy consumption, depth, heading, ground track per frame."""
        frames: list[dict[str, Any]] = []
        if not waypoints:
            return frames

        ptype = (platform_type or "glider").lower().strip()
        if ptype == "auv":
            p_prop = 120.0
            p_sensor = 25.0
            p_pump = 35.0
            capacity_wh = 4800.0
        elif ptype == "vessel":
            p_prop = 500000.0
            p_sensor = 1500.0
            p_pump = 0.0
            capacity_wh = 10000000.0
        else:  # glider
            p_prop = 8.5
            p_sensor = 3.2
            p_pump = 15.0
            capacity_wh = 3200.0

        total_dist_km = 0.0
        for i in range(1, len(waypoints)):
            total_dist_km += self._haversine_km(
                waypoints[i - 1]["latitude"], waypoints[i - 1]["longitude"],
                waypoints[i]["latitude"], waypoints[i]["longitude"]
            )
        total_dist_km = max(0.1, total_dist_km)

        cum_energy_wh = 0.0
        cum_distance_km = 0.0
        elapsed_h = 0.0
        frame_idx = 0

        # 1. Initial Deployment Frame
        dep_energy_wh = (p_sensor * 0.5) * 0.1
        cum_energy_wh += dep_energy_wh
        elapsed_h += 0.1
        used_pct = (cum_energy_wh / capacity_wh) * 100.0
        cur_batt = start_battery - used_pct
        rem_wh = max(0.0, (cur_batt / 100.0) * capacity_wh)

        frames.append({
            "frame": frame_idx,
            "latitude": round(waypoints[0]["latitude"], 5),
            "longitude": round(waypoints[0]["longitude"], 5),
            "depth_m": 0.0,
            "heading_deg": round(waypoints[0].get("heading_deg", 0.0), 1),
            "ground_track_deg": round(waypoints[0].get("ground_track_deg", 0.0), 1),
            "pitch_deg": 0.0,
            "current_u": round(waypoints[0].get("current_u", 0.0), 4),
            "current_v": round(waypoints[0].get("current_v", 0.0), 4),
            "current_speed_mps": round(waypoints[0].get("current_speed_mps", 0.0), 3),
            "current_direction_deg": round(waypoints[0].get("current_direction_deg", 0.0), 1),
            "effective_speed_mps": round(cruise_speed, 2),
            "distance_travelled_km": 0.0,
            "distance_remaining_km": round(total_dist_km, 2),
            "elapsed_hours": round(elapsed_h, 2),
            "initial_battery_percent": round(start_battery, 1),
            "battery_percent": round(max(0.0, cur_batt), 1),
            "energy_used_percent": round(used_pct, 1),
            "energy_used_wh": round(cum_energy_wh, 1),
            "energy_remaining_wh": round(rem_wh, 1),
            "safety_reserve_percent": round(safety_reserve_percent, 1),
            "battery_state": "NORMAL" if cur_batt >= safety_reserve_percent + 15 else ("WARNING" if cur_batt >= safety_reserve_percent else "CRITICAL"),
            "phase": "DEPLOYMENT"
        })
        frame_idx += 1

        # 2. Transit Waypoint Frames
        prev = waypoints[0]
        for i in range(1, len(waypoints)):
            curr = waypoints[i]
            seg_km = self._haversine_km(prev["latitude"], prev["longitude"], curr["latitude"], curr["longitude"])
            steps = max(3, int(seg_km / 5.0))

            heading = self._bearing(prev["latitude"], prev["longitude"], curr["latitude"], curr["longitude"])
            u, v = curr.get("current_u", 0.0), curr.get("current_v", 0.0)
            rad_h = math.radians(heading)
            along = u * math.cos(rad_h) + v * math.sin(rad_h)
            v_eff = max(0.05, cruise_speed + along)
            rad_c = math.radians(heading)
            gu = cruise_speed * math.cos(rad_c) + u
            gv = cruise_speed * math.sin(rad_c) + v
            ground_track = (math.degrees(math.atan2(gv, gu)) + 360.0) % 360.0

            # Power calculation with current drag penalty
            power_w = p_prop * (1.0 + max(0.0, -along) * 1.5) + p_sensor

            for s in range(1, steps + 1):
                step_km = seg_km / steps
                step_hours = (step_km * 1000.0) / (v_eff * 3600.0)
                step_energy_wh = power_w * step_hours

                cum_distance_km += step_km
                elapsed_h += step_hours
                cum_energy_wh += step_energy_wh
                used_pct = (cum_energy_wh / capacity_wh) * 100.0
                cur_batt = start_battery - used_pct
                rem_wh = max(0.0, (cur_batt / 100.0) * capacity_wh)

                ratio = s / steps
                lat = prev["latitude"] + ratio * (curr["latitude"] - prev["latitude"])
                lon = prev["longitude"] + ratio * (curr["longitude"] - prev["longitude"])

                batt_state = "NORMAL"
                if cur_batt < safety_reserve_percent:
                    batt_state = "CRITICAL"
                elif cur_batt < safety_reserve_percent + 15.0:
                    batt_state = "WARNING"

                phase = "TRANSIT" if i < len(waypoints) - 1 else "CURRENT_ADJUSTMENT"

                frames.append({
                    "frame": frame_idx,
                    "latitude": round(lat, 5),
                    "longitude": round(lon, 5),
                    "depth_m": 0.0,
                    "heading_deg": round(heading, 1),
                    "ground_track_deg": round(ground_track, 1),
                    "pitch_deg": -2.0,
                    "current_u": round(u, 4),
                    "current_v": round(v, 4),
                    "current_speed_mps": round(curr.get("current_speed_mps", 0.0), 3),
                    "current_direction_deg": round(curr.get("current_direction_deg", 0.0), 1),
                    "effective_speed_mps": round(v_eff, 2),
                    "distance_travelled_km": round(cum_distance_km, 2),
                    "distance_remaining_km": round(max(0.0, total_dist_km - cum_distance_km), 2),
                    "elapsed_hours": round(elapsed_h, 2),
                    "initial_battery_percent": round(start_battery, 1),
                    "battery_percent": round(max(0.0, cur_batt), 1),
                    "energy_used_percent": round(used_pct, 1),
                    "energy_used_wh": round(cum_energy_wh, 1),
                    "energy_remaining_wh": round(rem_wh, 1),
                    "safety_reserve_percent": round(safety_reserve_percent, 1),
                    "battery_state": batt_state,
                    "phase": phase,
                })
                frame_idx += 1
            prev = curr

        # 3. Descent & Deep Sampling Frames
        descent_depths = [0, 50, 100, 200, 350, int(target_depth)]
        if target_depth > 500:
            descent_depths.extend([750, 1000])
        descent_depths = sorted(set(d for d in descent_depths if d <= 1000))

        last_wp = waypoints[-1]
        for d_idx in range(1, len(descent_depths)):
            d_curr = descent_depths[d_idx]
            d_prev = descent_depths[d_idx - 1]
            delta_d = d_curr - d_prev

            descent_h = delta_d / (0.15 * 3600.0)
            descent_power_w = p_prop + p_pump + p_sensor
            descent_energy_wh = descent_power_w * descent_h

            elapsed_h += descent_h
            cum_energy_wh += descent_energy_wh
            used_pct = (cum_energy_wh / capacity_wh) * 100.0
            cur_batt = start_battery - used_pct
            rem_wh = max(0.0, (cur_batt / 100.0) * capacity_wh)

            if d_curr < target_depth:
                phase = "DESCENT"
                pitch = -20.0
            elif d_curr == target_depth:
                phase = "TARGET_REACHED"
                pitch = 0.0
            else:
                phase = "DEEP_SAMPLING"
                pitch = -12.0

            batt_state = "NORMAL"
            if cur_batt < safety_reserve_percent:
                batt_state = "CRITICAL"
            elif cur_batt < safety_reserve_percent + 15.0:
                batt_state = "WARNING"

            frames.append({
                "frame": frame_idx,
                "latitude": round(target_lat, 5),
                "longitude": round(target_lon, 5),
                "depth_m": float(d_curr),
                "heading_deg": frames[-1]["heading_deg"] if frames else 0.0,
                "ground_track_deg": frames[-1]["ground_track_deg"] if frames else 0.0,
                "pitch_deg": pitch,
                "current_u": round(last_wp.get("current_u", 0.0), 4),
                "current_v": round(last_wp.get("current_v", 0.0), 4),
                "current_speed_mps": round(last_wp.get("current_speed_mps", 0.0), 3),
                "current_direction_deg": round(last_wp.get("current_direction_deg", 0.0), 1),
                "effective_speed_mps": round(cruise_speed, 2),
                "distance_travelled_km": round(cum_distance_km, 2),
                "distance_remaining_km": 0.0,
                "elapsed_hours": round(elapsed_h, 2),
                "initial_battery_percent": round(start_battery, 1),
                "battery_percent": round(max(0.0, cur_batt), 1),
                "energy_used_percent": round(used_pct, 1),
                "energy_used_wh": round(cum_energy_wh, 1),
                "energy_remaining_wh": round(rem_wh, 1),
                "safety_reserve_percent": round(safety_reserve_percent, 1),
                "battery_state": batt_state,
                "phase": phase,
            })
            frame_idx += 1

        for f in frames:
            f["is_simulated"] = True
            f["provenance"] = "SIMULATED_TRAJECTORY_FRAME"

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
                "decision": "NO_FEASIBLE_PLATFORM",
                "failure_reason": (
                    f"No controllable observing platform in the active fleet possesses sufficient range, "
                    f"depth rating, or energy reserve to reach this remote information gap ({latitude:.2f}°, {longitude:.2f}°)."
                ),
                "recommended_alternatives": [
                    "Dispatch vessel-supported hydrographic expedition (ORV Sagar Kanya)",
                    "Air-deploy autonomous deep-profiling BGC-Argo float",
                    "Maintain remote monitoring via satellite altimetry & SST radiometry",
                    "Monitor for future opportunistic mobile asset repositioning"
                ],
                "target_gap": target_gap,
                "all_candidates": plan.get("all_candidates", []),
                "rejected_candidates": plan.get("rejected_candidates", []),
                "provenance": "CLOSED_LOOP_DECISION_SUPPORT_SIMULATION",
                "is_simulated": True,
            }

        ptype = winner["platform_type"]
        route = winner["route_details"]
        energy = winner["energy_details"]
        eig = information_gain_engine.compute_expected_information_gain(before_uncertainty, ptype, target_depth_m=depth_m)
        after_uncertainty = eig["posterior_uncertainty_percent"]
        info_gain = eig["expected_information_gain_percent"]

        seafloor_m, bathy_status = self.query_seafloor_depth(latitude, longitude)

        waypoints = route.get("waypoints", [])
        frames = self._build_trajectory_frames(
            ptype,
            waypoints,
            winner.get("energy_details", {}).get("initial_battery_percent", 82.0),
            route.get("effective_speed_mps", 0.35),
            depth_m,
            latitude,
            longitude,
            route.get("estimated_duration_hours", 24.0),
            winner.get("energy_details", {}).get("safety_reserve_percent", 15.0),
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
            "seafloor_depth_m": seafloor_m,
            "bathymetry_status": bathy_status,
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
            "is_simulated": True,
            "simulation_notice": "ALL TRAJECTORY COORDINATES, VELOCITIES, BATTERY LEVELS, AND SOUNDINGS ARE NUMERICALLY SIMULATED FOR MISSION PLANNING ONLY",
        }


mission_simulator = MissionSimulatorEngine()
