"""
OCEAN 3D — API Gateway / Backend (Architecture Sec. 5.2).

Run with:  uvicorn app.main:app --reload --port 8000
Then open frontend/index.html (it points at http://localhost:8000 by default).
"""
from __future__ import annotations
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, FileResponse
from typing import Optional

from .schemas import QueryFilters
from .storage import store
from .services import query_service, comparison_service, export_service

app = FastAPI(
    title="OCEAN 3D API",
    description="Web API layer for INCOIS OCEAN 3D — dataset discovery, "
                 "spatial/temporal/depth queries, model-observation comparison, and export.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo posture; Architecture Sec. 12 — restrict at deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dataset / Catalog API  (FR-033)
# ---------------------------------------------------------------------------

@app.get("/api/catalog")
def get_catalog():
    """List available datasets, variables, instruments, and metadata."""
    return {"datasets": [d.model_dump() for d in store.catalog.values()]}


# ---------------------------------------------------------------------------
# Query Service  (FR-034-037)
# ---------------------------------------------------------------------------

@app.get("/api/model")
def query_model(
    dataset_id: str = Query(..., description="e.g. incois_las_model, bgc_model"),
    variable: str = Query(...),
    min_lat: float = -90, max_lat: float = 90,
    min_lon: float = -180, max_lon: float = 180,
    min_depth: float = 0, max_depth: float = 6000,
    time: Optional[str] = Query(None, description="ISO timestamp; snapped to nearest available step"),
):
    """Filtered model field query -> used to render a depth-slice or volumetric field."""
    if min_lat > max_lat or min_lon > max_lon:
        raise HTTPException(400, "min must be <= max for lat/lon range")
    if min_depth > max_depth:
        raise HTTPException(400, "min_depth must be <= max_depth")

    f = QueryFilters(dataset_id=dataset_id, variable=variable,
                      min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon,
                      min_depth=min_depth, max_depth=max_depth, time=time)
    rows = query_service.model_grid(f)
    if not rows:
        raise HTTPException(404, "No model data matches this query. Try a different variable, "
                                  "depth, time, or a wider region.")
    return {
        "count": len(rows),
        "time": rows[0].time,
        "unit": rows[0].unit,
        "points": [
            {"lat": r.latitude, "lon": r.longitude, "depth": r.depth, "value": r.value}
            for r in rows
        ],
    }


@app.get("/api/model/times")
def model_times(dataset_id: str):
    times = query_service.available_times(dataset_id)
    if not times:
        raise HTTPException(404, f"Unknown dataset_id '{dataset_id}'")
    return {"dataset_id": dataset_id, "times": times}


@app.get("/api/model/volume")
def query_model_volume(
    dataset_id: str = Query(...),
    variable: str = Query(...),
    depths: Optional[str] = Query(None, description="Comma-separated depths, e.g. '0,100,200,500,1000'"),
    min_lat: float = -90, max_lat: float = 90,
    min_lon: float = -180, max_lon: float = 180,
    min_depth: float = 0, max_depth: float = 6000,
    time: Optional[str] = None,
):
    """Batched multi-depth query for stacked water-column visualization."""
    if min_lat > max_lat or min_lon > max_lon:
        raise HTTPException(400, "min must be <= max for lat/lon range")
    target_depths = [float(d.strip()) for d in depths.split(",")] if depths else None
    
    f = QueryFilters(dataset_id=dataset_id, variable=variable,
                      min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon,
                      min_depth=min_depth, max_depth=max_depth, time=time)
    by_depth = query_service.model_volume(f, target_depths)
    if not by_depth:
        raise HTTPException(404, "No volume data found for this selection")
    
    sample = next(iter(by_depth.values()))[0]
    return {
        "dataset_id": dataset_id,
        "variable": variable,
        "time": sample.time,
        "unit": sample.unit,
        "depths": list(by_depth.keys()),
        "layers": {
            str(d): [
                {"lat": r.latitude, "lon": r.longitude, "depth": r.depth, "value": r.value}
                for r in rows
            ]
            for d, rows in by_depth.items()
        }
    }


@app.get("/api/model/grid3d")
def query_model_grid3d(
    dataset_id: str = Query(...),
    variable: str = Query(...),
    min_lat: float = -90, max_lat: float = 90,
    min_lon: float = -180, max_lon: float = 180,
    min_depth: float = 0, max_depth: float = 6000,
    time: Optional[str] = None,
):
    """3D scalar grid for Marching Cubes isosurface extraction."""
    f = QueryFilters(dataset_id=dataset_id, variable=variable,
                      min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon,
                      min_depth=min_depth, max_depth=max_depth, time=time)
    res = query_service.model_grid3d(f)
    if not res or not res.get("grid"):
        raise HTTPException(404, "No 3D grid data found for this query")
    return res


@app.get("/api/bathymetry")
def query_bathymetry(
    min_lat: float = -90, max_lat: float = 90,
    min_lon: float = -180, max_lon: float = 180,
):
    """Real GEBCO / ETOPO Global Bathymetry Seafloor dataset query."""
    f = QueryFilters(dataset_id="gebco_bathymetry", variable="elevation",
                      min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon)
    rows = query_service.model_grid(f)
    if not rows:
        raise HTTPException(404, "No bathymetry data matches this query.")
    return {
        "dataset_id": "gebco_bathymetry",
        "source_organization": "GEBCO (General Bathymetric Chart of the Oceans)",
        "product_id": "GEBCO_2023_GRID",
        "data_status": rows[0].data_status,
        "unit": "meters",
        "count": len(rows),
        "points": [
            {"lat": r.latitude, "lon": r.longitude, "depth": r.depth, "elevation": r.value}
            for r in rows
        ],
    }


# Terrain heightmap endpoints for Three.js GLSL globe
TERRAIN_DIR = Path(__file__).resolve().parent.parent.parent / "gloab" / "data"

@app.get("/api/terrain/heightmap")
def get_terrain_heightmap():
    f32_path = TERRAIN_DIR / "etopo1_2048x1024.f32"
    if not f32_path.exists():
        raise HTTPException(404, "Heightmap f32 file not found")
    return FileResponse(f32_path, media_type="application/octet-stream", filename="etopo1_2048x1024.f32")

@app.get("/api/terrain/heightmap-meta")
def get_terrain_heightmap_meta():
    json_path = TERRAIN_DIR / "etopo1_2048x1024.json"
    if not json_path.exists():
        raise HTTPException(404, "Heightmap metadata json not found")
    return json.loads(json_path.read_text(encoding="utf-8"))


@app.get("/api/observations")
def query_observations(
    platform_type: Optional[str] = Query(None, description="argo | glider | ctd | bgc"),
    variable: Optional[str] = None,
    min_lat: float = -90, max_lat: float = 90,
    min_lon: float = -180, max_lon: float = 180,
    min_depth: float = 0, max_depth: float = 6000,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
):
    """Instrument observations for map/marker overlay (surface position per platform)."""
    f = QueryFilters(platform_type=platform_type, variable=variable,
                      min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon,
                      min_depth=min_depth, max_depth=max_depth,
                      time_start=time_start, time_end=time_end)
    rows = query_service.observations(f)

    # collapse to one marker per platform (shallowest sample) for map display;
    # full depth resolution is fetched via /api/observations/{platform_id}/profile
    by_platform: dict[str, dict] = {}
    for r in rows:
        cur = by_platform.get(r.platform_id)
        if cur is None or r.depth < cur["depth"]:
            by_platform[r.platform_id] = {
                "platform_id": r.platform_id,
                "platform_type": r.platform_type,
                "lat": r.latitude,
                "lon": r.longitude,
                "depth": r.depth,
                "time": r.time,
                "variable": r.variable,
                "value": r.value,
                "unit": r.unit,
                "quality_flag": r.quality_flag,
            }
    return {"count": len(by_platform), "markers": list(by_platform.values())}


@app.get("/api/observations/{platform_id}/profile")
def observation_profile(platform_id: str, variable: Optional[str] = None, time: Optional[str] = None):
    """Full depth-vs-variable profile for a single platform (UC-009, UC-010)."""
    rows = query_service.profile(platform_id)
    if variable:
        rows = [r for r in rows if r.variable == variable]
    if time:
        rows = [r for r in rows if r.time == time]
    if not rows:
        raise HTTPException(404, f"No profile data for platform '{platform_id}' with the given filters")
    rows = sorted(rows, key=lambda r: r.depth)
    return {
        "platform_id": platform_id,
        "platform_type": rows[0].platform_type,
        "profile": [
            {"depth": r.depth, "variable": r.variable, "value": r.value, "unit": r.unit,
             "time": r.time, "quality_flag": r.quality_flag, "latitude": r.latitude, "longitude": r.longitude}
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Comparison Service  (FR-029-032)
# ---------------------------------------------------------------------------

@app.get("/api/compare")
def compare(platform_id: str, variable: str, depth: float, time: str, dataset_id: Optional[str] = None):
    try:
        result = comparison_service.compare({
            "platform_id": platform_id, "variable": variable, "depth": depth, "time": time,
        }, dataset_id=dataset_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return result.model_dump()


# ---------------------------------------------------------------------------
# Export Service  (FR-041-043)
# ---------------------------------------------------------------------------

@app.get("/api/export", response_class=PlainTextResponse)
def export(
    kind: str = Query(..., description="model | observation"),
    dataset_id: Optional[str] = None,
    variable: Optional[str] = None,
    platform_type: Optional[str] = None,
    min_lat: float = -90, max_lat: float = 90,
    min_lon: float = -180, max_lon: float = 180,
    min_depth: float = 0, max_depth: float = 6000,
    time: Optional[str] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
):
    f = QueryFilters(dataset_id=dataset_id, variable=variable, platform_type=platform_type,
                      min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon,
                      min_depth=min_depth, max_depth=max_depth,
                      time=time, time_start=time_start, time_end=time_end)
    rows = query_service.model_grid(f) if kind == "model" else query_service.observations(f)
    if not rows:
        raise HTTPException(404, "No data matches this selection for export.")
    try:
        csv_text = export_service.to_csv(rows)
    except ValueError as e:
        raise HTTPException(413, str(e))
    return PlainTextResponse(csv_text, media_type="text/csv",
                              headers={"Content-Disposition": "attachment; filename=ocean3d_export.csv"})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok",
            "model_records": len(store.model_records),
            "observation_records": len(store.observation_records),
            "datasets": list(store.catalog.keys())}
