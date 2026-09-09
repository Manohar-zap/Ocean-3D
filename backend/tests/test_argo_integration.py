import pytest
from app.schemas import StandardRecord, DatasetMeta

def test_provenance_mapping_real():
    r = StandardRecord(kind="observation", dataset_id="test", variable="temp", latitude=0, longitude=0, depth=0, time="2026-01-01T00:00:00Z", value=20, unit="degC", data_source="real")
    assert r.data_status == "REAL DATA"

def test_provenance_mapping_cached():
    r = StandardRecord(kind="observation", dataset_id="test", variable="temp", latitude=0, longitude=0, depth=0, time="2026-01-01T00:00:00Z", value=20, unit="degC", data_source="cached")
    assert r.data_status == "CACHED REAL DATA"

def test_provenance_mapping_synthetic():
    r = StandardRecord(kind="observation", dataset_id="test", variable="temp", latitude=0, longitude=0, depth=0, time="2026-01-01T00:00:00Z", value=20, unit="degC", data_source="synthetic")
    assert r.data_status == "DEMONSTRATION DATA"

def test_provenance_mapping_unavailable():
    r = StandardRecord(kind="observation", dataset_id="test", variable="temp", latitude=0, longitude=0, depth=0, time="2026-01-01T00:00:00Z", value=20, unit="degC", data_source="unavailable")
    assert r.data_status == "UNAVAILABLE"

def test_dataset_meta_provenance():
    m = DatasetMeta(dataset_id="test", label="Test", variable_list=["temp"], units={"temp": "degC"}, valid_range={}, provenance="test", kind="observation", data_source="real")
    assert m.data_status == "REAL DATA"

def test_profile_lat_lon_fix():
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # 1. Get latest platforms to find a valid ID
    resp = client.get("/api/observations/platforms/latest")
    assert resp.status_code == 200
    p_data = resp.json()
    assert p_data["count"] > 0

    target_id = p_data["platforms"][0]["platform_id"]

    # 2. Test profile endpoint for this ID
    response = client.get(f"/api/observations/{target_id}/profile")
    assert response.status_code == 200
    data = response.json()
    assert "profile" in data
    assert "data_source" in data
    for entry in data["profile"]:
        assert "latitude" in entry
        assert "longitude" in entry
        assert "data_source" in entry
        assert isinstance(entry["latitude"], float)
        assert isinstance(entry["longitude"], float)
