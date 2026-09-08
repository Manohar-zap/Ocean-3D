# Terrain Builder Integration Plan

Fold the ETOPO1 heightmap generation logic from the standalone `etopo_heightmap_server.py` into the FastAPI backend as a dedicated builder module. This retires the redundant standalone server and consolidates the terrain data pipeline.

## Proposed Changes

### Backend Component

#### [NEW] [terrain_builder.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/terrain_builder.py)
- Port constants: `SOURCE_URL`, `SRC_W/SRC_H`, `OUT_W/OUT_H`, `MIN_ELEV/MAX_ELEV`.
- Port pipeline functions: `download()`, `extract_tiff()`, `resize_global()`, `build_heightmap()`.
- Adapt paths to use `gloab/data` as the target directory, matching the existing API contract in `main.py`.

#### [MODIFY] [requirements.txt](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/requirements.txt)
- Add `tifffile` and `Pillow` as dependencies required by the terrain builder.

#### [DELETE] [etopo_heightmap_server.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/etopo_heightmap_server.py)
- Remove the redundant standalone script from the repository (if found).

## Verification Plan

### Automated Tests
- Run `python backend/app/terrain_builder.py` (if made executable) or import it in a test script to verify it can identify existing data or trigger a download/build if missing.
- Verify `api/terrain/heightmap` still works in the browser.

### Manual Verification
- Check that `gloab/data/` contains the generated `.f32`, `.json`, and `.png` files.
- Confirm the Three.js globe still renders with terrain relief.
