# Implementation Plan - Fix Regression & Restore 3D Globe

This plan addresses the regression where the Cesium globe was stuck during initialization. The root cause was identified as a combination of a `NameError` in the backend's NOAA service and synchronous blocking during background preloading, which starved the FastAPI event loop and prevented the frontend from loading critical assets.

## User Review Required

> [!IMPORTANT]
> **Priority #1: Globe Restoration.** We are decoupling the application's boot process from the NOAA data layer. The globe will now initialize regardless of the NOAA service's status.
> **Backend Fix:** Moving the blocking NOAA preloading tasks to a separate thread pool to ensure the API remains responsive during startup.

## Proposed Changes

### 1. Backend: Non-Blocking & Robust NOAA Service
#### [MODIFY] [noaa_service.py](file:///C:/Users/Asus/Documents/ocean3d/backend/app/noaa_service.py)
- **Fix NameError**: Properly define `cache_key` for the registry.
- **Thread Safety**: Ensure the cache registry is handled safely across threads if necessary (using a simple lock if needed, though for a single preload it's fine).
- **Graceful Failure**: Add a `try/except` inside the threaded execution to prevent background exceptions from affecting the main process.

#### [MODIFY] [main.py](file:///C:/Users/Asus/Documents/ocean3d/backend/app/main.py)
- **Lifespan Update**: Ensure `noaa_service.preload()` is truly decoupled and doesn't block the startup sequence.

### 2. Frontend: Resilient Initialization
#### [MODIFY] [index.html](file:///C:/Users/Asus/Documents/ocean3d/frontend/index.html)
- **Boot Decoupling**: Update the `boot()` function to hide the loading screen even if `initCesiumGlobe` takes longer than expected or if non-critical catalog loading fails.
- **Error Handling**: Add `try/catch` around `initCesiumGlobe` calls and `loadCatalog` to ensure one failure doesn't stop the entire application.

## Verification Plan

### Test A: Independent Globe Initialization
- [ ] Start backend.
- [ ] Open website.
- [ ] **Expect**: The "Initializing..." loader disappears and the Cesium globe appears normally within 2-3 seconds, even while NOAA is preloading in the background.

### Test B: Current Layer Availability
- [ ] After the globe is ready, enable "Animated Ocean Currents."
- [ ] **Expect**: The current layer displays the status from the background task (e.g., "READY" or "LOADING").

### Test C: Backend Responsiveness
- [ ] Verify that `/api/health` and `config.js` are served immediately upon server start.
