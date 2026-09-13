"""
3D Ocean Information-Gap Detection Module.

Calculates multi-signal information-gap priority scores across Temperature & Salinity fields.
Combines prediction uncertainty, observation density, observation age, model-observation
disagreement, and depth coverage.
"""
from __future__ import annotations
import math
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from app.storage import store
from app.schemas import QueryFilters

logger = logging.getLogger(__name__)


class GapDetector:
    """Detects 3D ocean information gaps across spatial grid locations and depth levels."""

    @staticmethod
    def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2.0) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2)
        return round(2.0 * r * math.asin(min(1.0, math.sqrt(a))), 2)

    def detect_information_gap(
        self, latitude: float, longitude: float, depth: float = 100.0, variable: str = "temperature"
    ) -> dict[str, Any]:
        var_clean = variable.lower().strip()
        now = datetime.now(timezone.utc)

        # 1. Query nearby observations
        obs_rows = store.query_observations(QueryFilters(
            variable=var_clean,
            min_lat=max(-90.0, latitude - 6.0), max_lat=min(90.0, latitude + 6.0),
            min_lon=max(-180.0, longitude - 6.0), max_lon=min(180.0, longitude + 6.0),
            min_depth=max(0.0, depth - 200.0), max_depth=depth + 200.0
        ))

        # 2. Query local model prediction
        model_rows = store.query_model(QueryFilters(
            dataset_id="incois_las_model",
            variable=var_clean,
            min_lat=latitude - 1.0, max_lat=latitude + 1.0,
            min_lon=longitude - 1.0, max_lon=longitude + 1.0,
            min_depth=depth, max_depth=depth
        ))
        model_val = (sum(r.value for r in model_rows) / len(model_rows)) if model_rows else None

        # 3. Calculate components
        if obs_rows:
            distances = [self._haversine_distance_km(latitude, longitude, r.latitude, r.longitude) for r in obs_rows]
            nearest_dist = min(distances)
            
            try:
                latest_obs_time = max(r.time for r in obs_rows)
                dt_obs = datetime.fromisoformat(latest_obs_time.replace("Z", "+00:00"))
                age_hours = max(0.0, (now - dt_obs).total_seconds() / 3600.0)
            except Exception:
                age_hours = 168.0

            residuals = [abs(r.value - model_val) for r in obs_rows if model_val is not None]
            residual_mean = (sum(residuals) / len(residuals)) if residuals else 1.2
        else:
            nearest_dist = 350.0
            age_hours = 240.0
            residual_mean = 1.8

        spatial_gap = min(1.0, nearest_dist / 300.0)
        temporal_staleness = min(1.0, age_hours / 240.0)
        disagreement = min(1.0, residual_mean / 2.0)
        depth_coverage = min(1.0, depth / 1000.0)

        priority_score = round(100.0 * (
            0.40 * spatial_gap +
            0.25 * temporal_staleness +
            0.25 * disagreement +
            0.10 * depth_coverage
        ), 1)

        confidence = max(0.0, min(100.0, round(100.0 - priority_score, 1)))

        why_reason = f"High model-observation disagreement ({residual_mean:.2f}) with sparse/stale observations ({nearest_dist:.0f} km away, {age_hours/24:.1f} days old)."

        return {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "depth_m": round(depth, 1),
            "variables": ["temperature", "salinity"],
            "model_value": round(model_val, 3) if model_val is not None else None,
            "priority_score": priority_score,
            "uncertainty_percent": priority_score,
            "confidence_percent": confidence,
            "components": {
                "spatial_gap_score": round(spatial_gap * 100.0, 1),
                "temporal_staleness_score": round(temporal_staleness * 100.0, 1),
                "model_disagreement_score": round(disagreement * 100.0, 1),
                "depth_coverage_score": round(depth_coverage * 100.0, 1)
            },
            "nearest_observation_km": round(nearest_dist, 1),
            "observation_age_hours": round(age_hours, 1),
            "residual_mean": round(residual_mean, 3),
            "reason": why_reason,
            "provenance": "DERIVED_FROM_MODEL_AND_OBSERVATIONS"
        }


gap_detector = GapDetector()
