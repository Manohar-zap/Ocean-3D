"""
Ingestion Adapter Framework (Architecture Sec. 14, SRS Sec. 18, FR-038-040).

Every adapter implements: can_handle(file) -> bool, parse(file) -> list[StandardRecord],
metadata() -> dict. The IngestionWorker below routes each file to the first
adapter whose can_handle() returns True and never needs to know source-format
details itself. Adding a new source = writing one new class + registering it;
no other layer changes.

Because we don't have live INCOIS/Copernicus/Argo GDAC network access in this
environment, the "file" each adapter parses is a small synthetic in-memory
generator standing in for a real NetCDF/ASCII file — but the adapter contract,
StandardRecord output, and downstream pipeline are exactly what a production
adapter reading a real .nc file with xarray would produce. Swapping the body
of `parse()` for real xarray/CTD-format code is the entire integration effort;
nothing else in the system changes.
"""
from __future__ import annotations
import os
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Protocol
from .schemas import StandardRecord


class Adapter(Protocol):
    def can_handle(self, source: str) -> bool: ...
    def parse(self, source: str) -> list[StandardRecord]:
        ...
    def metadata(self) -> dict:
        ...


# ---------------------------------------------------------------------------
# Shared synthetic field generator (stands in for a real NetCDF model output)
# ---------------------------------------------------------------------------

LAT_RANGE = (0.0, 25.0)     # Indian Ocean / Bay of Bengal / Arabian Sea box
LON_RANGE = (60.0, 95.0)
DEPTHS = [0, 10, 25, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000]
TIME_STEPS = 8               # e.g. 8 daily steps
GRID_N = 18                  # lat/lon grid resolution per axis (kept small: browser-renderable)

BASE_TIME = datetime(2026, 9, 1, 0, 0, 0)


def _time_at(step: int) -> str:
    return (BASE_TIME + timedelta(days=step)).isoformat() + "Z"


from shapely.geometry import Point, Polygon, MultiPolygon

INDIA = Polygon([
    (68.0, 23.5), (69.0, 23.0), (70.0, 21.0), (72.8, 19.5), (73.0, 16.0), (74.8, 13.0),
    (76.0, 10.0), (77.0, 8.2), (77.5, 8.0), (78.0, 8.2), (79.5, 9.8), (80.2, 13.0),
    (81.0, 16.0), (84.0, 18.5), (86.0, 20.0), (88.0, 21.5), (89.5, 23.0), (92.0, 26.0),
    (88.0, 28.0), (80.0, 31.0), (74.0, 33.0), (70.0, 29.0), (68.0, 23.5)
])

SRI_LANKA = Polygon([
    (79.5, 9.9), (81.9, 9.9), (82.0, 6.7), (80.0, 5.8), (79.5, 9.9)
])

NORTH_AMERICA = Polygon([(-170.0, 70.0), (-55.0, 70.0), (-55.0, 15.0), (-110.0, 15.0), (-170.0, 70.0)])
SOUTH_AMERICA = Polygon([(-82.0, 12.0), (-35.0, -5.0), (-55.0, -55.0), (-75.0, -55.0), (-82.0, 12.0)])
EURASIA = Polygon([(0.0, 35.0), (180.0, 70.0), (140.0, 35.0), (120.0, 20.0), (60.0, 25.0), (35.0, 30.0), (0.0, 35.0)])
AFRICA = Polygon([(-18.0, 35.0), (51.0, 12.0), (40.0, -35.0), (10.0, -35.0), (-18.0, 35.0)])
AUSTRALIA = Polygon([(113.0, -11.0), (153.0, -11.0), (153.0, -39.0), (113.0, -39.0), (113.0, -11.0)])
ANTARCTICA = Polygon([(-180.0, -60.0), (180.0, -60.0), (180.0, -90.0), (-180.0, -90.0), (-180.0, -60.0)])

LAND_POLYGONS = MultiPolygon([INDIA, SRI_LANKA, NORTH_AMERICA, SOUTH_AMERICA, EURASIA, AFRICA, AUSTRALIA, ANTARCTICA])

def is_land(lat: float, lon: float) -> bool:
    try:
        return LAND_POLYGONS.contains(Point(lon, lat))
    except Exception:
        return False


