# BASELINE REPORT

**Date:** Sun Sep 6 2026  
**Repository:** Manohar-zap/Ocean-3D  
**Branch:** day2  
**Commit SHA:** `f7ff667104e79787ff02dd8bf73b064c5dbe99e7`

---

## 1. Test Suite Results
- **Total Tests:** 34
- **Passed:** 34
- **Failed:** 0
- **Status:** **OK (34/34 PASS)**

---

## 2. Active Server Status
- **Backend API Server (FastAPI / Uvicorn):** Running on `http://127.0.0.1:8000` (PID 2852)
- **Frontend HTTP Server (Python http.server):** Running on `http://127.0.0.1:5500` (PID 21348)

---

## 3. Browser & System Status
- **Cesium Globe:** Spherical 3D WGS84 Ellipsoid imagery layer active with Cesium World Terrain Provider.
- **Global Ocean Temperature Field:** `SingleTileImageryProvider` draped smoothly on global ocean domain (`-180°` to `+180°` Lon, `-75°` to `+75°` Lat) with land mask transparency.
- **Observation Tracker:** 169 platforms active on globe (ARGO: 139, Gliders: 10, CTD: 10, BGC-Argo: 10) with billboard icons.
- **3D Water-Column Analytical View:** Three.js user-controlled camera active (0 auto-rotation).

---

## 4. Known Data Provenance & Limitations
- **Model / Bathymetry Data:** `CACHED REAL DATA` (GEBCO 2023 Bathymetry, INCOIS ROMS, Copernicus Marine Model).
- **ARGO Floats:** `REAL DATA` (Live Argovis API) / `CACHED REAL DATA` (Cached Argovis profiles).
- **Gliders:** `CACHED REAL DATA` (IOOS Glider DAC dataset).
- **CTD Casts:** `CACHED REAL DATA` (NOAA/IOOS ERDDAP CTD dataset).
- **BGC-Argo Floats:** `CACHED REAL DATA` (Argo GDAC / Argovis BGC dataset).

---

## 5. Verification Checkpoint
All 34 tests passing cleanly. Working tree clean. Baseline established.
