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
from app.vehicles.vehicle_service import vehicle_service

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
        "operational_status": "SIMULATED_EXPEDITION_GLIDER",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED GLIDER]",
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
        "operational_status": "SIMULATED_EXPEDITION_GLIDER",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED GLIDER]",
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
        "operational_status": "SIMULATED_EXPEDITION_GLIDER",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED GLIDER]",
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
        "operational_status": "SIMULATED_EXPEDITION_AUV",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED AUV]",
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
        "operational_status": "SIMULATED_EXPEDITION_USV",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED USV]",
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
        "controllable": False,
        "status": "EXPEDITION_REFERENCE",
        "operational_status": "EXPEDITION_RESEARCH_VESSEL",
        "is_simulated": True,
        "provenance": "EXPEDITION_VESSEL_REFERENCE_ASSET",
        "telemetry_label": "[EXPEDITION VESSEL]",
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
        "operational_status": "SIMULATED_EXPEDITION_GLIDER",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED GLIDER]",
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
        "operational_status": "SIMULATED_EXPEDITION_USV",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED USV]",
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
        "operational_status": "SIMULATED_EXPEDITION_GLIDER",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED GLIDER]",
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
        "operational_status": "SIMULATED_EXPEDITION_AUV",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED AUV]",
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
        "operational_status": "SIMULATED_EXPEDITION_GLIDER",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED GLIDER]",
        "position_status": "SARGASSO_SEA_TRANSECT",
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
        "operational_status": "SIMULATED_EXPEDITION_GLIDER",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED GLIDER]",
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
        "operational_status": "SIMULATED_EXPEDITION_GLIDER",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED GLIDER]",
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
        "operational_status": "SIMULATED_IN_SITU_FLOAT",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED FLOAT]",
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
        "operational_status": "SIMULATED_IN_SITU_MOORING",
        "is_simulated": True,
        "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
        "telemetry_label": "[SIMULATED MOORING]",
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

    @staticmethod
    def _normalize_sensor_name(sensor: str) -> str:
        s = sensor.lower().strip()
        aliases = {
            "dissolved_oxygen": "oxygen",
            "doxy": "oxygen",
            "chlorophyll_a": "chlorophyll",
            "chlorophyll-a": "chlorophyll",
            "chla": "chlorophyll",
            "temperature_c": "temperature",
            "temp": "temperature",
            "sea_water_temperature": "temperature",
            "practical_salinity": "salinity",
            "sal": "salinity",
            "sea_water_salinity": "salinity",
        }
        return aliases.get(s, s)

    @classmethod
    def _matches_sensor(cls, required_sensor: str, available_sensors: list[str]) -> bool:
        if not required_sensor:
            return True
        norm_req = cls._normalize_sensor_name(required_sensor)
        norm_avail = {cls._normalize_sensor_name(s) for s in available_sensors}
        return norm_req in norm_avail

    def _evaluate_criteria(
        self, inst: dict[str, Any], dist_km: float, target_depth_m: float, required_sensor: str
    ) -> dict[str, Any]:
        """Build per-criterion pass/fail for animated feasibility display."""
        is_controllable = bool(inst.get("controllable", False)) and inst.get("platform_type", "").lower() != "vessel"
        checks = {
            "controllable": {
                "label": "STEERABLE",
                "passed": is_controllable,
                "detail": "Passive drift / expedition vessel" if not is_controllable else "Controllable",
            },
            "depth": {
                "label": "DEPTH",
                "passed": target_depth_m <= inst["maximum_depth_m"],
                "detail": f"Target: {target_depth_m:.0f} m | Max: {inst['maximum_depth_m']:.0f} m",
            },
            "sensor": {
                "label": "SENSOR",
                "passed": self._matches_sensor(required_sensor, inst.get("sensors", [])),
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
            controllable = ptype in ["glider", "auv", "uuv", "usv", "asv"]
            
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
                remaining_range_km = 200.0
                cruise_speed_mps = 1.5
                max_depth = 2000.0
            elif ptype == "uuv":
                remaining_range_km = 700.0
                cruise_speed_mps = 2.2
                max_depth = 1000.0
            elif ptype in ["usv", "asv"]:
                remaining_range_km = 2500.0
                cruise_speed_mps = 1.8
                max_depth = 500.0  # Winched CTD capability

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

        # 2. Add first-class Autonomous Fleet from vehicle_service (AUVs, UUVs, ROVs)
        try:
            for v in vehicle_service.get_all_vehicles():
                v_type = v.get("type", "glider") if isinstance(v, dict) else getattr(v, "type", "glider")
                ptype = (v_type or "glider").lower()
                v_id = v.get("id") if isinstance(v, dict) else getattr(v, "id", "")
                v_name = v.get("name") if isinstance(v, dict) else getattr(v, "name", "")
                v_lat = v.get("latitude") if isinstance(v, dict) else getattr(v, "latitude", 0.0)
                v_lon = v.get("longitude") if isinstance(v, dict) else getattr(v, "longitude", 0.0)
                v_max_depth = v.get("max_depth_m", 2000.0) if isinstance(v, dict) else getattr(v, "max_depth_m", 2000.0)
                v_range = v.get("remaining_range_km", 200.0) if isinstance(v, dict) else getattr(v, "remaining_range_km", 200.0)
                v_batt = v.get("battery_percent", 95.0) if isinstance(v, dict) else getattr(v, "battery_percent", 95.0)
                v_speed = v.get("cruise_speed_mps", 1.5) if isinstance(v, dict) else getattr(v, "cruise_speed_mps", 1.5)
                v_sensors = v.get("sensors", []) if isinstance(v, dict) else getattr(v, "sensors", [])
                v_status = v.get("status", "AVAILABLE") if isinstance(v, dict) else getattr(v, "status", "AVAILABLE")
                v_operator = v.get("operator", "Simulation") if isinstance(v, dict) else getattr(v, "operator", "Simulation")

                dynamic_fleet.append({
                    "instrument_id": v_id,
                    "name": v_name,
                    "platform_type": ptype,
                    "latitude": v_lat,
                    "longitude": v_lon,
                    "maximum_depth_m": v_max_depth,
                    "remaining_range_km": v_range,
                    "battery_percent": v_batt,
                    "cruise_speed_mps": v_speed,
                    "sensors": v_sensors,
                    "controllable": True,
                    "status": v_status,
                    "operational_status": f"SIMULATED_FLEET_{v_type}",
                    "is_simulated": True,
                    "provenance": "SIMULATED_MISSION_PLANNING_ASSETS",
                    "telemetry_label": f"[SIMULATED {v_type}]",
                    "position_status": f"{v_operator} ({v_type})",
                })
        except Exception as e:
            logger.warning(f"Error loading vehicle_service fleet into adaptive registry: {e}")

        # 3. Evaluate combined fleet with deduplication by instrument_id
        seen_ids = set()
        combined_fleet = []
        for inst in dynamic_fleet + MOBILE_FLEET:
            iid = inst.get("instrument_id")
            if iid and iid not in seen_ids:
                seen_ids.add(iid)
                combined_fleet.append(inst)

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

        feasible_list.sort(key=lambda c: c["distance_to_target_km"])
        rejected_list.sort(key=lambda c: c["distance_to_target_km"])
        
        # Display candidates: all feasible instruments + nearest rejected instruments
        display_candidates = feasible_list + rejected_list[:25]
        display_candidates.sort(key=lambda c: (not c["feasible"], c["distance_to_target_km"]))

        return {
            "fleet_provenance": FLEET_PROVENANCE,
            "target": {"latitude": target_lat, "longitude": target_lon, "depth_m": target_depth_m, "sensor": required_sensor},
            "all_candidates": display_candidates,
            "feasible_count": len(feasible_list),
            "rejected_count": len(rejected_list),
            "feasible_instruments": feasible_list,
            "rejected_instruments": rejected_list,
        }


instrument_registry = InstrumentRegistry()
