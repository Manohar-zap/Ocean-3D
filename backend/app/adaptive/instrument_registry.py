"""
Mobile Research Fleet Instrument Registry Module.

Manages controllable mobile observing platform specifications (Gliders, AUVs, Vessels) vs
passive observational platforms (Argo floats). Evaluates controllability and sensor capabilities.
"""
from __future__ import annotations
import math
import logging
from typing import Optional, Any

from app.storage import store
from app.schemas import QueryFilters

logger = logging.getLogger(__name__)

# Operational Mobile Fleet Registry (INCOIS / IOOS Mobile Observing Assets)
MOBILE_FLEET: list[dict[str, Any]] = [
    {
        "instrument_id": "GLIDER-07",
        "name": "SeaExplorer Glider #07",
        "platform_type": "glider",
        "latitude": 14.20,
        "longitude": 87.50,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 400.0,
        "battery_percent": 82.0,
        "cruise_speed_mps": 0.35,  # ~0.7 knots
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE"
    },
    {
        "instrument_id": "GLIDER-04",
        "name": "Slocum Glider #04",
        "platform_type": "glider",
        "latitude": 8.50,
        "longitude": 76.20,
        "maximum_depth_m": 350.0,
        "remaining_range_km": 280.0,
        "battery_percent": 65.0,
        "cruise_speed_mps": 0.30,
        "sensors": ["temperature", "salinity", "pressure"],
        "controllable": True,
        "status": "AVAILABLE"
    },
    {
        "instrument_id": "AUV-03",
        "name": "Deep Survey AUV #03",
        "platform_type": "auv",
        "latitude": 11.10,
        "longitude": 81.40,
        "maximum_depth_m": 1500.0,
        "remaining_range_km": 120.0,
        "battery_percent": 90.0,
        "cruise_speed_mps": 1.20,  # ~2.3 knots
        "sensors": ["temperature", "salinity", "pressure", "bathymetry", "camera"],
        "controllable": True,
        "status": "AVAILABLE"
    },
    {
        "instrument_id": "VESSEL-SAGAR",
        "name": "ORV Sagar Kanya Research Vessel",
        "platform_type": "vessel",
        "latitude": 12.80,
        "longitude": 74.80,
        "maximum_depth_m": 6000.0,
        "remaining_range_km": 2500.0,
        "battery_percent": 100.0,
        "cruise_speed_mps": 5.50,  # ~10.5 knots
        "sensors": ["temperature", "salinity", "pressure", "ctd", "oxygen", "chlorophyll", "adcp"],
        "controllable": True,
        "status": "AVAILABLE"
    },
    {
        "instrument_id": "ARGO-5906203",
        "name": "Argo Profiling Float #5906203",
        "platform_type": "argo",
        "latitude": 9.80,
        "longitude": 75.80,
        "maximum_depth_m": 2000.0,
        "remaining_range_km": 0.0,
        "battery_percent": 75.0,
        "cruise_speed_mps": 0.0,
        "sensors": ["temperature", "salinity", "pressure"],
        "controllable": False,  # PASSIVE FLOAT — CANNOT BE NAVIGATED TO WAYPOINT
        "status": "PASSIVE_DRIFT"
    }
]


class InstrumentRegistry:
    """Fleet Registry & Controllability Filter Manager."""

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2.0) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2)
        return round(2.0 * r * math.asin(min(1.0, math.sqrt(a))), 2)

    def discover_candidate_instruments(
        self, target_lat: float, target_lon: float, target_depth_m: float = 100.0, required_sensor: str = "temperature"
    ) -> dict[str, Any]:
        """Discovers, filters, and reports feasible vs rejected instruments with explicit rejection reasons."""
        feasible_list = []
        rejected_list = []

        for inst in MOBILE_FLEET:
            dist_km = self._distance_km(inst["latitude"], inst["longitude"], target_lat, target_lon)
            inst_copy = dict(inst)
            inst_copy["distance_to_target_km"] = dist_km

            # Check 1: Controllability
            if not inst["controllable"]:
                inst_copy["rejection_reason"] = "Passive drift platform (Cannot navigate or steer to waypoint)"
                rejected_list.append(inst_copy)
                continue

            # Check 2: Sensor Capability
            if required_sensor not in inst["sensors"]:
                inst_copy["rejection_reason"] = f"Required sensor '{required_sensor}' not equipped"
                rejected_list.append(inst_copy)
                continue

            # Check 3: Depth Capability
            if target_depth_m > inst["maximum_depth_m"]:
                inst_copy["rejection_reason"] = f"Target depth ({target_depth_m}m) exceeds max operating depth ({inst['maximum_depth_m']}m)"
                rejected_list.append(inst_copy)
                continue

            # Check 4: Range & Endurance Capability
            if dist_km > inst["remaining_range_km"]:
                inst_copy["rejection_reason"] = f"Target distance ({dist_km:.1f}km) exceeds remaining range ({inst['remaining_range_km']}km)"
                rejected_list.append(inst_copy)
                continue

            feasible_list.append(inst_copy)

        return {
            "target": {"latitude": target_lat, "longitude": target_lon, "depth_m": target_depth_m, "sensor": required_sensor},
            "feasible_count": len(feasible_list),
            "rejected_count": len(rejected_list),
            "feasible_instruments": feasible_list,
            "rejected_instruments": rejected_list
        }


instrument_registry = InstrumentRegistry()
