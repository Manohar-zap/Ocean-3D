"""
Current-Aware Trajectory & Routing Module.

Interpolates hydrodynamic current velocity vectors (current_u, current_v) along candidate routes.
Calculates current-adjusted heading angles, ground speeds, travel times, and current-assisted waypoints.
"""
from __future__ import annotations
import math
import logging
from typing import Optional, Any

from app.storage import store
from app.schemas import QueryFilters

logger = logging.getLogger(__name__)


class CurrentRouterEngine:
    """Current-Aware Waypoint Trajectory Planner."""

    @staticmethod
    def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2.0) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2)
        return round(2.0 * r * math.asin(min(1.0, math.sqrt(a))), 2)

    @staticmethod
    def _calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
        x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) -
             math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1)))
        return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    def query_current_vector(self, lat: float, lon: float, depth: float = 0.0) -> tuple[float, float, float, float]:
        """Queries local current_u and current_v from model store, returning (u, v, speed_mps, dir_deg)."""
        rows_u = store.query_model(QueryFilters(dataset_id="incois_las_model", variable="current_u", min_lat=lat-1, max_lat=lat+1, min_lon=lon-1, max_lon=lon+1, min_depth=depth, max_depth=depth))
        rows_v = store.query_model(QueryFilters(dataset_id="incois_las_model", variable="current_v", min_lat=lat-1, max_lat=lat+1, min_lon=lon-1, max_lon=lon+1, min_depth=depth, max_depth=depth))
        
        u = (sum(r.value for r in rows_u) / len(rows_u)) if rows_u else 0.35
        v = (sum(r.value for r in rows_v) / len(rows_v)) if rows_v else -0.25

        speed = math.sqrt(u * u + v * v)
        direction = (math.degrees(math.atan2(v, u)) + 360.0) % 360.0
        return u, v, round(speed, 3), round(direction, 1)

    def plan_current_aware_trajectory(
        self,
        start_lat: float, start_lon: float,
        target_lat: float, target_lon: float, target_depth_m: float = 100.0,
        cruise_speed_mps: float = 0.35,
        n_waypoints: int = 5
    ) -> dict[str, Any]:
        direct_dist = self._haversine_distance_km(start_lat, start_lon, target_lat, target_lon)
        direct_bearing = self._calculate_bearing(start_lat, start_lon, target_lat, target_lon)

        waypoints = []
        u_avg, v_avg = 0.0, 0.0

        for i in range(n_waypoints + 1):
            ratio = i / float(n_waypoints)
            w_lat = start_lat + ratio * (target_lat - start_lat)
            w_lon = start_lon + ratio * (target_lon - start_lon)
            
            # Add slight lateral offset toward current stream for current-assisted routing
            u, v, c_speed, c_dir = self.query_current_vector(w_lat, w_lon, target_depth_m)
            u_avg += u
            v_avg += v

            # Current-assisted lateral deviation
            offset_factor = 0.05 * math.sin(ratio * math.pi)
            opt_lat = w_lat + v * offset_factor
            opt_lon = w_lon + u * offset_factor

            waypoints.append({
                "sequence": i + 1,
                "latitude": round(opt_lat, 4),
                "longitude": round(opt_lon, 4),
                "depth_m": round(target_depth_m * min(1.0, ratio * 1.2), 1),
                "current_speed_mps": c_speed,
                "current_direction_deg": c_dir
            })

        u_avg /= (n_waypoints + 1)
        v_avg /= (n_waypoints + 1)
        avg_current_speed = math.sqrt(u_avg * u_avg + v_avg * v_avg)
        avg_current_dir = (math.degrees(math.atan2(v_avg, u_avg)) + 360.0) % 360.0

        # Current opposition/assistance component along bearing
        rad_b = math.radians(direct_bearing)
        current_headwind = u_avg * math.cos(rad_b) + v_avg * math.sin(rad_b)

        # Cost Objective Function C = w_t * T_travel + w_e * E_consumption + w_r * Risk
        effective_speed = max(0.05, cruise_speed_mps - current_headwind)
        duration_hours = (direct_dist * 1000.0) / (effective_speed * 3600.0)

        cost_score = round(duration_hours * 1.2 + (avg_current_speed * 15.0), 2)

        return {
            "start": {"latitude": start_lat, "longitude": start_lon},
            "target": {"latitude": target_lat, "longitude": target_lon, "depth_m": target_depth_m},
            "direct_distance_km": direct_dist,
            "direct_bearing_deg": round(direct_bearing, 1),
            "avg_current_speed_mps": round(avg_current_speed, 3),
            "avg_current_direction_deg": round(avg_current_dir, 1),
            "current_headwind_mps": round(current_headwind, 3),
            "effective_speed_mps": round(effective_speed, 3),
            "estimated_duration_hours": round(duration_hours, 1),
            "routing_cost_score": cost_score,
            "waypoints": waypoints
        }


current_router = CurrentRouterEngine()
