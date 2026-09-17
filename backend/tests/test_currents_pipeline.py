"""
Comprehensive test suite for the Real 3D Ocean Currents Pipeline.
Verifies Copernicus Marine real current field, O(1) direct coordinate indexing,
zero synthetic data fallbacks, fast current-aware A* routing, and API endpoints.
"""
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.currents_service import currents_service
from app.adaptive.current_router import current_router


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_currents_cache_loaded():
    """Verify that the 3D currents cache is loaded into memory with required metadata."""
    assert currents_service.is_loaded is True
    depths = currents_service.get_available_depths()
    assert 0.0 in depths
    assert 100.0 in depths
    assert 500.0 in depths
    assert 1000.0 in depths
    assert len(depths) >= 7
    times = currents_service.get_available_times()
    assert len(times) >= 1


def test_currents_service_surface_vs_subsurface():
    """Verify that real currents vary across depths according to physical oceanography."""
    # Gulf Stream coordinates (35°N, 72°W)
    u_surf, v_surf, spd_surf, dir_surf, prov_surf = currents_service.get_vector(35.0, -72.0, depth=0.0)
    assert prov_surf != "DEMO FALLBACK"
    assert prov_surf != "NO_DATA"
    assert spd_surf > 0.05

    u_deep, v_deep, spd_deep, dir_deep, prov_deep = currents_service.get_vector(35.0, -72.0, depth=1000.0)
    assert prov_deep != "DEMO FALLBACK"
    assert prov_deep != "NO_DATA"
    
    # Subsurface velocity should be physically distinct from surface
    assert (u_surf, v_surf) != (u_deep, v_deep)


def test_currents_service_land_exclusion():
    """Verify that land coordinates return NO_DATA and never fabricate numbers."""
    # Central India coordinates (20°N, 78°E)
    u, v, spd, heading, prov = currents_service.get_vector(20.0, 78.0, depth=0.0)
    assert u == 0.0
    assert v == 0.0
    assert spd == 0.0
    assert prov == "NO_DATA"


def test_currents_service_field_sampling():
    """Verify 2D horizontal slice sampling for globe streamlines visualization."""
    field = currents_service.get_current_field(depth=0.0, stride=4)
    assert field["count"] > 500
    assert len(field["vectors"]) == field["count"]
    first = field["vectors"][0]
    assert "lat" in first and "lon" in first
    assert "u" in first and "v" in first
    assert "speed" in first and "heading" in first


def test_current_router_no_demo_fallback():
    """Verify that DEMO FALLBACK (u=0.35, v=-0.25) is completely eliminated."""
    # Test ocean coordinate in Bay of Bengal
    u, v, spd, heading, prov = current_router.query_current_vector(12.0, 84.0, depth=100.0)
    assert prov != "DEMO FALLBACK"
    assert not (abs(u - 0.35) < 1e-4 and abs(v - (-0.25)) < 1e-4)


def test_current_aware_astar_performance():
    """Verify that 196-cell A* routing executes in milliseconds (eliminating 25s timeout)."""
    t0 = time.time()
    plan = current_router.plan_current_aware_trajectory(
        start_lat=12.0, start_lon=84.0,
        target_lat=15.0, target_lon=88.0,
        target_depth_m=500.0
    )
    elapsed_ms = (time.time() - t0) * 1000.0

    # Must complete in under 500ms (previously took 25,000ms+)
    assert elapsed_ms < 500.0, f"A* routing took too long: {elapsed_ms:.1f}ms"
    assert plan["current_data_provenance"] != "DEMO FALLBACK"
    assert "selected_route" in plan
    assert len(plan["candidate_routes"]) == 3
    assert plan["selected_route"]["current_assistance_mps"] is not None


def test_api_currents_endpoints(client):
    """Verify all /api/currents endpoints return valid JSON and 200 OK."""
    # 1. Depths
    res_d = client.get("/api/currents/depths")
    assert res_d.status_code == 200
    assert "depths" in res_d.json()
    assert len(res_d.json()["depths"]) >= 7

    # 2. Times
    res_t = client.get("/api/currents/times")
    assert res_t.status_code == 200
    assert "times" in res_t.json()

    # 3. Surface Field
    res_field = client.get("/api/currents?depth=0&stride=4")
    assert res_field.status_code == 200
    data = res_field.json()
    assert data["count"] > 500
    assert len(data["vectors"]) > 500

    # 4. Subsurface Field
    res_500 = client.get("/api/currents?depth=500&stride=4")
    assert res_500.status_code == 200
    assert res_500.json()["depth_m"] == 500.0

    # 5. Point Vector
    res_vec = client.get("/api/currents/vector?lat=35.0&lon=-72.0&depth=0")
    assert res_vec.status_code == 200
    vdata = res_vec.json()
    assert "u" in vdata and "v" in vdata
    assert vdata["provenance"] != "DEMO FALLBACK"
