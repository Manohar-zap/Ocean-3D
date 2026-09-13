"""
Adaptive observation decision engine for OCEAN 3D.

Prototype scope:
- Builds an uncertainty field from model state + nearby in-situ observations.
- Scores candidate observation locations using expected information gain,
  spatial coverage, dynamics, platform feasibility and mission cost.
- Produces an explainable recommendation for a simulated glider/AUV mission.

This is deliberately deterministic and explainable for the prototype. A trained
probabilistic ML model can replace the uncertainty estimator later without
changing the API contract.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .storage import store


@dataclass(frozen=True)
class Candidate:
    latitude: float
    longitude: float
    depth: float
    platform: str


class AdaptiveObservationEngine:
    """Explainable prototype for uncertainty-driven observation planning."""

    def _model_value(self, variable: str, lat: float, lon: float, depth: float, time: str | None) -> float | None:
        rows = [
            r for r in store.model_records
            if r.variable == variable
            and abs(r.latitude - lat) < 1e-6
            and abs(r.longitude - lon) < 1e-6
            and abs(r.depth - depth) < 1e-6
        ]
        if not rows:
            return None
        if time:
            return min(rows, key=lambda r: self._time_distance(r.time, time)).value
        return rows[-1].value

    @staticmethod
    def _time_distance(a: str, b: str) -> float:
        try:
            ta = datetime.fromisoformat(a.replace("Z", ""))
            tb = datetime.fromisoformat(b.replace("Z", ""))
            return abs((ta - tb).total_seconds())
        except Exception:
            return 0.0

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        # Haversine; adequate for the regional prototype.
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(min(1.0, math.sqrt(a)))

    def _observations(self, variable: str) -> list[Any]:
        return [r for r in store.observation_records if r.variable == variable]

    def _uncertainty_at(self, variable: str, lat: float, lon: float, depth: float) -> dict[str, float]:
        """Estimate uncertainty from local observation support and disagreement.

        Two components are intentionally exposed:
        - coverage_gap: lack of nearby observations in space/depth
        - disagreement: local observation-model mismatch
        """
        obs = self._observations(variable)
        if not obs:
            return {"coverage_gap": 1.0, "disagreement": 1.0, "uncertainty": 1.0}

        neighbours = []
        for r in obs:
            horizontal = self._distance_km(lat, lon, r.latitude, r.longitude)
            vertical = abs(depth - r.depth) / 1000.0
            d = math.sqrt((horizontal / 300.0) ** 2 + vertical ** 2)
            if d <= 2.5:
                neighbours.append((d, r))

        if not neighbours:
            return {"coverage_gap": 1.0, "disagreement": 0.75, "uncertainty": 0.95}

        neighbours.sort(key=lambda x: x[0])
        nearest = neighbours[0][0]
        coverage_gap = min(1.0, nearest / 1.5)

        model = self._model_value(variable, lat, lon, depth, None)
        if model is None:
            model = sum(r.value for _, r in neighbours[:5]) / min(5, len(neighbours))
        residuals = [r.value - model for _, r in neighbours[:8]]
        mean_abs = sum(abs(x) for x in residuals) / len(residuals)
        spread = math.sqrt(sum((x - sum(residuals) / len(residuals)) ** 2 for x in residuals) / len(residuals))

        # Normalize robustly for demo use; this produces a confidence-oriented score,
        # not a physical posterior variance.
        scale = max(abs(model) * 0.08, 0.5)
        disagreement = min(1.0, (0.65 * mean_abs + 0.35 * spread) / scale)
        uncertainty = min(1.0, 0.65 * coverage_gap + 0.35 * disagreement)
        return {
            "coverage_gap": round(coverage_gap, 4),
            "disagreement": round(disagreement, 4),
            "uncertainty": round(uncertainty, 4),
        }

    def uncertainty_field(
        self,
        variable: str = "temperature",
        min_lat: float = 0,
        max_lat: float = 25,
        min_lon: float = 60,
        max_lon: float = 95,
        depth: float = 200,
        step: float = 1.5,
    ) -> dict[str, Any]:
        points = []
        lat = min_lat
        while lat <= max_lat + 1e-9:
            lon = min_lon
            while lon <= max_lon + 1e-9:
                u = self._uncertainty_at(variable, round(lat, 4), round(lon, 4), depth)
                points.append({
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "depth": depth,
                    **u,
                })
                lon += step
            lat += step
        return {
            "variable": variable,
            "depth": depth,
            "points": points,
            "method": "coverage + local model-observation disagreement",
            "note": "Prototype uncertainty score; replaceable by a trained probabilistic model.",
        }

    def recommend(
        self,
        variable: str = "temperature",
        depth: float = 200,
        min_lat: float = 0,
        max_lat: float = 25,
        min_lon: float = 60,
        max_lon: float = 95,
        platform: str = "glider",
        candidate_step: float = 2.0,
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        lat = min_lat
        while lat <= max_lat + 1e-9:
            lon = min_lon
            while lon <= max_lon + 1e-9:
                u = self._uncertainty_at(variable, round(lat, 4), round(lon, 4), depth)
                # Feasibility is a soft regional constraint for the prototype.
                edge_penalty = 0.0 if (min_lat + 1 <= lat <= max_lat - 1 and min_lon + 1 <= lon <= max_lon - 1) else 0.15
                feasibility = max(0.0, 1.0 - edge_penalty)
                scientific_importance = min(1.0, 0.55 + 0.45 * u["disagreement"])
                mission_cost = 0.35 + 0.015 * abs(lat - (min_lat + max_lat) / 2) + 0.01 * abs(lon - (min_lon + max_lon) / 2)
                score = (u["uncertainty"] * scientific_importance * feasibility) / mission_cost
                candidates.append({
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "depth": depth,
                    "uncertainty": u["uncertainty"],
                    "coverage_gap": u["coverage_gap"],
                    "disagreement": u["disagreement"],
                    "scientific_importance": round(scientific_importance, 4),
                    "feasibility": round(feasibility, 4),
                    "mission_cost_index": round(mission_cost, 4),
                    "information_gain_score": round(score, 4),
                    "platform": platform,
                })
                lon += candidate_step
            lat += candidate_step

        candidates.sort(key=lambda x: x["information_gain_score"], reverse=True)
        best = candidates[0]
        return {
            "decision": "OBSERVE" if best["uncertainty"] >= 0.45 else "CONTINUE_MONITORING",
            "recommendation": best,
            "alternatives": candidates[1:6],
            "objective": "maximize expected information gain per mission-cost index",
            "constraints": {
                "platform": platform,
                "target_depth_m": depth,
                "note": "Prototype feasibility model; vehicle dynamics/battery/current constraints can be added to the optimizer.",
            },
        }

    def what_if(self, variable: str, lat: float, lon: float, depth: float, value: float) -> dict[str, Any]:
        before = self._uncertainty_at(variable, lat, lon, depth)
        # Virtual observation: compare the proposed measurement to the model and
        # estimate local support after adding a high-confidence observation.
        model = self._model_value(variable, lat, lon, depth, None)
        if model is None:
            model = value
        residual = abs(value - model)
        after_disagreement = min(1.0, residual / max(abs(model) * 0.08, 0.5))
        after = {
            "coverage_gap": round(before["coverage_gap"] * 0.15, 4),
            "disagreement": round(0.5 * before["disagreement"] + 0.5 * after_disagreement, 4),
        }
        after["uncertainty"] = round(min(1.0, 0.65 * after["coverage_gap"] + 0.35 * after["disagreement"]), 4)
        reduction = max(0.0, before["uncertainty"] - after["uncertainty"])
        return {
            "variable": variable,
            "location": {"lat": lat, "lon": lon, "depth": depth},
            "virtual_observation": value,
            "before": before,
            "after": after,
            "estimated_uncertainty_reduction": round(reduction, 4),
            "note": "What-if simulation only; no physical vehicle or operational model is controlled.",
        }


adaptive_engine = AdaptiveObservationEngine()
