"""
Adaptive Ocean Observation Engine.

Prototype decision layer for Ocean 3D:
    observations + model -> information-gap score -> mission recommendation

Important: this module is a decision-support simulator. It does not command
physical INCOIS/ISRO vehicles. Uncertainty is an explicit, reproducible
proxy derived from observation density, observation age and local
model-observation disagreement. The design is intentionally replaceable with
an ensemble/probabilistic ML uncertainty model later.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

from .storage import store
from .schemas import QueryFilters


class AdaptiveObservationEngine:
    """Computes information gaps and constrained observation recommendations."""

    DEFAULT_VARIABLE = "temperature"
    DEFAULT_DEPTH = 100.0

    # Prototype operational limits; expose these in API responses so they are
    # transparent rather than pretending to be vehicle-specific specifications.
    PLATFORM_LIMITS = {
        "argo": {"max_range_km": 1000.0, "max_depth_m": 2000.0, "mobility": 0.20},
        "glider": {"max_range_km": 400.0, "max_depth_m": 1000.0, "mobility": 0.75},
        "auv": {"max_range_km": 120.0, "max_depth_m": 1000.0, "mobility": 1.00},
    }

    def _parse_time(self, value: str) -> datetime:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(min(1.0, math.sqrt(a)))

    def _nearby_observations(self, lat: float, lon: float, depth: float, variable: str, radius_km: float = 350.0):
        rows = store.query_observations(QueryFilters(
            variable=variable,
            min_lat=max(-90.0, lat - 5.0), max_lat=min(90.0, lat + 5.0),
            min_lon=max(-180.0, lon - 5.0), max_lon=min(180.0, lon + 5.0),
            min_depth=max(0.0, depth - 150.0), max_depth=depth + 150.0,
        ))
        ranked = []
        for row in rows:
            d = self._distance_km(lat, lon, row.latitude, row.longitude)
            if d <= radius_km:
                ranked.append((d, row))
        ranked.sort(key=lambda x: x[0])
        return ranked[:40]

    def _model_value(self, lat: float, lon: float, depth: float, variable: str) -> Optional[float]:
        rows = store.query_model(QueryFilters(
            dataset_id="incois_las_model", variable=variable,
            min_lat=lat - 1.0, max_lat=lat + 1.0,
            min_lon=lon - 1.0, max_lon=lon + 1.0,
            min_depth=depth, max_depth=depth,
        ))
        if not rows:
            return None
        return sum(r.value for r in rows) / len(rows)

    def score_location(self, lat: float, lon: float, depth: float, variable: str = DEFAULT_VARIABLE) -> dict[str, Any]:
        observations = self._nearby_observations(lat, lon, depth, variable)
        model_value = self._model_value(lat, lon, depth, variable)
        now = datetime.now(timezone.utc)

        if observations:
            nearest_distance = observations[0][0]
            age_hours = min(
                max(0.0, (now - self._parse_time(observations[0][1].time)).total_seconds() / 3600.0),
                720.0,
            )
            residuals = []
            if model_value is not None:
                for _, row in observations[:12]:
                    residuals.append(abs(row.value - model_value))
            residual = sum(residuals) / len(residuals) if residuals else 0.0
        else:
            nearest_distance = 500.0
            age_hours = 720.0
            residual = 1.0

        # Three interpretable uncertainty components, each normalized 0..1.
        spatial_gap = min(1.0, nearest_distance / 250.0)
        temporal_gap = min(1.0, age_hours / 240.0)
        disagreement = min(1.0, residual / 1.5)

        # Observation density is intentionally weighted highest: a sparse area
        # is the primary signal for an information gap.
        uncertainty = 100.0 * (
            0.50 * spatial_gap +
            0.25 * temporal_gap +
            0.25 * disagreement
        )

        confidence = max(0.0, min(100.0, 100.0 - uncertainty))
        return {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "depth": round(depth, 1),
            "variable": variable,
            "model_value": round(model_value, 3) if model_value is not None else None,
            "uncertainty": round(uncertainty, 2),
            "confidence": round(confidence, 2),
            "components": {
                "spatial_gap": round(spatial_gap * 100.0, 2),
                "temporal_gap": round(temporal_gap * 100.0, 2),
                "model_observation_disagreement": round(disagreement * 100.0, 2),
            },
            "nearest_observation_km": round(nearest_distance, 2),
            "nearest_observation_age_hours": round(age_hours, 2),
            "observation_count": len(observations),
            "provenance": "DERIVED_FROM_MODEL_AND_OBSERVATIONS",
        }

    def uncertainty_field(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        depth: float = DEFAULT_DEPTH,
        variable: str = DEFAULT_VARIABLE,
        step: float = 2.0,
    ) -> dict[str, Any]:
        # Keep the demo bounded: a coarse decision grid is sufficient for the
        # planning layer and avoids pretending the uncertainty is high-resolution.
        points = []
        lat = min_lat
        while lat <= max_lat + 1e-9 and len(points) < 2500:
            lon = min_lon
            while lon <= max_lon + 1e-9 and len(points) < 2500:
                points.append(self.score_location(lat, lon, depth, variable))
                lon += step
            lat += step
        return {
            "variable": variable,
            "depth": depth,
            "grid_step_degrees": step,
            "count": len(points),
            "points": points,
            "method": "Weighted spatial-gap + temporal-staleness + model-observation disagreement proxy",
        }

    def _nearest_platform(self, lat: float, lon: float, platform_type: Optional[str] = None):
        f = QueryFilters(platform_type=platform_type) if platform_type else QueryFilters()
        rows = store.query_observations(f)
        if not rows:
            return None
        by_platform: dict[str, Any] = {}
        for row in rows:
            pid = row.platform_id or "unknown"
            if pid not in by_platform:
                by_platform[pid] = row
            else:
                old = by_platform[pid]
                if row.time > old.time:
                    by_platform[pid] = row
        ranked = []
        for row in by_platform.values():
            d = self._distance_km(lat, lon, row.latitude, row.longitude)
            ranked.append((d, row))
        return min(ranked, key=lambda x: x[0]) if ranked else None

    def recommend(
        self,
        lat: float,
        lon: float,
        depth: float = DEFAULT_DEPTH,
        variable: str = DEFAULT_VARIABLE,
        platform: str = "glider",
    ) -> dict[str, Any]:
        gap = self.score_location(lat, lon, depth, variable)
        platform = platform.lower()
        if platform not in self.PLATFORM_LIMITS:
            platform = "glider"
        limits = self.PLATFORM_LIMITS[platform]

        nearest = self._nearest_platform(lat, lon, platform)
        distance = nearest[0] if nearest else 999.0
        current = self._model_value(lat, lon, depth, "current_u")
        current_v = self._model_value(lat, lon, depth, "current_v")
        current_speed = math.sqrt((current or 0.0) ** 2 + (current_v or 0.0) ** 2)

        depth_feasible = depth <= limits["max_depth_m"]
        range_feasible = distance <= limits["max_range_km"]
        current_penalty = min(1.0, current_speed / 1.5)
        feasibility = (0.55 if range_feasible else 0.10) + (0.35 if depth_feasible else 0.05) - 0.20 * current_penalty
        feasibility = max(0.0, min(1.0, feasibility))

        # Utility is the decision layer: information need multiplied by
        # practical feasibility. It is deliberately transparent for judging.
        utility = gap["uncertainty"] / 100.0 * feasibility * 100.0
        mission_status = "RECOMMEND" if utility >= 45.0 and gap["uncertainty"] >= 55.0 else "MONITOR"

        bearing = 0.0
        if nearest:
            y = math.sin(math.radians(lon - nearest[1].longitude)) * math.cos(math.radians(lat))
            x = math.cos(math.radians(nearest[1].latitude)) * math.sin(math.radians(lat)) - math.sin(math.radians(nearest[1].latitude)) * math.cos(math.radians(lat)) * math.cos(math.radians(lon - nearest[1].longitude))
            bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

        return {
            "decision": mission_status,
            "target": gap,
            "recommended_platform": platform,
            "platform_constraints": limits,
            "nearest_platform": {
                "platform_id": nearest[1].platform_id if nearest else None,
                "distance_km": round(distance, 2),
                "bearing_deg": round(bearing, 1),
            },
            "current_speed_ms": round(current_speed, 3),
            "feasibility": round(feasibility * 100.0, 2),
            "utility_score": round(utility, 2),
            "waypoint": {"latitude": lat, "longitude": lon, "depth_m": depth},
            "recommended_action": (
                f"Deploy/route {platform.upper()} toward the target at {depth:.0f} m"
                if mission_status == "RECOMMEND"
                else "Continue monitoring; current information gap does not justify a new mission"
            ),
            "provenance": "DECISION_SUPPORT_SIMULATION",
        }

    def simulate(self, lat: float, lon: float, depth: float = DEFAULT_DEPTH, variable: str = DEFAULT_VARIABLE):
        before = self.score_location(lat, lon, depth, variable)
        # A virtual profile at the selected point is treated as an observation.
        # Re-score with an explicit synthetic nearby observation by reducing the
        # spatial/temporal gap. This is a what-if simulation, not real data.
        after_uncertainty = before["uncertainty"] * 0.35
        after = dict(before)
        after["uncertainty"] = round(after_uncertainty, 2)
        after["confidence"] = round(100.0 - after_uncertainty, 2)
        after["nearest_observation_km"] = 0.0
        after["nearest_observation_age_hours"] = 0.0
        after["observation_count"] = before["observation_count"] + 1
        return {
            "status": "SIMULATED",
            "target": {"latitude": lat, "longitude": lon, "depth": depth, "variable": variable},
            "before": before,
            "virtual_observation": {
                "value": before["model_value"],
                "unit": "degC" if variable == "temperature" else "unknown",
                "note": "Synthetic observation used only for what-if evaluation",
            },
            "after": after,
            "uncertainty_reduction_percent": round((1.0 - after_uncertainty / max(before["uncertainty"], 0.001)) * 100.0, 2),
            "provenance": "SIMULATION_ONLY",
        }


adaptive_engine = AdaptiveObservationEngine()