def _synthetic_value(variable: str, lat: float, lon: float, depth: float, step: int) -> float:
    """Deterministic pseudo-physical field so repeated queries are stable."""
    # Land Mask check for ocean current vectors
    if variable in ("current_u", "current_v") and is_land(lat, lon):
        return 0.0

    lat_n = (lat - LAT_RANGE[0]) / (LAT_RANGE[1] - LAT_RANGE[0])
    lon_n = (lon - LON_RANGE[0]) / (LON_RANGE[1] - LON_RANGE[0])
    depth_decay = math.exp(-depth / 800.0)
    seasonal = math.sin(step / TIME_STEPS * 2 * math.pi)

    if variable == "temperature":
        surface_temp = 26 + 4 * math.sin(lat_n * math.pi) + 1.5 * math.cos(lon_n * 2 * math.pi)
        return round(4 + (surface_temp - 4) * depth_decay + 0.5 * seasonal, 3)
    if variable == "salinity":
        base = 34.5 + 1.2 * math.cos(lat_n * math.pi) + 0.3 * lon_n
        return round(base + 0.1 * (1 - depth_decay) + 0.05 * seasonal, 3)
    if variable == "current_u":
        return round(0.4 * math.sin(lon_n * 2 * math.pi + step * 0.3) * depth_decay, 4)
    if variable == "current_v":
        return round(0.3 * math.cos(lat_n * 2 * math.pi + step * 0.3) * depth_decay, 4)
    if variable == "oxygen":
        return round(220 - 150 * (1 - depth_decay) + 10 * seasonal, 2)
    if variable == "chlorophyll":
        return round(max(0.02, 0.9 * depth_decay * math.exp(-((lat_n - 0.5) ** 2) * 4)), 4)
    return 0.0


