"""
Prediction Feature Builder Module.

Provides shared, time-aware feature extraction logic used identically during
training, validation, and inference to prevent feature representation mismatch
and temporal leakage.
"""
from __future__ import annotations
import math
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from .storage import store, _parse
from .schemas import QueryFilters

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "latitude",
    "longitude",
    "depth",
    "val_t0",
    "val_t_minus1",
    "val_t_minus2",
    "bias"
]


def get_series_key(r: Any) -> tuple[str, float, float, float]:
    """Define stable spatial/variable time-series group key."""
    return (
        r.variable.lower().strip(),
        round(r.latitude, 2),
        round(r.longitude, 2),
        round(r.depth, 1)
    )


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def extract_time_aware_features_at(
    latitude: float,
    longitude: float,
    depth: float,
    variable: str = "temperature",
    time: Optional[str] = None
) -> tuple[list[float], dict[str, float]] | None:
    """
    Extracts time-aware features [lat, lon, depth, val_t0, val_t_minus1, val_t_minus2, 1.0]
    strictly from historical time-series records belonging to the same series group.
    Returns None if lag features are missing/unavailable.
    """
    var_clean = variable.lower().strip()
    target_dt = ensure_utc(_parse(time)) if time else datetime.now(timezone.utc)

    # 1. Query records near lat/lon/depth for this variable
    delta = 6.0
    rows = store.query_model(QueryFilters(
        variable=var_clean,
        min_lat=latitude - delta, max_lat=latitude + delta,
        min_lon=longitude - delta, max_lon=longitude + delta,
        min_depth=max(0.0, depth - 50.0), max_depth=depth + 50.0
    ))

    var_rows = [r for r in rows if r.variable.lower().strip() == var_clean]
    if not var_rows:
        return None

    # Group by stable spatial key
    groups: dict[tuple, list[Any]] = {}
    for r in var_rows:
        k = (round(r.latitude, 2), round(r.longitude, 2), round(r.depth, 1))
        groups.setdefault(k, []).append(r)

    # Filter for spatial grid cell groups that contain at least 3 historical time steps <= target_dt
    time_series_groups = {
        k: v for k, v in groups.items()
        if len({ensure_utc(_parse(r.time)) for r in v if ensure_utc(_parse(r.time)) <= target_dt}) >= 3
    }

    if not time_series_groups:
        return None

    # Find nearest spatial grid cell with complete time-series
    best_key = min(time_series_groups.keys(), key=lambda c: (c[0] - latitude)**2 + (c[1] - longitude)**2 + ((c[2] - depth)/20.0)**2)
    group_recs = time_series_groups[best_key]

    # Deduplicate and sort strictly chronologically
    time_map = {}
    for r in group_recs:
        dt = ensure_utc(_parse(r.time))
        if dt <= target_dt:
            time_map[dt] = (r.time, float(r.value))

    sorted_dts = sorted(time_map.keys())

    # STRICT HISTORICAL REQUIREMENT: Must have at least 3 historical time steps (t0, t-1, t-2)
    if len(sorted_dts) < 3:
        return None

    t0_dt = sorted_dts[-1]
    t1_dt = sorted_dts[-2]
    t2_dt = sorted_dts[-3]

    # Verify strict historical direction (t2 < t1 < t0 <= target_dt)
    if not (t2_dt < t1_dt < t0_dt <= target_dt):
        return None

    val_t0 = time_map[t0_dt][1]
    val_t_minus1 = time_map[t1_dt][1]
    val_t_minus2 = time_map[t2_dt][1]

    if math.isnan(val_t0) or math.isnan(val_t_minus1) or math.isnan(val_t_minus2):
        return None

    feature_vec = [
        latitude,
        longitude,
        depth,
        val_t0,
        val_t_minus1,
        val_t_minus2,
        1.0
    ]

    feature_dict = {
        "latitude": latitude,
        "longitude": longitude,
        "depth": depth,
        "val_t0": val_t0,
        "val_t_minus1": val_t_minus1,
        "val_t_minus2": val_t_minus2,
        "bias": 1.0
    }

    return feature_vec, feature_dict
