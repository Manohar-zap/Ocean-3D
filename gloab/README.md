# ETOPO Globe

This directory contains the standalone Three.js globe. The terrain data is managed by the backend terrain builder.

## Quick start

The repository includes the generated 2048 x 1024 heightmap, so the large NOAA source archive is not needed for the normal workflow.

1. Start the FastAPI backend (see `backend/README.md`).
2. Serve or open `index2_corrected.html`. The globe loads its heightmap from the backend API.

## Regenerate the heightmap

If you need to regenerate `data/etopo1_2048x1024.f32` or `data/etopo1_2048x1024.json`, use the integrated terrain builder in the backend:

```powershell
cd backend
python -m app.terrain_builder
```

The builder downloads the NOAA ETOPO1 Bedrock source archive automatically and extracts the GeoTIFF locally:

- Source: https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO1/data/bedrock/grid_registered/georeferenced_tiff/ETOPO1_Bed_g_geotiff.zip
- Downloaded archive: `data/ETOPO1_Bed_g_geotiff.zip`
- Extracted raster: `data/etopo1_bedrock.tif`

The source files are intentionally ignored by Git because they are hundreds of megabytes. Keep enough disk space for both files and expect the first regeneration to take time. The generated `.f32` and `.json` files are the files used by the browser and are small enough to keep in the repository.
