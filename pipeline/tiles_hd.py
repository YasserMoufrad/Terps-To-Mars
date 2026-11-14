"""Cut native-resolution HiRISE into a Leaflet EPSG:4326 tile pyramid (habitat-to-scarp corridor).

One 4K overlay covers ~1 km; the walk from the habitat to the scarp spans ~3 km, and many 4K
overlays would all download at page load. Tiles load only where the viewer looks, like CTX.

Grid: Leaflet's CRS.EPSG4326 (level z = 2^(z+1) x 2^z tiles of 256 px; tile (x, y) spans
lon -180 + x*180/2^z eastward and lat 90 - y*180/2^z southward), so tiles line up with the
CTX/THEMIS basemaps. The HiRISE orthoimage is equirectangular, so lat/lon map linearly to
source pixels: no warp. Every output pixel is a no-data-aware box average of the source pixels
it covers, or the single nearest source pixel where the tile grid is finer than the source;
no pixel is interpolated or invented. Null (0) source pixels become transparent.
"""

import argparse
import json
import logging
import math
import os
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform as project
from rasterio.windows import Window

from pipeline.export import validate_geographic_bounds, write_json
from pipeline.logging_config import configure_logging, event, traced
from pipeline.terrain import MARS_GEOGRAPHIC

TILE = 256
WEBP_QUALITY = 80
READ_FACTORS = (1, 2, 4, 8, 16, 32)


def tile_range(bounds, zoom):
    """Leaflet EPSG4326 tile columns/rows covering bounds at zoom: (x0, x1, y0, y1), inclusive."""
    south, west, north, east = bounds
    span = 180.0 / 2 ** zoom  # degrees per tile, both axes
    x0, x1 = math.floor((west + 180) / span), math.floor((east + 180) / span - 1e-12)
    y0, y1 = math.floor((90 - north) / span), math.floor((90 - south) / span - 1e-12)
    return x0, x1, y0, y1


def tile_bounds(x, y, zoom):
    """(south, west, north, east) of Leaflet EPSG4326 tile (x, y, zoom)."""
    span = 180.0 / 2 ** zoom
    west, north = -180 + x * span, 90 - y * span
    return north - span, west, north, west + span


def _edges(start, stop, count):
    """count+1 evenly spaced fractional edges from start to stop (source pixel coordinates)."""
    return np.linspace(start, stop, count + 1)


def _box_average(values, valid, row_edges, col_edges):
    """No-data-aware box average over [row_edges] x [col_edges] cells of values (uint8 block).

    Each output cell covers source pixels floor(edge0)..max(floor(edge1), floor(edge0)+1); a cell
    narrower than one source pixel takes that single pixel (nearest, no interpolation).
    Returns (gray uint8, alpha uint8): alpha 255 when at least half the covered pixels are valid.
    """
    # Work on the sub-block this tile covers only (an integral image of the whole corridor per
    # tile would cost O(corridor) per tile).
    top = max(0, int(np.floor(row_edges.min())) - 1)
    left = max(0, int(np.floor(col_edges.min())) - 1)
    bottom = min(values.shape[0], int(np.ceil(row_edges.max())) + 2)
    right = min(values.shape[1], int(np.ceil(col_edges.max())) + 2)
    if bottom <= top or right <= left:
        empty = np.zeros((len(row_edges) - 1, len(col_edges) - 1), np.uint8)
        return empty, empty.copy()
    values, valid = values[top:bottom, left:right], valid[top:bottom, left:right]
    row_edges, col_edges = row_edges - top, col_edges - left
    h, w = values.shape
    r0 = np.clip(np.floor(row_edges[:-1]).astype(int), 0, h)
    r1 = np.clip(np.maximum(np.floor(row_edges[1:]).astype(int), r0 + 1), 0, h)
    c0 = np.clip(np.floor(col_edges[:-1]).astype(int), 0, w)
    c1 = np.clip(np.maximum(np.floor(col_edges[1:]).astype(int), c0 + 1), 0, w)
    total = np.zeros((h + 1, w + 1), np.int64)
    count = np.zeros((h + 1, w + 1), np.int64)
    total[1:, 1:] = np.cumsum(np.cumsum(values.astype(np.int64) * valid, 0), 1)
    count[1:, 1:] = np.cumsum(np.cumsum(valid.astype(np.int64), 0), 1)
    R0, R1, C0, C1 = r0[:, None], r1[:, None], c0[None, :], c1[None, :]
    box = lambda s: s[R1, C1] - s[R0, C1] - s[R1, C0] + s[R0, C0]
    sums, counts = box(total), box(count)
    area = np.maximum((R1 - R0) * (C1 - C0), 1)
    gray = np.where(counts > 0, np.round(sums / np.maximum(counts, 1)), 0).astype(np.uint8)
    alpha = np.where(counts * 2 >= area, 255, 0).astype(np.uint8)
    return gray, alpha


