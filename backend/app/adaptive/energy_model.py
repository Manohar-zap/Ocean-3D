"""
Vehicle Propulsion & Battery Drain Energy Engine.

Calculates energy expenditure, propulsion power demand, sensor load,
and safety reserve margins based on distance, speed, depth, and ocean current drag.
"""
from __future__ import annotations
import math
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class EnergyModelEngine:
    """Calculates propulsion and payload battery energy consumption."""

    def evaluate_energy_expenditure(
        self,
        platform_type: str,
        initial_battery_percent: float,
        distance_km: float,
        cruise_speed_mps: float,
        depth_m: float,
        current_drag_mps: float = 0.0,
        safety_reserve_percent: float = 15.0
    ) -> dict[str, Any]:
        ptype = platform_type.lower().strip()
        
        # Vehicle power specifications (Watts & Battery Capacity Wh)
        if ptype == "auv":
            propulsion_watts = 120.0  # High power propulsion motor
            sensor_watts = 25.0
            battery_capacity_wh = 4800.0  # Lithium-ion AUV battery bank
        elif ptype == "vessel":
            propulsion_watts = 500000.0  # Marine diesel engine
            sensor_watts = 1500.0
            battery_capacity_wh = 10000000.0
        else:  # Glider
            propulsion_watts = 8.5    # Low power buoyancy engine
            sensor_watts = 3.2
            battery_capacity_wh = 3200.0   # Long-range primary lithium battery pack (2400-3600 Wh)

        # Effective ground speed considering ocean current drag (v_effective = v_cruise - v_current_headwind)
        effective_speed = max(0.05, cruise_speed_mps - max(-0.5, min(0.5, current_drag_mps)))
        travel_seconds = (distance_km * 1000.0) / effective_speed
        duration_hours = travel_seconds / 3600.0

        # Dive vertical buoyancy pumping energy for gliders/AUVs
        dives = math.ceil(depth_m / 200.0)
        pumping_wh_per_dive = 2.5 if ptype == "glider" else 12.0
        dive_energy_wh = dives * pumping_wh_per_dive

        # Total Watt-hours required
        transit_energy_wh = (propulsion_watts + sensor_watts) * duration_hours + dive_energy_wh
        energy_req_percent = (transit_energy_wh / battery_capacity_wh) * 100.0

        usable_battery = max(0.0, initial_battery_percent - safety_reserve_percent)
        remaining_battery = initial_battery_percent - energy_req_percent
        feasible = (remaining_battery >= safety_reserve_percent) and (energy_req_percent <= usable_battery)

        reason = None
        if not feasible:
            reason = f"INSUFFICIENT ENERGY MARGIN (Required: {energy_req_percent:.1f}%, Usable: {usable_battery:.1f}%, Safety Reserve: {safety_reserve_percent:.1f}%)"

        return {
            "platform_type": ptype,
            "initial_battery_percent": round(initial_battery_percent, 1),
            "effective_speed_mps": round(effective_speed, 2),
            "duration_hours": round(duration_hours, 1),
            "transit_energy_wh": round(transit_energy_wh, 1),
            "energy_required_percent": round(energy_req_percent, 1),
            "energy_remaining_percent": round(max(0.0, remaining_battery), 1),
            "usable_battery_percent": round(usable_battery, 1),
            "safety_reserve_percent": round(safety_reserve_percent, 1),
            "feasible": feasible,
            "rejection_reason": reason
        }


energy_engine = EnergyModelEngine()
