# ETOPO + DAY2 MERGE PLAN

**Branch:** day2  
**Target Architecture:** Known-Good ETOPO Globe + Day2 Features & Data Pipeline  

---

## 1. Branch Inspection & Component Mapping

| Component | Source Branch | Implementation Files / Functions |
| :--- | :--- | :--- |
| **A. ETOPO Globe & Terrain** | `feature/etopo-ocean` | `gloab/etopo_heightmap_server.py`, `gloab/data/etopo1_2048x1024.f32` |
| **B. Water-Level / Depth Behavior** | `feature/etopo-ocean` | `waterMaterial.uniforms.uSeaLevel`, `updateSeaLevel(meters)` |
| **C. Globe Initialization & Shader** | `feature/etopo-ocean` | `terrainMesh`, `waterMesh`, `sampleElevationSmooth`, `thermalColor` |
| **D. Heightmap Texture Encoding** | `feature/etopo-ocean` | `buildPackedHeightTexture(elevations, width, height)` |
| **E. Observation Icons (ARGO, Glider, CTD, BGC)** | `day2` | `frontend/assets/icons/`, `loadObservations()`, `PLATFORM_ICON` |
| **F. Observation Historical Tracks** | `day2` | `loadPlatformTrack(platform_id)`, `/api/observations/{platform_id}/track` |
| **G. Right-Side 3D Profile Panel** | `day2` | `initThreeWaterColumn()`, `renderRightPanelWaterColumn()` |
| **H. Backend API & Real Data Adapters** | `day2` | `backend/app/main.py`, `backend/app/adapters.py` (Argovis, IOOS Glider, CTD, BGC) |
| **I. UI Controls & Tracker Summary** | `day2` | `frontend/index.html` (Tracker summary card, info card, time & depth sliders) |

---

## 2. Integration Strategy

```
               DAY2 APPLICATION LAYER
                         │
      ┌──────────────────┼──────────────────┐
      │                  │                  │
  MODEL API         OBSERVATIONS       UI & CONTROLS
  (/api/model)  (Argovis/IOOS/ERDDAP)   (Sliders/Panels)
      │                  │                  │
      └──────────────────┼──────────────────┘
                         │
                         ▼
             KNOWN-GOOD ETOPO GLOBE
      (Three.js ETOPO1 Float32 Heightmap Shader)
                         │
     ├── Terrain Mesh (CPU Displaced + Earth Texture)
     ├── Water Mesh (GPU Sea-Level Mask + Thermal Shader)
     ├── Observation Platform Markers (Billboard Icons)
     └── Historical Drift Trajectory Lines (Cyan Polyline)
                         +
            THREE.JS RIGHT-SIDE PANEL
             (3D Water-Column Profile)
```

---

## 3. Step-by-Step Milestones

### Milestone 1: ETOPO Heightmap Backend Integration
- Move ETOPO1 heightmap binary data files (`etopo1_2048x1024.f32`, `etopo1_2048x1024.json`, `etopo1_2048x1024_packed.png`) into `backend/data/` or `gloab/data/`.
- Mount FastAPI static/data endpoints in `backend/app/main.py` (`GET /heightmap`, `GET /heightmap-meta`, `GET /etopo1_2048x1024_packed.png`) so FastAPI serves the ETOPO1 Float32 heightmap on port 8000.

### Milestone 2: ETOPO Globe & Water-Level Shader Integration
- Transplant the known-good Three.js ETOPO Globe & Water Shader from `feature/etopo-ocean` into `frontend/index.html`.
- Connect the ETOPO water level slider to `updateSeaLevel(meters)`.
- Verify sea-level/depth reduction and shoreline exposure.

### Milestone 3: Day2 Observation Platform Icons & Tracker Integration
- Mount Day2 platform billboard icons (ARGO, Glider, CTD, BGC) on 3D ETOPO Globe at exact WGS84 geographic lat/lon positions.
- Connect platform clicks to `openProfile(platform_id)` and `loadPlatformTrack(platform_id)`.
- Render historical drift trajectories on the ETOPO Globe.

### Milestone 4: Right-Side 3D Profile & Model Control Integration
- Preserve Day2's Three.js Right-Panel 3D Water-Column Analytical View (`initThreeWaterColumn`, `renderRightPanelWaterColumn`).
- Connect depth slider to both ETOPO water level and model depth query.

### Milestone 5: Test Suite & Browser Verification
- Run complete backend test suite (`python -m unittest discover -s tests -v`).
- Perform browser verification in Selenium.
- Create `ETOPO_DAY2_MERGE_REPORT.md`.
