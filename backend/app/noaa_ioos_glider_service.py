"""
NOAA/IOOS Operational Glider Service.
Fetches, normalizes, and caches real-time and recent autonomous glider deployments
from the U.S. IOOS Glider Data Assembly Center (DAC):
Registry API: https://gliders.ioos.us/providers/api/deployment
ERDDAP Endpoints: https://gliders.ioos.us/erddap/tabledap/{dataset_id}.json

Strict isolation: Completely independent from NOAA/AOML historical layer and OceanGliders Global.
"""

from __future__ import annotations
import os
import json
import ssl
import time
import urllib.parse
import urllib.request
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("noaa_ioos_glider_service")
logger.setLevel(logging.INFO)


class NoaaIoosGliderService:
    REGISTRY_URL = "https://gliders.ioos.us/providers/api/deployment"
    CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "cache_noaa_ioos_gliders.json")
    CACHE_TTL_SECONDS = 3600  # 1 hour
    SOURCE_NAME = "U.S. IOOS National Glider Data Assembly Center"

    def __init__(self) -> None:
        self._memory_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0.0
        self.status = "INITIALIZING"
        self.last_error: Optional[str] = None

    def _get_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def get_latest_gliders(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Return cached normalized NOAA/IOOS gliders or fetch from IOOS registry & ERDDAP."""
        now = time.time()

        if not force_refresh and self._memory_cache and (now - self._cache_timestamp < self.CACHE_TTL_SECONDS):
            return self._memory_cache

        if not force_refresh and not self._memory_cache and os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("status") == "READY" and cached.get("gliders"):
                    self._memory_cache = cached
                    self._cache_timestamp = now
                    self.status = "READY"
                    logger.info("Loaded %d NOAA/IOOS gliders from disk cache", len(cached["gliders"]))
                    return cached
            except Exception as e:
                logger.warning("Failed reading disk cache: %s", e)

        try:
            result = self._fetch_from_ioos()
            if result.get("status") == "READY":
                self._memory_cache = result
                self._cache_timestamp = now
                self.status = "READY"
                self.last_error = None
                self._save_to_disk(result)
                return result
        except Exception as e:
            self.status = "ERROR"
            self.last_error = str(e)
            logger.error("Error fetching from IOOS Glider DAC: %s", e)

        # Fallback to disk cache if available
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                self._memory_cache = cached
                self._cache_timestamp = now
                logger.warning("Network failed; falling back to existing IOOS disk cache.")
                return cached
            except Exception as e:
                logger.error("Disk cache fallback failed: %s", e)

        # Graceful unavailable response (NEVER generate synthetic data)
        return {
            "status": "UNAVAILABLE",
            "source": self.SOURCE_NAME,
            "dataset_id": "ioos_glider_dac_deployments",
            "message": f"NOAA/IOOS glider data unavailable: {self.last_error or 'Connection failed'}",
            "count": 0,
            "gliders": []
        }

    def _save_to_disk(self, payload: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.CACHE_FILE), exist_ok=True)
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info("Saved %d NOAA/IOOS gliders to disk cache %s", payload.get("count", 0), self.CACHE_FILE)
        except Exception as e:
            logger.warning("Could not write disk cache: %s", e)

    def _determine_basin(self, lat: float, lon: float) -> str:
        """Helper to classify geographic ocean basin for UI display."""
        if lat < -60.0:
            return "Southern Ocean / Antarctica"
        if lat > 66.0:
            return "Arctic / Nordic Seas"
        if 30.0 <= lat <= 46.0 and -6.0 <= lon <= 36.0:
            return "Mediterranean Sea"
        if -30.0 <= lat <= 30.0 and 35.0 <= lon <= 105.0:
            return "Indian Ocean"
        if lat >= 0 and lon < -60.0:
            if lon < -100.0:
                return "North Pacific"
            return "North Atlantic"
        if lat < 0 and lon < -20.0:
            if lon < -70.0:
                return "South Pacific"
            return "South Atlantic"
        if lat >= 0 and lon >= 100.0:
            return "North Pacific"
        return "Atlantic / Global Ocean"

    def _query_deployment_latest(self, dep: Dict[str, Any], ctx: ssl.SSLContext) -> Optional[Dict[str, Any]]:
        """Query individual IOOS deployment ERDDAP endpoint for minimum required latest observation."""
        erddap_url = dep.get("erddap")
        if not erddap_url:
            return None

        # Convert HTML endpoint to JSON endpoint
        json_url = erddap_url.replace(".html", ".json")
        t_14d = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT00:00:00Z")
        query_url = f"{json_url}?time,latitude,longitude,depth,pressure,temperature,salinity&time>={t_14d}"

        try:
            req = urllib.request.Request(query_url, headers={"User-Agent": "Ocean3D-NOAA-IOOS/1.0"})
            with urllib.request.urlopen(req, timeout=9, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            table = data.get("table", {})
            cols = table.get("columnNames", [])
            rows = table.get("rows", [])
            if not rows:
                return None

            col_map = {name: idx for idx, name in enumerate(cols)}
            # Take the latest row (last row in time order)
            row = rows[-1]

            t_val = row[col_map.get("time", 0)] if "time" in col_map else None
            lat_val = row[col_map.get("latitude", 1)] if "latitude" in col_map else None
            lon_val = row[col_map.get("longitude", 2)] if "longitude" in col_map else None

            if t_val is None or lat_val is None or lon_val is None:
                return None

            lat = float(lat_val)
            lon = float(lon_val)
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                return None

            depth = float(row[col_map["depth"]]) if "depth" in col_map and row[col_map["depth"]] is not None else None
            pres = float(row[col_map["pressure"]]) if "pressure" in col_map and row[col_map["pressure"]] is not None else None
            temp = float(row[col_map["temperature"]]) if "temperature" in col_map and row[col_map["temperature"]] is not None else None
            sal = float(row[col_map["salinity"]]) if "salinity" in col_map and row[col_map["salinity"]] is not None else None

            return {
                "time": t_val,
                "latitude": round(lat, 5),
                "longitude": round(lon, 5),
                "depth": depth,
                "pressure": pres,
                "temperature": round(temp, 4) if temp is not None else None,
                "salinity": round(sal, 4) if sal is not None else None
            }
        except Exception as e:
            logger.debug("Failed querying ERDDAP for deployment %s: %s", dep.get("name"), e)
            return None

    def _fetch_from_ioos(self) -> Dict[str, Any]:
        """
        1. Fetch deployment registry from https://gliders.ioos.us/providers/api/deployment
        2. Filter candidates (completed == false or recently updated).
        3. Query ERDDAP endpoints with bounded concurrency (max 8 workers, 9s timeout).
        4. Apply 30-day window and ACTIVE/NRT vs RECENT classification.
        5. Deduplicate by glider_name (keeping deployment with newest valid observation).
        """
        logger.info("Fetching NOAA/IOOS deployment registry from %s", self.REGISTRY_URL)
        ctx = self._get_ssl_context()

        req = urllib.request.Request(self.REGISTRY_URL, headers={"User-Agent": "Ocean3D-NOAA-IOOS/1.0"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            registry = json.loads(resp.read().decode("utf-8"))

        if isinstance(registry, dict) and "results" in registry:
            registry = registry["results"]

        if not isinstance(registry, list):
            raise ValueError("IOOS deployment registry returned unexpected format.")

        now_utc = datetime.now(timezone.utc)
        cutoff_30d = now_utc - timedelta(days=30)

        # Filter candidate deployments: completed == false or recently updated
        candidates = []
        for d in registry:
            completed = d.get("completed", True)
            erddap = d.get("erddap")
            if not erddap:
                continue
            # If completed is false or updated within last 60 days
            updated_str = d.get("updated")
            is_recent_meta = False
            if updated_str:
                try:
                    dt_up = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                    if dt_up >= now_utc - timedelta(days=60):
                        is_recent_meta = True
                except Exception:
                    pass

            if not completed or is_recent_meta:
                candidates.append(d)

        logger.info("Found %d candidate operational/recent deployments from registry (out of %s total)", len(candidates), len(registry))

        # Query ERDDAP endpoints concurrently with bounded workers (max 8)
        raw_results: List[Dict[str, Any]] = []
        max_workers = min(8, len(candidates)) if candidates else 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_dep = {executor.submit(self._query_deployment_latest, dep, ctx): dep for dep in candidates}
            for future in as_completed(future_to_dep):
                dep = future_to_dep[future]
                try:
                    res = future.result()
                    if res:
                        # Parse timestamp
                        t_str = res["time"]
                        try:
                            t_dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                        except Exception:
                            continue

                        # Apply 30-day window filter
                        if t_dt >= cutoff_30d:
                            # Classify operational status
                            age_days = (now_utc - t_dt).days
                            if age_days <= 7:
                                status_label = "ACTIVE / NRT"
                            else:
                                status_label = "RECENT"

                            raw_results.append({
                                "dep_meta": dep,
                                "obs": res,
                                "datetime": t_dt,
                                "status_label": status_label
                            })
                except Exception as e:
                    logger.debug("Error processing deployment %s: %s", dep.get("name"), e)

        logger.info("Retrieved %d valid observations within 30-day window", len(raw_results))

        # Deduplicate by physical platform id (glider_name); keep newest observation per glider_name
        by_glider: Dict[str, Dict[str, Any]] = {}
        for item in raw_results:
            dep = item["dep_meta"]
            glider_name = dep.get("glider_name")
            # Fallback identity if glider_name is missing
            platform_id = glider_name if glider_name else None
            key = glider_name if glider_name else dep.get("name", "unknown")

            if key not in by_glider:
                by_glider[key] = item
            else:
                # Keep the one with the newer timestamp
                if item["datetime"] > by_glider[key]["datetime"]:
                    by_glider[key] = item

        # Build final normalized markers
        gliders: List[Dict[str, Any]] = []
        lats: List[float] = []
        lons: List[float] = []
        timestamps: List[str] = []
        basins_found = set()

        for key, item in sorted(by_glider.items()):
            dep = item["dep_meta"]
            obs = item["obs"]
            dt = item["datetime"]
            status_label = item["status_label"]

            lat = obs["latitude"]
            lon = obs["longitude"]
            basin = self._determine_basin(lat, lon)
            basins_found.add(basin)

            glider_item = {
                "source": self.SOURCE_NAME,
                "dataset_id": dep.get("name"),
                "instrument_type": "NOAA/IOOS Operational Gliders",
                "platform_id": dep.get("glider_name"),  # Real source glider_name or null
                "deployment_id": dep.get("name"),
                "wmo_id": dep.get("wmo_id"),
                "operator": dep.get("operator"),
                "latitude": lat,
                "longitude": lon,
                "timestamp": dt.isoformat().replace("+00:00", "Z"),
                "depth": obs.get("depth"),
                "pressure": obs.get("pressure"),
                "temperature": obs.get("temperature"),
                "salinity": obs.get("salinity"),
                "completed": dep.get("completed"),
                "delayed_mode": dep.get("delayed_mode"),
                "status": status_label,
                "ocean_basin": basin,
                "qc": {
                    "position_qc": None,
                    "temp_qc": None,
                    "sal_qc": None
                },
                "source_url": dep.get("erddap")
            }
            gliders.append(glider_item)
            lats.append(lat)
            lons.append(lon)
            timestamps.append(dt.isoformat().replace("+00:00", "Z"))

        bounds = {
            "min_lat": min(lats) if lats else 0.0,
            "max_lat": max(lats) if lats else 0.0,
            "min_lon": min(lons) if lons else 0.0,
            "max_lon": max(lons) if lons else 0.0
        }
        time_range = {
            "start": min(timestamps) if timestamps else "",
            "end": max(timestamps) if timestamps else ""
        }

        return {
            "status": "READY",
            "source": self.SOURCE_NAME,
            "dataset_id": "ioos_glider_dac_deployments",
            "data_status": "Near-Real-Time + Recent Operational",
            "notice": "U.S. IOOS Glider DAC operational telemetry (active/recent within 30 days).",
            "count": len(gliders),
            "registered_deployments_total": len(registry),
            "candidates_evaluated": len(candidates),
            "recent_valid_deployments": len(raw_results),
            "unique_physical_gliders": len(gliders),
            "time_range": time_range,
            "bounds": bounds,
            "basins_represented": sorted(list(basins_found)),
            "gliders": gliders
        }


noaa_ioos_glider_service = NoaaIoosGliderService()
