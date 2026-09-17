"""
Global 3D Ocean Currents Service.

Loads precomputed, depth-aware, multi-temporal real ocean velocity fields (uo, vo)
from Copernicus Marine Service (cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m)
with secondary surface velocity fallback from NOAA CoastWatch ERDDAP.

Features:
- O(1) direct coordinate lookup for (lat, lon, depth, time)
- Zero synthetic fallbacks (never fabricates u=0.35, v=-0.25)
- Shared across:
  1. Cesium current vector streamlines (/api/currents)
  2. Depth slider (0, 10, 50, 100, 200, 500, 1000m)
  3. Time slider (multi-timestamp real physics)
  4. Adaptive glider mission router & current-aware A*
  5. Mission simulation engine & power/drift modeling
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

CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "cache_currents_global_3d.npz"


class CurrentsService:
    """Unified 3D ocean currents service providing O(1) vector lookups and global visualization fields."""

    def __init__(self):
        self._loaded: bool = False
        self._latitudes: Optional[np.ndarray] = None   # 1D array of floats
        self._longitudes: Optional[np.ndarray] = None  # 1D array of floats
        self._depths: Optional[np.ndarray] = None      # 1D array of standard depth levels
        self._times: list[str] = []                    # list of ISO strings
        self._u: Optional[np.ndarray] = None           # shape: (n_times, n_depths, n_lat, n_lon)
        self._v: Optional[np.ndarray] = None           # shape: (n_times, n_depths, n_lat, n_lon)
        self._provenance: str = "Copernicus Marine Global Ocean Analysis (0.083°)"
        self.load()

    def load(self):
        """Load compressed 3D currents binary cache into memory."""
        if not CACHE_FILE.exists():
            logger.warning(f"Currents binary cache not found at {CACHE_FILE}. Currents service operating in offline mode.")
            self._loaded = False
            return

        try:
            data = np.load(CACHE_FILE)
            self._latitudes = data["latitudes"]
            self._longitudes = data["longitudes"]
            self._depths = data["depths"]
            self._times = [str(t) for t in data["times"]]
            self._u = data["u"]
            self._v = data["v"]
            if "provenance" in data:
                self._provenance = str(data["provenance"])
            self._loaded = True
            logger.info(
                f"Loaded 3D currents cache: shape={self._u.shape}, depths={list(self._depths)}, "
                f"times={self._times}, provenance={self._provenance}"
            )
        except Exception as e:
            logger.error(f"Error loading 3D currents cache: {e}")
            self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get_available_depths(self) -> list[float]:
        if self._depths is not None:
            return [float(d) for d in self._depths]
        return [0.0, 10.0, 50.0, 100.0, 200.0, 500.0, 1000.0]

    def get_available_times(self) -> list[str]:
        if self._times:
            return self._times
        return ["2024-03-01T00:00:00Z"]

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

    def get_vector(
        self,
        lat: float,
        lon: float,
        depth: float = 0.0,
        time_str: Optional[str] = None
    ) -> tuple[float, float, float, float, str]:
        """
        Fast O(1) query returning (u, v, speed_mps, direction_deg, provenance).
        Returns (0.0, 0.0, 0.0, 0.0, 'NO_DATA') if point is land, out-of-bounds, or NaN.
        Never fabricates synthetic velocity values.
        """
        if not self._loaded or self._u is None or self._v is None:
            return 0.0, 0.0, 0.0, 0.0, "NO_DATA"

        d_idx = self._find_nearest_depth_idx(depth)
        t_idx = self._find_time_idx(time_str)
        if t_idx is None:
            return 0.0, 0.0, 0.0, 0.0, "NO_DATA"
        lat_idx, lon_idx = self._coord_to_indices(lat, lon)

        if lat_idx is None or lon_idx is None:
            return 0.0, 0.0, 0.0, 0.0, "NO_DATA"

        u = float(self._u[t_idx, d_idx, lat_idx, lon_idx])
        v = float(self._v[t_idx, d_idx, lat_idx, lon_idx])

        if math.isnan(u) or math.isnan(v):
            return 0.0, 0.0, 0.0, 0.0, "NO_DATA"

        speed = math.hypot(u, v)
        direction = (math.degrees(math.atan2(v, u)) + 360.0) % 360.0
        return round(u, 4), round(v, 4), round(speed, 3), round(direction, 1), self._provenance

    def get_current_field(
        self,
        depth: float = 0.0,
        time_str: Optional[str] = None,
        min_lat: float = -75.0,
        max_lat: float = 75.0,
        min_lon: float = -180.0,
        max_lon: float = 180.0,
        stride: int = 4
    ) -> dict[str, Any]:
        """
        Sample 2D horizontal slice of vectors for 3D globe visualization.
        Global view uses stride=4 (producing ~1,500-2,000 streamlines for 60 FPS).
        Regional view uses stride=1 or 2 for high density.
        """
        if not self._loaded or self._u is None or self._v is None:
            return {
                "depth_m": depth,
                "time": time_str or (self._times[0] if self._times else ""),
                "provenance": "NO_DATA",
                "count": 0,
                "vectors": []
            }

        d_idx = self._find_nearest_depth_idx(depth)
        actual_depth = float(self._depths[d_idx]) if self._depths is not None else depth
        t_idx = self._find_time_idx(time_str)
        if t_idx is None:
            return {
                "depth_m": actual_depth,
                "time": time_str or "",
                "provenance": "NO_DATA",
                "available": False,
                "count": 0,
                "vectors": []
            }
        actual_time = self._times[t_idx] if self._times else ""

        u_slice = self._u[t_idx, d_idx]
        v_slice = self._v[t_idx, d_idx]

        lat_min_idx = max(0, int(math.floor(min_lat - float(self._latitudes[0]))))
        lat_max_idx = min(len(self._latitudes) - 1, int(math.ceil(max_lat - float(self._latitudes[0]))))

        vectors = []
        stride = max(1, stride)
        for i in range(lat_min_idx, lat_max_idx + 1, stride):
            lat_val = float(self._latitudes[i])
            for j in range(0, len(self._longitudes), stride):
                lon_val = float(self._longitudes[j])
                # Filter longitude range
                if min_lon <= max_lon:
                    if not (min_lon <= lon_val <= max_lon):
                        continue
                else:  # Pacific wrap
                    if not (lon_val >= min_lon or lon_val <= max_lon):
                        continue

                u_val = float(u_slice[i, j])
                v_val = float(v_slice[i, j])

                if math.isnan(u_val) or math.isnan(v_val):
                    continue

                speed = math.hypot(u_val, v_val)
                if speed < 0.02:
                    continue

                heading = (math.degrees(math.atan2(v_val, u_val)) + 360.0) % 360.0
                vectors.append({
                    "lat": round(lat_val, 2),
                    "lon": round(lon_val, 2),
                    "u": round(u_val, 4),
                    "v": round(v_val, 4),
                    "speed": round(speed, 3),
                    "heading": round(heading, 1)
                })

        return {
            "depth_m": actual_depth,
            "time": actual_time,
            "provenance": self._provenance,
            "count": len(vectors),
            "vectors": vectors
        }

    def get_current_grid(
        self,
        depth: float = 0.0,
        time_str: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Return full 2D regular velocity grid for frontend particle advection and interpolation.
        Zero synthetic values.
        """
        if not self._loaded or self._u is None or self._v is None:
            return {
                "lat_min": -80.0,
                "lat_max": 90.0,
                "lat_step": 1.0,
                "lon_min": -180.0,
                "lon_max": 179.0,
                "lon_step": 1.0,
                "n_lat": 0,
                "n_lon": 0,
                "depth_m": depth,
                "time": time_str or "",
                "provenance": "NO_DATA",
                "u": [],
                "v": []
            }

        d_idx = self._find_nearest_depth_idx(depth)
        actual_depth = float(self._depths[d_idx]) if self._depths is not None else depth
        t_idx = self._find_time_idx(time_str)
        if t_idx is None:
            return {
                "lat_min": -80.0,
                "lat_max": 90.0,
                "lat_step": 1.0,
                "lon_min": -180.0,
                "lon_max": 179.0,
                "lon_step": 1.0,
                "n_lat": 0,
                "n_lon": 0,
                "depth_m": actual_depth,
                "time": time_str or "",
                "provenance": "NO_DATA",
                "available": False,
                "u": [],
                "v": []
            }
        actual_time = self._times[t_idx] if self._times else ""

        u_slice = self._u[t_idx, d_idx]
        v_slice = self._v[t_idx, d_idx]

        lat_min = float(self._latitudes[0])
        lat_max = float(self._latitudes[-1])
        lat_step = float(self._latitudes[1] - self._latitudes[0]) if len(self._latitudes) > 1 else 1.0

        lon_min = float(self._longitudes[0])
        lon_max = float(self._longitudes[-1])
        lon_step = float(self._longitudes[1] - self._longitudes[0]) if len(self._longitudes) > 1 else 1.0

        # Export flat lists with None for NaN/land cells
        u_flat = [round(float(val), 4) if not np.isnan(val) else None for val in u_slice.flat]
        v_flat = [round(float(val), 4) if not np.isnan(val) else None for val in v_slice.flat]

        return {
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
            "u": u_flat,
            "v": v_flat
        }


currents_service = CurrentsService()
