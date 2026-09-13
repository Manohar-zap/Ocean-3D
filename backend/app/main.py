from __future__ import annotations
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from typing import Optional

from .schemas import QueryFilters
from .storage import store
from .services import query_service, comparison_service, export_service
from .adaptive import adaptive_engine

app = FastAPI(
    title="OCEAN 3D API",
    description="Web API layer for INCOIS OCEAN 3D — data, model-observation comparison, adaptive uncertainty, and mission recommendation.",
    version="1.1.0-adaptive",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/catalog")
def get_catalog():
    return {"datasets": [d.model_dump() for d in store.catalog.values()]}

@app.get("/api/model")
def query_model(dataset_id: str = Query(...), variable: str = Query(...), min_lat: float = -90, max_lat: float = 90, min_lon: float = -180, max_lon: float = 180, min_depth: float = 0, max_depth: float = 6000, time: Optional[str] = None):
    f = QueryFilters(dataset_id=dataset_id, variable=variable, min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, min_depth=min_depth, max_depth=max_depth, time=time)
    rows = query_service.model_grid(f)
    if not rows: raise HTTPException(404, "No model data matches this query.")
    return {"count": len(rows), "time": rows[0].time, "unit": rows[0].unit, "points": [{"lat": r.latitude, "lon": r.longitude, "depth": r.depth, "value": r.value} for r in rows]}

@app.get("/api/model/times")
def model_times(dataset_id: str):
    times = query_service.available_times(dataset_id)
    if not times: raise HTTPException(404, f"Unknown dataset_id '{dataset_id}'")
    return {"dataset_id": dataset_id, "times": times}

@app.get("/api/model/volume")
def query_model_volume(dataset_id: str = Query(...), variable: str = Query(...), depths: Optional[str] = Query(None), min_lat: float = -90, max_lat: float = 90, min_lon: float = -180, max_lon: float = 180, min_depth: float = 0, max_depth: float = 6000, time: Optional[str] = None):
    target_depths = [float(d.strip()) for d in depths.split(",")] if depths else None
    f = QueryFilters(dataset_id=dataset_id, variable=variable, min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, min_depth=min_depth, max_depth=max_depth, time=time)
    by_depth = query_service.model_volume(f, target_depths)
    if not by_depth: raise HTTPException(404, "No volume data found for this selection")
    sample = next(iter(by_depth.values()))[0]
    return {"dataset_id": dataset_id, "variable": variable, "time": sample.time, "unit": sample.unit, "depths": list(by_depth.keys()), "layers": {str(d): [{"lat": r.latitude, "lon": r.longitude, "depth": r.depth, "value": r.value} for r in rows] for d, rows in by_depth.items()}}

@app.get("/api/model/grid3d")
def query_model_grid3d(dataset_id: str = Query(...), variable: str = Query(...), min_lat: float = -90, max_lat: float = 90, min_lon: float = -180, max_lon: float = 180, min_depth: float = 0, max_depth: float = 6000, time: Optional[str] = None):
    f = QueryFilters(dataset_id=dataset_id, variable=variable, min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, min_depth=min_depth, max_depth=max_depth, time=time)
    res = query_service.model_grid3d(f)
    if not res or not res.get("grid"): raise HTTPException(404, "No 3D grid data found for this query")
    return res

@app.get("/api/bathymetry")
def query_bathymetry(min_lat: float = -90, max_lat: float = 90, min_lon: float = -180, max_lon: float = 180):
    f = QueryFilters(dataset_id="gebco_bathymetry", variable="elevation", min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon)
    rows = query_service.model_grid(f)
    if not rows: raise HTTPException(404, "No bathymetry data matches this query.")
    return {"dataset_id": "gebco_bathymetry", "source_organization": "GEBCO (General Bathymetric Chart of the Oceans)", "product_id": "GEBCO_2023_GRID", "data_status": rows[0].data_status, "unit": "meters", "count": len(rows), "points": [{"lat": r.latitude, "lon": r.longitude, "depth": r.depth, "elevation": r.value} for r in rows]}

@app.get("/api/observations")
def query_observations(platform_type: Optional[str] = Query(None), variable: Optional[str] = None, min_lat: float = -90, max_lat: float = 90, min_lon: float = -180, max_lon: float = 180, min_depth: float = 0, max_depth: float = 6000, time_start: Optional[str] = None, time_end: Optional[str] = None):
    f = QueryFilters(platform_type=platform_type, variable=variable, min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, min_depth=min_depth, max_depth=max_depth, time_start=time_start, time_end=time_end)
    rows = query_service.observations(f)
    by_platform: dict[str, dict] = {}
    for r in rows:
        cur = by_platform.get(r.platform_id)
        if cur is None or r.depth < cur["depth"]:
            by_platform[r.platform_id] = {"platform_id": r.platform_id, "platform_type": r.platform_type, "lat": r.latitude, "lon": r.longitude, "depth": r.depth, "time": r.time, "variable": r.variable, "value": r.value, "unit": r.unit, "quality_flag": r.quality_flag}
    return {"count": len(by_platform), "markers": list(by_platform.values())}

@app.get("/api/observations/{platform_id}/profile")
def observation_profile(platform_id: str, variable: Optional[str] = None, time: Optional[str] = None):
    rows = query_service.profile(platform_id)
    if variable: rows = [r for r in rows if r.variable == variable]
    if time: rows = [r for r in rows if r.time == time]
    if not rows: raise HTTPException(404, f"No profile data for platform '{platform_id}' with the given filters")
    rows.sort(key=lambda r: r.depth)
    return {"platform_id": platform_id, "platform_type": rows[0].platform_type, "profile": [{"depth": r.depth, "variable": r.variable, "value": r.value, "unit": r.unit, "time": r.time, "quality_flag": r.quality_flag} for r in rows]}

@app.get("/api/compare")
def compare(platform_id: str, variable: str, depth: float, time: str):
    try: result = comparison_service.compare({"platform_id": platform_id, "variable": variable, "depth": depth, "time": time})
    except ValueError as e: raise HTTPException(404, str(e))
    return result.model_dump()

@app.get("/api/export", response_class=PlainTextResponse)
def export(kind: str = Query(...), dataset_id: Optional[str] = None, variable: Optional[str] = None, platform_type: Optional[str] = None, min_lat: float = -90, max_lat: float = 90, min_lon: float = -180, max_lon: float = 180, min_depth: float = 0, max_depth: float = 6000, time: Optional[str] = None, time_start: Optional[str] = None, time_end: Optional[str] = None):
    f = QueryFilters(dataset_id=dataset_id, variable=variable, platform_type=platform_type, min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, min_depth=min_depth, max_depth=max_depth, time=time, time_start=time_start, time_end=time_end)
    rows = query_service.model_grid(f) if kind == "model" else query_service.observations(f)
    if not rows: raise HTTPException(404, "No data matches this selection for export.")
    try: csv_text = export_service.to_csv(rows)
    except ValueError as e: raise HTTPException(413, str(e))
    return PlainTextResponse(csv_text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=ocean3d_export.csv"})

# ---------------- Adaptive observation decision layer ----------------
@app.get("/api/adaptive/uncertainty")
def adaptive_uncertainty(variable: str = "temperature", depth: float = 200, min_lat: float = 0, max_lat: float = 25, min_lon: float = 60, max_lon: float = 95, step: float = 1.5):
    return adaptive_engine.uncertainty_field(variable, min_lat, max_lat, min_lon, max_lon, depth, step)

@app.get("/api/adaptive/recommendation")
def adaptive_recommendation(variable: str = "temperature", depth: float = 200, min_lat: float = 0, max_lat: float = 25, min_lon: float = 60, max_lon: float = 95, platform: str = "glider", candidate_step: float = 2.0):
    return adaptive_engine.recommend(variable, depth, min_lat, max_lat, min_lon, max_lon, platform, candidate_step)

@app.get("/api/adaptive/what-if")
def adaptive_what_if(variable: str = "temperature", lat: float = 12, lon: float = 75, depth: float = 200, value: float = 25.0):
    return adaptive_engine.what_if(variable, lat, lon, depth, value)

@app.get("/api/health")
def health():
    return {"status": "ok", "model_records": len(store.model_records), "observation_records": len(store.observation_records), "datasets": list(store.catalog.keys()), "adaptive_observation": True}
