# Research Notes: Data Provenance & grid3d Investigation

## 1. Data Provenance Audit (Code Citations)

### a. /api/observations (Argo)
**Finding:** Hits a synthetic fallback in two places.
- **Function:** `ArgoGliderAdapter.parse`
- **Location:** `backend/app/adapters.py:421-427`
```python
        if get_data_mode() == "auto":
            for i in range(2):
                pid = f"ARGO_ARGOVIS_{i}"
                # ... hardcoded records ...
                records.append(StandardRecord(
                    # ...
                    data_status="CACHED REAL DATA", # NOTE: Misleading label!
                    source_organization="Argo GDAC / Argovis"
                ))
```
- **Function:** `run_ingestion`
- **Location:** `backend/app/adapters.py:469-478`
```python
    # Final Fallback: Synthetic observations if auto mode and still nothing
    if get_data_mode() == "auto" and not any(r.kind == "observation" for r in all_records):
        recs = _generate_synthetic_observations()
        all_records.extend(recs)
```

### b. /api/bathymetry
**Finding:** No explicit synthetic data *generation* in `parse`, but `metadata` reports it.
- **Function:** `BathymetryAdapter.metadata`
- **Location:** `backend/app/adapters.py:195`
```python
        status = "CACHED REAL DATA" if has_file else "DEMONSTRATION DATA"
```
- **Function:** `BathymetryAdapter.parse`
- **Location:** `backend/app/adapters.py:203-239`
It returns an empty list if `sample_bathymetry_gebco.nc` is missing.

### c. /api/model (Copernicus)
**Finding:** Yes, has a silent synthetic fallback.
- **Function:** `CopernicusMarineAdapter.parse`
- **Location:** `backend/app/adapters.py:183-184`
```python
        if get_data_mode() == "auto":
            return parse_synthetic_grid("copernicus_cmems", ["temperature"], {"temperature": "degC"}, "DEMONSTRATION DATA", "Copernicus Marine Service", "GLOBAL_MULTIYEAR_PHY_001_030")
```

## 2. /api/model/grid3d Investigation

**Finding:** Removed in the migration to the Three.js globe.
- **Git Log:** Commit `ff2b94f` ("ETOPO globe migration...") and `5394537` ("Remove legacy CesiumJS frontend").
- **Reason:** The legacy Cesium frontend used `grid3d` for Marching Cubes isosurface extraction. The new Three.js globe (`index2_corrected.html`) uses a point-based or slice-based approach, which is handled more efficiently by `/api/model/volume`.
- **Backend Note:** `backend/app/main.py:131`:
```python
# NOTE: /api/model/grid3d removed (Requirement 5: API Cleanup).
# Volumetric visualization is handled by /api/model/volume.
```
**Recommendation:** Do not re-add `grid3d` to the UI unless isosurface rendering is explicitly required, as `/api/model/volume` is the intended replacement for the current frontend's volumetric needs.
