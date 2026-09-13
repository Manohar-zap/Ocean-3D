# Implementation Plan - Optimized NOAA Current Preload & Caching

The goal is to fix the NOAA current layer by implementing an asynchronous backend preloading and caching architecture. This ensures immediate rendering on the frontend, eliminates wait times during animation, and provides a robust UX for real-time data.

## User Review Required

> [!IMPORTANT]
> The backend will now initialize the NOAA field in the background. The API will return a `LOADING` status if the user requests currents before the initial preload completes. The frontend will show "Preparing NOAA surface currents..." during this phase.

> [!TIP]
> To ensure fast initialization, the initial preload will focus on the Indian Ocean (60-100E, -10-30N) with a stride of 4.

## Proposed Changes

### Backend: NOAA Service Optimization

#### [MODIFY] [noaa_service.py](file:///C:/Users/Asus/Documents/ocean3d/backend/app/noaa_service.py)
- **Async Initialization**: Ensure `preload()` is non-blocking and runs in a background task (already initiated in `main.py`).
- **Optimized Initial Bounding Box**: Use `min_lat=-10, max_lat=30, min_lon=50, max_lon=100` and `stride=4` for the initial preload.
- **Processed Cache**: Store data as a structured dictionary containing typed lists or compact objects, not raw JSON.
- **Time Snapping**: Implement `get_closest_noaa_date(requested_time)` to find the best match in the ERDDAP dataset.
- **Cache Registry**: A simple dictionary mapping `(timestamp, bounds, stride)` to the processed field.

### Backend: API Layer

#### [MODIFY] [main.py](file:///C:/Users/Asus/Documents/ocean3d/backend/app/main.py)
- **Status-Aware Endpoint**: Update `/api/model` for `dataset_id=noaa_currents` to return:
    - `{ "status": "LOADING", "message": "Preparing NOAA surface currents..." }` (202 status)
    - `{ "status": "READY", "timestamp": "...", "points": [...] }` (200 status)
    - `{ "status": "ERROR", "detail": "..." }` (502 status)
- **Favicon Fix**: Update the `/favicon.ico` endpoint to return a 204 or a tiny placeholder to silence 404s.

### Frontend: UI & Particle System

#### [MODIFY] [index.html](file:///C:/Users/Asus/Documents/ocean3d/frontend/index.html)
- **State Handling**: Update `loadVectors()` to handle the `LOADING` status by updating the `#hint` element.
- **Atomic Update**: Ensure that when `READY` data arrives, it replaces the `OceanVectorField` without resetting the entire particle system if possible.
- **Performance Optimization**:
    - Review the particle update loop to ensure no `fetch` or heavy allocations occur per frame.
    - Clamp `deltaTime` to prevent jumps after backgrounding the tab.
    - Ensure trail resets are staggered or optimized to prevent "synchronized stutter".

## Verification Plan

### Automated Tests
- **Startup Check**: Verify backend logs show `[NOAA Service] Starting background preload...` and the server is immediately responsive.
- **API Performance**: Measure time from request to 200 OK for a cached region (expected < 50ms).
- **Date Matching**: Verify that requesting "2026-09-01" returns the closest valid NOAA date (e.g., 2026-09-11) and reports it in the response.

### Manual Verification
1.  Restart backend.
2.  Open browser, toggle currents.
3.  Observe "Preparing..." message.
4.  Observe transition to "Source: NOAA (Cached)" and particle appearance.
5.  Verify no stuttering during animation.
6.  Check console for 404s.
