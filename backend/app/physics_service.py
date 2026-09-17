"""
Global 3D Ocean Physics Service (Temperature, Salinity, Pressure).

Loads precomputed, multi-temporal, multi-depth operational physical fields
from Copernicus Marine Service (GLOBAL_ANALYSISFORECAST_PHY_001_024).

Features:
- O(1) direct coordinate lookup for (lat, lon, depth, time)
- Fast regular 2D grid extraction for Cesium GPU texture visualization
- Strict date resolution: returns None / available=False if date is not in dataset
- Zero synthetic fallbacks (never fabricates temperatures via trigonometric math)
- Shared across:
  1. Cesium 3D Earth scalar field rendering (/api/model/grid, /api/model)
  2. 14-Day Date Explorer & Calendar
  3. Depth slider (0, 10, 50, 100, 200, 500, 1000m)
  4. Argo profile collocation and model error analysis
"""
from __future__ import annotations

import os
import math
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any
import numpy as np

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "cache_scalars_global_3d.npz"


class PhysicsService:
    """Unified physical oceanography service providing temperature, salinity, and pressure fields."""

    def __init__(self):
        self._loaded: bool = False
        self._latitudes: Optional[np.ndarray] = None   # 1D array of 171 floats
        self._longitudes: Optional[np.ndarray] = None  # 1D array of 360 floats
        self._depths: Optional[np.ndarray] = None      # 1D array of 7 floats
        self._times: list[str] = []                    # list of 14 ISO strings
        self._temperature: Optional[np.ndarray] = None # shape: (14, 7, 171, 360)
        self._salinity: Optional[np.ndarray] = None    # shape: (14, 7, 171, 360)
        self._pressure: Optional[np.ndarray] = None    # shape: (14, 7, 171, 360)
        self._provenance: str = "Copernicus Marine GLOBAL_ANALYSISFORECAST_PHY_001_024"
        self.load()

    def load(self):
        """Load compressed 3D physical scalars binary cache into memory."""
        if not CACHE_FILE.exists():
            logger.warning(f"Scalars binary cache not found at {CACHE_FILE}. Physics service offline.")
            self._loaded = False
            return

        try:
            data = np.load(CACHE_FILE)
            self._latitudes = data["latitudes"]
            self._longitudes = data["longitudes"]
            self._depths = data["depths"]
            self._times = [str(t) for t in data["times"]]
            self._temperature = data["temperature"]
            self._salinity = data["salinity"]
            self._pressure = data["pressure"]
            if "provenance" in data:
                self._provenance = str(data["provenance"])
            self._loaded = True
            logger.info(
                f"Loaded 3D scalars cache: temp_shape={self._temperature.shape}, "
                f"depths={list(self._depths)}, times={len(self._times)} days, "
                f"provenance={self._provenance}"
            )
        except Exception as e:
            logger.error(f"Error loading 3D scalars cache: {e}")
            self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get_available_depths(self) -> list[float]:
        if self._depths is not None:
            return [float(d) for d in self._depths]
        return [0.0, 10.0, 50.0, 100.0, 200.0, 500.0, 1000.0]

    def get_available_times(self) -> list[str]:
        return self._times

    def _find_nearest_depth_idx(self, depth: float) -> int:
        if self._depths is None or len(self._depths) == 0:
            return 0
        diffs = np.abs(self._depths - depth)
        return int(np.argmin(diffs))

    def _find_time_idx(self, time_str: Optional[str]) -> Optional[int]:
        if not self._times:
            return None
        if not time_str:
            return len(self._times) - 1
        time_clean = time_str.strip()
        for idx, t in enumerate(self._times):
            if t == time_clean or t.startswith(time_clean[:10]) or time_clean.startswith(t[:10]):
                return idx
        return None

    def _coord_to_indices(self, lat: float, lon: float) -> tuple[Optional[int], Optional[int]]:
        """Map geographic coordinate to integer grid indices in O(1)."""
        if self._latitudes is None or self._longitudes is None:
            return None, None

        min_lat = float(self._latitudes[0])
        max_lat = float(self._latitudes[-1])
        if lat < min_lat or lat > max_lat:
            return None, None

        lat_idx = int(round(lat - min_lat))
        if lat_idx < 0 or lat_idx >= len(self._latitudes):
            return None, None

        norm_lon = ((lon + 180.0) % 360.0) - 180.0
        min_lon = float(self._longitudes[0])
        lon_idx = int(round(norm_lon - min_lon)) % len(self._longitudes)

        return lat_idx, lon_idx

    def get_scalar_grid(
        self,
        variable: str,
        depth: float = 0.0,
        time_str: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Return full 2D regular scalar grid for Cesium surface rendering.
        Zero synthetic values. Strict date resolution.
        """
        if not self._loaded:
            self.load()

        var_map = {
            "temperature": self._temperature,
            "salinity": self._salinity,
            "pressure": self._pressure
        }
        var_data = var_map.get(variable)
        if not self._loaded or var_data is None:
            return {
                "available": False,
                "variable": variable,
                "depth_m": depth,
                "time": time_str or "",
                "provenance": "NO_DATA",
                "values": []
            }

        d_idx = self._find_nearest_depth_idx(depth)
        actual_depth = float(self._depths[d_idx]) if self._depths is not None else depth
        t_idx = self._find_time_idx(time_str)

        if t_idx is None:
            return {
                "available": False,
                "variable": variable,
                "depth_m": actual_depth,
                "time": time_str or "",
                "provenance": "NO_DATA",
                "values": []
            }

        actual_time = self._times[t_idx]
        grid_slice = var_data[t_idx, d_idx]

        lat_min = float(self._latitudes[0])
        lat_max = float(self._latitudes[-1])
        lat_step = float(self._latitudes[1] - self._latitudes[0]) if len(self._latitudes) > 1 else 1.0

        lon_min = float(self._longitudes[0])
        lon_max = float(self._longitudes[-1])
        lon_step = float(self._longitudes[1] - self._longitudes[0]) if len(self._longitudes) > 1 else 1.0

        vals_flat = [round(float(val), 4) if not np.isnan(val) else None for val in grid_slice.flat]

        return {
            "available": True,
            "variable": variable,
            "lat_min": round(lat_min, 4),
            "lat_max": round(lat_max, 4),
            "lat_step": round(lat_step, 4),
            "lon_min": round(lon_min, 4),
            "lon_max": round(lon_max, 4),
            "lon_step": round(lon_step, 4),
            "n_lat": int(len(self._latitudes)),
            "n_lon": int(len(self._longitudes)),
            "depth_m": actual_depth,
            "time": actual_time,
            "provenance": self._provenance,
            "values": vals_flat
        }

    def get_points(
        self,
        variable: str,
        depth: float = 0.0,
        time_str: Optional[str] = None,
        min_lat: float = -75.0,
        max_lat: float = 75.0,
        min_lon: float = -180.0,
        max_lon: float = 180.0,
        stride: int = 2
    ) -> list[dict[str, Any]]:
        """Return sparse points list for legacy /api/model compatible consumption."""
        if not self._loaded:
            self.load()

        var_map = {
            "temperature": self._temperature,
            "salinity": self._salinity,
            "pressure": self._pressure
        }
        var_data = var_map.get(variable)
        if not self._loaded or var_data is None:
            return []

        d_idx = self._find_nearest_depth_idx(depth)
        t_idx = self._find_time_idx(time_str)
        if t_idx is None:
            return []

        actual_depth = float(self._depths[d_idx])
        grid_slice = var_data[t_idx, d_idx]

        lat_min_idx = max(0, int(math.floor(min_lat - float(self._latitudes[0]))))
        lat_max_idx = min(len(self._latitudes) - 1, int(math.ceil(max_lat - float(self._latitudes[0]))))

        points = []
        stride = max(1, stride)
        for i in range(lat_min_idx, lat_max_idx + 1, stride):
            lat_val = float(self._latitudes[i])
            for j in range(0, len(self._longitudes), stride):
                lon_val = float(self._longitudes[j])
                if min_lon <= max_lon:
                    if not (min_lon <= lon_val <= max_lon):
                        continue
                else:
                    if not (lon_val >= min_lon or lon_val <= max_lon):
                        continue

                val = float(grid_slice[i, j])
                if math.isnan(val):
                    continue

                points.append({
                    "lat": round(lat_val, 2),
                    "lon": round(lon_val, 2),
                    "depth": actual_depth,
                    "value": round(val, 3)
                })

        return points


physics_service = PhysicsService()
