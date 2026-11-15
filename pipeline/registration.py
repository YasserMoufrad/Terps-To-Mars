"""Measure HiRISE HD-image registration against the DTM-associated orthoimage (offsets in metres).

This is a measurement, not a correction: no pixels are moved. The ~1 m RED_C orthoimage shares the
DTM's grid, so agreement with it is the first evidence that HD imagery lines up with DTM-derived
hazards and routes. CTX is a coarser secondary check and is not implemented here.
"""

import argparse
import json
import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import Window, transform as window_transform

from pipeline.export import validate_geographic_bounds, write_json
from pipeline.logging_config import configure_logging, event, traced
from pipeline.terrain import MARS_GEOGRAPHIC


def phase_correlation(reference, moving, upsample=20):
    """Return (dy, dx, error): shift in pixels of `moving` relative to `reference`.

    Both are equal-shape 2D float arrays. A feature at (r, c) in reference appears at
    (r + dy, c + dx) in moving. Uses scikit-image's upsampled cross-correlation (1/upsample
    pixel precision, no frame-fixed window that would bias shifts toward zero).
    error: normalized RMS mismatch after alignment (0 = identical, 1 = unrelated).
    """
    from skimage.registration import phase_cross_correlation

    if reference.shape != moving.shape or min(reference.shape) < 8:
        raise ValueError("Patches must share a shape of at least 8 x 8")
    shift, error, _ = phase_cross_correlation(reference - reference.mean(), moving - moving.mean(),
                                              upsample_factor=upsample, normalization=None)
    # scikit-image returns the shift that moves `moving` back onto `reference`.
    return float(-shift[0]), float(-shift[1]), float(error)


def _patch_pair(hd, ref, center_xy, size_px):
    """Read a reference patch and the HD image resampled (area average, measurement only) onto its grid."""
    col, row = ~ref.transform * center_xy
    window = Window(int(round(col - size_px / 2)), int(round(row - size_px / 2)), size_px, size_px)
    if window.col_off < 0 or window.row_off < 0 or window.col_off + size_px > ref.width or window.row_off + size_px > ref.height:
        return None
    reference = ref.read(1, window=window).astype(np.float64)
    transform = window_transform(window, ref.transform)
    with WarpedVRT(hd, crs=ref.crs, transform=transform, width=size_px, height=size_px,
                   resampling=Resampling.average, src_nodata=0, nodata=0) as vrt:
        moving = vrt.read(1).astype(np.float64)
    return reference, moving, window


