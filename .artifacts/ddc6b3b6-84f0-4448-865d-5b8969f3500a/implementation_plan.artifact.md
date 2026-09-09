# Implementation Plan: ARGO Integration & Scientific Accuracy Fixes (v2)

Fix visual regressions, restore the real ARGO data pipeline, and implement rigorous scientific oceanographic probing.

## User Review Required

> [!IMPORTANT]
> - **Visual Fix:** I will disable the automatic rendering of `modelPointsGroup` on initial load to remove the unwanted "vertical spikes/rods". The point cloud will only render if explicitly selected by the user.
> - **Authoritative ARGO Pipeline:** I will restore the intended priority: **REAL REMOTE API** -> **CACHED REAL NetCDF DATA** -> **UNAVAILABLE**. Silent synthetic fallbacks will be removed.
> - **Water-Validation:** ARGO markers will only be rendered if their location is currently submerged in the simulation (`ETOPO elevation < currentSeaLevelMeters`).
> - **Scientific Depth Probe:** The tooltip will now dynamically distinguish between land and water, calculate water depth relative to the slider, and query the 3D model for depth-aware temperature.

## Proposed Changes

### [Backend]

#### [MODIFY] [adapters.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/adapters.py)
- **Path Correction:** Update `run_ingestion` to look for local real data in `BASE_DIR.parent / "insitu_data" / "indian_ocean_insitu_recent"`.
- **Remove Silent Fallbacks:** Update `ArgoGliderAdapter.parse` and `run_ingestion` to return an empty list/error rather than synthetic data if the real API/cache fails, unless `DATA_MODE` is explicitly set to `"synthetic"`.
- **Dynamic Dates:** Update `_fetch_and_parse_argovis_live` to calculate the 30-day window dynamically from `datetime.now(timezone.utc)`.
- **Provenance Derivation:** Ensure `data_status` is always derived from the authoritative `data_source` field in `StandardRecord` using the mapping: `real` -> `REAL DATA`, `cached` -> `CACHED REAL DATA`, `synthetic` -> `DEMONSTRATION DATA`, `unavailable` -> `UNAVAILABLE`.
- **Bathymetry Fix:** If GEBCO NetCDF is missing, report `data_source="unavailable"` and return no data.

#### [MODIFY] [main.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/main.py)
- **New Probe Endpoint:** Add `GET /api/model/probe` accepting `lat`, `lon`, and `depth`. It will perform spatial/depth interpolation on the `cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m` dataset.
- **Profile Coordinate Fix:** Ensure `/api/observations/{id}/profile` returns the authoritative `latitude` and `longitude` of the profile in the response.

---

### [Frontend]

#### [MODIFY] [index2_corrected.html](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/gloab/index2_corrected.html)
- **Remove Spikes:** Disable the auto-selection of the Copernicus dataset in `loadCatalog`, ensuring `modelPointsGroup` is empty on load.
- **Dynamic Observation Control:**
    - Update `renderObservationMarkers` to sample ETOPO elevation at each platform coordinate.
    - Marker visibility logic: `sprite.visible = (sampledElevation < currentSeaLevelMeters)`.
    - Trigger `updateMarkerVisibility()` whenever `updateSeaLevel` is called.
- **Scientific Tooltip (Depth Probe):**
    - Refactor `onPointerMove` to implement **Case A (LAND)** vs **Case B (WATER)** logic.
    - Case B (WATER): Calculate `waterDepth = currentSeaLevelMeters - seafloorElevation`.
    - **Throttled Probing:** Fetch temperature from `/api/model/probe` at the calculated depth, throttled to avoid excessive requests.
- **Indian Ocean Filtering:**
    - Add UI selector for "All", "Indian Ocean" (Core), and "Near Indian Ocean" (10° buffer).
    - core: `lat: [-40, 25], lon: [30, 120]`.
    - near: `lat: [-50, 35], lon: [20, 130]`.
- **Depth-Aware Visualization:** Adjust the water shader or a sampled visualization layer to reflect model temperature at the current simulated depth.

## Verification Plan

### Automated Tests
- `pytest backend/tests/test_argo_integration.py` updated with:
    - Provenance mapping checks (all 4 states).
    - Profile response `latitude`/`longitude` presence.
    - `/api/model/probe` accuracy test.

### Manual Verification (Runtime Evidence Required)
- **Visual:** Globe surface is clean on load; ARGO markers appear as high-quality sprites.
- **Pipeline:** Platform panel shows "REAL DATA" or "CACHED REAL DATA" using the 30-day dynamic window.
- **Water Logic:** Markers disappear when the sea level is lowered below their seafloor elevation.
- **Scientific Probe:** Tooltip correctly switches from "EXPOSED TERRAIN" to "OCEAN WATER", calculates depth, and shows depth-aware temperature.
- **Filters:** Verify "Visible platforms: X" updates correctly with region and water filters.
