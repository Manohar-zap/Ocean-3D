# Implementation Plan: Copernicus Marine Real-Data Integration & Persistent Daily Snapshot Caching

Migrate from synthetic data to real Copernicus Marine Service datasets for both ocean models and in-situ observations. Implement a robust 24-hour scheduled ingestion system that accumulates daily snapshots to provide approximately 3 months of historical observation trajectories.

## User Review Required

> [!IMPORTANT]
> - **Refresh Schedule:** Both Ocean Model and In-situ observations will be refreshed exactly every **24 hours**.
> - **Historical Accumulation (3 Months):** Since the NRT in-situ dataset only provides a rolling ~30-day window, the system will **retain** every successful daily snapshot in `backend/cache/snapshots/`. Snapshots will never be deleted or overwritten. The backend will merge and deduplicate observations across all retained snapshots (~90 days) to build a continuous 3-month history.
> - **Scientific Correctness:** Observation data will use real WMO IDs, coordinates, and timestamps. Synthetic data fallback will only be used if NO real data exists; once real data is ingested, the system will never silently revert to synthetic.
> - **Freshness Logic:**
>   - **Cache Freshness:** Indicated as "Last successful refresh: Xh ago". Marked as STALE/OFFLINE only if the 24h refresh cycle fails.
>   - **Platform Reporting:** Per-platform status "Last reported: Xh/Xd ago". Note: Argo floats may naturally show "stale" reporting (up to 10 days) which is normal behavior, not a system error.
> - **Data Persistence:** On refresh failure, the last successful real cache is preserved and served.

## Proposed Changes

### 1. Backend: Unified In-Situ Ingestion (`adapters.py`)
- **[NEW] `InSituTACAdapter`**:
  - Dataset: `cmems_obs-ins_glo_phybgcwav_mynrt_na_irr`.
  - Subsetting: `INDIAN_OCEAN_BBOX` (`lat -40 to 25`, `lon 30 to 120`).
  - File Handling: process the directory of individual platform NetCDF files.
  - Record Shape: Map real coordinates, timestamps, measurements (`TEMP`, `PSAL`, etc.), and real QC flags.
  - Metadata: Distinguish between observation time and snapshot download time.

### 2. Backend: Scheduled Worker & Deduplication (`storage.py`)
- **[NEW] `IngestionWorker`**: A background task running every 24 hours.
- **Snapshot Management**:
  - Save each subset to `backend/cache/snapshots/YYYYMMDD_HHMM/`.
  - On load, iterate through all snapshots from the last 90 days.
  - **Deduplication:** Merge records using `(platform_id, time, depth, variable)` as a unique key to prevent redundant points from overlapping 30-day windows.
- **Fail-safe:** If a pull fails, the system logs the error and continues serving the previous merged state.

### 3. Backend: Provenance & Trajectory API (`main.py`, `schemas.py`, `services.py`)
- Update `StandardRecord` to include:
    - `observation_time`: Actual time of measurement.
    - `download_time`: Time the snapshot was retrieved from Copernicus.
    - `is_real`: Boolean flag.
- Ensure `/api/observations/{id}/profile` returns the full merged trajectory (historical path) for that platform.
- **[DELETE]** `/api/model/grid3d`: Remove dead endpoint.

### 4. Frontend: Dual-Freshness Provenance UI (`index.html`)
- **Global Badge:** Display "Last successful refresh: Xh ago" in the header or side panel.
- **Platform Tooltip:** Display "Last reported: Xh/Xd ago" for the selected instrument.
- **Trajectory Rendering:** Re-wire observation paths to render multi-month trajectories by connecting all deduplicated positions.

## Verification Plan

### Automated Tests
- `backend/tests/test_real_data.py`: Verify conversion of real NetCDF variables to `StandardRecord`.
- `backend/tests/test_merging.py`: Mock two overlapping 30-day snapshots and verify the resulting `Store` contains a single deduplicated trajectory.

### Manual Verification
- Verify `backend/cache/snapshots/` accumulates folders over multiple runs.
- Trigger a mock "Refresh Failure" and confirm the UI shows a "Stale Cache" warning while still displaying the previous real data.
- Confirm WMO IDs and coordinates in the side panel match real-world Indian Ocean deployments.
