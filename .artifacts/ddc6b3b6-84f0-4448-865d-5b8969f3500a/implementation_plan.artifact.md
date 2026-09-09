# Implementation Plan: ARGO Backend Integration into Ocean-3D (Revised)

Integrate ARGO branch backend capabilities and analytical UI overlays into the current `feature/etopo-migration-agent` branch. This plan prioritizes authoritative data provenance, protects existing ETOPO/Three.js functionality, and fixes known bugs.

## User Review Required

> [!IMPORTANT]
> - **Authoritative Provenance:** `data_source` is now the single source of truth. `data_status` will be automatically derived from it (e.g., `real` -> `REAL DATA`).
> - **No Alias:** The `/api/heightmap` alias will be removed to keep the ETOPO API clean and protected.
> - **Grid3D:** The `/api/model/grid3d` endpoint integration is marked as a **Future Phase** and will not be wired into the UI in this iteration.
> - **Dynamic Window:** Live in-situ queries (Argovis) will now use a dynamic rolling 30-day window instead of hardcoded dates.

## Proposed Changes

### [Backend]

#### [MODIFY] [schemas.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/schemas.py)
- Change default `data_source` in `StandardRecord` and `DatasetMeta` from `"cached"` to `"unavailable"`.

#### [MODIFY] [adapters.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/adapters.py)
- Update all adapters to use `data_source` as the authoritative provenance field.
- Implement logic to ensure `data_status` consistently derives from `data_source`:
    - `real` -> `REAL DATA`
    - `cached` -> `CACHED REAL DATA`
    - `synthetic` -> `DEMONSTRATION DATA`
    - `unavailable` -> `UNAVAILABLE`
- **ArgoGliderAdapter:** Change `_fetch_and_parse_argovis_live` to calculate a rolling 30-day window from `datetime.now()`.
- **BathymetryAdapter:** If `sample_bathymetry_gebco.nc` is missing, `metadata()` will report `data_source="unavailable"` and `parse()` will return an empty list.
- **Variable Narrowing:** Ensure all Copernicus/Argovis adapters maintain strict variable selection (e.g., `data=pressure,temperature,salinity`) to avoid large downloads.

#### [MODIFY] [main.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/main.py)
- Revert the `/api/heightmap` and `/api/heightmap/meta` aliases added in the previous turn.
- **Bug Fix:** Ensure `/api/observations/{platform_id}/profile` response includes `latitude` and `longitude` fields for every point in the profile to enable 3D path rendering.
- Add ARGO endpoints: `/api/observations/platforms/latest` and `/api/observations/{platform_id}/track`.

#### [MODIFY] [storage.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/storage.py)
- Ensure `Store._build_catalog` correctly maps `data_source` and `data_status` from adapter metadata.

---

### [Frontend]

#### [MODIFY] [index2_corrected.html](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/gloab/index2_corrected.html)
- **Independent ARGO Layer:** Add observation markers and drift tracks as an additive Three.js layer.
- **3D Water Column:** Port the Three.js-based vertical profile renderer into the observation panel.
- **Provenance Badges:** Display badges (Real, Cached, Synthetic, Unavailable) driven by the `data_source` field in the API response.
- **Error Isolation:** Wrap ARGO fetch calls in `try/catch` to ensure failures do not impact the core globe/ETOPO rendering.

## Verification Plan

### Automated Tests
- `pytest backend/tests/` verifying all endpoints.
- New test case: Verify profile endpoint returns non-null `latitude` and `longitude`.

### Manual Verification (Evidence Required)
- `git status` and `git diff --stat`.
- Raw JSON response from `/api/terrain/heightmap-meta` (showing ETOPO is healthy).
- Raw JSON response from `/api/observations/platforms/latest` (showing `data_source` field).
- Raw JSON response from `/api/observations/{platform_id}/profile` (showing `latitude`/`longitude`).
- UI check: Verify "Synthetic" badge appears for BGC/Demo data.
- ETOPO Stability check: Manually block ARGO backend ports and verify the globe/ETOPO still works.
