"""Standalone NASA HiRISE DTM slope map: python -m pipeline.slope_mvp.

Reads the real DTM, measures slope with pipeline.terrain.analyze (metric spacing, Mars CRS),
classifies it with the thresholds in hazard_rules.json and publishes slope.png,
slope.meta.json and slope.bounds.json into public/data/. It never reads routes or the
mission scenario, so an infeasible mission cannot stop the diagnostic map from being made.

The DTM is equirectangular (eqc), which is linear in longitude and latitude, so every PNG
pixel is exactly one DTM cell and the geographic bounds are exact; no reprojection or
resampling happens. Unknown cells (no-data, artifact, incomplete gradient) are drawn with a
gray checker pattern, never as a slope class.
"""

import argparse
import json
import logging
import math
import os
import shutil
import tempfile
from pathlib import Path
from time import perf_counter

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform as transform_coordinates

from pipeline.export import validate_geographic_bounds, write_json
from pipeline.logging_config import configure_logging, event, operation, traced
from pipeline.terrain import MARS_GEOGRAPHIC, analyze, load_rules, read_terrain, signed_longitude, threshold

SCHEMA_VERSION = "1.0"
DTM_NAME = "DTEEC_071085_2345_071006_2345_A01.IMG"
DEFAULT_DTM = Path("pipeline/raw") / DTM_NAME
# Habitat-to-scarp corridor plus surroundings (signed degrees). Covers main's placeholder
# endpoints, the traced scarp (54.1635-54.1651 N) and the HiRISE crop.
DEFAULT_BOUNDS = {"south": 54.120, "west": -147.925, "north": 54.175, "east": -147.880}
MAX_PIXELS = 8000 * 8000  # one PNG; larger areas should be tiled instead
LIVE_FILES = ("slope.png", "slope.meta.json", "slope.bounds.json")  # bounds last: the app draws once it exists
ACQUIRE_HINT = ("Download the HiRISE DTM with `python -m pipeline.acquire` (see pipeline/README.md) "
                "so that pipeline/raw/" + DTM_NAME + " exists; synthetic terrain is never published.")

# Palette indices. 0 = outside the analysed footprint (fully transparent).
OUTSIDE, BELOW, CAUTION, CREW_EXCLUDED, ROVER_EXCLUDED, UNKNOWN_A, UNKNOWN_B = range(7)
PALETTE = {
    OUTSIDE: (0, 0, 0, 0),
    BELOW: (77, 163, 255, 150),       # blue: below the crew caution threshold
    CAUTION: (245, 165, 36, 200),     # amber: crew caution
    CREW_EXCLUDED: (229, 72, 77, 220),  # red: crew excluded under the model
    ROVER_EXCLUDED: (142, 78, 198, 235),  # purple: crew and rover excluded under the model
    UNKNOWN_A: (150, 150, 150, 200),  # gray checker: cannot assess
    UNKNOWN_B: (90, 90, 90, 200),
}
CHECKER_CELLS = 4  # unknown-pattern square size in DTM cells


def class_thresholds(rules):
    """Return (caution, crew_exclude, rover_exclude) degrees from the versioned hazard rules."""
    values = tuple(float(threshold(rules, name)) for name in ("crew_caution_deg", "crew_exclude_deg", "rover_exclude_deg"))
    if not values[0] < values[1] <= values[2]:
        raise ValueError("Slope thresholds must increase: caution < crew exclude <= rover exclude")
    return values


