"""
Mobile Research Fleet Instrument Registry Module.

Manages controllable mobile observing platform specifications vs passive floats.
All fleet positions are SIMULATED DEMO data unless a real telemetry source is wired.
"""
from __future__ import annotations

import math
import logging
from typing import Any

from app.storage import store
from app.schemas import QueryFilters

logger = logging.getLogger(__name__)

FLEET_PROVENANCE = "SIMULATED_DEMO_FLEET"

# Simulated demo fleet — NOT operational INCOIS telemetry
MOBILE_FLEET: list[dict[str, Any]] = [
    {
        "instrument_id": "GLIDER-07",
        "name": "GLIDER-07 (SeaExplorer)",
        "platform_type": "glider",
        "latitude": 14.20,
        "longitude": 87.50,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 400.0,
        "battery_percent": 82.0,
        "cruise_speed_mps": 0.35,
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE",
    },
    {
        "instrument_id": "GLIDER-04",
        "name": "GLIDER-04 (Slocum)",
        "platform_type": "glider",
        "latitude": 8.50,
        "longitude": 76.20,
        "maximum_depth_m": 350.0,
        "remaining_range_km": 280.0,
        "battery_percent": 65.0,
        "cruise_speed_mps": 0.30,
        "sensors": ["temperature", "salinity", "pressure"],
        "controllable": True,
        "status": "AVAILABLE",
    },
    {
        "instrument_id": "AUV-03",
        "name": "AUV-03 (Deep Survey)",
        "platform_type": "auv",
        "latitude": 11.10,
        "longitude": 81.40,
        "maximum_depth_m": 1500.0,
        "remaining_range_km": 120.0,
        "battery_percent": 90.0,
        "cruise_speed_mps": 1.20,
        "sensors": ["temperature", "salinity", "pressure", "bathymetry", "camera"],
        "controllable": True,
        "status": "AVAILABLE",
    },
    {
        "instrument_id": "VESSEL-SAGAR",
        "name": "VESSEL-SAGAR (ORV Sagar Kanya)",
        "platform_type": "vessel",
        "latitude": 12.80,
        "longitude": 74.80,
        "maximum_depth_m": 6000.0,
        "remaining_range_km": 2500.0,
        "battery_percent": 100.0,
        "cruise_speed_mps": 5.50,
        "sensors": ["temperature", "salinity", "pressure", "ctd", "oxygen", "chlorophyll", "adcp"],
        "controllable": True,
        "status": "AVAILABLE",
    },
    {
        "instrument_id": "ARGO-5906203",
        "name": "ARGO-5906203 (Profiling Float)",
        "platform_type": "argo",
        "latitude": 9.80,
        "longitude": 75.80,
        "maximum_depth_m": 2000.0,
        "remaining_range_km": 0.0,
        "battery_percent": 75.0,
        "cruise_speed_mps": 0.0,
        "sensors": ["temperature", "salinity", "pressure"],
        "controllable": False,
        "status": "PASSIVE_DRIFT",
    },
]


class InstrumentRegistry:
    """Fleet registry with explicit feasibility criteria for mission animation."""

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
        )
        return round(2.0 * r * math.asin(min(1.0, math.sqrt(a))), 2)

    def _evaluate_criteria(
        self, inst: dict[str, Any], dist_km: float, target_depth_m: float, required_sensor: str
    ) -> dict[str, Any]:
        """Build per-criterion pass/fail for animated feasibility display."""
        checks = {
            "controllable": {
                "label": "STEERABLE",
                "passed": inst["controllable"],
                "detail": "Passive drift platform" if not inst["controllable"] else "Controllable",
            },
            "depth": {
                "label": "DEPTH",
                "passed": target_depth_m <= inst["maximum_depth_m"],
                "detail": f"Target: {target_depth_m:.0f} m | Max: {inst['maximum_depth_m']:.0f} m",
            },
            "sensor": {
                "label": "SENSOR",
                "passed": required_sensor in inst["sensors"],
                "detail": f"Requires {required_sensor}",
            },
            "range": {
                "label": "RANGE",
                "passed": dist_km <= inst["remaining_range_km"],
                "detail": f"Target: {dist_km:.1f} km | Remaining: {inst['remaining_range_km']:.0f} km",
            },
        }
        passed = all(c["passed"] for c in checks.values())
        failed = [k for k, c in checks.items() if not c["passed"]]
        return {"checks": checks, "feasible": passed, "failed_criteria": failed}

    def discover_candidate_instruments(
        self, target_lat: float, target_lon: float, target_depth_m: float = 100.0, required_sensor: str = "temperature"
    ) -> dict[str, Any]:
        """Discover all fleet instruments with detailed feasibility for each."""
        all_candidates: list[dict[str, Any]] = []
        feasible_list: list[dict[str, Any]] = []
        rejected_list: list[dict[str, Any]] = []

        for inst in MOBILE_FLEET:
            dist_km = self._distance_km(inst["latitude"], inst["longitude"], target_lat, target_lon)
            inst_copy = dict(inst)
            inst_copy["distance_to_target_km"] = dist_km
            inst_copy["fleet_provenance"] = FLEET_PROVENANCE
            criteria = self._evaluate_criteria(inst, dist_km, target_depth_m, required_sensor)
            inst_copy["feasibility_checks"] = criteria["checks"]
            inst_copy["feasible"] = criteria["feasible"]
            inst_copy["failed_criteria"] = criteria["failed_criteria"]
            all_candidates.append(inst_copy)

            if not criteria["feasible"]:
                reasons = []
                if not criteria["checks"]["controllable"]["passed"]:
                    reasons.append("NON-STEERABLE")
                if not criteria["checks"]["depth"]["passed"]:
                    reasons.append("DEPTH")
                if not criteria["checks"]["sensor"]["passed"]:
                    reasons.append("SENSOR")
                if not criteria["checks"]["range"]["passed"]:
                    reasons.append("RANGE")
                inst_copy["rejection_reason"] = " / ".join(reasons) if reasons else "Constraint limit exceeded"
                rejected_list.append(inst_copy)
            else:
                feasible_list.append(inst_copy)

        return {
            "fleet_provenance": FLEET_PROVENANCE,
            "target": {"latitude": target_lat, "longitude": target_lon, "depth_m": target_depth_m, "sensor": required_sensor},
            "all_candidates": all_candidates,
            "feasible_count": len(feasible_list),
            "rejected_count": len(rejected_list),
            "feasible_instruments": feasible_list,
            "rejected_instruments": rejected_list,
        }


instrument_registry = InstrumentRegistry()
