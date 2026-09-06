# Migration Plan: Replace CesiumJS with Three.js GLSL Globe and Integrate ETOPO Terrain & Ocean Features

Migrate the Ocean-3D frontend from CesiumJS 1.114 to a standalone Three.js (r128) single-sphere GLSL shader globe with real NOAA ETOPO1 heightmap vertex displacement, and absorb the ETOPO heightmap server functionality into the FastAPI backend (`backend/app/main.py`), incorporating all six mandatory engineering requirements.

## User Review Required / Decisions

> [!IMPORTANT]
> - **Region Navigation Decision:** The "Fly to Himalayas" button and region select (Indian, Pacific, Atlantic, Southern, Arctic Ocean) **are in scope** and will be rebuilt as smooth OrbitControls camera position/target transitions targeting lat/lon positions on the Three.js sphere.
> - **UI Shell Preservation:** When porting scene/shader/heightmap logic from `gloab/index2_corrected.html`, **only the script logic** is imported. `frontend/index.html`'s existing glassmorphic research/public UI panels, timebar, depth slider, and profile panel are fully preserved.
> - **Performance & Batched Geometry:** Observation markers and current-vector arrows will use batched/instanced geometry (`InstancedMesh` or optimized buffer geometries / instanced points) to prevent object pollution and ensure high framerates.
> - **Robust Path Resolution:** Terrain endpoints (`/api/terrain/heightmap`, `/api/terrain/heightmap-meta`) resolve `.f32` and `.json` paths relative to `Path(__file__).resolve()` to eliminate CWD dependence.
> - **Config Cleanup:** `CESIUM_ION_TOKEN` will be removed from `frontend/config.js` and `.env.example` / `.env`.
> - **Regression Tests:** Automated pytest tests will cover profile lat/lon inclusion, explicit `dataset_id` comparison parameter, and terrain endpoint smoke tests.

## Proposed Changes

### Backend (`backend/app/`)

#### [MODIFY] [main.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/main.py)
- Add GET `/api/terrain/heightmap` streaming `gloab/data/etopo1_2048x1024.f32` (resolved robustly via `Path(__file__)`) as `application/octet-stream`.
- Add GET `/api/terrain/heightmap-meta` serving `gloab/data/etopo1_2048x1024.json` as JSON.
- Fix bug 1: Add `"latitude": r.latitude, "longitude": r.longitude` to observation profile response items in `/api/observations/{platform_id}/profile`.
- Fix bug 2: Add optional `dataset_id` query parameter to `/api/compare` and thread it through to `comparison_service.compare()`.

#### [MODIFY] [services.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/services.py)
- Update `ComparisonService.compare()` to accept optional `dataset_id` parameter to resolve dataset ambiguity for shared variables.

#### [NEW / MODIFY] Tests (`backend/tests/`)
- Add tests for profile lat/lon, compare with `dataset_id`, and terrain endpoints smoke test.

### Frontend (`frontend/`)

#### [MODIFY] [config.js](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/frontend/config.js)
- Remove `CESIUM_ION_TOKEN`.

#### [MODIFY] [index.html](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/frontend/index.html)
- Remove CesiumJS CDN scripts, `widgets.css`, and Cesium initialization code.
- Import Three.js r128 and OrbitControls.
- Integrate Three.js globe setup, GLSL shaders, and `loadLocalHeightmap()` fetching from `http://localhost:8000/api/terrain/heightmap`.
- Implement lat/lon -> sphere-vertex/UV conversion helpers matching ETOPO grid convention (row 0 = north, col 0 = -180°).
- Re-wire model slices (`/api/model`), volume stacks (`/api/model/volume`), ocean current vectors (`current_u`/`current_v` using batched line geometries or instanced meshes), observation markers (batched meshes/points), 3D profile paths (`/api/observations/{id}/profile`), depth cursor, comparison panel (`/api/compare`), CSV export (`/api/export`), and region fly-to controls.

### Cleanup (`gloab/`)

#### [DELETE] [etopo_heightmap_server.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/gloab/etopo_heightmap_server.py)
- Retire standalone heightmap server script.

## Verification Plan

### Automated Tests
- Run `pytest` to execute existing and new regression tests (profile lat/lon, compare dataset_id, terrain smoke test).

### Manual Verification
- Start FastAPI backend (`uvicorn app.main:app --port 8000`).
- Open `frontend/index.html` in browser.
- Verify Three.js globe renders real ETOPO1 terrain and water shader, controls work smoothly, markers and vectors render efficiently using batched geometry.
