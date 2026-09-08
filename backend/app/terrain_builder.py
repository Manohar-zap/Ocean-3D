"""
ETOPO1 terrain-data builder for OCEAN 3D.
Integrated from the legacy standalone etopo_heightmap_server.py.

This module handles:
1. Downloading NOAA ETOPO1 Bedrock 1-arc-minute GeoTIFF ZIP.
2. Extracting the GeoTIFF.
3. Resampling the global DEM to a browser-friendly 2048 x 1024 float32 grid.
4. Generating a packed 16-bit PNG for texture-based elevation decoding.
"""

from __future__ import annotations

import json
import os
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

try:
    import tifffile
except ImportError:
    # This will be resolved when requirements.txt is updated and re-installed
    tifffile = None

# NOAA ETOPO1 Bedrock, grid-registered GeoTIFF.
SOURCE_URL = (
    "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO1/data/"
    "bedrock/grid_registered/georeferenced_tiff/ETOPO1_Bed_g_geotiff.zip"
)

# Paths relative to this file: backend/app/terrain_builder.py
# Targets gloab/data to match the existing API contract in main.py
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "gloab" / "data"
ZIP_PATH = DATA_DIR / "ETOPO1_Bed_g_geotiff.zip"
CACHE_TIF = DATA_DIR / "etopo1_bedrock.tif"
RAW_PATH = DATA_DIR / "etopo1_2048x1024.f32"
PNG_PATH = DATA_DIR / "etopo1_2048x1024_packed.png"
META_PATH = DATA_DIR / "etopo1_2048x1024.json"

OUT_W = 2048
OUT_H = 1024

# ETOPO1 global grid dimensions
SRC_W = 21601
SRC_H = 10801
MIN_ELEV = -11000.0
MAX_ELEV = 9000.0


def download(url: str = SOURCE_URL, path: Path = ZIP_PATH):
    """Download the NOAA ETOPO1 source archive."""
    if path.exists() and path.stat().st_size > 100_000_000:
        print(f"Using existing download: {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")

    print(f"Downloading NOAA ETOPO1 (312 MB) from {url}...")
    req = Request(url, headers={"User-Agent": "OCEAN-3D-Terrain-Builder/1.0"})

    with urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", "0") or 0)
        done = 0
        started = time.time()

        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)

            if total:
                pct = done / total * 100
                rate = done / max(time.time() - started, 0.001) / 1024 / 1024
                print(f"\r{pct:6.2f}%  {done/1024/1024:7.1f}/{total/1024/1024:.1f} MB  {rate:5.1f} MB/s", end="")
    print("\nDownload complete.")
    tmp.replace(path)


def extract_tiff():
    """Extract the GeoTIFF from the downloaded ZIP."""
    if CACHE_TIF.exists() and CACHE_TIF.stat().st_size > 100_000_000:
        print(f"Using cached GeoTIFF: {CACHE_TIF}")
        return

    if not ZIP_PATH.exists():
        raise FileNotFoundError(f"Source ZIP not found at {ZIP_PATH}. Run download() first.")

    print("Extracting GeoTIFF...")
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        names = [n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))]
        if not names:
            raise RuntimeError("No GeoTIFF found inside NOAA ETOPO1 ZIP.")
        name = names[0]
        with z.open(name) as src, open(CACHE_TIF, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
    print(f"Extracted: {CACHE_TIF}")


def resize_global(arr: np.ndarray) -> np.ndarray:
    """
    Resample the 21601x10801 global grid to 2048x1024.
    Treats the input as a regular global sample grid with lon [-180,180] and lat [90,-90].
    """
    arr = np.asarray(arr)

    if arr.shape != (SRC_H, SRC_W):
        raise RuntimeError(f"Unexpected ETOPO1 dimensions {arr.shape}; expected {(SRC_H, SRC_W)}")

    # Drop the duplicated longitude endpoint and duplicate polar endpoint.
    src = arr[:-1, :-1].astype(np.float32)
    src[~np.isfinite(src)] = 0.0

    x = np.linspace(0, src.shape[1] - 1, OUT_W).round().astype(np.int32)
    y = np.linspace(0, src.shape[0] - 1, OUT_H).round().astype(np.int32)

    out = src[np.ix_(y, x)].astype("<f4", copy=False)
    out = np.clip(out, MIN_ELEV, MAX_ELEV).astype("<f4")
    return out


def build_heightmap(force: bool = False):
    """Run the full build pipeline to produce .f32, .png and .json metadata."""
    if not force and RAW_PATH.exists() and META_PATH.exists():
        print("Using existing processed heightmap files in gloab/data.")
        return

    if tifffile is None:
        raise ImportError("tifffile is required for building heightmaps. Install it via requirements.txt.")

    if not CACHE_TIF.exists():
        if not ZIP_PATH.exists():
            download()
        extract_tiff()

    print("Reading ETOPO1 GeoTIFF and resampling...")
    with tifffile.TiffFile(CACHE_TIF) as tif:
        page = tif.pages[0]
        arr = page.asarray()

    print(f"Source DEM loaded: {arr.shape}, dtype={arr.dtype}")
    out = resize_global(arr)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(out.tobytes(order="C"))

    # Create packed 16-bit elevation PNG (R=high, G=low)
    code = np.round((out - MIN_ELEV) / (MAX_ELEV - MIN_ELEV) * 65535.0)
    code = np.clip(code, 0, 65535).astype(np.uint16)
    packed = np.empty((OUT_H, OUT_W, 4), dtype=np.uint8)
    packed[..., 0] = (code >> 8).astype(np.uint8)
    packed[..., 1] = (code & 255).astype(np.uint8)
    packed[..., 2] = 0
    packed[..., 3] = 255
    Image.fromarray(packed, "RGBA").save(PNG_PATH, optimize=True)

    meta = {
        "width": OUT_W,
        "height": OUT_H,
        "dtype": "float32-le",
        "byteOrder": "little-endian",
        "minElevationMeters": MIN_ELEV,
        "maxElevationMeters": MAX_ELEV,
        "longitudeMin": -180.0,
        "longitudeMax": 180.0,
        "latitudeMin": -90.0,
        "latitudeMax": 90.0,
        "sampleConvention": "row 0 = north, column 0 = -180 longitude",
        "source": "NOAA ETOPO1 Bedrock 1 arc-minute Global Relief Model",
        "sourceUrl": SOURCE_URL,
        "packedPng": "/etopo1_2048x1024_packed.png",
        "packedEncoding": "R=high8bits, G=low8bits of unsigned 16-bit normalized elevation code",
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Build complete. Created {RAW_PATH} ({RAW_PATH.stat().st_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    # Allows running as a standalone script for regeneration
    build_heightmap()
