# Task List: ETOPO Globe Migration & Backend Integration

- [x] Backend: Add robust `/api/terrain/heightmap` and `/api/terrain/heightmap-meta` endpoints using `Path(__file__)` in `backend/app/main.py`
- [x] Backend: Fix profile endpoint bug (include latitude/longitude in response rows) in `backend/app/main.py`
- [x] Backend: Fix comparison service dataset ambiguity (add optional `dataset_id` param) in `backend/app/main.py` and `backend/app/services.py`
- [x] Backend: Add regression tests for profile lat/lon, compare `dataset_id`, and terrain endpoints smoke test
- [x] Config: Remove `CESIUM_ION_TOKEN` from `frontend/config.js` and `.env.example`
- [x] Frontend: Remove CesiumJS dependencies and code from `frontend/index.html`
- [x] Frontend: Integrate Three.js r128 GLSL globe and `loadLocalHeightmap()` fetching from FastAPI backend
- [x] Frontend: Re-wire model data, batched observation markers, batched current vectors, 3D profile paths, region camera fly-to, and comparison/export tools onto Three.js scene
- [x] Cleanup: Remove `gloab/etopo_heightmap_server.py`
- [x] Verification: Run pytest and test frontend functionality
