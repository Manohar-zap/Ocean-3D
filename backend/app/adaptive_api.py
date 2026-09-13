"""HTTP API for the Ocean 3D adaptive observation decision layer."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .adaptive_engine import adaptive_engine

router = APIRouter(prefix="/api/adaptive", tags=["Adaptive Observation"])


@router.get("/health")
def adaptive_health():
    return {
        "status": "OK",
        "engine": "Ocean 3D Adaptive Observation Engine",
        "mode": "DECISION_SUPPORT_SIMULATION",
    }


@router.get("/score")
def score_location(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    depth: float = Query(100.0, ge=0, le=6000),
    variable: str = Query("temperature"),
):
    """Return interpretable information-gap and uncertainty components."""
    return adaptive_engine.score_location(lat, lon, depth, variable)


@router.get("/field")
def uncertainty_field(
    min_lat: float = Query(-10.0, ge=-90, le=90),
    max_lat: float = Query(30.0, ge=-90, le=90),
    min_lon: float = Query(50.0, ge=-180, le=180),
    max_lon: float = Query(100.0, ge=-180, le=180),
    depth: float = Query(100.0, ge=0, le=6000),
    variable: str = Query("temperature"),
    step: float = Query(2.0, gt=0.25, le=10.0),
):
    """Return a bounded 2D uncertainty field for the current 3D slice."""
    if min_lat > max_lat or min_lon > max_lon:
        raise HTTPException(400, "Minimum bounds must not exceed maximum bounds")
    return adaptive_engine.uncertainty_field(
        min_lat, max_lat, min_lon, max_lon, depth, variable, step
    )


@router.get("/recommend")
def recommend_observation(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    depth: float = Query(100.0, ge=0, le=6000),
    variable: str = Query("temperature"),
    platform: str = Query("glider", pattern="^(argo|glider|auv)$"),
):
    """Translate an information gap into a platform-constrained recommendation."""
    return adaptive_engine.recommend(lat, lon, depth, variable, platform)


@router.get("/simulate")
def simulate_observation(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    depth: float = Query(100.0, ge=0, le=6000),
    variable: str = Query("temperature"),
):
    """Run a what-if virtual observation and report simulated uncertainty reduction."""
    return adaptive_engine.simulate(lat, lon, depth, variable)
