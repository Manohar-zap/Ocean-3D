# Ocean-3D Backend Correction & Argo/Glider Pipeline

Standardize the backend on Copernicus Marine Service as the authoritative source, implement environment-based configuration, and add a real Argo/Glider observation pipeline with fallback mechanisms.

## User Review Required

> [!IMPORTANT]
> **CESIUM_ION_TOKEN Clarification:**
> The provided `CESIUM_ION_TOKEN` implies a CesiumJS globe, but the current frontend (`gloab/index2_corrected.html`) uses Three.js. I will configure the token in `.env` as requested, but I will not build any new Cesium-specific infrastructure unless you confirm a planned migration.
>
> **Credentials Security:**
> The shared Argovis key and Cesium token should be rotated once the integration is confirmed working, as they were shared in a chat session.

## Proposed Changes

### Configuration & Environment

#### [NEW] [.env](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/.env)
- Store `ARGOVIS_API_KEY`, `CESIUM_ION_TOKEN`, `DATA_MODE`, `PORT`, and `HOST`.
- **Verification:** Confirm `.gitignore` covers `backend/.env`.

#### [MODIFY] [requirements.txt](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/requirements.txt)
- Ensure `python-dotenv` is an explicit line item.

#### [MODIFY] [main.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/main.py)
- Load `.env` using `python-dotenv` at the top of the file.
- Update `/api/model`, `/api/model/volume`, `/api/compare`, and `/api/export` to make `dataset_id` optional (defaulting to `"copernicus_cmems"`).
- Enrich `/api/observations` with `total_available` and `summary` metadata.
- [NEW] Add `GET /api/observations/{platform_id}/track` endpoint.
- **Note:** `/api/bathymetry` will remain untouched.

---

### Data Models

#### [MODIFY] [schemas.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/schemas.py)
- Update `StandardRecord` to include `status` (default `"ACTIVE"`) and `sequence_number`.

---

### Data Adapters & Pipeline

#### [MODIFY] [adapters.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/adapters.py)
- Implement `DATA_MODE` logic:
    - `auto`: try real API → cached file → synthetic.
    - `real`: Live API only (fail if unavailable).
    - `cached`: Local files only.
- **Unregister** `ModelNetCDFAdapter` (INCOIS) and `BGCFieldAdapter` from `REGISTERED_ADAPTERS`.
- [NEW] `ArgoGliderAdapter`: Pulls from Argovis API using the environment key.
- [NEW] `IOOSGliderAdapter`: Pulls from NOAA ERDDAP.
- Update `run_ingestion` to use the fallback adapters only if `InSituTACAdapter` returns no data for a platform type.

---

### Storage Layer

#### [MODIFY] [storage.py](file:///C:/Users/Asus/Documents/Ocean-3D-feature-etopo-ocean/backend/app/storage.py)
- Update `_build_catalog` to only include datasets originating from Copernicus (plus fallback datasets if active).

---

## Verification Plan

### Automated Tests
- `python -m pytest backend/tests/` (Ensure existing tests pass).
- New test: `test_datamode_logic` — Verify `DATA_MODE` accurately gates the fallback chain.
- New test: `test_optional_dataset_id` — Verify endpoints default to `copernicus_cmems`.
- New test: `test_observation_track` — Verify the new `/track` endpoint returns sorted points.

### Manual Verification
- `curl http://localhost:8000/api/catalog` — Confirm only authorized dataset IDs are listed.
- `curl http://localhost:8000/api/observations` — Verify the new `summary` block exists.
- `curl http://localhost:8000/api/model` (No `dataset_id`): Verify it defaults to `copernicus_cmems` and contains NO records from unregistered adapters (e.g. `incois_las_model`).
- Verify `data_status` and `source_organization` accurately reflect the source of each record.
