"""
Tests for Model-Observation Co-Validation Service and INCOIS OMNI Moored Buoy Integration.
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_moored_buoys_present():
    """Verify INCOIS OMNI moored buoys are ingested and returned in platforms list."""
    res = client.get("/api/observations/platforms/latest")
    assert res.status_code == 200
    data = res.json()
    platforms = data["platforms"]
    pids = {p["platform_id"] for p in platforms}

    assert "OMNI-BD08" in pids
    assert "OMNI-AD02" in pids
    assert "RAMA-15N90E" in pids

    bd08 = next(p for p in platforms if p["platform_id"] == "OMNI-BD08")
    assert bd08["platform_type"] == "mooring"
    assert bd08["source_organization"] == "INCOIS / NIOT (MoES, India)"
    assert bd08["data_status"] == "CACHED REAL DATA"


def test_profile_validation_endpoint():
    """Verify /api/observations/{platform_id}/validation returns dual curves and skill metrics."""
    res = client.get("/api/observations/ARGO-5906796/validation?variable=temperature")
    assert res.status_code == 200
    val = res.json()

    assert val["platform_id"] == "ARGO-5906796"
    assert val["variable"] == "temperature"
    assert val["unit"] == "degC"
    assert "observation_profile" in val
    assert "model_profile" in val
    assert len(val["observation_profile"]) > 0
    assert len(val["model_profile"]) == len(val["observation_profile"])

    metrics = val["metrics"]
    assert "bias" in metrics
    assert "rmse" in metrics
    assert "r2" in metrics
    assert "willmott_d" in metrics
    assert metrics["rmse"] >= 0.0
    assert 0.0 <= metrics["r2"] <= 1.0
    assert 0.0 <= metrics["willmott_d"] <= 1.0


def test_mooring_profile_validation():
    """Verify co-validation on INCOIS OMNI Moored Buoy BD08."""
    res = client.get("/api/observations/OMNI-BD08/validation?variable=salinity")
    assert res.status_code == 200
    val = res.json()

    assert val["platform_id"] == "OMNI-BD08"
    assert val["variable"] == "salinity"
    assert val["unit"] == "psu"
    assert len(val["observation_profile"]) == 8
    assert val["metrics"]["sample_count"] == 8
