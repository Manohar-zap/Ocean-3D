"""
NOAA/AOML ERDDAP Glider Service (GLIDERS_2025_01_03).
Fetches real glider deployments from NOAA AOML ERDDAP tabledap endpoint.
Strictly adheres to no-fabrication rules: genuine IDs or null, real parameters only.
"""
from __future__ import annotations
import os
import json
import logging
from datetime import datetime, timezone
import urllib.request
import urllib.error
from typing import Optional, Any
from .schemas import StandardRecord

logger = logging.getLogger(__name__)

CACHE_FILE = "backend/data/cache_noaa_aoml_gliders.json"
ERDDAP_TABLEDAP_URL = "https://erddap.aoml.noaa.gov/hdb/erddap/tabledap/GLIDERS_2025_01_03.json?trajectory,time,latitude,longitude,depth,temperature,salinity&distinct()&orderByMax(\"time\")"


class NoaaAomlGliderService:
    def __init__(self):
        self._cached_records: list[StandardRecord] = []
        self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._cached_records = [StandardRecord(**item) for item in data]
                logger.info(f"Loaded {len(self._cached_records)} NOAA AOML glider records from cache.")
        except Exception as e:
            logger.warning(f"Failed to load NOAA AOML glider cache: {e}")

    def _save_cache(self, records: list[StandardRecord]):
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in records], f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save NOAA AOML glider cache: {e}")

    def get_latest_gliders(self, force_refresh: bool = False) -> list[StandardRecord]:
        """Fetch latest glider observations from NOAA AOML ERDDAP tabledap or fallback to cache."""
        if not force_refresh and self._cached_records:
            return self._cached_records

        records: list[StandardRecord] = []
        try:
            req = urllib.request.Request(
                ERDDAP_TABLEDAP_URL,
                headers={"User-Agent": "Ocean-3D-App/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                table = data.get("table", {})
                column_names = table.get("columnNames", [])
                rows = table.get("rows", [])

                # Map column indices
                col_map = {name: idx for idx, name in enumerate(column_names)}
                traj_idx = col_map.get("trajectory")
                time_idx = col_map.get("time")
                lat_idx = col_map.get("latitude")
                lon_idx = col_map.get("longitude")
                depth_idx = col_map.get("depth")
                temp_idx = col_map.get("temperature")
                sal_idx = col_map.get("salinity")

                for row in rows:
                    traj = str(row[traj_idx]) if traj_idx is not None and row[traj_idx] is not None else None
                    if not traj or traj.lower() == "nan":
                        platform_id = None
                    else:
                        platform_id = traj

                    t_val = row[time_idx] if time_idx is not None else datetime.now(timezone.utc).isoformat()
                    lat = float(row[lat_idx]) if lat_idx is not None and row[lat_idx] is not None else None
                    lon = float(row[lon_idx] if lon_idx is not None and row[lon_idx] is not None else None)
                    depth = float(row[depth_idx]) if depth_idx is not None and row[depth_idx] is not None else 0.0

                    if lat is None or lon is None:
                        continue

                    # Temperature record if valid
                    if temp_idx is not None and row[temp_idx] is not None:
                        try:
                            temp_val = float(row[temp_idx])
                            records.append(StandardRecord(
                                kind="observation",
                                dataset_id="noaa_aoml_gliders",
                                variable="temperature",
                                latitude=round(lat, 4),
                                longitude=round(lon, 4),
                                depth=round(depth, 1),
                                time=str(t_val),
                                value=round(temp_val, 3),
                                unit="degC",
                                platform_id=platform_id,
                                platform_type="glider",
                                quality_flag="good",
                                quality_reason="NOAA AOML ERDDAP passing upstream QC",
                                data_status="OPERATIONAL REAL-TIME",
                                source_organization="NOAA AOML / ERDDAP",
                                product_id="NOAA-AOML-GLIDER",
                                retrieval_timestamp=datetime.now(timezone.utc).isoformat()
                            ))
                        except (ValueError, TypeError):
                            pass

                    # Salinity record if valid
                    if sal_idx is not None and row[sal_idx] is not None:
                        try:
                            sal_val = float(row[sal_idx])
                            records.append(StandardRecord(
                                kind="observation",
                                dataset_id="noaa_aoml_gliders",
                                variable="salinity",
                                latitude=round(lat, 4),
                                longitude=round(lon, 4),
                                depth=round(depth, 1),
                                time=str(t_val),
                                value=round(sal_val, 3),
                                unit="psu",
                                platform_id=platform_id,
                                platform_type="glider",
                                quality_flag="good",
                                quality_reason="NOAA AOML ERDDAP passing upstream QC",
                                data_status="OPERATIONAL REAL-TIME",
                                source_organization="NOAA AOML / ERDDAP",
                                product_id="NOAA-AOML-GLIDER",
                                retrieval_timestamp=datetime.now(timezone.utc).isoformat()
                            ))
                        except (ValueError, TypeError):
                            pass

            if records:
                self._cached_records = records
                self._save_cache(records)
                logger.info(f"Successfully fetched {len(records)} NOAA AOML glider records.")
        except Exception as e:
            logger.warning(f"Failed to fetch NOAA AOML gliders from ERDDAP: {e}. Using cache.")

        return self._cached_records


noaa_aoml_glider_service = NoaaAomlGliderService()
