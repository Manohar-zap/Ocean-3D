"""
NOAA CoastWatch ERDDAP Surface Currents Service (nesdisSSH1day).
Provides secondary real-time surface-current velocity fallback (ugos, vgos).
"""
from __future__ import annotations
import os
import math
import json
import logging
from datetime import datetime, timezone
import urllib.request
import urllib.error
from typing import Optional, Any

logger = logging.getLogger(__name__)

CACHE_FILE = "backend/data/cache_noaa_currents.json"
ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/nesdisSSH1day.json"


class NoaaERDDAPService:
    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                logger.info(f"Loaded NOAA surface currents cache from {CACHE_FILE}")
        except Exception as e:
            logger.warning(f"Could not load NOAA currents cache: {e}")

    def fetch_live_surface_currents(
        self,
        min_lat: float = -50.0,
        max_lat: float = 50.0,
        min_lon: float = -180.0,
        max_lon: float = 180.0,
        stride: int = 16
    ) -> Optional[dict[str, Any]]:
        """Fetch real-time geostrophic surface velocity (ugos, vgos) from NOAA CoastWatch ERDDAP."""
        try:
            url = f"{ERDDAP_BASE}?ugos[(last)][({min_lat}):({stride}):({max_lat})][({min_lon}):({stride}):({max_lon})],vgos[(last)][({min_lat}):({stride}):({max_lat})][({min_lon}):({stride}):({max_lon})]"
            req = urllib.request.Request(url, headers={"User-Agent": "Ocean3D/1.0"})
            with urllib.request.urlopen(req, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
                rows = data.get("table", {}).get("rows", [])
                vectors = []
                for row in rows:
                    if len(row) >= 6 and row[4] is not None and row[5] is not None:
                        u, v = float(row[4]), float(row[5])
                        speed = math.hypot(u, v)
                        if speed > 0.02:
                            heading = (math.degrees(math.atan2(v, u)) + 360.0) % 360.0
                            vectors.append({
                                "lat": round(float(row[2]), 2),
                                "lon": round(float(row[3]), 2),
                                "u": round(u, 4),
                                "v": round(v, 4),
                                "speed": round(speed, 3),
                                "heading": round(heading, 1)
                            })
                result = {
                    "dataset_id": "nesdisSSH1day",
                    "status": "operational",
                    "provenance": "NOAA CoastWatch nesdisSSH1day",
                    "depth_m": 0.0,
                    "count": len(vectors),
                    "vectors": vectors
                }
                self._cache = result
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(result, f)
                return result
        except Exception as e:
            logger.warning(f"Live NOAA ERDDAP surface currents fetch error: {e}")
            return None

    def get_currents(self, time_str: Optional[str] = None) -> dict[str, Any]:
        """Return surface current vector field for visualization."""
        if self._cache:
            return self._cache
        return {
            "dataset_id": "nesdisSSH1day",
            "status": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vectors": []
        }


noaa_service = NoaaERDDAPService()
