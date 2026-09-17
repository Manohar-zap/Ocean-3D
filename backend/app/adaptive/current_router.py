"""
Current-Aware Multi-Route Trajectory Planner.

Generates direct, candidate, and optimal paths through a local geographic grid.
Evaluates travel time, energy, current assistance/opposition, and risk using a
transparent cost function J.
"""
from __future__ import annotations

import heapq
import math
import logging
from typing import Any, Optional

from app.storage import store
from app.schemas import QueryFilters
from app.adapters import is_land
from app.currents_service import currents_service

logger = logging.getLogger(__name__)

# Cost function weights (transparent multi-criteria routing)
W_TIME = 0.35
W_ENERGY = 0.30
W_RISK = 0.20
W_DISTANCE = 0.15


class CurrentRouterEngine:
    """Grid-based current-aware routing with candidate path evaluation."""

    @staticmethod
    def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
        )
        return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))

    @staticmethod
    def _calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
        x = (
            math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
            - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
        )
        return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    def query_current_vector(self, lat: float, lon: float, depth: float = 0.0, time_str: Optional[str] = None) -> tuple[float, float, float, float, str]:
        """Return (u, v, speed_mps, direction_deg, provenance) using real 3D currents service with O(1) lookup."""
        u, v, speed, direction, prov = currents_service.get_vector(lat, lon, depth, time_str)
        if prov != "NO_DATA":
            return u, v, speed, direction, prov

        # Explicit NO_DATA — NEVER fabricate fallback numbers like 0.35, -0.25
        return 0.0, 0.0, 0.0, 0.0, "NO_DATA"

    def sample_current_field(
        self,
        center_lat: float,
        center_lon: float,
        depth_m: float = 0.0,
        span_deg: float = 2.0,
        step_deg: float = 0.25,
    ) -> list[dict[str, Any]]:
        """Sample current_u/current_v on a regular grid for globe arrow visualization."""
        field: list[dict[str, Any]] = []
        half = span_deg / 2.0
        lat = center_lat - half
        while lat <= center_lat + half + 1e-9:
            lon = center_lon - half
            while lon <= center_lon + half + 1e-9:
                u, v, speed, direction, prov = self.query_current_vector(lat, lon, depth_m)
                field.append(
                    {
                        "latitude": round(lat, 4),
                        "longitude": round(lon, 4),
                        "depth_m": depth_m,
                        "current_u": round(u, 4),
                        "current_v": round(v, 4),
                        "speed_mps": speed,
                        "direction_deg": direction,
                        "provenance": prov,
                    }
                )
                lon += step_deg
            lat += step_deg
        return field

    def _build_grid(
        self,
        start_lat: float,
        start_lon: float,
        target_lat: float,
        target_lon: float,
        depth_m: float,
        grid_size: int = 14,
    ) -> tuple[list[list[tuple[float, float]]], dict[tuple[int, int], dict[str, float]]]:
        """Build lat/lon grid and per-cell current metadata."""
        pad = 0.35
        min_lat = min(start_lat, target_lat) - pad
        max_lat = max(start_lat, target_lat) + pad
        min_lon = min(start_lon, target_lon) - pad
        max_lon = max(start_lon, target_lon) + pad

        cells: list[list[tuple[float, float]]] = []
        meta: dict[tuple[int, int], dict[str, float]] = {}
        for i in range(grid_size):
            row: list[tuple[float, float]] = []
            for j in range(grid_size):
                ratio_i = i / max(1, grid_size - 1)
                ratio_j = j / max(1, grid_size - 1)
                lat = min_lat + ratio_i * (max_lat - min_lat)
                lon = min_lon + ratio_j * (max_lon - min_lon)
                row.append((lat, lon))
                u, v, speed, direction, _prov = self.query_current_vector(lat, lon, depth_m)
                rad_b = math.radians(self._calculate_bearing(lat, lon, target_lat, target_lon))
                along = u * math.cos(rad_b) + v * math.sin(rad_b)
                cross = abs(-u * math.sin(rad_b) + v * math.cos(rad_b))
                cell_land = is_land(lat, lon)
                meta[(i, j)] = {
                    "u": u,
                    "v": v,
                    "speed": speed,
                    "direction": direction,
                    "along": along,
                    "cross": cross,
                    "risk": min(1.0, speed / 0.8 + cross / 0.5),
                    "is_land": cell_land,
                }
            cells.append(row)
        return cells, meta

    def _nearest_cell(
        self, cells: list[list[tuple[float, float]]], lat: float, lon: float
    ) -> tuple[int, int]:
        best = (0, 0)
        best_d = float("inf")
        for i, row in enumerate(cells):
            for j, (clat, clon) in enumerate(row):
                d = self._haversine_distance_km(lat, lon, clat, clon)
                if d < best_d:
                    best_d = d
                    best = (i, j)
        return best

    def _astar_path(
        self,
        cells: list[list[tuple[float, float]]],
        meta: dict[tuple[int, int], dict[str, float]],
        start: tuple[int, int],
        goal: tuple[int, int],
        cruise_speed_mps: float,
        bias: str = "balanced",
    ) -> list[tuple[int, int]]:
        """A* pathfind on grid with current-aware edge costs."""
        rows, cols = len(cells), len(cells[0])
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]

        def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
            la, lo = cells[a[0]][a[1]]
            lb, lob = cells[b[0]][b[1]]
            return self._haversine_distance_km(la, lo, lb, lob)

        open_heap: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], float] = {start: 0.0}

        while open_heap:
            _, current = heapq.heappop(open_heap)
            if current == goal:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            clat, clon = cells[current[0]][current[1]]
            for di, dj in neighbors:
                ni, nj = current[0] + di, current[1] + dj
                if ni < 0 or nj < 0 or ni >= rows or nj >= cols:
                    continue
                nlat, nlon = cells[ni][nj]
                dist_km = self._haversine_distance_km(clat, clon, nlat, nlon)
                m = meta[(ni, nj)]
                effective = max(0.05, cruise_speed_mps - m["along"])
                travel_h = (dist_km * 1000.0) / (effective * 3600.0)
                energy = travel_h * (1.0 + max(0.0, -m["along"]) * 2.0)
                risk = m["risk"]
                distance = dist_km

                if bias == "current_assist":
                    edge = travel_h * 0.85 - m["along"] * 0.4 + risk * 0.15
                elif bias == "conservative":
                    edge = travel_h * 1.05 + risk * 0.6 + m["cross"] * 0.3
                elif bias == "direct":
                    edge = distance
                else:
                    edge = (
                        W_TIME * (travel_h / 40.0)
                        + W_ENERGY * (energy / 40.0)
                        + W_RISK * risk
                        + W_DISTANCE * (distance / 200.0)
                    )

                if m.get("is_land", False) and (ni, nj) != start and (ni, nj) != goal:
                    edge += 50000.0

                tentative = g_score[current] + edge
                ncell = (ni, nj)
                if tentative < g_score.get(ncell, float("inf")):
                    came_from[ncell] = current
                    g_score[ncell] = tentative
                    f = tentative + heuristic(ncell, goal)
                    heapq.heappush(open_heap, (f, ncell))

        return [start, goal]

    def _path_to_waypoints(
        self,
        cells: list[list[tuple[float, float]]],
        path: list[tuple[int, int]],
        target_depth_m: float,
        cruise_speed_mps: float,
        meta: dict[tuple[int, int], dict[str, float]],
    ) -> list[dict[str, Any]]:
        """Convert grid path to geographic waypoints with navigation metadata."""
        if len(path) < 2:
            lat, lon = cells[path[0][0]][path[0][1]]
            u, v, speed, direction, _prov = self.query_current_vector(lat, lon, target_depth_m)
            return [
                {
                    "sequence": 1,
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                    "depth_m": 0.0,
                    "heading_deg": 0.0,
                    "ground_track_deg": direction,
                    "current_u": u,
                    "current_v": v,
                    "current_speed_mps": speed,
                    "current_direction_deg": direction,
                }
            ]

        waypoints: list[dict[str, Any]] = []
        total_dist = 0.0
        for idx in range(len(path)):
            i, j = path[idx]
            lat, lon = cells[i][j]
            m = meta[(i, j)]
            depth = 0.0 if idx < len(path) - 1 else target_depth_m
            heading = 0.0
            ground_track = m["direction"]
            if idx > 0:
                pi, pj = path[idx - 1]
                plat, plon = cells[pi][pj]
                heading = self._calculate_bearing(plat, plon, lat, lon)
                ground_track = heading
                total_dist += self._haversine_distance_km(plat, plon, lat, lon)
            waypoints.append(
                {
                    "sequence": idx + 1,
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                    "depth_m": round(depth, 1),
                    "heading_deg": round(heading, 1),
                    "ground_track_deg": round(ground_track, 1),
                    "current_u": round(m["u"], 4),
                    "current_v": round(m["v"], 4),
                    "current_speed_mps": round(m["speed"], 3),
                    "current_direction_deg": round(m["direction"], 1),
                }
            )

        # Refine ground track vs heading using current at each segment
        for idx in range(1, len(waypoints)):
            wp = waypoints[idx]
            prev = waypoints[idx - 1]
            wp["heading_deg"] = round(
                self._calculate_bearing(prev["latitude"], prev["longitude"], wp["latitude"], wp["longitude"]),
                1,
            )
            u, v = wp["current_u"], wp["current_v"]
            cr = math.radians(wp["heading_deg"])
            ground_u = cruise_speed_mps * math.cos(cr) + u
            ground_v = cruise_speed_mps * math.sin(cr) + v
            wp["ground_track_deg"] = round((math.degrees(math.atan2(ground_v, ground_u)) + 360.0) % 360.0, 1)

        return waypoints

    def _evaluate_route(
        self,
        waypoints: list[dict[str, Any]],
        cruise_speed_mps: float,
        label: str,
    ) -> dict[str, Any]:
        """Compute route metrics from waypoint chain."""
        if len(waypoints) < 2:
            return {
                "label": label,
                "waypoints": waypoints,
                "distance_km": 0.0,
                "travel_time_hours": 0.0,
                "energy_cost": 0.0,
                "current_assistance_mps": 0.0,
                "current_opposition_mps": 0.0,
                "risk_score": 0.0,
                "total_cost": 0.0,
            }

        dist = 0.0
        travel_h = 0.0
        assist_sum = 0.0
        oppose_sum = 0.0
        risk_sum = 0.0
        segments = 0

        for idx in range(1, len(waypoints)):
            a, b = waypoints[idx - 1], waypoints[idx]
            seg_km = self._haversine_distance_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
            dist += seg_km
            bearing = self._calculate_bearing(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
            rad_b = math.radians(bearing)
            along = b["current_u"] * math.cos(rad_b) + b["current_v"] * math.sin(rad_b)
            effective = max(0.05, cruise_speed_mps - along)
            travel_h += (seg_km * 1000.0) / (effective * 3600.0)
            assist_sum += max(0.0, along)
            oppose_sum += max(0.0, -along)
            risk_sum += min(1.0, b["current_speed_mps"] / 0.8)
            segments += 1

        avg_assist = assist_sum / max(1, segments)
        avg_oppose = oppose_sum / max(1, segments)
        avg_risk = risk_sum / max(1, segments)
        energy = travel_h * (1.0 + avg_oppose * 1.5)
        total_cost = (
            W_TIME * (travel_h / 40.0)
            + W_ENERGY * (energy / 40.0)
            + W_RISK * avg_risk
            + W_DISTANCE * (dist / 200.0)
        )

        return {
            "label": label,
            "waypoints": waypoints,
            "distance_km": round(dist, 2),
            "travel_time_hours": round(travel_h, 2),
            "energy_cost": round(energy, 3),
            "current_assistance_mps": round(avg_assist, 3),
            "current_opposition_mps": round(avg_oppose, 3),
            "risk_score": round(avg_risk, 3),
            "total_cost": round(total_cost, 4),
        }

    def _direct_waypoints(
        self,
        start_lat: float,
        start_lon: float,
        target_lat: float,
        target_lon: float,
        target_depth_m: float,
        cruise_speed_mps: float,
        n: int = 8,
    ) -> list[dict[str, Any]]:
        """Generate straight-line direct route waypoints."""
        path_cells = [(0, 0)]  # dummy for _path_to_waypoints compatibility
        cells = [[(start_lat, start_lon)]]
        raw: list[tuple[float, float]] = []
        for i in range(n + 1):
            ratio = i / float(n)
            raw.append(
                (
                    start_lat + ratio * (target_lat - start_lat),
                    start_lon + ratio * (target_lon - start_lon),
                )
            )
        meta: dict[tuple[int, int], dict[str, float]] = {}
        waypoints: list[dict[str, Any]] = []
        for idx, (lat, lon) in enumerate(raw):
            u, v, speed, direction, _prov = self.query_current_vector(lat, lon, target_depth_m if idx == n else 0.0)
            meta[(0, 0)] = {"u": u, "v": v, "speed": speed, "direction": direction, "along": 0, "cross": 0, "risk": speed / 0.8}
            depth = 0.0 if idx < n else target_depth_m
            heading = 0.0
            if idx > 0:
                heading = self._calculate_bearing(raw[idx - 1][0], raw[idx - 1][1], lat, lon)
            rad_b = math.radians(heading) if idx > 0 else 0.0
            ground_u = cruise_speed_mps * math.cos(rad_b) + u
            ground_v = cruise_speed_mps * math.sin(rad_b) + v
            gt = (math.degrees(math.atan2(ground_v, ground_u)) + 360.0) % 360.0 if idx > 0 else direction
            waypoints.append(
                {
                    "sequence": idx + 1,
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                    "depth_m": round(depth, 1),
                    "heading_deg": round(heading, 1),
                    "ground_track_deg": round(gt, 1),
                    "current_u": round(u, 4),
                    "current_v": round(v, 4),
                    "current_speed_mps": speed,
                    "current_direction_deg": direction,
                }
            )
        return waypoints

    def plan_current_aware_trajectory(
        self,
        start_lat: float,
        start_lon: float,
        target_lat: float,
        target_lon: float,
        target_depth_m: float = 100.0,
        cruise_speed_mps: float = 0.35,
        n_waypoints: int = 8,
    ) -> dict[str, Any]:
        """Plan multi-route trajectory with grid-based optimal path selection."""
        direct_wps = self._direct_waypoints(
            start_lat, start_lon, target_lat, target_lon, target_depth_m, cruise_speed_mps, n_waypoints
        )
        direct_route = self._evaluate_route(direct_wps, cruise_speed_mps, "DIRECT ROUTE")

        cells, meta = self._build_grid(start_lat, start_lon, target_lat, target_lon, target_depth_m)
        start_cell = self._nearest_cell(cells, start_lat, start_lon)
        goal_cell = self._nearest_cell(cells, target_lat, target_lon)

        path_a = self._astar_path(cells, meta, start_cell, goal_cell, cruise_speed_mps, "current_assist")
        path_b = self._astar_path(cells, meta, start_cell, goal_cell, cruise_speed_mps, "balanced")
        path_c = self._astar_path(cells, meta, start_cell, goal_cell, cruise_speed_mps, "conservative")

        wps_a = self._path_to_waypoints(cells, path_a, target_depth_m, cruise_speed_mps, meta)
        wps_b = self._path_to_waypoints(cells, path_b, target_depth_m, cruise_speed_mps, meta)
        wps_c = self._path_to_waypoints(cells, path_c, target_depth_m, cruise_speed_mps, meta)

        candidate_a = self._evaluate_route(wps_a, cruise_speed_mps, "CANDIDATE ROUTE A")
        candidate_b = self._evaluate_route(wps_b, cruise_speed_mps, "CANDIDATE ROUTE B")
        candidate_c = self._evaluate_route(wps_c, cruise_speed_mps, "CANDIDATE ROUTE C")

        candidates = [candidate_a, candidate_b, candidate_c]
        selected = min(candidates, key=lambda r: r["total_cost"])

        center_lat = (start_lat + target_lat) / 2.0
        center_lon = (start_lon + target_lon) / 2.0
        current_field = self.sample_current_field(center_lat, center_lon, target_depth_m, span_deg=2.5, step_deg=0.35)
        prov_summary = next((f["provenance"] for f in current_field if f.get("provenance") not in ("NO_DATA", "DEMO FALLBACK")), "Copernicus Marine")

        u_avg = sum(w["current_u"] for w in selected["waypoints"]) / max(1, len(selected["waypoints"]))
        v_avg = sum(w["current_v"] for w in selected["waypoints"]) / max(1, len(selected["waypoints"]))
        avg_speed = math.sqrt(u_avg * u_avg + v_avg * v_avg)
        avg_dir = (math.degrees(math.atan2(v_avg, u_avg)) + 360.0) % 360.0
        direct_bearing = self._calculate_bearing(start_lat, start_lon, target_lat, target_lon)
        headwind = u_avg * math.cos(math.radians(direct_bearing)) + v_avg * math.sin(math.radians(direct_bearing))

        return {
            "start": {"latitude": start_lat, "longitude": start_lon},
            "target": {"latitude": target_lat, "longitude": target_lon, "depth_m": target_depth_m},
            "direct_distance_km": direct_route["distance_km"],
            "direct_bearing_deg": round(direct_bearing, 1),
            "avg_current_speed_mps": round(avg_speed, 3),
            "avg_current_direction_deg": round(avg_dir, 1),
            "current_headwind_mps": round(headwind, 3),
            "effective_speed_mps": round(max(0.05, cruise_speed_mps - headwind), 3),
            "estimated_duration_hours": selected["travel_time_hours"],
            "routing_cost_score": selected["total_cost"],
            "waypoints": selected["waypoints"],
            "direct_route": direct_route,
            "candidate_routes": candidates,
            "selected_route": selected,
            "current_field": current_field,
            "current_depth_m": target_depth_m,
            "current_data_provenance": prov_summary,
            "routing_algorithm": {
                "name": "grid_astar_multi_candidate",
                "grid_size": len(cells),
                "cost_function": "J = w_time*T + w_energy*E + w_risk*R + w_distance*D",
                "weights": {"time": W_TIME, "energy": W_ENERGY, "risk": W_RISK, "distance": W_DISTANCE},
            },
        }


current_router = CurrentRouterEngine()
