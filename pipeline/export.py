"""Deterministic web-sized raster and JSON exports on a Mars geographic grid."""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import array_bounds
from rasterio.warp import calculate_default_transform, reproject

from pipeline.terrain import MARS_GEOGRAPHIC, signed_longitude
from pipeline.logging_config import traced, event, operation


@traced("json_export")
def write_json(path, payload):
    """Write finite JSON payload deterministically to path; never serialize NaN."""
    Path(path).write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    event("json_exported", filename=Path(path).name, schema_version=payload.get("schema_version"), feature_count=len(payload.get("features", [])))


@traced("raster_export")
def export_overlay(terrain, data, destination, source, max_pixels=1024):
    """Reproject terrain-aligned data; destination selects format, max_pixels limits display size."""
    if data.shape != terrain.elevation.shape or max_pixels < 1:
        raise ValueError("Overlay grid must match terrain and output size must be positive")
    height, width = data.shape
    transform, out_width, out_height = calculate_default_transform(
        terrain.crs, MARS_GEOGRAPHIC, width, height,
        *array_bounds(height, width, terrain.transform))
    scale = max(1, out_width / max_pixels, out_height / max_pixels)
    out_width, out_height = max(1, int(out_width / scale)), max(1, int(out_height / scale))
    transform = transform * rasterio.Affine.scale(scale, scale)
    output = np.full((out_height, out_width), np.nan, dtype="float32")
    with operation("reprojection", source=source, evidence=terrain.evidence):
        reproject(data.astype("float32"), output, src_transform=terrain.transform,
                  src_crs=terrain.crs, src_nodata=np.nan, dst_transform=transform,
                  dst_crs=MARS_GEOGRAPHIC, dst_nodata=np.nan, resampling=Resampling.nearest)
    valid = np.isfinite(output)
    if not valid.any():
        raise ValueError("Overlay has no valid pixels")
    low, high = np.percentile(output[valid], [2, 98])
    gray = np.uint8(np.clip((np.nan_to_num(output, nan=low) - low) / max(high - low, 1e-9), 0, 1) * 255)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() == ".png":
        rgba = np.stack([gray, gray, gray, valid.astype(np.uint8) * 255], axis=-1)
        image = Image.fromarray(rgba)
    else:
        gray[~valid] = 0
        image = Image.fromarray(gray).convert("RGB")
    if terrain.evidence == "simulated":
        ImageDraw.Draw(image).text((2, 2), "SYNTHETIC", fill="red" if image.mode == "RGB" else (255, 0, 0, 255))
    image.save(destination)
    west, south, east, north = array_bounds(out_height, out_width, transform)
    bounds = {"schema_version": "1.0", "south": south, "west": signed_longitude(west),
              "north": north, "east": signed_longitude(east), "source": source,
              "processing": f"Mars lat/lon reprojection; nearest-neighbour downsampling; percentile display stretch; evidence={terrain.evidence}"}
    if bounds["west"] >= bounds["east"]:
        raise ValueError("Antimeridian overlays must be split before export")
    write_json(destination.with_suffix(".bounds.json"), bounds)
    event("overlay_exported", filename=destination.name, evidence=terrain.evidence,
          dimensions=[out_height, out_width], invalid_cells=int((~valid).sum()), source=source)
    return bounds


@traced("image_reprojection")
def aligned_image(path, terrain):
    """Reproject image path to terrain's grid; matching extents do not prove landmark alignment."""
    with rasterio.open(path) as image:
        parameters = image.crs.to_dict() if image.crs else {}
        radius = float(parameters.get("R", parameters.get("a", 0)))
        if not 3_300_000 < radius < 3_500_000:
            raise ValueError("Image must have a Mars CRS")
        output = np.full(terrain.elevation.shape, np.nan, dtype="float32")
        reproject(rasterio.band(image, 1), output, src_transform=image.transform,
                  src_crs=image.crs, src_nodata=image.nodata,
                  dst_transform=terrain.transform, dst_crs=terrain.crs,
                  dst_nodata=np.nan, resampling=Resampling.nearest)
        if not np.isfinite(output).any():
            raise ValueError("Image does not cover the terrain crop")
        event("image_reprojected", source=Path(path).name, invalid_cells=int((~np.isfinite(output)).sum()), landmark_alignment="not_verified")
        return output