@traced("image_registration")
def measure_registration(hd_path, reference_path, bounds, grid=3, patch_px=96, tolerance_m=1.0,
                         max_match_error=0.5, min_texture=2.0):
    """Measure offsets of the HD image against the reference orthoimage at grid x grid patches.

    bounds: signed lat/lon area to sample {south, west, north, east}; patches are spread across it.
    patch_px: patch size in reference pixels (~1 m each). tolerance_m: accepted RMS and max offset.
    Patches without texture (std < min_texture) or a poor match (error > max_match_error)
    are skipped, never counted as agreement. Returns a report with per-patch offsets, RMS and max.
    """
    south, west, north, east = validate_geographic_bounds(bounds)
    if grid < 1 or patch_px < 16:
        raise ValueError("Need at least one patch of 16 pixels or more")
    patches = []
    with rasterio.open(hd_path) as hd, rasterio.open(reference_path) as ref:
        for dataset in (hd, ref):
            radius = float(dataset.crs.to_dict().get("R", dataset.crs.to_dict().get("a", 0)) or 0)
            if not 3_300_000 < radius < 3_500_000:
                raise ValueError(f"{Path(dataset.name).name} is not on a Mars sphere")
        left, bottom, right, top = transform_bounds(MARS_GEOGRAPHIC, ref.crs, west, south, east, north, densify_pts=21)
        lat_ts = math.radians(float(ref.crs.to_dict().get("lat_ts", 0)))
        ew_scale = math.cos(math.radians((south + north) / 2)) / math.cos(lat_ts)
        res_x, res_y = abs(ref.transform.a), abs(ref.transform.e)
        for i in range(grid):
            for j in range(grid):
                x = left + (right - left) * (j + 0.5) / grid
                y = top - (top - bottom) * (i + 0.5) / grid
                pair = _patch_pair(hd, ref, (x, y), patch_px)
                record = {"patch": [i, j]}
                if pair is None:
                    record["status"] = "outside_reference"
                else:
                    reference, moving, window = pair
                    record["window_px"] = [int(window.col_off), int(window.row_off), patch_px, patch_px]
                    if (moving == 0).mean() > 0.01 or (reference == 0).mean() > 0.01:
                        record["status"] = "nodata"
                    elif reference.std() < min_texture:
                        record["status"] = "low_texture"
                    else:
                        dy, dx, error = phase_correlation(reference, moving)
                        record.update({"dy_px": dy, "dx_px": dx, "match_error": error,
                                       "north_m": -dy * res_y, "east_m": dx * res_x * ew_scale})
                        record["offset_m"] = math.hypot(record["north_m"], record["east_m"])
                        record["status"] = "measured" if error <= max_match_error and max(abs(dy), abs(dx)) < patch_px / 4 else "ambiguous_match"
                patches.append(record)
    measured = [p for p in patches if p["status"] == "measured"]
    offsets = np.array([p["offset_m"] for p in measured])
    rms = float(np.sqrt(np.mean(offsets ** 2))) if measured else None
    worst = float(offsets.max()) if measured else None
    mean_north = float(np.mean([p["north_m"] for p in measured])) if measured else None
    mean_east = float(np.mean([p["east_m"] for p in measured])) if measured else None
    if len(measured) < 3:
        state = "insufficient_landmarks"
    elif rms <= tolerance_m and worst <= tolerance_m:
        state = "measured_within_tolerance"
    else:
        state = "measured_exceeds_tolerance"
    report = {"schema_version": "1.0", "report_type": "image_registration", "hd_image": Path(hd_path).name,
              "reference_image": Path(reference_path).name, "bounds": [south, west, north, east],
              "method": "upsampled phase cross-correlation on area-averaged HD resampled to the reference grid (measurement only)",
              "patch_px": patch_px, "reference_resolution_m": [res_x, res_y], "tolerance_m": tolerance_m,
              "patches": patches, "measured_patches": len(measured), "rms_m": rms, "max_m": worst,
              "mean_offset_north_m": mean_north, "mean_offset_east_m": mean_east, "landmark_alignment": state,
              "limitations": ("Registration against the DTM-folder orthoimage, not independent ground truth; "
                              "CTX comparison not performed; sub-metre agreement is limited by the 1 m reference.")}
    event("registration_measured", logging.INFO if state == "measured_within_tolerance" else logging.WARNING,
          hd_image=report["hd_image"], reference_image=report["reference_image"], measured_patches=len(measured),
          skipped={s: sum(p["status"] == s for p in patches) for s in {p["status"] for p in patches} if s != "measured"},
          rms_m=rms, max_m=worst, tolerance_m=tolerance_m, landmark_alignment=state)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hd", type=Path, default=Path("pipeline/raw/ESP_071006_2345_RED_A_01_ORTHO.JP2"))
    parser.add_argument("--reference", type=Path, default=Path("pipeline/raw/ESP_071006_2345_RED_C_01_ORTHO.JP2"))
    parser.add_argument("--bounds", type=float, nargs=4, metavar=("SOUTH", "WEST", "NORTH", "EAST"), required=True)
    parser.add_argument("--grid", type=int, default=3)
    parser.add_argument("--tolerance-m", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    configure_logging()
    south, west, north, east = arguments.bounds
    result = measure_registration(arguments.hd, arguments.reference,
                                  {"south": south, "west": west, "north": north, "east": east},
                                  grid=arguments.grid, tolerance_m=arguments.tolerance_m)
    write_json(arguments.output, result)
    print(json.dumps({k: result[k] for k in ("measured_patches", "rms_m", "max_m", "landmark_alignment")}, indent=2))
