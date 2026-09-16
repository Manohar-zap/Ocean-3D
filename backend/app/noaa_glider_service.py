"""
NOAA AOML ERDDAP Glider Service (Test Integration).
Fetches and normalizes autonomous glider trajectories from NOAA/AOML ERDDAP:
https://erddap.aoml.noaa.gov/hdb/erddap/tabledap/GLIDERS_2025_01_03
"""
from __future__ import annotations
import os
import json
import ssl
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from collections import defaultdict


class NoaaGliderService:
    DATASET_ID = "GLIDERS_2025_01_03"
    BASE_URL = f"https://erddap.aoml.noaa.gov/hdb/erddap/tabledap/{DATASET_ID}.json"
    CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache_noaa_gliders.json")
    CACHE_TTL_SECONDS = 3600  # 1 hour

    def __init__(self):
        self._memory_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0
        self.status = "INITIALIZING"
        self.last_error: Optional[str] = None

    def _get_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def get_latest_gliders(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Retrieve normalized latest observation per unique trajectory.
        Uses in-memory cache, then local disk cache, then live NOAA ERDDAP query.
        """
        now = time.time()
        if not force_refresh and self._memory_cache and (now - self._cache_timestamp < self.CACHE_TTL_SECONDS):
            return self._memory_cache

        # Check local disk cache if memory cache is empty
        if not force_refresh and not self._memory_cache and os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
                if disk_data.get("gliders"):
                    self._memory_cache = disk_data
                    self._cache_timestamp = now
                    self.status = "READY"
                    return disk_data
            except Exception as e:
                print(f"[NoaaGliderService] Failed to read disk cache: {e}")

        # Fetch from NOAA ERDDAP
        try:
            result = self._fetch_from_erddap()
            if result.get("gliders"):
                self._memory_cache = result
                self._cache_timestamp = now
                self.status = "READY"
                self.last_error = None
                # Save to disk cache for offline resilience
                try:
                    os.makedirs(os.path.dirname(self.CACHE_FILE), exist_ok=True)
                    with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2)
                except Exception as disk_err:
                    print(f"[NoaaGliderService] Failed to write disk cache: {disk_err}")
                return result
        except Exception as e:
            self.status = "ERROR"
            self.last_error = str(e)
            print(f"[NoaaGliderService] ERDDAP fetch error: {e}")

        # Fallback to existing memory or disk cache if available
        if self._memory_cache:
            return self._memory_cache

        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Graceful non-blocking empty response (no synthetic data)
        return {
            "status": "UNAVAILABLE",
            "message": f"NOAA glider data unavailable: {self.last_error or 'Connection failed'}",
            "source": "NOAA/AOML/IOOS ERDDAP",
            "dataset_id": self.DATASET_ID,
            "data_status": "UNAVAILABLE",
            "count": 0,
            "total_trajectories": 0,
            "gliders": []
        }

    def _fetch_from_erddap(self) -> Dict[str, Any]:
        """Queries NOAA ERDDAP for distinct trajectory positions and selects latest per trajectory."""
        query_url = f"{self.BASE_URL}?trajectory,time,latitude,longitude&distinct()"
        req = urllib.request.Request(query_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Ocean3D-NOAA-Test/1.0"
        })

        ctx = self._get_ssl_context()
        with urllib.request.urlopen(req, context=ctx, timeout=35) as resp:
            raw_data = json.loads(resp.read().decode("utf-8"))

        table = raw_data.get("table", {})
        col_names = table.get("columnNames", [])
        rows = table.get("rows", [])

        if not rows:
            return {
                "status": "EMPTY",
                "message": "NOAA ERDDAP returned zero records",
                "source": "NOAA/AOML/IOOS ERDDAP",
                "dataset_id": self.DATASET_ID,
                "count": 0,
                "total_trajectories": 0,
                "gliders": []
            }

        idx_traj = col_names.index("trajectory")
        idx_time = col_names.index("time")
        idx_lat = col_names.index("latitude")
        idx_lon = col_names.index("longitude")

        # Group observations strictly by unique trajectory ID
        traj_records: Dict[str, List[tuple]] = defaultdict(list)
        all_lats = []
        all_lons = []
        all_times = []

        for r in rows:
            traj = r[idx_traj]
            t_str = r[idx_time]
            lat = r[idx_lat]
            lon = r[idx_lon]

            # Validation: discard invalid or missing coordinates/timestamps
            if not traj or lat is None or lon is None or not t_str:
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (ValueError, TypeError):
                continue

            if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
                continue

            traj_records[str(traj)].append((t_str, lat_f, lon_f))
            all_lats.append(lat_f)
            all_lons.append(lon_f)
            all_times.append(t_str)

        # Extract latest observation for each unique trajectory
        gliders: List[Dict[str, Any]] = []
        for traj, recs in traj_records.items():
            recs.sort(key=lambda x: x[0])
            latest_time, latest_lat, latest_lon = recs[-1]

            gliders.append({
                "source": "NOAA/AOML/IOOS ERDDAP",
                "dataset_id": self.DATASET_ID,
                "instrument_type": "NOAA/AOML Glider (Test)",
                "trajectory": traj,               # Exact real trajectory from NOAA
                "platform_id": None,              # None (not artificially split)
                "latitude": round(latest_lat, 5),
                "longitude": round(latest_lon, 5),
                "depth": None,                    # None (not 0.0)
                "timestamp": latest_time,         # Latest observation timestamp
                "temperature": None,              # None
                "salinity": None,                 # None
                "total_fixes": len(recs),
                "data_status": "HISTORICAL TEST DATA (2025)",
            })

        # Sort gliders by trajectory name for deterministic presentation
        gliders.sort(key=lambda g: g["trajectory"])

        all_times.sort()
        return {
            "status": "READY",
            "source": "NOAA/AOML/IOOS ERDDAP",
            "dataset_id": self.DATASET_ID,
            "data_status": "HISTORICAL TEST DATA (2025)",
            "notice": "Historical observations from 2025-01-02 to 2025-12-12. Not live real-time telemetry.",
            "count": len(gliders),
            "total_trajectories": len(gliders),
            "total_observations": len(rows),
            "time_range": {
                "start": all_times[0] if all_times else "",
                "end": all_times[-1] if all_times else ""
            },
            "bounds": {
                "min_lat": min(all_lats) if all_lats else -90,
                "max_lat": max(all_lats) if all_lats else 90,
                "min_lon": min(all_lons) if all_lons else -180,
                "max_lon": max(all_lons) if all_lons else 180
            },
            "gliders": gliders
        }


noaa_glider_service = NoaaGliderService()