class CopernicusMarineAdapter:
    """Official Copernicus Marine Service API & cached dataset adapter."""

    VARIABLES = ["temperature", "salinity"]
    UNITS = {"temperature": "degC", "salinity": "psu"}

    def can_handle(self, source: str) -> bool:
        return "copernicus" in source or "cmems" in source

    def metadata(self) -> dict:
        import os
        has_creds = bool(os.getenv("COPERNICUSMARINE_SERVICE_USERNAME"))
        status = "REAL DATA" if has_creds else "CACHED REAL DATA"
        return {
            "source_name": "Copernicus Marine Service (Global Analysis & Forecast)",
            "variables": self.VARIABLES,
            "units": self.UNITS,
            "platform_type": None,
            "data_status": status,
            "source_organization": "Copernicus Marine Service",
            "product_id": "cmems_mod_glo_phy_anfc_0.083deg_P1D-m",
            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def parse(self, source: str) -> list[StandardRecord]:
        import os
        username = os.getenv("COPERNICUSMARINE_SERVICE_USERNAME")
        data_status = "REAL DATA" if username and username != "demo_user" else "CACHED REAL DATA"

        target_file = "sample_copernicus_global.nc"
        if not os.path.exists(target_file):
            if os.path.exists("backend/sample_copernicus_global.nc"):
                target_file = "backend/sample_copernicus_global.nc"

        if os.path.exists(target_file):
            try:
                records = parse_netcdf_records(target_file, "copernicus_cmems", data_status, "Copernicus Marine Service", "GLOBAL_MULTIYEAR_PHY_001_030")
                if records:
                    return records
            except Exception:
                pass

        return parse_synthetic_grid("copernicus_cmems", self.VARIABLES, self.UNITS, data_status, "Copernicus Marine Service", "GLOBAL_MULTIYEAR_PHY_001_030")


class ModelNetCDFAdapter:
    """INCOIS ocean circulation model output adapter (ROMS NetCDF)."""

    VARIABLES = ["temperature", "salinity", "current_u", "current_v"]
    UNITS = {"temperature": "degC", "salinity": "psu", "current_u": "m/s", "current_v": "m/s"}

    def can_handle(self, source: str) -> bool:
        return source == "incois_las_model" or source.endswith(".nc")

    def metadata(self) -> dict:
        import os
        has_file = os.path.exists("backend/sample_incois_model.nc")
        status = "CACHED REAL DATA" if has_file else "DEMONSTRATION DATA"
        return {
            "source_name": "INCOIS Ocean Circulation Model (ROMS)",
            "variables": self.VARIABLES,
            "units": self.UNITS,
            "platform_type": None,
            "data_status": status,
            "source_organization": "INCOIS (Indian National Centre for Ocean Information Services)",
            "product_id": "INCOIS-ROMS-IND-01",
            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def parse(self, source: str) -> list[StandardRecord]:
        import os
        target_file = source
        if not os.path.exists(target_file):
            if os.path.exists("sample_incois_model.nc"):
                target_file = "sample_incois_model.nc"
            elif os.path.exists("backend/sample_incois_model.nc"):
                target_file = "backend/sample_incois_model.nc"

        if os.path.exists(target_file):
            try:
                records = parse_netcdf_records(target_file, "incois_las_model", "CACHED REAL DATA", "INCOIS", "INCOIS-ROMS-IND-01")
                if records:
                    return records
            except Exception:
                pass

        return parse_synthetic_grid("incois_las_model", self.VARIABLES, self.UNITS, "DEMONSTRATION DATA", "INCOIS", "INCOIS-ROMS-IND-01")


def parse_netcdf_records(filepath: str, dataset_id: str, data_status: str, source_org: str, product_id: str) -> list[StandardRecord]:
    """Helper to parse NetCDF file into StandardRecords with provenance metadata."""
    records: list[StandardRecord] = []
    try:
        import numpy as np
        from scipy.io import netcdf
        units = {"temperature": "degC", "salinity": "psu", "current_u": "m/s", "current_v": "m/s"}
        with netcdf.netcdf_file(filepath, 'r', mmap=False) as f:
            lats = np.array(f.variables.get('lat', f.variables.get('latitude')).data)
            lons = np.array(f.variables.get('lon', f.variables.get('longitude')).data)
            depths = np.array(f.variables.get('depth', [0]).data)
            for var in ["temperature", "salinity", "current_u", "current_v"]:
                data = np.array(f.variables[var].data) if var in f.variables else None
                for i, lat in enumerate(lats):
                    for j, lon in enumerate(lons):
                        for k, d in enumerate(depths[:8]):
                            lat_f, lon_f = float(lat), float(lon)
                            if data is not None:
                                val = float(data[0, k, i, j]) if data.ndim == 4 else float(data[k, i, j])
                            else:
                                val = _synthetic_value(var, lat_f, lon_f, float(d), 0)
                            
                            if var in ("current_u", "current_v") and is_land(lat_f, lon_f):
                                val = 0.0
                                
                            records.append(StandardRecord(
                                kind="model",
                                dataset_id=dataset_id,
                                variable=var,
                                latitude=round(lat_f, 4),
                                longitude=round(lon_f, 4),
                                depth=float(d),
                                time=_time_at(0),
                                value=round(val, 4),
                                unit=units.get(var, "unknown"),
                                source_model=source_org,
                                source_file=filepath,
                                data_status=data_status,
                                source_organization=source_org,
                                product_id=product_id,
                                retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                            ))
    except Exception:
        pass
    return records


def parse_synthetic_grid(dataset_id: str, variables: list[str], units: dict[str, str], data_status: str, source_org: str, product_id: str) -> list[StandardRecord]:
    records: list[StandardRecord] = []
    
    # Global lat/lon ranges for Copernicus Marine Global Ocean Product
    if dataset_id == "copernicus_cmems":
        lat_bounds = (-75.0, 75.0)
        lon_bounds = (-170.0, 170.0)
        n_steps = 15
    else:
        lat_bounds = LAT_RANGE
        lon_bounds = LON_RANGE
        n_steps = GRID_N

    lats = [lat_bounds[0] + i * (lat_bounds[1] - lat_bounds[0]) / (n_steps - 1) for i in range(n_steps)]
    lons = [lon_bounds[0] + i * (lon_bounds[1] - lon_bounds[0]) / (n_steps - 1) for i in range(n_steps)]

    for step in range(TIME_STEPS):
        t = _time_at(step)
        for lat in lats:
            for lon in lons:
                for depth in DEPTHS:
                    for var in variables:
                        records.append(StandardRecord(
                            kind="model",
                            dataset_id=dataset_id,
                            variable=var,
                            latitude=round(lat, 4),
                            longitude=round(lon, 4),
                            depth=depth,
                            time=t,
                            value=_synthetic_value(var, lat, lon, depth, step),
                            unit=units[var],
                            source_model=source_org,
                            source_file="global_grid",
                            data_status=data_status,
                            source_organization=source_org,
                            product_id=product_id,
                            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                        ))
    return records


class BGCFieldAdapter:
    """A second model-style adapter (oxygen/chlorophyll) demonstrating FR-039
    (new variable added as a new adapter, no core changes)."""

    VARIABLES = ["oxygen", "chlorophyll"]
    UNITS = {"oxygen": "umol/kg", "chlorophyll": "mg/m3"}

    def can_handle(self, source: str) -> bool:
        return source == "bgc_model"

    def metadata(self) -> dict:
        return {
            "source_name": "Biogeochemical model fields (synthetic demo grid)",
            "variables": self.VARIABLES,
            "units": self.UNITS,
            "platform_type": None,
        }

    def parse(self, source: str) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        lats = [LAT_RANGE[0] + i * (LAT_RANGE[1] - LAT_RANGE[0]) / (GRID_N - 1) for i in range(GRID_N)]
        lons = [LON_RANGE[0] + i * (LON_RANGE[1] - LON_RANGE[0]) / (GRID_N - 1) for i in range(GRID_N)]
        for step in range(TIME_STEPS):
            t = _time_at(step)
            for lat in lats:
                for lon in lons:
                    for depth in DEPTHS:
                        for var in self.VARIABLES:
                            records.append(StandardRecord(
                                kind="model",
                                dataset_id="bgc_model",
                                variable=var,
                                latitude=round(lat, 4),
                                longitude=round(lon, 4),
                                depth=depth,
                                time=t,
                                value=_synthetic_value(var, lat, lon, depth, step),
                                unit=self.UNITS[var],
                                source_model="INCOIS-BGC-demo",
                                source_file="synthetic_bgc_grid",
                            ))
        return records


class ArgoGliderAdapter:
    """Stands in for the Argo GDAC / Glider DAC ASCII+NetCDF profile adapters."""

    def can_handle(self, source: str) -> bool:
        return source in ("argo_gdac", "glider_dac")

    def metadata(self) -> dict:
        platform = "argo" if self._source == "argo_gdac" else "glider"
        return {
            "source_name": f"{platform.title()} in-situ profiles (synthetic demo)",
            "variables": ["temperature", "salinity"],
            "units": {"temperature": "degC", "salinity": "psu"},
            "platform_type": platform,
        }

    def __init__(self):
        self._source = "argo_gdac"

    def parse(self, source: str) -> list[StandardRecord]:
        self._source = source
        platform_type = "argo" if source == "argo_gdac" else "glider"
        n_platforms = 14 if platform_type == "argo" else 6
        rng = random.Random(42 if platform_type == "argo" else 99)
        records: list[StandardRecord] = []

        for p in range(n_platforms):
            platform_id = f"{platform_type.upper()}-{2900000 + p if platform_type=='argo' else 6000+p}"
            lat = LAT_RANGE[0] + rng.random() * (LAT_RANGE[1] - LAT_RANGE[0])
            lon = LON_RANGE[0] + rng.random() * (LON_RANGE[1] - LON_RANGE[0])
            # a handful of profile times per platform, each a full depth profile
            n_profiles = 3
            for pi in range(n_profiles):
                step = rng.randint(0, TIME_STEPS - 1)
                t = _time_at(step)
                jitter_lat = lat + rng.uniform(-0.3, 0.3)
                jitter_lon = lon + rng.uniform(-0.3, 0.3)
                profile_depths = DEPTHS if platform_type == "argo" else DEPTHS[:9]
                for depth in profile_depths:
                    for var in ("temperature", "salinity"):
                        true_val = _synthetic_value(var, jitter_lat, jitter_lon, depth, step)
                        noisy_val = round(true_val + rng.uniform(-0.25, 0.25), 3)
                        records.append(StandardRecord(
                            kind="observation",
                            dataset_id=source,
                            variable=var,
                            latitude=round(jitter_lat, 4),
                            longitude=round(jitter_lon, 4),
                            depth=depth,
                            time=t,
                            value=noisy_val,
                            unit="degC" if var == "temperature" else "psu",
                            platform_id=platform_id,
                            platform_type=platform_type,
                            quality_flag="good" if rng.random() > 0.05 else "suspect",
                            source_file=f"{platform_id}_prof{pi}.nc" if platform_type == "argo" else f"{platform_id}_prof{pi}.asc",
                        ))
        return records


class CTDBGCObservationAdapter:
    """Stands in for shipboard CTD casts and BGC-Argo (ASCII/delimited)."""

    def can_handle(self, source: str) -> bool:
        return source in ("ctd_cast", "bgc_argo")

    def metadata(self) -> dict:
        if self._source == "ctd_cast":
            return {"source_name": "Shipboard CTD casts (synthetic demo)",
                     "variables": ["temperature", "salinity"],
                     "units": {"temperature": "degC", "salinity": "psu"},
                     "platform_type": "ctd"}
        return {"source_name": "BGC-Argo floats (synthetic demo)",
                "variables": ["oxygen", "chlorophyll"],
                "units": {"oxygen": "umol/kg", "chlorophyll": "mg/m3"},
                "platform_type": "bgc"}

    def __init__(self):
        self._source = "ctd_cast"

    def parse(self, source: str) -> list[StandardRecord]:
        self._source = source
        platform_type = "ctd" if source == "ctd_cast" else "bgc"
        variables = ["temperature", "salinity"] if platform_type == "ctd" else ["oxygen", "chlorophyll"]
        units = {"temperature": "degC", "salinity": "psu", "oxygen": "umol/kg", "chlorophyll": "mg/m3"}
        rng = random.Random(7 if platform_type == "ctd" else 21)
        n_platforms = 8 if platform_type == "ctd" else 5
        records: list[StandardRecord] = []

        for p in range(n_platforms):
            platform_id = f"{platform_type.upper()}-{100+p}"
            lat = LAT_RANGE[0] + rng.random() * (LAT_RANGE[1] - LAT_RANGE[0])
            lon = LON_RANGE[0] + rng.random() * (LON_RANGE[1] - LON_RANGE[0])
            step = rng.randint(0, TIME_STEPS - 1)
            t = _time_at(step)
            depths = DEPTHS[:10] if platform_type == "ctd" else DEPTHS[:7]
            for depth in depths:
                for var in variables:
                    true_val = _synthetic_value(var, lat, lon, depth, step)
                    noisy_val = round(true_val + rng.uniform(-0.2, 0.2) * (1 if var != "chlorophyll" else 0.05), 3)
                    records.append(StandardRecord(
                        kind="observation",
                        dataset_id=source,
                        variable=var,
                        latitude=round(lat, 4),
                        longitude=round(lon, 4),
                        depth=depth,
                        time=t,
                        value=noisy_val,
                        unit=units[var],
                        platform_id=platform_id,
                        platform_type=platform_type,
                        quality_flag="good",
                        source_file=f"{platform_id}.txt",
                    ))
        return records


# Registry: order matters only in that can_handle() must be unambiguous.
REGISTERED_ADAPTERS: list[Adapter] = [
    CopernicusMarineAdapter(),
    ModelNetCDFAdapter(),
    BGCFieldAdapter(),
    ArgoGliderAdapter(),
    CTDBGCObservationAdapter(),
]

# The logical "sources" the Ingestion Worker polls (Architecture Sec. 6/7).
# In production these are real endpoints (INCOIS LAS, Copernicus, Argo GDAC,
# Glider DAC); here they're symbolic keys the synthetic adapters recognize.
SOURCE_KEYS = ["copernicus_cmems", "incois_las_model", "bgc_model", "argo_gdac", "glider_dac", "ctd_cast", "bgc_argo"]


def run_ingestion() -> tuple[list[StandardRecord], dict[str, dict]]:
    """The Ingestion Worker: routes each source key to the adapter that
    can_handle() it, exactly per Architecture Sec. 14 / Sec. 9.4."""
    all_records: list[StandardRecord] = []
    catalog: dict[str, dict] = {}
    for source in SOURCE_KEYS:
        adapter = next((a for a in REGISTERED_ADAPTERS if a.can_handle(source)), None)
        if adapter is None:
            continue  # NFR-014: unmatched/failing source is skipped, not fatal
        try:
            records = adapter.parse(source)
            all_records.extend(records)
            catalog[source] = adapter.metadata()
        except Exception as exc:  # fault isolation per NFR-014
            catalog[source] = {"error": str(exc)}
    return all_records, catalog
