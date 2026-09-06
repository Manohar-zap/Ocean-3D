# Implementation Plan: Complete Debug & Fix of Ocean-3D Visualization

Fix all 25 identified problems, focusing on geographic correctness, proper 3D hierarchy, and functional data controls.

## Diagnosis of Major Bugs

### 1. Earth Rotation / Orbit Bug
- **Root Cause:** In `frontend/index.html`, the `terrainMesh` (Earth) and `waterMesh` are rotated by `-0.25` radians (Lines 460, 520) to align the texture, but the data layers (`modelGroup`, `observationGroup`, etc.) are added to the `scene` at the origin without this rotation. This causes a geographic mismatch. Furthermore, `OrbitControls` targets `(0,0,0)` but independent object rotations make interaction feel disjointed.
- **Fix:** Move all components into a single `globeGroup` at `(0,0,0)`. Rotate the *group* once if needed, or better, fix the `latLonToVector3` math to align with the default texture projection.

### 2. Geographic Displacement
- **Root Cause:** Multiple coordinate conversion logics or misalignment between `SphereGeometry` UVs and the `Blue Marble` texture.
- **Fix:** Establish a single `latLonToVector3` utility aligned with the texture (0° lon at X+).

### 3. Rectangular Tiles / Grid
- **Root Cause:** Gridded data is being rendered as flat entities or incorrectly projected.
- **Fix:** Every cell/vertex will be mapped to the sphere surface using `latLonToVector3`. **Confirmed:** We will NOT just change parent groups; every data point will be individually curved onto the sphere.

## Proposed Changes

### Frontend (`frontend/index.html`)

#### [MODIFY] Scene Hierarchy & Performance
- Refactor all globe-related meshes and groups into a single `globeGroup` parent.
- **GPU Memory:** Implement recursive `disposeGroup(group)` and call it in `refreshAll()` before every update.

#### [MODIFY] Canonical Math Utility
- Implement `latLonToVector3(lat, lon, radius)`:
  - Latitude 0, Longitude 0 -> (R, 0, 0)
  - Latitude 90 (N) -> (0, R, 0)
  - Longitude 90 (E) -> (0, 0, -R) (matching Three.js standard spherical mapping).
- Align `SphereGeometry` rotation to this math (removing the `-0.25` hack).

#### [MODIFY] Data Controls (Sliders/Selectors)
- **Depth Slider:** Implement snapping to nearest available depth from `DEPTHS` constant.
- **UI Readout:** Display "Selected: [Val]m / Data: [Actual]m" when slider is moved.
- **Time Slider:** Connect to fetch and display the correct timestamp from backend.
- **Variable Selector:** Dynamic colorbar scale (min/max) based on dataset metadata.

#### [MODIFY] Interactivity & Profile Panel
- Fix platform selection using `userData.platformIds` on `InstancedMesh`.
- Update `openProfile` to display coordinates and profile data from the real API response.

### Backend (`backend/app/`)
- Verified `/api/model` and `/api/observations` fields (lat, lon, depth, value, platform_id) match frontend expectations.

## Verification Plan

### Acceptance Tests (Manual via Browser)
1. **Globe rotation**: Drag Earth. Verify it rotates around its center.
2. **Zoom**: Scroll. Verify Earth stays centered.
3. **India position**: Click "Fly to India". Verify India is centered.
4. **Instrument coordinates**: Click a marker. Verify coordinates in the panel match its geographical location.
5. **Depth Snapping**: Move depth slider. Verify it snaps to the closest discrete level (e.g. 0, 10, 25...).
6. **Variable Switch**: Change to Oxygen. Verify colorbar scale and labels update.
7. **Marker click**: Click Argo marker. Verify real profile chart and metadata appear.

## Fabricated Data Audit
- `Math.random()`: Used only for `Starfield` (visual background).
- Hardcoded Coords: `REGION_TARGETS` only (correct for camera navigation).
- All ocean data is driven by `/api/` endpoints (with synthetic fallback in backend if real data is missing).
