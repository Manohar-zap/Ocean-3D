# Task List: Copernicus Marine Real-Data Integration

- [ ] Backend: Update `StandardRecord` and `schemas.py` with dual-timestamp and real-data flags.
- [ ] Backend: Implement `InSituTACAdapter` in `adapters.py` for real-world multi-file NetCDF processing.
- [ ] Backend: Update `storage.py` with 24-hour background scheduler and snapshot accumulation/deduplication logic (~3 months history).
- [ ] Backend: Update `ModelNetCDFAdapter` to support monthly subsetting for backfills.
- [ ] Backend: Modify observation endpoints to serve merged trajectories and freshness metadata.
- [ ] Backend: Remove dead `/api/model/grid3d` endpoint.
- [ ] Frontend: Implement dual-freshness badges ("Refresh Time" vs "Platform Report Time") in `index.html`.
- [ ] Frontend: Re-wire trajectory rendering for long-term platform paths.
- [ ] Verification: Run merging and deduplication tests.
