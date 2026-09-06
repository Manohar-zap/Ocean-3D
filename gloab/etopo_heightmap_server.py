"""
ETOPO1 local heightmap server for the 3D Earth project.

What it does:
1. Downloads NOAA ETOPO1 Bedrock 1-arc-minute GeoTIFF ZIP (~312 MB).
2. Extracts the GeoTIFF.
3. Resamples the global DEM to a browser-friendly 2048 x 1024 float32 grid.
4. Saves:
      data/etopo1_2048x1024.f32
      data/etopo1_2048x1024.json
5. Starts a local HTTP server on http://127.0.0.1:8765/
6. Serves /heightmap as the raw float32 grid.

Install:
    py -m pip install numpy tifffile requests

Run:
    py etopo_heightmap_server.py

The HTML can fetch:
    http://127.0.0.1:8765/heightmap
"""

from __future__ import annotations

import io
import json
import math
import os
import struct
import sys
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

try:
    import tifffile
except ImportError:
    print("Missing dependency: tifffile")
    print("Run: py -m pip install numpy tifffile pillow")
    raise

# NOAA ETOPO1 Bedrock, grid-registered GeoTIFF.
# ETOPO1 is 21601 x 10801, 1 arc-minute, WGS84, vertical datum sea level.
SOURCE_URL = (
    "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO1/data/"
    "bedrock/grid_registered/georeferenced_tiff/ETOPO1_Bed_g_geotiff.zip"
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ZIP_PATH = DATA_DIR / "ETOPO1_Bed_g_geotiff.zip"
CACHE_TIF = DATA_DIR / "etopo1_bedrock.tif"
RAW_PATH = DATA_DIR / "etopo1_2048x1024.f32"
PNG_PATH = DATA_DIR / "etopo1_2048x1024_packed.png"
META_PATH = DATA_DIR / "etopo1_2048x1024.json"

OUT_W = 2048
OUT_H = 1024
PORT = 8765

# ETOPO1 global grid:
# longitude: -180..180, 1 arc-minute, 21601 nodes
# latitude:  +90..-90, 1 arc-minute, 10801 nodes
SRC_W = 21601
SRC_H = 10801
MIN_ELEV = -11000.0
MAX_ELEV = 9000.0


def download(url: str, path: Path):
    if path.exists() and path.stat().st_size > 100_000_000:
        print(f"Using existing download: {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")

    print("Downloading NOAA ETOPO1...")
    print("This is about 312 MB and only needs to happen once.")
    req = Request(url, headers={"User-Agent": "ETOPO1-local-Earth-explorer/1.0"})

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
    print()

    tmp.replace(path)


def extract_tiff():
    if CACHE_TIF.exists() and CACHE_TIF.stat().st_size > 100_000_000:
        print(f"Using cached GeoTIFF: {CACHE_TIF}")
        return

    print("Extracting GeoTIFF...")
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        names = [n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))]
        if not names:
            raise RuntimeError("NO GeoTIFF found inside NOAA ETOPO1 ZIP.")
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
    Resample the 21601x10801 global grid to 2048x1024 by block-area
    averaging. This keeps real ETOPO values while making browser use practical.

    The source is grid-registered. We treat the output as a regular global
    sample grid with lon in [-180,180) and lat in [-90,90].
    """
    arr = np.asarray(arr)

    if arr.shape != (SRC_H, SRC_W):
        raise RuntimeError(
            f"Unexpected ETOPO1 dimensions {arr.shape}; expected {(SRC_H, SRC_W)}"
        )

    # Drop the duplicated longitude endpoint and duplicate polar endpoint.
    src = arr[:-1, :-1].astype(np.float32)

    # Replace any nodata-ish nonfinite values.
    src[~np.isfinite(src)] = 0.0

    # Exact integer-ish reduction is not possible because 21600/2048 is
    # non-integer. Use nearest samples in latitude/longitude. For the visual
    # Earth and sea-level classification this preserves coastline/bathymetry
    # better than converting through an 8-bit image.
    x = np.linspace(0, src.shape[1] - 1, OUT_W).round().astype(np.int32)
    y = np.linspace(0, src.shape[0] - 1, OUT_H).round().astype(np.int32)

    out = src[np.ix_(y, x)].astype("<f4", copy=False)

    # Clamp impossible values only to ETOPO1's physical range.
    out = np.clip(out, MIN_ELEV, MAX_ELEV).astype("<f4")
    return out


def build_heightmap():
    if RAW_PATH.exists() and META_PATH.exists():
        print("Using existing processed heightmap.")
        return

    print("Reading ETOPO1 GeoTIFF. This may take a little time...")
    with tifffile.TiffFile(CACHE_TIF) as tif:
        page = tif.pages[0]
        arr = page.asarray()

    print(f"Source DEM loaded: {arr.shape}, dtype={arr.dtype}")
    out = resize_global(arr)

    RAW_PATH.write_bytes(out.tobytes(order="C"))

    # Also create a browser-friendly packed 16-bit elevation PNG.
    # R = high byte, G = low byte. B/A are constant.
    # This avoids relying on browser support for 16-bit/float PNG textures.
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
    print(f"Created {RAW_PATH} ({RAW_PATH.stat().st_size/1024/1024:.1f} MB)")


class Handler(BaseHTTPRequestHandler):
    def _headers(self, content_type, length, cache="no-store"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cache)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (
                b"ETOPO1 local heightmap server is running.\n"
                b"GET /heightmap\n"
                b"GET /heightmap-meta\n"
            )
            self._headers("text/plain; charset=utf-8", len(body))
            self.wfile.write(body)
            return

        if self.path == "/heightmap-meta":
            body = META_PATH.read_bytes()
            self._headers("application/json", len(body))
            self.wfile.write(body)
            return

        if self.path == "/etopo1_2048x1024_packed.png":
            size = PNG_PATH.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(size))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            with open(PNG_PATH, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            return

        if self.path == "/heightmap":
            size = RAW_PATH.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()

            with open(RAW_PATH, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            return

        self.send_response(404)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"Not found")

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    DATA_DIR.mkdir(exist_ok=True)

    print("=== Local NOAA ETOPO1 Heightmap Server ===")

    if RAW_PATH.exists() and META_PATH.exists():
        print("Using committed processed heightmap; source ETOPO1 files are not required.")
    else:
        download(SOURCE_URL, ZIP_PATH)
        extract_tiff()
        build_heightmap()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print()
    print(f"READY: http://127.0.0.1:{PORT}/")
    print(f"HEIGHTMAP: http://127.0.0.1:{PORT}/heightmap")
    print("Keep this window open while your HTML is running.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
