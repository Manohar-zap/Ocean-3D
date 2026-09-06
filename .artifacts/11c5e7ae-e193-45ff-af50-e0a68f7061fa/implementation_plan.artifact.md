# Implementation Plan: physically Accurate 3D Water Drain & Scientific Grid Mapping

Transform the static globe into a dynamic 3D ocean explorer with a physically accurate "water drain" effect and high-fidelity model data mapping.

## User Review Required

> [!IMPORTANT]
> - **Drained Water Surface:** The `waterMesh` shell will physically decrease in radius as depth increases (`radius = R - scaledDepth`).
> - **ETOPO Sign Convention:** The shader will use `if (elevation > -selectedDepth) discard;`. This ensures land (positive elevation) and shallow seabed (elevation between 0 and -selectedDepth) are revealed as "dry" ground.
> - **Grid Tile Logic:** "Square Blocks" will be replaced by oriented tiles (`PlaneGeometry`) sized to match the real grid spacing.
> - **Bathymetry Masking for Data:** Model data points will be CPU-masked. If the local seabed elevation is shallower than the data depth (`elevation > -depth`), the data point will not be rendered to prevent it from floating above dry ground or being buried in land.

## Proposed Changes

### Frontend (`frontend/index.html`)

#### [MODIFY] True 3D Water Drain (Shader & Scene)
- **State:** `state.selectedDepth` will be the snapped value from `DEPTHS`.
- **Sinking Surface:** In `refreshAll()`, update `waterMesh.scale` using `BASE_RADIUS * (1 - state.selectedDepth * TERRAIN_SCALE * state.verticalExaggeration)`.
- **Shader Masking:** Update `waterMaterial.uniforms.uSeaLevel` to `-state.selectedDepth`.
  - The fragment shader will `discard` water if `elevation > uSeaLevel`, correctly revealing land and shallow seabed while keeping deep water visible below the new surface level.

#### [MODIFY] Scientific Grid Mapping (Fixing "Square Blocks")
- **Refactor `renderSurfaceGrid`**:
  - Calculate `latStep` and `lonStep` from the data points to determine tile size.
  - Use `PlaneGeometry` for the `InstancedMesh`.
  - **Orientation:** Each tile will use `dummy.lookAt(0,0,0)` to ensure it follows the Earth's curvature.
  - **Placement:** Position at `radius = BASE_RADIUS * (1 - depth * TERRAIN_SCALE * state.verticalExaggeration)`.
  - **Bathymetry Mask:** Sample `elevationCache` at each `(u, v)`. If `elevation > -depth`, skip the instance.

#### [MODIFY] Centralized State & Controls
- **Depth Slider:**
  - Update `min/max` to `0` and `2000`.
  - Implement snapping to `DEPTHS` array.
  - Display: `Selected: [Slider]m / Data: [Nearest]m`.
- **Time Slider:** Trigger `refreshAll()` to fetch data for the selected timestamp.
- **Variable Selector:** Trigger `refreshAll()` and update colorbar labels/min/max.

#### [MODIFY] Resource Disposal
- Enhance `disposeGroup` to handle nested maps and materials to ensure memory stability during high-frequency slider updates.

## Verification Plan

### Mandatory Bathymetry Tests
Verify the following logic in the running application:
- **ETOPO +500m (Land), Depth 500m:** Land must be visible and dry.
- **ETOPO -200m (Shelf), Depth 500m:** Seabed must be exposed and dry.
- **ETOPO -1000m (Deep), Depth 500m:** Water surface must be visible at the 500m level.
- **ETOPO -700m, Depth 1000m:** Seabed must be exposed.
- **ETOPO -1500m, Depth 1000m:** Water remains.

### Functional Checks
1. **Rotation:** Verify Earth rotates around its center (0,0,0).
2. **Lat/Lon:** Verify markers appear in correct geographic locations.
3. **Variable Sync:** Verify colorbar and grid update when switching variables.
