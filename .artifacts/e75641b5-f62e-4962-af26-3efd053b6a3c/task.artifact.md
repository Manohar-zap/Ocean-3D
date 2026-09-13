# Task List - Fix Regression & Restore Globe

- [x] Fix `NameError` and define `cache_key` in `backend/app/noaa_service.py`.
- [x] Move NOAA `preload()` logic to run via `threading.Thread` to avoid blocking the main event loop.
- [x] Refactor frontend `boot()` in `index.html` to be more resilient and decouple Cesium from NOAA.
- [x] Add safety checks to `loadVectors` and `refreshAll`.
- [x] Verify immediate globe appearance upon site load.
- [x] Verify NOAA currents become available after the background task completes.
