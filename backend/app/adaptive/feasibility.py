"""
Feasibility & Constraints Assessment Engine.

Evaluates spatial, depth, sensor, range, battery, and ocean current feasibility
for candidate mobile observing platforms.
"""
from __future__ import annotations
import math
import logging
from typing import Optional, Any

from .energy_model import energy_engine
from .current_router import current_router

logger = logging.getLogger(__name__)


class FeasibilityEngine:
    """Evaluates mission feasibility against candidate instrument specifications."""

    def assess_feasibility(
        self,
        candidate_instrument: dict[str, Any],
        target_lat: float,
        target_lon: float,
        target_depth_m: float = 100.0,
        required_sensor: str = "temperature",
        safety_reserve_percent: float = 15.0
    ) -> dict[str, Any]:
        inst = candidate_instrument
        rejection_reasons = []

        # 1. Controllability check
        if not inst.get("controllable", True):
            rejection_reasons.append("Passive drift platform (Cannot steer or navigate to target waypoint)")

        # 2. Sensor check
        if required_sensor not in inst.get("sensors", []):
            rejection_reasons.append(f"Required sensor '{required_sensor}' not equipped")

        # 3. Depth check
        if target_depth_m > inst.get("maximum_depth_m", 1000.0):
            rejection_reasons.append(
                f"Target depth ({target_depth_m:.0f}m) exceeds max operating depth ({inst.get('maximum_depth_m'):.0f}m)"
            )

        # 4. Route & Distance
        route = current_router.plan_current_aware_trajectory(
            inst["latitude"], inst["longitude"], target_lat, target_lon, target_depth_m, inst.get("cruise_speed_mps", 0.35)
        )
        dist_km = route["direct_distance_km"]

        # 5. Range check
        if dist_km > inst.get("remaining_range_km", 400.0):
            rejection_reasons.append(
                f"Target distance ({dist_km:.1f}km) exceeds remaining range ({inst.get('remaining_range_km')}km)"
            )

        # 6. Battery Energy Evaluation
        energy = energy_engine.evaluate_energy_expenditure(
            inst["platform_type"],
            inst["battery_percent"],
            dist_km,
            inst.get("cruise_speed_mps", 0.35),
            target_depth_m,
            route["current_headwind_mps"],
            safety_reserve_percent
        )

        if not energy["feasible"]:
            rejection_reasons.append(energy["rejection_reason"])

        feasible = len(rejection_reasons) == 0

        reasons = [
            f"Target depth ({target_depth_m:.0f}m) within capability",
            f"Required sensor '{required_sensor}' available",
            f"Transit distance ({dist_km:.1f}km) within remaining range",
            f"Battery margin safe ({energy['energy_remaining_percent']:.1f}% remaining after mission)",
            f"Current-adjusted trajectory feasible ({route['effective_speed_mps']:.2f} m/s effective speed)"
        ] if feasible else rejection_reasons

        return {
            "instrument_id": inst["instrument_id"],
            "feasible": feasible,
            "distance_km": dist_km,
            "estimated_duration_hours": route["estimated_duration_hours"],
            "energy_required_percent": energy["energy_required_percent"],
            "remaining_battery_percent": energy["energy_remaining_percent"],
            "safety_reserve_percent": safety_reserve_percent,
            "route_details": route,
            "energy_details": energy,
            "reasons": reasons
        }


feasibility_engine = FeasibilityEngine()
