"""
Prediction Feature Builder Module.

Provides shared, time-aware feature extraction logic used identically during
training, validation, and inference to prevent feature representation mismatch
and temporal leakage.
"""
from __future__ import annotations
import math
import logging
from typing import Optional, Any
from .storage import store
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


def extract_time_aware_features_at(
    latitude: float,
    longitude: float,
    depth: float,
    variable: str = "temperature",
    time: Optional[str] = None
) -> tuple[list[float], dict[str, float]] | None:
    """
    Extracts time-aware features [lat, lon, depth, val_t0, val_t_minus1, val_t_minus2, 1.0]
    strictly from store.model_records without synthetic offsets.
    """
    delta = 10.0
    rows = store.query_model(QueryFilters(
        variable=variable,
        min_lat=latitude - delta, max_lat=latitude + delta,
        min_lon=longitude - delta, max_lon=longitude + delta,
        min_depth=max(0.0, depth - 50.0), max_depth=depth + 500.0
    ))

    var_rows = [r for r in rows if r.variable == variable]
    if not var_rows:
        return None

    # Find nearest grid record
    nearest_rec = min(var_rows, key=lambda r: (r.latitude - latitude)**2 + (r.longitude - longitude)**2 + ((r.depth - depth)/50.0)**2)
    val_t0 = float(nearest_rec.value)

    # Search for historical/depth lags
    lags = [r for r in var_rows if r.time != nearest_rec.time or abs(r.depth - depth) > 1e-4]
    lags_sorted = sorted(lags, key=lambda r: abs(r.depth - depth) + (0 if r.time < nearest_rec.time else 50))

    if len(lags_sorted) >= 2:
        val_t_minus1 = float(lags_sorted[0].value)
        val_t_minus2 = float(lags_sorted[1].value)
    elif len(lags_sorted) == 1:
        val_t_minus1 = float(lags_sorted[0].value)
        val_t_minus2 = val_t0
    else:
        val_t_minus1 = val_t0
        val_t_minus2 = val_t0

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
