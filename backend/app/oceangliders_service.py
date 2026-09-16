"""
OceanGliders GDAC Service.
Fetches, normalizes, and caches multi-basin glider positions from
the OceanGliders Global Data Assembly Center (hosted at Ifremer/Coriolis).
Dataset: OceanGlidersGDACTrajectories.

Strict isolation: Completely independent from core observations and NOAA test service.
"""

import json
import logging
import os
import ssl
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("oceangliders_service")
logger.setLevel(logging.INFO)


class OceanGlidersService:
    """Service to retrieve normalized OceanGliders GDAC latest positions."""

    CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "cache_oceangliders.json")
    ERDDAP_BASE = "https://erddap.ifremer.fr/erddap/tabledap/OceanGlidersGDACTrajectories.json"
    DATASET_ID = "OceanGlidersGDACTrajectories"
    SOURCE_NAME = "OceanGliders Global Data Assembly Center"
    CACHE_TTL_SECONDS = 3600  # 1 hour

    # Curated benchmark historical deployments across non-operational polar & global basins
    HISTORICAL_BENCHMARKS = [
        "Agathe_575",       # Southern Ocean (Amundsen Sea, Antarctica: -72.55°, -119.41°)
        "Bottlenose_629",   # Southern Ocean (Weddell Sea, Antarctic Peninsula: -63.56°, -52.88°)
        "urd_20221021",     # Arctic / Norwegian Sea: +72.75°, +3.81°
        "sea027_20240316",  # Western Indian Ocean (Mayotte): -12.90°, +45.32°
        "sea042_20220329",  # Western Indian Ocean (Comoros): -12.78°, +45.25°
        "Ziggy_623",        # North Atlantic (Rockall Trough): +56.83°, -9.97°
        "Marlin_505",       # Bay of Bengal / Indian Ocean: +7.90°, +89.10°
        "Bellatrix_555",    # Hebrides / North Atlantic: +56.81°, -6.70°
        "amerigo_20250111", # Mediterranean Sea: +42.84°, +5.31°
        "amadeus_20191123", # Mediterranean Sea: +43.01°, +5.48°
    ]

    def __init__(self) -> None:
        self._memory_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0.0

    def _get_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def get_latest_gliders(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Return cached normalized gliders or fetch from ERDDAP."""
        now = time.time()

        # 1. In-memory cache
        if not force_refresh and self._memory_cache and (now - self._cache_timestamp < self.CACHE_TTL_SECONDS):
            return self._memory_cache

        # 2. Disk cache if memory empty
        if not force_refresh and not self._memory_cache and os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("status") == "READY" and cached.get("gliders"):
                    self._memory_cache = cached
                    self._cache_timestamp = now
                    logger.info("Loaded %d OceanGliders from disk cache", len(cached["gliders"]))
                    return cached
            except Exception as e:
                logger.warning("Failed reading disk cache: %s", e)

        # 3. Live fetch from ERDDAP
        try:
            result = self._fetch_from_erddap()
            if result.get("status") == "READY":
                self._memory_cache = result
                self._cache_timestamp = now
                self._save_to_disk(result)
                return result
        except Exception as e:
            logger.error("Error fetching from OceanGliders ERDDAP: %s", e)

        # 4. Fallback to disk cache if available
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                self._memory_cache = cached
                self._cache_timestamp = now
                logger.warning("Network failed; falling back to existing disk cache.")
                return cached
            except Exception as e:
                logger.error("Disk cache fallback failed: %s", e)

        # 5. Graceful unavailable response (NEVER generate synthetic data)
        return {
            "status": "UNAVAILABLE",
            "source": self.SOURCE_NAME,
            "dataset_id": self.DATASET_ID,
            "message": "OceanGliders data unavailable from upstream ERDDAP.",
            "count": 0,
            "gliders": []
        }

    def _save_to_disk(self, payload: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.CACHE_FILE), exist_ok=True)
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info("Saved %d OceanGliders to disk cache %s", payload.get("count", 0), self.CACHE_FILE)
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
            return "North Atlantic"
        if lat >= 0 and lon < -100.0:
            return "North Pacific"
        if lat < 0 and lon < -20.0:
            return "South Atlantic"
        if lat < 0 and lon < -70.0:
            return "South Pacific"
        return "Atlantic / Global Ocean"

    def _fetch_from_erddap(self) -> Dict[str, Any]:
        """
        Query OceanGliders ERDDAP:
        1. Operational 2026 stream: surface fixes (PRES <= 5 dbar) to capture latest GPS coordinates.
        2. Historical polar & global benchmarks to provide Southern Ocean, Arctic, and Indian Ocean coverage.
        """
        logger.info("Fetching OceanGliders GDAC observations from %s", self.ERDDAP_BASE)
        ctx = self._get_ssl_context()

        # Step 1: Query 2026 operational stream
        query_2026 = (
            "platform_deployment,time,latitude,longitude,PRES,TEMP,PSAL,POSITION_QC,PRES_QC,TEMP_QC,PSAL_QC"
            "&time>=2026-01-01T00:00:00Z&PRES<=5&latitude>=-90&latitude<=90&distinct()"
        )
        url_2026 = f"{self.ERDDAP_BASE}?{urllib.parse.quote(query_2026, safe=',=&')}"

        req_2026 = urllib.request.Request(url_2026, headers={"User-Agent": "Ocean3D-OceanGliders/1.0"})
        with urllib.request.urlopen(req_2026, timeout=45, context=ctx) as resp:
            raw_data = json.loads(resp.read().decode("utf-8"))

        rows_2026 = raw_data.get("table", {}).get("rows", [])
        total_observations = len(rows_2026)
        logger.info("Retrieved %d operational surface observations from 2026", total_observations)

        # Group by platform_deployment and select latest valid fix
        by_deployment: Dict[str, Dict[str, Any]] = {}
        for r in rows_2026:
            dep = r[0]
            t = r[1]
            lat = r[2]
            lon = r[3]
            if lat is None or lon is None or t is None:
                continue
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                continue

            if dep not in by_deployment:
                by_deployment[dep] = {
                    "deployment": dep,
                    "total_fixes": 0,
                    "latest_time": t,
                    "latest_row": r
                }

            by_deployment[dep]["total_fixes"] += 1
            if t > by_deployment[dep]["latest_time"]:
                by_deployment[dep]["latest_time"] = t
                by_deployment[dep]["latest_row"] = r

        # Step 2: Query historical polar & global benchmark deployments
        logger.info("Querying historical polar & global benchmark deployments...")
        for dep in self.HISTORICAL_BENCHMARKS:
            if dep in by_deployment:
                continue
            try:
                url_h = (
                    f"{self.ERDDAP_BASE}?platform_deployment,time,latitude,longitude,PRES,TEMP,PSAL,"
                    f"POSITION_QC,PRES_QC,TEMP_QC,PSAL_QC&platform_deployment=%22{urllib.parse.quote(dep)}%22"
                    f"&orderByMax(%22time%22)"
                )
                req_h = urllib.request.Request(url_h, headers={"User-Agent": "Ocean3D-OceanGliders/1.0"})
                with urllib.request.urlopen(req_h, timeout=8, context=ctx) as r_h:
                    data_h = json.loads(r_h.read().decode("utf-8"))
                    h_rows = data_h.get("table", {}).get("rows", [])
                    if h_rows and h_rows[0][2] is not None and h_rows[0][3] is not None:
                        rec = h_rows[0]
                        total_observations += 1
                        by_deployment[dep] = {
                            "deployment": dep,
                            "total_fixes": 1,
                            "latest_time": rec[1],
                            "latest_row": rec
                        }
            except Exception as e_h:
                logger.debug("Benchmark query failed for %s: %s", dep, e_h)

        # Step 3: Build normalized records
        gliders: List[Dict[str, Any]] = []
        lats: List[float] = []
        lons: List[float] = []
        timestamps: List[str] = []
        basins_found = set()

        for dep, info in sorted(by_deployment.items()):
            r = info["latest_row"]
            dep_id = r[0]
            obs_time = r[1]
            lat = float(r[2])
            lon = float(r[3])

            # Preserve real scientific values; return None if unavailable (NEVER fake 0.0)
            pres = float(r[4]) if r[4] is not None else None
            temp = float(r[5]) if r[5] is not None else None
            psal = float(r[6]) if r[6] is not None else None

            # Preserve QC metadata
            pos_qc = int(r[7]) if r[7] is not None else None
            pres_qc = int(r[8]) if r[8] is not None else None
            temp_qc = int(r[9]) if r[9] is not None else None
            psal_qc = int(r[10]) if r[10] is not None else None

            # Determine operational status based on timestamp
            if obs_time >= "2026-01-01T00:00:00Z":
                status = "Near-Real-Time"
            else:
                status = "Historical Archive"

            basin = self._determine_basin(lat, lon)
            basins_found.add(basin)

            glider_item = {
                "source": self.SOURCE_NAME,
                "dataset_id": self.DATASET_ID,
                "instrument_type": "OceanGliders Global (Test)",
                "deployment_id": dep_id,
                "platform_id": None,      # Real source value: glider_name column not present in this table (do not fabricate)
                "trajectory": None,       # Real source value: distinct trajectory not separated from deployment
                "latitude": round(lat, 5),
                "longitude": round(lon, 5),
                "depth": pres,            # Pressure in dbar corresponds to approx depth in meters
                "temperature": round(temp, 4) if temp is not None else None,
                "salinity": round(psal, 4) if psal is not None else None,
                "timestamp": obs_time,
                "total_fixes": info["total_fixes"],
                "data_status": status,
                "ocean_basin": basin,
                "qc": {
                    "position_qc": pos_qc,
                    "pres_qc": pres_qc,
                    "temp_qc": temp_qc,
                    "psal_qc": psal_qc
                }
            }
            gliders.append(glider_item)
            lats.append(lat)
            lons.append(lon)
            timestamps.append(obs_time)

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
            "dataset_id": self.DATASET_ID,
            "data_status": "Near-Real-Time + Historical Archive",
            "notice": "OceanGliders GDAC multi-basin observations. Not every glider worldwide.",
            "count": len(gliders),
            "total_deployments": len(gliders),
            "total_observations": total_observations,
            "time_range": time_range,
            "bounds": bounds,
            "basins_represented": sorted(list(basins_found)),
            "gliders": gliders
        }


oceangliders_service = OceanGlidersService()