def _promote(staging, output):
    """Move the finished staging folder to `output` (which must not exist).

    A directory rename is preferred; Docker bind mounts on Windows can refuse it (PermissionError),
    so the fallback copies the complete set and then removes staging. tiles.json is copied last,
    so a reader never sees a manifest for tiles that are not yet in place.
    """
    try:
        os.replace(staging, output)
        return "rename"
    except PermissionError:
        manifest = staging / "tiles.json"
        shutil.copytree(staging, output, ignore=lambda folder, names: ["tiles.json"] if Path(folder) == staging else [])
        shutil.copy2(manifest, output / "tiles.json")
        shutil.rmtree(staging, ignore_errors=True)
        event("hd_tiles_promoted_by_copy", logging.WARNING, output=str(output), reason="directory rename refused")
        return "copy"


def _save(gray, alpha, path):
    """Write one tile as lossy WebP with alpha (transparent where alpha is 0)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba = np.dstack([gray, gray, gray, alpha])
    Image.fromarray(rgba, "RGBA").save(path, "WEBP", quality=WEBP_QUALITY, method=4)


@traced("hd_tile_pyramid")
def build_pyramid(source, bounds, output, min_zoom=12, max_zoom=17, registration=None, read_factor=1,
                  url_prefix="hirise-tiles", role="core"):
    """Write {z}/{x}/{y}.webp tiles and tiles.json for the signed lat/lon bounds into output.

    source: HiRISE RED orthoimage (equirectangular, null 0). bounds: {south, west, north, east}.
    max_zoom: deepest level (17 ~ 0.19 m E-W x 0.32 m N-S per tile pixel at 54 N; the map
    enlarges it at 18). registration: optional pipeline.registration report copied into tiles.json.
    read_factor: 1 reads native pixels (corridor "4K" detail); 4 reads a no-data-aware 4x average
    (~1 m, "1080p-equivalent" context ring) so a wide area stays small; 16 (~4 m) suits the whole-strip
    "wide" set at zoom 9-11. url_prefix/role: where the app finds this set under public/data and
    whether it is the native core, the reduced context ring or the wide strip.
    The pyramid is built in a temporary folder and moved into place at the end (Vite EBUSY rule).
    """
    started = time.perf_counter()
    south, west, north, east = validate_geographic_bounds(bounds)
    if not 0 <= min_zoom <= max_zoom <= 19:
        raise ValueError("Need 0 <= min_zoom <= max_zoom <= 19")
    if read_factor not in READ_FACTORS:
        raise ValueError(f"read_factor must be one of {READ_FACTORS} (powers of two match the JP2 overviews)")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Tile output folder must be empty or absent")
    with rasterio.open(source) as dataset:
        radius = float(dataset.crs.to_dict().get("R", 0) or 0)
        if not 3_300_000 < radius < 3_500_000:
            raise ValueError("Source is not on a Mars sphere")
        # Read the corridor once at native resolution (one JP2 decode, not one per tile).
        xs, ys = project(MARS_GEOGRAPHIC, dataset.crs, [west, east], [north, south])
        inv = ~dataset.transform
        (c_w, r_n), (c_e, r_s) = inv * (xs[0], ys[0]), inv * (xs[1], ys[1])
        col0, row0 = max(0, math.floor(min(c_w, c_e))), max(0, math.floor(min(r_n, r_s)))
        col1 = min(dataset.width, math.ceil(max(c_w, c_e)))
        row1 = min(dataset.height, math.ceil(max(r_n, r_s)))
        if col1 - col0 < 2 or row1 - row0 < 2:
            raise ValueError("Bounds fall outside the HiRISE image")
        nodata = dataset.nodata if dataset.nodata is not None else 0
        window = Window(col0, row0, col1 - col0, row1 - row0)
        if read_factor == 1:
            block = dataset.read(1, window=window)
        else:
            # GDAL's average skips the declared null, so edges are not darkened by no-data.
            from rasterio.enums import Resampling
            shape = (max(1, (row1 - row0) // read_factor), max(1, (col1 - col0) // read_factor))
            block = dataset.read(1, window=window, out_shape=shape, resampling=Resampling.average)
        src_crs, src_transform = dataset.crs, dataset.transform
        res = [v * read_factor for v in dataset.res]
    valid = block != nodata
    if not valid.any():
        raise ValueError("Corridor contains only no-data")
    low, high = (float(v) for v in np.percentile(block[valid], [2, 98]))
    lut = np.clip(np.round((np.arange(256) - low) / max(high - low, 1) * 255), 0, 255).astype(np.uint8)
    lut[int(nodata)] = 0
    stretched = lut[block]
    event("hd_tiles_source_read", source=Path(source).name, window_px=[col0, row0, col1 - col0, row1 - row0],
          read_factor=read_factor, role=role,
          nodata_fraction=float(1 - valid.mean()), stretch=[low, high], evidence="nasa_derived",
          duration_s=round(time.perf_counter() - started, 1))

    def source_px(lon, lat):
        """Fractional (col, row) in `block` for arrays of lon/lat (linear equirectangular mapping)."""
        x, y = project(MARS_GEOGRAPHIC, src_crs, list(lon), list(lat))
        cols, rows = (~src_transform) * (np.asarray(x), np.asarray(y))
        scale_c = (col1 - col0) / block.shape[1]  # source pixels per block pixel (read_factor, exact)
        scale_r = (row1 - row0) / block.shape[0]
        return (np.asarray(cols) - col0) / scale_c, (np.asarray(rows) - row0) / scale_r

    # Stage beside the destination so the final rename stays on one filesystem.
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=output.parent))
    counts, total_bytes = {}, 0
    try:
        # Deepest level straight from source pixels; tiles are clipped to the corridor bounds.
        level = {}
        x0, x1, y0, y1 = tile_range((south, west, north, east), max_zoom)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                t_south, t_west, t_north, t_east = tile_bounds(x, y, max_zoom)
                lon_edges, lat_edges = _edges(t_west, t_east, TILE), _edges(t_north, t_south, TILE)
                cols, _ = source_px(lon_edges, np.full(TILE + 1, (t_north + t_south) / 2))
                _, rows = source_px(np.full(TILE + 1, (t_west + t_east) / 2), lat_edges)
                gray, alpha = _box_average(stretched, valid, rows, cols)
                # Outside the corridor box or the read block is transparent, never stretched edge data.
                lon_c = (lon_edges[:-1] + lon_edges[1:]) / 2
                lat_c = (lat_edges[:-1] + lat_edges[1:]) / 2
                inside = (((lat_c >= south) & (lat_c <= north))[:, None] & ((lon_c >= west) & (lon_c <= east))[None, :])
                inside &= ((rows[:-1] >= 0) & (rows[1:] <= stretched.shape[0]))[:, None]
                inside &= ((cols[:-1] >= 0) & (cols[1:] <= stretched.shape[1]))[None, :]
                alpha = np.where(inside, alpha, 0).astype(np.uint8)
                if alpha.any():
                    level[(x, y)] = (gray, alpha)
        for zoom in range(max_zoom, min_zoom - 1, -1):
            for (x, y), (gray, alpha) in level.items():
                path = staging / str(zoom) / str(x) / f"{y}.webp"
                _save(gray, alpha, path)
                total_bytes += path.stat().st_size
            counts[zoom] = len(level)
            if zoom == min_zoom:
                break
            # Parent = 2x2 children averaged over valid pixels only (no-data never darkens edges).
            parents = {}
            for (x, y) in level:
                parents.setdefault((x // 2, y // 2), None)
            next_level = {}
            for (px, py) in parents:
                g = np.zeros((2 * TILE, 2 * TILE), np.float64)
                a = np.zeros((2 * TILE, 2 * TILE), np.float64)
                for dx in (0, 1):
                    for dy in (0, 1):
                        child = level.get((2 * px + dx, 2 * py + dy))
                        if child:
                            g[dy * TILE:(dy + 1) * TILE, dx * TILE:(dx + 1) * TILE] = child[0]
                            a[dy * TILE:(dy + 1) * TILE, dx * TILE:(dx + 1) * TILE] = child[1] > 0
                weight = a.reshape(TILE, 2, TILE, 2).sum(axis=(1, 3))
                summed = (g * a).reshape(TILE, 2, TILE, 2).sum(axis=(1, 3))
                gray = np.where(weight > 0, np.round(summed / np.maximum(weight, 1)), 0).astype(np.uint8)
                alpha = np.where(weight >= 2, 255, 0).astype(np.uint8)
                if alpha.any():
                    next_level[(px, py)] = (gray, alpha)
            level = next_level
        report = None
        if registration:
            report = json.loads(Path(registration).read_text())
        meta = {"schema_version": "1.0", "source": Path(source).name, "bounds": {
                    "south": south, "west": west, "north": north, "east": east},
                "url_template": f"{url_prefix}/{{z}}/{{x}}/{{y}}.webp", "role": role, "read_factor": read_factor,
                "tile_size": TILE, "grid": "leaflet_epsg4326",
                "min_zoom": min_zoom, "max_native_zoom": max_zoom, "tile_counts": {str(z): n for z, n in counts.items()},
                "bytes": total_bytes, "source_resolution_m": list(res), "stretch": {"method": "percentile_2_98",
                "low": low, "high": high}, "resampling": "nodata_aware_box_average; nearest single pixel where the tile grid is finer than the source",
                "reprojection": "none (equirectangular is linear in lat/lon)", "evidence": "nasa_derived",
                "landmark_alignment": report["landmark_alignment"] if report else "not_verified",
                "registration_rms_m": report["rms_m"] if report else None,
                "registration_max_m": report["max_m"] if report else None,
                "limitations": "0.25 m map sampling is not 0.25 m optical resolution; visible rocks are candidates, not verified hazards; one global display stretch."}
        write_json(staging / "tiles.json", meta)
        if output.exists():
            output.rmdir()
        output.parent.mkdir(parents=True, exist_ok=True)
        _promote(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    event("hd_tiles_written", source=Path(source).name, tile_counts=counts, bytes=total_bytes,
          zooms=[min_zoom, max_zoom], landmark_alignment=meta["landmark_alignment"], evidence="nasa_derived",
          duration_s=round(time.perf_counter() - started, 1))
    return meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("pipeline/raw/ESP_071006_2345_RED_A_01_ORTHO.JP2"))
    parser.add_argument("--bounds", type=float, nargs=4, metavar=("SOUTH", "WEST", "NORTH", "EAST"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-zoom", type=int, default=12)
    parser.add_argument("--max-zoom", type=int, default=17)
    parser.add_argument("--registration", type=Path)
    parser.add_argument("--read-factor", type=int, default=1, help="1 = native core, 4 = ~1 m context ring")
    parser.add_argument("--url-prefix", default="hirise-tiles", help="path of this tile set under public/data")
    parser.add_argument("--role", choices=["core", "context", "wide"], default="core",
                        help="wide (whole strip, low zoom) < context (~1 m ring) < core (native corridor)")
    arguments = parser.parse_args()
    configure_logging()
    s, w, n, e = arguments.bounds
    result = build_pyramid(arguments.source, {"south": s, "west": w, "north": n, "east": e}, arguments.output,
                           arguments.min_zoom, arguments.max_zoom, arguments.registration,
                           arguments.read_factor, arguments.url_prefix, arguments.role)
    print(json.dumps({k: result[k] for k in ("tile_counts", "bytes", "landmark_alignment")}, indent=2))
