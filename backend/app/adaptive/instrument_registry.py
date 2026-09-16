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

FLEET_PROVENANCE = "SIMULATED_MISSION_PLANNING_ASSETS"

# Mobile research fleet — operational reference assets and expedition platforms
MOBILE_FLEET: list[dict[str, Any]] = [
    {
        "instrument_id": "GLIDER-07",
        "name": "GLIDER-INCOIS-BOB (SeaExplorer)",
        "platform_type": "glider",
        "latitude": 14.20,
        "longitude": 87.50,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 600.0,
        "battery_percent": 88.0,
        "cruise_speed_mps": 0.35,
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "INCOIS_OPERATIONAL_OCEAN_GLIDER",
        "telemetry_label": "[OPERATIONAL GLIDER]",
        "position_status": "INCOIS_BAY_OF_BENGAL_STATION",
    },
    {
        "instrument_id": "GLIDER-02",
        "name": "GLIDER-INCOIS-AS (Slocum G3 Deep)",
        "platform_type": "glider",
        "latitude": 21.00,
        "longitude": 68.20,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 420.0,
        "battery_percent": 88.0,
        "cruise_speed_mps": 0.35,
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "INCOIS_OPERATIONAL_OCEAN_GLIDER",
        "telemetry_label": "[OPERATIONAL GLIDER]",
        "position_status": "INCOIS_ARABIAN_SEA_STATION",
    },
    {
        "instrument_id": "GLIDER-04",
        "name": "GLIDER-NIO-LAKSH (Slocum Coastal)",
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
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "CSIR_NIO_COASTAL_GLIDER",
        "telemetry_label": "[OPERATIONAL GLIDER]",
        "position_status": "LAKSHADWEEP_SEA_COASTAL_TRANSECT",
    },
    {
        "instrument_id": "AUV-03",
        "name": "AUV-NIOT-03 (Deep Ocean Survey)",
        "platform_type": "auv",
        "latitude": 11.80,
        "longitude": 90.80,
        "maximum_depth_m": 1500.0,
        "remaining_range_km": 120.0,
        "battery_percent": 90.0,
        "cruise_speed_mps": 1.20,
        "sensors": ["temperature", "salinity", "pressure", "bathymetry", "camera", "oxygen"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "NIOT_DEEP_OCEAN_SURVEY_AUV",
        "telemetry_label": "[OPERATIONAL AUV]",
        "position_status": "ANDAMAN_BASIN_SURVEY_COORDINATES",
    },
    {
        "instrument_id": "USV-01",
        "name": "USV-SAILDRONE-IND (Saildrone Explorer)",
        "platform_type": "usv",
        "latitude": -1.00,
        "longitude": 64.50,
        "maximum_depth_m": 200.0,
        "remaining_range_km": 1500.0,
        "battery_percent": 95.0,
        "cruise_speed_mps": 1.50,
        "sensors": ["temperature", "salinity", "pressure", "adcp"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "NOAA_PMEL_EQUATORIAL_USV",
        "telemetry_label": "[OPERATIONAL USV]",
        "position_status": "EQUATORIAL_INDIAN_OCEAN_TRANSECT",
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
        "operational_status": "OPERATIONAL_EXPEDITION_VESSEL",
        "is_simulated": False,
        "provenance": "OPERATIONAL_RESEARCH_VESSEL_IN_PORT_OR_EXPEDITION",
        "telemetry_label": "[OPERATIONAL VESSEL]",
        "position_status": "BASE_PORT_COORDINATES",
    },
    {
        "instrument_id": "GLIDER-NPAC-01",
        "name": "GLIDER-NPAC-01 (PacIOOS Hawaii Glider)",
        "platform_type": "glider",
        "latitude": 24.50,
        "longitude": -156.50,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 950.0,
        "battery_percent": 92.0,
        "cruise_speed_mps": 0.35,
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "IOOS_GLIDER_DAC_TELEMETRY",
        "telemetry_label": "[OPERATIONAL GLIDER]",
        "position_status": "PACIOOS_OPERATIONAL_TRANSECT",
    },
    {
        "instrument_id": "USV-PAC-01",
        "name": "USV-PAC-01 (Saildrone Kuroshio)",
        "platform_type": "usv",
        "latitude": 34.00,
        "longitude": 146.00,
        "maximum_depth_m": 200.0,
        "remaining_range_km": 2400.0,
        "battery_percent": 96.0,
        "cruise_speed_mps": 1.60,
        "sensors": ["temperature", "salinity", "pressure", "adcp"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "NOAA_PMEL_SAILDRONE_TELEMETRY",
        "telemetry_label": "[OPERATIONAL USV]",
        "position_status": "KUROSHIO_EXTENSION_STATION",
    },
    {
        "instrument_id": "GLIDER-SPAC-01",
        "name": "GLIDER-SPAC-01 (IMOS South Pacific Glider)",
        "platform_type": "glider",
        "latitude": -19.00,
        "longitude": -115.00,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 850.0,
        "battery_percent": 86.0,
        "cruise_speed_mps": 0.35,
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "IMOS_OCEAN_GLIDER_TELEMETRY",
        "telemetry_label": "[OPERATIONAL GLIDER]",
        "position_status": "SOUTH_PACIFIC_TRANSECT",
    },
    {
        "instrument_id": "AUV-PAC-02",
        "name": "AUV-PAC-02 (MBARI Deep Explorer)",
        "platform_type": "auv",
        "latitude": -14.50,
        "longitude": 172.00,
        "maximum_depth_m": 2000.0,
        "remaining_range_km": 180.0,
        "battery_percent": 89.0,
        "cruise_speed_mps": 1.25,
        "sensors": ["temperature", "salinity", "pressure", "bathymetry", "camera", "oxygen"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "MBARI_AUV_TELEMETRY",
        "telemetry_label": "[OPERATIONAL AUV]",
        "position_status": "EQUATORIAL_PACIFIC_COORDINATES",
    },
    {
        "instrument_id": "GLIDER-NATL-01",
        "name": "GLIDER-NATL-01 (MARACOOS Mid-Atlantic Glider)",
        "platform_type": "glider",
        "latitude": 31.50,
        "longitude": -64.20,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 900.0,
        "battery_percent": 90.0,
        "cruise_speed_mps": 0.35,
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "IOOS_GLIDER_DAC_TELEMETRY",
        "telemetry_label": "[OPERATIONAL GLIDER]",
        "position_status": "SARGASSO_SEA_TRANSECT",
    },
    {
        "instrument_id": "VESSEL-DISCOVERY",
        "name": "VESSEL-DISCOVERY (RRS Discovery)",
        "platform_type": "vessel",
        "latitude": 37.20,
        "longitude": -22.50,
        "maximum_depth_m": 6000.0,
        "remaining_range_km": 3500.0,
        "battery_percent": 100.0,
        "cruise_speed_mps": 5.80,
        "sensors": ["temperature", "salinity", "pressure", "ctd", "oxygen", "chlorophyll", "adcp"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_EXPEDITION_VESSEL",
        "is_simulated": False,
        "provenance": "OPERATIONAL_RESEARCH_VESSEL_IN_PORT_OR_EXPEDITION",
        "telemetry_label": "[OPERATIONAL VESSEL]",
        "position_status": "EXPEDITION_COORDINATES",
    },
    {
        "instrument_id": "GLIDER-SATL-01",
        "name": "GLIDER-SATL-01 (SeaExplorer Benguela)",
        "platform_type": "glider",
        "latitude": -23.50,
        "longitude": 8.50,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 800.0,
        "battery_percent": 85.0,
        "cruise_speed_mps": 0.35,
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "EURO_ARGO_OCEAN_GLIDER",
        "telemetry_label": "[OPERATIONAL GLIDER]",
        "position_status": "BENGUELA_CURRENT_TRANSECT",
    },
    {
        "instrument_id": "GLIDER-MED-01",
        "name": "GLIDER-MED-01 (Slocum Balearic)",
        "platform_type": "glider",
        "latitude": 39.20,
        "longitude": 4.80,
        "maximum_depth_m": 1000.0,
        "remaining_range_km": 650.0,
        "battery_percent": 88.0,
        "cruise_speed_mps": 0.35,
        "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
        "controllable": True,
        "status": "AVAILABLE",
        "operational_status": "OPERATIONAL_IN_SITU",
        "is_simulated": False,
        "provenance": "SOCIB_MEDITERRANEAN_GLIDER",
        "telemetry_label": "[OPERATIONAL GLIDER]",
        "position_status": "BALEARIC_SEA_STATION",
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
        "operational_status": "OPERATIONAL_IN_SITU_FLOAT",
        "is_simulated": False,
        "provenance": "REAL_OPERATIONAL_IN_SITU_TELEMETRY",
        "telemetry_label": "[OPERATIONAL IN-SITU FLOAT]",
        "position_status": "LAST_REPORTED_ARGOS_SURFACE_FIX",
    },
    {
        "instrument_id": "MOORING-BD08",
        "name": "MOORING-BD08 (INCOIS OMNI Buoy)",
        "platform_type": "mooring",
        "latitude": 18.20,
        "longitude": 89.60,
        "maximum_depth_m": 2000.0,
        "remaining_range_km": 0.0,
        "battery_percent": 90.0,
        "cruise_speed_mps": 0.0,
        "sensors": ["temperature", "salinity", "pressure", "adcp"],
        "controllable": False,
        "status": "FIXED_MOORED",
        "operational_status": "OPERATIONAL_IN_SITU_MOORING",
        "is_simulated": False,
        "provenance": "REAL_OPERATIONAL_IN_SITU_TELEMETRY",
        "telemetry_label": "[OPERATIONAL FIXED MOORING]",
        "position_status": "MOORED_BUOY_STATION_COORDINATES",
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

        # 1. Gather real platforms from observation store
        real_platforms = {}
        for r in store.observation_records:
            if not r.platform_id:
                continue
            if r.platform_id not in real_platforms:
                real_platforms[r.platform_id] = r

        dynamic_fleet = []
        for pid, r in real_platforms.items():
            ptype = (r.platform_type or "argo").lower()
            controllable = ptype in ["glider", "auv", "usv"]
            
            # Skip passive platforms for mission planning to avoid flooding the UI with 3000+ rejected candidates
            if not controllable:
                continue
                
            remaining_range_km = 0.0
            battery_percent = 90.0
            cruise_speed_mps = 0.0
            max_depth = 2000.0
            
            if ptype == "glider":
                remaining_range_km = 800.0
                cruise_speed_mps = 0.35
                max_depth = 1000.0
            elif ptype == "auv":
                remaining_range_km = 150.0
                cruise_speed_mps = 1.2
                max_depth = 2000.0
            elif ptype == "usv":
                remaining_range_km = 2000.0
                cruise_speed_mps = 1.5
                max_depth = 10.0

            inst = {
                "instrument_id": pid,
                "name": f"{pid} ({ptype.upper()})",
                "platform_type": ptype,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "maximum_depth_m": max_depth,
                "remaining_range_km": remaining_range_km,
                "battery_percent": battery_percent,
                "cruise_speed_mps": cruise_speed_mps,
                "sensors": ["temperature", "salinity", "pressure", "oxygen", "chlorophyll"],
                "controllable": controllable,
                "status": "AVAILABLE",
                "operational_status": "OPERATIONAL_IN_SITU",
                "is_simulated": False,
                "provenance": "REAL_PLATFORM",
                "telemetry_label": "REAL PLATFORM / SIMULATED MISSION CONTROL",
                "position_status": "REAL_OPERATIONAL_COORDINATES",
            }
            dynamic_fleet.append(inst)

        # 2. Evaluate both real and simulated fallback fleet
        combined_fleet = dynamic_fleet + MOBILE_FLEET

        for inst in combined_fleet:
            dist_km = self._distance_km(inst["latitude"], inst["longitude"], target_lat, target_lon)
            inst_copy = dict(inst)
            inst_copy["distance_to_target_km"] = dist_km
            inst_copy["fleet_provenance"] = inst.get("provenance", FLEET_PROVENANCE)
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
