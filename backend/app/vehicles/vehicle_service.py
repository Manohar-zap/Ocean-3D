"""
Vehicle Registry, Mission Planning, and Telemetry Service for AUV, UUV, and ROV Platforms.

Supports 3D autonomous vehicle mission planning, simulation, and data collection
using oceanographic baseline observations.
All vehicle movements and missions are SIMULATED unless a real authorized telemetry feed is wired.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SensorReading(BaseModel):
    temperature: Optional[float] = None
    salinity: Optional[float] = None
    oxygen: Optional[float] = None
    chlorophyll: Optional[float] = None
    pressure: Optional[float] = None
    turbidity: Optional[float] = None


class VehicleState(BaseModel):
    id: str
    type: Literal["AUV", "UUV", "ROV"]
    name: str
    latitude: float
    longitude: float
    depth: float
    status: Literal[
        "AVAILABLE",
        "MISSION_PLANNED",
        "EN_ROUTE",
        "DIVING",
        "SAMPLING",
        "TARGET_REACHED",
        "DATA_COLLECTED"
    ] = "AVAILABLE"
    source: Literal["SIMULATED", "LIVE", "NEAR_REAL_TIME", "HISTORICAL"] = "SIMULATED"
    target: Optional[Dict[str, Any]] = None
    sensors: List[str] = Field(default_factory=lambda: ["temperature", "salinity", "oxygen", "chlorophyll"])
    lastUpdate: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mission: Optional[Dict[str, Any]] = None
    # Extended platform specifications
    max_depth_m: float = 2000.0
    cruise_speed_mps: float = 1.5
    battery_percent: float = 95.0
    remaining_range_km: float = 200.0
    heading_deg: float = 0.0
    tethered: bool = False
    operator: str = "INCOIS / Ocean 3D Simulation"


class TelemetryPacket(BaseModel):
    """Uniform vehicle state telemetry interface for simulator and future live telemetry feeds."""
    vehicleId: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    latitude: float
    longitude: float
    depth: float
    heading: float = 0.0
    speed: float = 1.5
    status: str = "AVAILABLE"
    sensorData: Dict[str, Any] = Field(default_factory=dict)


class MissionPlanRequest(BaseModel):
    vehicle_id: str
    target_lat: float
    target_lon: float
    target_depth: float
    sensors: List[str] = Field(default_factory=lambda: ["temperature", "salinity", "oxygen", "chlorophyll"])


class VehicleService:
    def __init__(self):
        self._vehicles: Dict[str, VehicleState] = {}
        self._tracks: Dict[str, List[Dict[str, Any]]] = {}
        self._missions: Dict[str, Dict[str, Any]] = {}
        self._init_demo_fleet()

    def _init_demo_fleet(self):
        """Initialize deterministic demo fleet placed in Indian Ocean & Arabian Sea basins."""
        now_str = datetime.now(timezone.utc).isoformat()

        fleet = [
            VehicleState(
                id="AUV-001",
                type="AUV",
                name="AUV-001 (Maya Deep Surveyor)",
                latitude=14.204,
                longitude=73.812,
                depth=650.0,
                status="AVAILABLE",
                source="SIMULATED",
                sensors=["temperature", "salinity", "oxygen", "chlorophyll"],
                lastUpdate=now_str,
                max_depth_m=2000.0,
                cruise_speed_mps=1.5,
                battery_percent=92.0,
                remaining_range_km=180.0,
                heading_deg=215.0,
                tethered=False,
                operator="CSIR-NIO / Autonomous Underwater Vehicle Facility",
            ),
            VehicleState(
                id="AUV-002",
                type="AUV",
                name="AUV-002 (Matsya Deep Explorer)",
                latitude=11.520,
                longitude=86.410,
                depth=1200.0,
                status="AVAILABLE",
                source="SIMULATED",
                sensors=["temperature", "salinity", "oxygen", "chlorophyll"],
                lastUpdate=now_str,
                max_depth_m=3000.0,
                cruise_speed_mps=1.8,
                battery_percent=88.0,
                remaining_range_km=240.0,
                heading_deg=45.0,
                tethered=False,
                operator="NIOT Deep Ocean Mission Initiative",
            ),
            VehicleState(
                id="UUV-001",
                type="UUV",
                name="UUV-001 (Varun Subsea Patrol)",
                latitude=9.850,
                longitude=76.120,
                depth=250.0,
                status="AVAILABLE",
                source="SIMULATED",
                sensors=["temperature", "salinity", "oxygen"],
                lastUpdate=now_str,
                max_depth_m=600.0,
                cruise_speed_mps=2.4,
                battery_percent=96.0,
                remaining_range_km=520.0,
                heading_deg=290.0,
                tethered=False,
                operator="Maritime Uncrewed Reconnaissance Wing",
            ),
            VehicleState(
                id="UUV-002",
                type="UUV",
                name="UUV-002 (Sagarika Long-Range UUV)",
                latitude=18.410,
                longitude=84.820,
                depth=400.0,
                status="AVAILABLE",
                source="SIMULATED",
                sensors=["temperature", "salinity", "oxygen", "chlorophyll"],
                lastUpdate=now_str,
                max_depth_m=1000.0,
                cruise_speed_mps=2.0,
                battery_percent=90.0,
                remaining_range_km=750.0,
                heading_deg=135.0,
                tethered=False,
                operator="INCOIS Bay of Bengal Observation Array",
            ),
            VehicleState(
                id="ROV-001",
                type="ROV",
                name="ROV-001 (Samudrayan Trench ROV)",
                latitude=10.220,
                longitude=72.350,
                depth=1800.0,
                status="AVAILABLE",
                source="SIMULATED",
                sensors=["temperature", "salinity", "oxygen", "chlorophyll"],
                lastUpdate=now_str,
                max_depth_m=6000.0,
                cruise_speed_mps=0.8,
                battery_percent=100.0,
                remaining_range_km=25.0,
                heading_deg=180.0,
                tethered=True,
                operator="Ministry of Earth Sciences Deep Sea Mining / Survey Unit",
            ),
            VehicleState(
                id="ROV-002",
                type="ROV",
                name="ROV-002 (NIOT Subsea Arm ROV)",
                latitude=16.710,
                longitude=82.900,
                depth=2200.0,
                status="AVAILABLE",
                source="SIMULATED",
                sensors=["temperature", "salinity", "oxygen", "chlorophyll"],
                lastUpdate=now_str,
                max_depth_m=4000.0,
                cruise_speed_mps=0.6,
                battery_percent=100.0,
                remaining_range_km=20.0,
                heading_deg=90.0,
                tethered=True,
                operator="NIOT Deep Water Hydrothermal Survey Team",
            ),
        ]

        for v in fleet:
            self._vehicles[v.id] = v
            # Deterministic historical track segment (last 4 fixes leading to current location)
            hist = []
            for i in range(4, 0, -1):
                hist_lat = round(v.latitude - (i * 0.08 * math.cos(math.radians(v.heading_deg))), 4)
                hist_lon = round(v.longitude - (i * 0.08 * math.sin(math.radians(v.heading_deg))), 4)
                hist_depth = max(10.0, round(v.depth - (i * 35.0), 1))
                hist.append({
                    "lat": hist_lat,
                    "lon": hist_lon,
                    "depth": hist_depth,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "HISTORICAL_TRACK"
                })
            hist.append({
                "lat": v.latitude,
                "lon": v.longitude,
                "depth": v.depth,
                "timestamp": v.lastUpdate,
                "status": "CURRENT_POSITION"
            })
            self._tracks[v.id] = hist

    def get_all_vehicles(self, vehicle_type: Optional[str] = None) -> List[Dict[str, Any]]:
        vehicles = list(self._vehicles.values())
        if vehicle_type:
            v_type_clean = vehicle_type.upper().strip()
            vehicles = [v for v in vehicles if v.type == v_type_clean]
        return [v.model_dump() for v in vehicles]

    def get_vehicle_by_id(self, vehicle_id: str) -> Optional[Dict[str, Any]]:
        v = self._vehicles.get(vehicle_id)
        if not v:
            return None
        data = v.model_dump()
        data["track"] = self._tracks.get(vehicle_id, [])
        return data

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
        )
        return round(2.0 * r * math.asin(min(1.0, math.sqrt(a))), 2)

    def plan_mission(self, req: MissionPlanRequest) -> Dict[str, Any]:
        vehicle = self._vehicles.get(req.vehicle_id)
        if not vehicle:
            raise ValueError(f"Vehicle '{req.vehicle_id}' not found in registry.")

        if req.target_depth > vehicle.max_depth_m:
            raise ValueError(
                f"Target depth {req.target_depth:.0f} m exceeds vehicle maximum rated depth of {vehicle.max_depth_m:.0f} m."
            )

        dist_km = self._haversine_km(vehicle.latitude, vehicle.longitude, req.target_lat, req.target_lon)

        # Generate waypoint polyline (minimum 7 points along great-circle arc)
        num_pts = max(7, min(25, int(dist_km / 15.0)))
        waypoints = []
        depth_waypoints = []

        start_lat, start_lon, start_depth = vehicle.latitude, vehicle.longitude, vehicle.depth
        target_lat, target_lon, target_depth = req.target_lat, req.target_lon, req.target_depth

        for i in range(num_pts + 1):
            t = i / float(num_pts)
            # Spherical interpolation for geographic path
            cur_lat = round(start_lat + (target_lat - start_lat) * t, 5)
            cur_lon = round(start_lon + (target_lon - start_lon) * t, 5)

            # 3D Depth Mission trajectory:
            # First 50% transit at current cruising depth
            # Next 35% dive/descend down to target depth
            # Final 15% sample at target depth
            if t <= 0.50:
                cur_depth = start_depth
                stage = "TRANSIT"
            elif t <= 0.85:
                dt = (t - 0.50) / 0.35
                cur_depth = round(start_depth + (target_depth - start_depth) * dt, 1)
                stage = "DIVING"
            else:
                cur_depth = target_depth
                stage = "SAMPLING"

            wp = {
                "sequence": i,
                "latitude": cur_lat,
                "longitude": cur_lon,
                "depth_m": cur_depth,
                "stage": stage,
                "progress_percent": round(t * 100.0, 1),
            }
            waypoints.append(wp)
            depth_waypoints.append({"progress": round(t * 100, 1), "depth": cur_depth, "stage": stage})

        speed_kmh = vehicle.cruise_speed_mps * 3.6
        duration_hours = round(max(0.2, dist_km / max(1.0, speed_kmh)), 2)

        mission_id = f"MIS-{vehicle.type}-{uuid.uuid4().hex[:6].upper()}"

        mission = {
            "mission_id": mission_id,
            "vehicle_id": vehicle.id,
            "vehicle_name": vehicle.name,
            "vehicle_type": vehicle.type,
            "status": "MISSION_PLANNED",
            "source": "SIMULATED",
            "origin": {
                "latitude": start_lat,
                "longitude": start_lon,
                "depth_m": start_depth
            },
            "target": {
                "latitude": target_lat,
                "longitude": target_lon,
                "depth_m": target_depth
            },
            "direct_distance_km": dist_km,
            "estimated_duration_hours": duration_hours,
            "requested_sensors": req.sensors,
            "waypoints": waypoints,
            "depth_profile": depth_waypoints,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "simulation_notice": (
                "SIMULATED MISSION: All trajectory waypoints, duration estimates, "
                "and depths are synthesized for autonomous ocean mission planning."
            ),
        }

        # Update vehicle active mission
        vehicle.status = "MISSION_PLANNED"
        vehicle.target = mission["target"]
        vehicle.mission = mission
        self._missions[mission_id] = mission

        return mission

    def sample_observation_at_target(
        self,
        lat: float,
        lon: float,
        depth: float,
        sensors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Synthesizes / queries oceanographic observations for given coordinates and depth.
        Uses realistic oceanographic physics of the Indian Ocean (Mixed Layer, Thermocline,
        Oxygen Minimum Zone, Deep Water).
        """
        # Realistic vertical ocean profile formulas:
        # Surface warm layer (~28°C) declining to ~2°C in deep abyssal waters
        if depth <= 30.0:
            temp = 28.6 - (depth / 30.0) * 0.4
        elif depth <= 200.0:
            # Main thermocline
            dt = (depth - 30.0) / 170.0
            temp = 28.2 - dt * 14.5
        elif depth <= 1000.0:
            dt = (depth - 200.0) / 800.0
            temp = 13.7 - dt * 6.5
        else:
            dt = min(1.0, (depth - 1000.0) / 3000.0)
            temp = 7.2 - dt * 4.8

        # Salinity: Northern Indian Ocean / Arabian Sea high salinity surface (36.0 PSU),
        # intermediate water ~35.0, deep 34.7 PSU
        if depth <= 80.0:
            sal = 35.85 - (depth / 80.0) * 0.35
        elif depth <= 500.0:
            sal = 35.50 - ((depth - 80.0) / 420.0) * 0.65
        else:
            sal = 34.85 + min(0.15, (depth - 500.0) * 0.00005)

        # Dissolved Oxygen (µmol/kg): Surface saturated (~200),
        # pronounced Oxygen Minimum Zone (OMZ) between 150m - 750m (down to ~25 µmol/kg),
        # then rising in ventilated deep water (~110 µmol/kg)
        if depth <= 50.0:
            oxy = 208.0 - (depth / 50.0) * 25.0
        elif depth <= 350.0:
            dt = (depth - 50.0) / 300.0
            oxy = 183.0 - dt * 155.0  # Down to ~28 µmol/kg (OMZ)
        elif depth <= 800.0:
            dt = (depth - 350.0) / 450.0
            oxy = 28.0 + dt * 24.0
        else:
            dt = min(1.0, (depth - 800.0) / 2000.0)
            oxy = 52.0 + dt * 62.0

        # Chlorophyll-a (mg/m³): Subsurface chlorophyll maximum (SCM) at ~40-60m,
        # undetectable in the aphotic deep ocean (>150m)
        if depth <= 55.0:
            chl = 0.35 + math.sin((depth / 55.0) * math.pi / 2.0) * 0.85
        elif depth <= 120.0:
            dt = (depth - 55.0) / 65.0
            chl = 1.20 * math.exp(-dt * 3.5)
        else:
            chl = max(0.01, 0.05 * math.exp(-(depth - 120.0) / 60.0))

        # Add subtle deterministic spatial gradient variation based on lat/lon
        lat_mod = math.sin(math.radians(lat * 3.0)) * 0.3
        lon_mod = math.cos(math.radians(lon * 2.0)) * 0.2
        temp = round(max(-1.5, temp + lat_mod), 2)
        sal = round(max(30.0, sal + lon_mod * 0.1), 2)
        oxy = round(max(10.0, oxy + lat_mod * 4.0), 1)
        chl = round(max(0.01, chl), 3)

        readings = {
            "temperature": temp,
            "salinity": sal,
            "oxygen": oxy,
            "chlorophyll": chl,
        }

        requested_readings = {}
        target_sensors = sensors or ["temperature", "salinity", "oxygen", "chlorophyll"]
        for s in target_sensors:
            s_clean = s.lower().replace("dissolved_", "").replace("_a", "").strip()
            if s_clean in readings:
                requested_readings[s_clean] = readings[s_clean]

        return {
            "target": {
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "depth_m": round(depth, 1)
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "measurements": requested_readings,
            "units": {
                "temperature": "°C",
                "salinity": "PSU",
                "oxygen": "µmol/kg",
                "chlorophyll": "mg/m³",
            },
            "source": "SIMULATED",
            "provenance": "SIMULATED OCEANOGRAPHIC OBSERVATION (INCOIS Hydrographic Baseline Model)",
            "validation_status": "INTERPOLATED_OCEAN_SOUNDING"
        }

    def ingest_telemetry(self, packet: TelemetryPacket) -> Dict[str, Any]:
        """Future real telemetry ingestion endpoint supporting authorized hardware feeds."""
        vehicle = self._vehicles.get(packet.vehicleId)
        if not vehicle:
            # Create dynamic entry if new authorized platform connects
            vehicle = VehicleState(
                id=packet.vehicleId,
                type="AUV",
                name=f"{packet.vehicleId} (Connected Asset)",
                latitude=packet.latitude,
                longitude=packet.longitude,
                depth=packet.depth,
                status="AVAILABLE",
                source="NEAR_REAL_TIME",
                lastUpdate=packet.timestamp
            )
            self._vehicles[packet.vehicleId] = vehicle

        vehicle.latitude = packet.latitude
        vehicle.longitude = packet.longitude
        vehicle.depth = packet.depth
        vehicle.heading_deg = packet.heading
        vehicle.cruise_speed_mps = packet.speed
        vehicle.lastUpdate = packet.timestamp
        vehicle.source = "LIVE" if packet.status.upper() == "LIVE" else "SIMULATED"

        track = self._tracks.setdefault(packet.vehicleId, [])
        track.append({
            "lat": packet.latitude,
            "lon": packet.longitude,
            "depth": packet.depth,
            "timestamp": packet.timestamp,
            "status": packet.status
        })
        # Keep track length manageable
        if len(track) > 100:
            self._tracks[packet.vehicleId] = track[-100:]

        return {"status": "TELEMETRY_ACCEPTED", "vehicleId": packet.vehicleId, "timestamp": packet.timestamp}


vehicle_service = VehicleService()
