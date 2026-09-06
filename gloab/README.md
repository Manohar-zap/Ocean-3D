# ETOPO Globe

This directory contains the standalone Three.js globe and its local ETOPO1 heightmap server.

## Quick start

The repository includes the generated 2048 x 1024 heightmap, so the large NOAA source archive is not needed for the normal workflow.

1. Install Python 3.10 or newer.
2. Install the server dependencies:

   ```powershell
   py -m pip install numpy tifffile pillow
   ```

3. Start the heightmap server:

   ```powershell
   py etopo_heightmap_server.py
   ```

4. Serve or open `index2_corrected.html` while the server is running. The globe loads its heightmap from `http://127.0.0.1:8765/heightmap`.

## Regenerate the heightmap

If you remove `data/etopo1_2048x1024.f32` or `data/etopo1_2048x1024.json`, the server downloads the NOAA ETOPO1 Bedrock source archive automatically and extracts the GeoTIFF locally:

- Source: https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO1/data/bedrock/grid_registered/georeferenced_tiff/ETOPO1_Bed_g_geotiff.zip
- Downloaded archive: `data/ETOPO1_Bed_g_geotiff.zip`
- Extracted raster: `data/etopo1_bedrock.tif`

The source files are intentionally ignored by Git because they are hundreds of megabytes. Keep enough disk space for both files and expect the first regeneration to take time. The generated `.f32` and `.json` files are the files used by the browser and are small enough to keep in the repository.