def classify(slope, valid, rules):
    """Map slope (degrees, 2D) to palette indices; cells where valid is False become the unknown pattern.

    Comparisons follow hazard_rules.json (">="): 15 is caution, 20 crew-excluded, 24 rover-excluded.
    """
    caution, crew, rover = class_thresholds(rules)
    known = valid & np.isfinite(slope)
    s = np.where(known, slope, 0.0)
    classes = np.full(slope.shape, BELOW, dtype=np.uint8)
    classes[s >= caution] = CAUTION
    classes[s >= crew] = CREW_EXCLUDED
    classes[s >= rover] = ROVER_EXCLUDED
    rows, cols = np.indices(slope.shape)
    checker = ((rows // CHECKER_CELLS + cols // CHECKER_CELLS) % 2).astype(np.uint8)
    classes[~known] = np.where(checker[~known] == 0, UNKNOWN_A, UNKNOWN_B)
    return classes


def window_for_bounds(dataset, bounds, pad, clip=False):
    """Return (col, row, width, height) DTM window covering bounds plus pad cells, and the unpadded offsets.

    bounds: signed lat/lon box; pad: extra cells each side so gradients at the crop edge are complete.
    Raises when the box (without padding) leaves the raster, unless clip=True trims it to the raster
    (the route audit then reports cells beyond the crop as outside the assessed terrain).
    """
    south, west, north, east = validate_geographic_bounds(bounds)
    lon0 = float(dataset.crs.to_dict().get("lon_0", 0))
    # Express longitudes near the CRS central meridian (HiRISE uses 0-360 east) before projecting.
    xs, ys = transform_coordinates(MARS_GEOGRAPHIC, dataset.crs,
                                   [lon0 + signed_longitude(west - lon0), lon0 + signed_longitude(east - lon0)], [north, south])
    col0, row0 = ~dataset.transform * (xs[0], ys[0])
    col1, row1 = ~dataset.transform * (xs[1], ys[1])
    col0, row0 = int(math.floor(col0 + 1e-9)), int(math.floor(row0 + 1e-9))
    col1, row1 = int(math.ceil(col1 - 1e-9)), int(math.ceil(row1 - 1e-9))
    if clip:
        col0, row0 = max(0, col0), max(0, row0)
        col1, row1 = min(dataset.width, col1), min(dataset.height, row1)
    if col0 < 0 or row0 < 0 or col1 > dataset.width or row1 > dataset.height or col1 - col0 < 3 or row1 - row0 < 3:
        raise ValueError("Requested slope bounds leave the DTM coverage")
    pc0, pr0 = max(0, col0 - pad), max(0, row0 - pad)
    pc1, pr1 = min(dataset.width, col1 + pad), min(dataset.height, row1 + pad)
    return (pc0, pr0, pc1 - pc0, pr1 - pr0), (col0 - pc0, row0 - pr0, col1 - col0, row1 - row0)


def grid_bounds(terrain, inner):
    """Signed geographic south/west/north/east of the inner (col, row, width, height) block of terrain."""
    col, row, width, height = inner
    west, north = terrain.lonlat(row, col, center=False)
    east, south = terrain.lonlat(row + height, col + width, center=False)
    return {"south": south, "west": west, "north": north, "east": east}


@traced("slope_analysis")
def compute_slope(dtm_path, bounds, rules):
    """Read dtm_path around bounds (with gradient padding), run terrain.analyze and crop the padding off.

    Returns (terrain, slope degrees, valid mask, inner window, padded window); terrain is the padded crop.
    """
    window_m = threshold(rules, "roughness_window_m")
    with rasterio.open(dtm_path) as dataset:
        pad = int(math.ceil(window_m / abs(dataset.transform.a))) + 2
        padded, inner = window_for_bounds(dataset, bounds, pad)
    if padded[2] * padded[3] > MAX_PIXELS:
        raise ValueError("Slope area too large for one PNG; reduce the bounds or tile it")
    terrain = read_terrain(dtm_path, window=padded)
    result = analyze(terrain, rules)
    col, row, width, height = inner
    crop = (slice(row, row + height), slice(col, col + width))
    return terrain, result["slope"][crop], result["valid"][crop], inner, padded


def write_png(classes, path):
    """Write palette indices (2D uint8) as an indexed PNG with per-index alpha; returns bytes written."""
    image = Image.fromarray(np.ascontiguousarray(classes, dtype=np.uint8))
    flat = [channel for index in range(len(PALETTE)) for channel in PALETTE[index][:3]]
    image.putpalette(flat + [0] * (768 - len(flat)))  # turns the "L" image into palette mode "P"
    alpha = bytes(PALETTE[index][3] for index in range(len(PALETTE)))
    image.save(path, format="PNG", optimize=True, transparency=alpha)
    return path.stat().st_size


def build_meta(classes, slope, valid, terrain, inner, bounds, rules, source, checksum):
    """Assemble slope.meta.json: provenance, grid, thresholds, legend and class statistics."""
    caution, crew, rover = class_thresholds(rules)
    total = classes.size
    known = valid & np.isfinite(slope)
    counts = {
        "below_caution": int((classes == BELOW).sum()), "crew_caution": int((classes == CAUTION).sum()),
        "crew_excluded": int((classes == CREW_EXCLUDED).sum()), "crew_and_rover_excluded": int((classes == ROVER_EXCLUDED).sum()),
        "unknown": int(((classes == UNKNOWN_A) | (classes == UNKNOWN_B)).sum()),
    }
    spacing = terrain.column_spacing[inner[1]:inner[1] + inner[3]]
    legend = [
        {"class": "below_caution", "label": f"Below {caution:g}° (below crew caution threshold)", "rgba": list(PALETTE[BELOW]), "min_deg": None, "max_deg": caution},
        {"class": "crew_caution", "label": f"{caution:g}° to <{crew:g}° (crew caution)", "rgba": list(PALETTE[CAUTION]), "min_deg": caution, "max_deg": crew},
        {"class": "crew_excluded", "label": f"{crew:g}° to <{rover:g}° (crew excluded under model)", "rgba": list(PALETTE[CREW_EXCLUDED]), "min_deg": crew, "max_deg": rover},
        {"class": "crew_and_rover_excluded", "label": f"{rover:g}° and above (crew and rover excluded under model)", "rgba": list(PALETTE[ROVER_EXCLUDED]), "min_deg": rover, "max_deg": None},
        {"class": "unknown", "label": "Unknown (no data, artifact or incomplete gradient): cannot assess", "rgba": list(PALETTE[UNKNOWN_A]), "min_deg": None, "max_deg": None},
    ]
    return {
        "schema_version": SCHEMA_VERSION, "evidence": "nasa_derived", "source": source, "source_sha256": checksum,
        "source_crs": terrain.crs.to_string(), "product": "NASA HiRISE DTM-derived slope",
        "grid": {"pixels": [int(classes.shape[1]), int(classes.shape[0])], "dtm_window_px": [int(v) for v in inner],
                 "projected_cell_m": float(terrain.resolution),
                 "ground_cell_m_ew": [float(spacing.min()), float(spacing.max())], "ground_cell_m_ns": float(terrain.resolution)},
        "bounds": bounds, "reprojection": "none (equirectangular is linear in lat/lon; one PNG pixel = one DTM cell)",
        "method": "numpy.gradient on metric spacing with east-west latitude correction (pipeline.terrain.analyze); slope = atan(|grad|)",
        "thresholds_deg": {"crew_caution": caution, "crew_exclude": crew, "rover_exclude": rover},
        "threshold_sources": {name: rules["rules"][name]["classification"] for name in ("crew_caution_deg", "crew_exclude_deg", "rover_exclude_deg")},
        "legend": legend, "class_cells": counts, "unknown_fraction": counts["unknown"] / total,
        "slope_max_deg": float(np.nanmax(np.where(known, slope, np.nan))) if known.any() else None,
        "limitations": ("Approximately 1 m DTM grid: does not resolve sub-metre rocks, overhangs, loose soil or surface "
                        "instability. Thresholds are planning assumptions, not certified crew or rover limits; the 24° "
                        "rover value is provisional until Brianna's rover design supplies one. Unknown cells are never safe."),
    }


def _validate_staged(staging, classes, bounds):
    """Re-read staged files: decoded PNG size and indices must match the grid; bounds must be a valid box."""
    with Image.open(staging / "slope.png") as image:
        if image.size != (classes.shape[1], classes.shape[0]) or image.mode != "P":
            raise ValueError("Staged slope.png does not match the DTM grid")
        if not np.array_equal(np.asarray(image), classes):
            raise ValueError("Staged slope.png pixels differ from the classified grid")
    staged = json.loads((staging / "slope.bounds.json").read_text())
    validate_geographic_bounds(staged)
    if any(abs(staged[k] - bounds[k]) > 1e-9 for k in ("south", "west", "north", "east")):
        raise ValueError("Staged slope.bounds.json differs from the grid bounds")


def _activate(staging, data_dir, names=LIVE_FILES):
    """Move staged files into data_dir in `names` order (default LIVE_FILES); on failure restore the previous set."""
    backups = []
    try:
        for name in names:
            live = data_dir / name
            if live.exists():
                backup = data_dir / f".{name}.previous"
                shutil.copy2(live, backup)
                backups.append((live, backup))
            os.replace(staging / name, live)
    except Exception:
        for live, backup in backups:
            try:
                os.replace(backup, live)
            except OSError:
                event("slope_restore_failed", logging.ERROR, file=live.name, backup=backup.name)
        event("slope_publish_rolled_back", logging.ERROR, restored=[live.name for live, _ in backups])
        raise
    for _, backup in backups:
        backup.unlink(missing_ok=True)


@traced("slope_publication")
def publish_slope(dtm_path=DEFAULT_DTM, data_dir=Path("public/data"), bounds=None, rules=None):
    """Compute, classify, stage, validate and publish the slope map; returns the metadata dict.

    dtm_path: real HiRISE DTM (.IMG); missing input fails with acquisition instructions.
    data_dir: destination (public/data). bounds: signed lat/lon box (default: habitat-to-scarp corridor).
    """
    started = perf_counter()
    dtm_path, data_dir = Path(dtm_path), Path(data_dir)
    bounds = dict(bounds or DEFAULT_BOUNDS)
    if not dtm_path.exists():
        event("slope_input_missing", logging.ERROR, path=str(dtm_path), reason="dtm_not_found")
        raise FileNotFoundError(f"{dtm_path} not found. {ACQUIRE_HINT}")
    rules = rules or load_rules()
    terrain, slope, valid, inner, padded = compute_slope(dtm_path, bounds, rules)
    if terrain.evidence != "nasa_derived":
        raise ValueError("Only nasa_derived terrain may be published")
    classes = classify(slope, valid, rules)
    grid = grid_bounds(terrain, inner)
    manifest = dtm_path.with_suffix(dtm_path.suffix + ".json")
    checksum = json.loads(manifest.read_text()).get("sha256") if manifest.exists() else None
    meta = build_meta(classes, slope, valid, terrain, inner, grid, rules, dtm_path.name, checksum)
    data_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".slope-", dir=data_dir))
    try:
        png_bytes = write_png(classes, staging / "slope.png")
        write_json(staging / "slope.meta.json", meta)
        write_json(staging / "slope.bounds.json", {
            "schema_version": SCHEMA_VERSION, **grid, "source": dtm_path.stem,
            "processing": ("NASA HiRISE DTM-derived slope, ~1 m grid; one PNG pixel per DTM cell, no reprojection; "
                           "classes from hazard_rules.json; unknown cells gray-checkered; evidence=nasa_derived")})
        _validate_staged(staging, classes, grid)
        _activate(staging, data_dir)
    except Exception as error:
        event("slope_publish_refused", logging.ERROR, reason=str(error))
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    event("slope_published", dataset_id=dtm_path.stem, evidence="nasa_derived", pixels=meta["grid"]["pixels"],
          bounds=grid, class_cells=meta["class_cells"], unknown_fraction=meta["unknown_fraction"],
          slope_max_deg=meta["slope_max_deg"], thresholds_deg=meta["thresholds_deg"], png_bytes=png_bytes,
          padded_window=list(padded), duration_ms=(perf_counter() - started) * 1000)
    return meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dtm", type=Path, default=DEFAULT_DTM)
    parser.add_argument("--data-dir", type=Path, default=Path("public/data"))
    parser.add_argument("--bounds", type=float, nargs=4, metavar=("SOUTH", "WEST", "NORTH", "EAST"))
    arguments = parser.parse_args()
    configure_logging()
    box = dict(zip(("south", "west", "north", "east"), arguments.bounds)) if arguments.bounds else None
    with operation("slope_mvp", dataset_id=arguments.dtm.name):
        result = publish_slope(arguments.dtm, arguments.data_dir, box)
    print(json.dumps({k: result[k] for k in ("grid", "bounds", "class_cells", "unknown_fraction", "slope_max_deg")}, indent=2))
