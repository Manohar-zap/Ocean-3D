"""
NOAA ERDDAP Service for Real-Time Surface Currents.
Fetches geostrophic U/V data from CoastWatch.
"""
import json
import math
import urllib.request
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

class NoaaERDDAPService:
    BASE_URL = "https://coastwatch.noaa.gov/erddap/griddap/noaacwBLENDEDNRTcurrentsDaily.json"

    # Dataset coverage from metadata
    LAT_BOUNDS = (-89.875, 89.875)
    LON_BOUNDS = (-179.875, 179.875)

    def __init__(self):
        # In-memory cache for the velocity fields
        # Key: (time_str, min_lat, max_lat, min_lon, max_lon, stride)
        self.cache_registry = {}
        self.available_times = []
        self.status = "EMPTY" # EMPTY, LOADING, READY, ERROR
        self.last_error = None
        self.preload_task = None

    async def preload(self):
        """Startup task to fetch the initial Indian Ocean current field."""
        print("[NOAA Service] Starting background preload for Indian Ocean...")
        self.status = "LOADING"
        try:
            # 1. Fetch available times first to enable date snapping
            print("[NOAA Service] Fetching available times...")
            import asyncio
            loop = asyncio.get_running_loop()
            times = await loop.run_in_executor(None, self._fetch_available_times)
            if times:
                self.available_times = times
                print(f"[NOAA Service] Found {len(times)} available daily records.")

            # 2. Broad Indian Ocean coverage optimized for performance
            # Use a stride of 4 for fast initial load
            points = await loop.run_in_executor(
                None,
                lambda: self.fetch_surface_currents(
                    min_lat=-10.0, max_lat=30.0,
                    min_lon=50.0, max_lon=100.0,
                    time_str=None, # Defaults to (last)
                    stride=4
                )
            )
            if points:
                self.status = "READY"
                print(f"[NOAA Service] Preload complete: {len(points)} points cached.")
            else:
                self.status = "EMPTY"
                print("[NOAA Service] Preload resulted in no data.")
        except Exception as e:
            self.status = "ERROR"
            self.last_error = str(e)
            print(f"[NOAA Service] Preload failed: {e}")

    def _fetch_available_times(self) -> List[str]:
        """Queries NOAA ERDDAP for available timestamps."""
        url = f"https://coastwatch.noaa.gov/erddap/griddap/noaacwBLENDEDNRTcurrentsDaily.json?time"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OCEAN3D/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("table", {}).get("rows", [])
                return [r[0] for r in rows if r]
        except Exception as e:
            print(f"[NOAA Service] Error fetching times: {e}")
            return []

    def _snap_time(self, requested_time: Optional[str]) -> str:
        """Finds the closest available NOAA timestamp."""
        if not self.available_times:
            return "(last)"

        if not requested_time or requested_time in ("null", "undefined", ""):
            return "(last)"

        # Normalize requested time to UTC
        try:
            # ERDDAP times are like "2026-09-11T00:00:00Z"
            req_dt = datetime.fromisoformat(requested_time.replace("Z", "+00:00"))

            # Simple nearest neighbor search
            best_t = self.available_times[-1]
            min_diff = float('inf')

            for t in reversed(self.available_times): # Search from newest
                t_dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
                diff = abs((req_dt - t_dt).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    best_t = t
                else:
                    # Since it's sorted, once it starts increasing, we can stop if we search from closest
                    # But reverse search is safer if requested time is very new
                    if diff > min_diff:
                        break

            return f"({best_t})"
        except Exception:
            return "(last)"

    def fetch_surface_currents(
        self,
        min_lat: float, max_lat: float,
        min_lon: float, max_lon: float,
        time_str: Optional[str] = None,
        stride: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Queries NOAA ERDDAP for u_current and v_current in the specified viewport.
        Checks cache first with spatial overlap support.
        """
        # 1. Normalize and Clamp Coordinates
        s_min_lat = round(min(min_lat, max_lat), 2)
        s_max_lat = round(max(min_lat, max_lat), 2)
        s_min_lon = round(min(min_lon, max_lon), 2)
        s_max_lon = round(max(min_lon, max_lon), 2)

        s_min_lat = max(self.LAT_BOUNDS[0], min(self.LAT_BOUNDS[1], s_min_lat))
        s_max_lat = max(self.LAT_BOUNDS[0], min(self.LAT_BOUNDS[1], s_max_lat))
        s_min_lon = max(self.LON_BOUNDS[0], min(self.LON_BOUNDS[1], s_min_lon))
        s_max_lon = max(self.LON_BOUNDS[0], min(self.LON_BOUNDS[1], s_max_lon))

        # 2. Determine target time with snapping
        target_time_val = self._snap_time(time_str)

        # 3. Intelligent Cache Check (Spatial Subset)
        # We look for any cached entry that FULLY contains the requested region and has <= stride
        for (c_time, c_min_lat, c_max_lat, c_min_lon, c_max_lon, c_stride), points in self.cache_registry.items():
            if c_time == target_time_val and c_stride <= stride:
                # Basic containment check (handling lon wrap if necessary, though here we assume standard [-180, 180])
                if c_min_lat <= s_min_lat and c_max_lat >= s_max_lat and \
                   c_min_lon <= s_min_lon and c_max_lon >= s_max_lon:

                    print(f"[NOAA Cache] Hit (Spatial Subset) from {c_min_lat, c_max_lat, c_min_lon, c_max_lon}")
                    # Filter points within requested viewport
                    subset = [
                        p for p in points
                        if s_min_lat <= p["lat"] <= s_max_lat and s_min_lon <= p["lon"] <= s_max_lon
                    ]
                    # If we have points, return them. If empty, maybe it's all land, but we should return it anyway.
                    return subset

        # 4. Construct the ERDDAP query URL (If cache miss)
        # Syntax: variable[(time)][(lat):stride:(lat)][(lon):stride:(lon)]
        cache_key = (target_time_val, s_min_lat, s_max_lat, s_min_lon, s_max_lon, stride)

        query = (
            f"u_current[{target_time_val}][({s_min_lat}):{stride}:({s_max_lat})][({s_min_lon}):{stride}:({s_max_lon})],"
            f"v_current[{target_time_val}][({s_min_lat}):{stride}:({s_max_lat})][({s_min_lon}):{stride}:({s_max_lon})]"
        )
        url = f"{self.BASE_URL}?{query}"

        print(f"[NOAA Proxy] Cache miss. Requesting: {url}")

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (OCEAN3D; Research-Tool)"
            })
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status != 200:
                    raise Exception(f"NOAA Server returned {response.status}")

                raw_data = response.read().decode('utf-8')
                data = json.loads(raw_data)
                points = self._parse_erddap_json(data)

                # Cache the result
                if points:
                    self.cache_registry[cache_key] = points
                return points
        except Exception as e:
            print(f"[NOAA Proxy Exception] {e}")
            # If (last) fails, it might be a transient error or NOAA is down
            raise e

    def _parse_erddap_json(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parses the ERDDAP .json response table into internal point format."""
        table = data.get("table", {})
        cols = table.get("columnNames", [])
        rows = table.get("rows", [])

        if not rows:
            return []

        try:
            idx_time = cols.index("time")
            idx_lat = cols.index("latitude")
            idx_lon = cols.index("longitude")
            idx_u = cols.index("u_current")
            idx_v = cols.index("v_current")
        except ValueError as e:
            raise Exception(f"Unexpected NOAA data format: {e}")

        points = []
        for row in rows:
            u = row[idx_u]
            v = row[idx_v]
            if u is None or v is None:
                continue

            points.append({
                "time": row[idx_time],
                "lat": float(row[idx_lat]),
                "lon": float(row[idx_lon]),
                "u": float(u),
                "v": float(v)
            })

        return points

noaa_service = NoaaERDDAPService()
