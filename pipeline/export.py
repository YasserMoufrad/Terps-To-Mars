"""Deterministic web-sized raster and JSON exports on a Mars geographic grid."""

import json
import os
import tempfile
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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
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
        if image.width < 128:
            image = image.resize((128, max(1, round(image.height * 128 / image.width))), Image.Resampling.NEAREST)
        ImageDraw.Draw(image).text((2, 2), "SYNTHETIC", fill="red" if image.mode == "RGB" else (255, 0, 0, 255))
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        image.save(temporary, format="PNG" if destination.suffix.lower() == ".png" else "JPEG")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
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


HD_MAX_DIMENSION = 4096
HD_JPEG_QUALITY = 95


def validate_geographic_bounds(bounds):
    """Return (south, west, north, east) from bounds (signed degrees) or raise on an invalid box."""
    try:
        south, west, north, east = (float(bounds[key]) for key in ("south", "west", "north", "east"))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Bounds need numeric south, west, north and east") from error
    if not all(np.isfinite([south, west, north, east])):
        raise ValueError("Bounds must be finite")
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError("Bounds must satisfy south < north and west < east in signed degrees")
    return south, west, north, east


def _validate_mars_image(dataset):
    """Reject images lacking north-up Mars georeferencing; dataset is an open Rasterio reader.

    Returns (CRS parameters, sphere radius in metres). The radius window (3,300-3,500 km)
    accepts HiRISE local radii (3,384.4 km here) and rejects Earth (6,371 km).
    """
    if dataset.crs is None:
        raise ValueError("Image has no CRS")
    parameters = dataset.crs.to_dict()
    radius = float(parameters.get("R", parameters.get("a", 0)) or 0)
    if not 3_300_000 < radius < 3_500_000:
        raise ValueError(f"Image CRS radius {radius} m is not a Mars sphere")
    if parameters.get("units", "m") != "m":
        raise ValueError("Image CRS must use metres")
    transform = dataset.transform
    if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
        raise ValueError("Image must be north-up without rotation")
    if dataset.count < 1:
        raise ValueError("Image has no bands")
    return parameters, radius


def stretch_to_uint8(values, valid, stretch):
    """Map values (2D array) to uint8 using only valid pixels (bool mask).

    stretch: 'percentile' = deterministic 2nd-98th percentile display stretch;
    'none' = unenhanced reference (identity for 8-bit data, min-max otherwise).
    Returns (gray uint8 array, low, high); invalid pixels become 0.
    """
    if stretch == "none":
        if values.dtype == np.uint8:
            low, high = 0.0, 255.0
        else:
            low, high = float(values[valid].min()), float(values[valid].max())
    elif stretch == "percentile":
        low, high = (float(v) for v in np.percentile(values[valid], [2, 98]))
    else:
        raise ValueError("stretch must be 'percentile' or 'none'")
    scaled = (values.astype("float64") - low) / max(high - low, 1e-9)
    gray = np.round(np.clip(scaled, 0, 1) * 255).astype(np.uint8)
    gray[~valid] = 0
    return gray, low, high


def _write_jpeg(gray, path, quality):
    """Atomically write gray (2D uint8) to path as a grayscale JPEG at the given quality (1-100)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, suffix=".tmp") as stream:
        temporary = Path(stream.name)
    try:
        Image.fromarray(gray, mode="L").save(temporary, format="JPEG", quality=int(quality), optimize=True)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@traced("hd_imagery_export")
def export_hirise_hd(source_path, bounds, output_path, max_dimension=HD_MAX_DIMENSION,
                     quality=HD_JPEG_QUALITY, stretch="percentile", nodata=None, label="diagnostic_unverified",
                     reference_path=None):
    """Export a native-resolution HiRISE crop read directly from the source (never via the DTM grid).

    bounds: requested crop, signed Mars lat/lon degrees {south, west, north, east}.
    max_dimension: output cap in pixels; larger crops are area-averaged, smaller crops are never upscaled.
    stretch: 'percentile' (display) or 'none' (unenhanced reference).
    nodata: source null value; defaults to the file's no-data, else HiRISE CORE_NULL 0.
    label: review state recorded in metadata; DTM landmark alignment is not verified here.
    reference_path: optional second JPEG with no stretch, written from the same decoded pixels.
    Writes output_path (JPEG), <stem>.bounds.json (schema 1.0 overlay contract) and <stem>.meta.json.
    """
    from time import perf_counter
    from rasterio.warp import transform_bounds
    from rasterio.windows import Window, from_bounds as window_from_bounds, transform as window_transform

    started = perf_counter()
    south, west, north, east = validate_geographic_bounds(bounds)
    if isinstance(max_dimension, bool) or not isinstance(max_dimension, int) or max_dimension < 1:
        raise ValueError("max_dimension must be a positive integer")
    if not 1 <= int(quality) <= 100:
        raise ValueError("quality must be 1-100")
    source_path, output_path = Path(source_path), Path(output_path)
    with rasterio.open(source_path) as dataset:
        parameters, radius = _validate_mars_image(dataset)
        if parameters.get("proj") != "eqc":
            # Equirectangular is the HiRISE DTM-product projection; other projections would need a warp path.
            raise ValueError("Only equirectangular (eqc) sources are supported; no warp path is implemented")
        null = nodata if nodata is not None else (dataset.nodata if dataset.nodata is not None else 0)
        resolution_m = (abs(dataset.transform.a), abs(dataset.transform.e))
        event("hd_source_inspected", dataset_id=source_path.stem, width_px=dataset.width, height_px=dataset.height,
              bands=dataset.count, dtype=dataset.dtypes[0], crs=dataset.crs.to_string(), sphere_radius_m=radius,
              resolution_m=list(resolution_m), nodata=null, driver=dataset.driver,
              compression=str(dataset.compression.value) if dataset.compression else None,
              source_bounds=list(dataset.bounds), transform=list(dataset.transform)[:6])
        # Geographic box -> projected box. Equirectangular maps each axis linearly, so this is exact.
        left, bottom, right, top = transform_bounds(MARS_GEOGRAPHIC, dataset.crs, west, south, east, north, densify_pts=21)
        requested = window_from_bounds(left, bottom, right, top, dataset.transform)
        col0 = int(np.floor(requested.col_off + 1e-6))
        row0 = int(np.floor(requested.row_off + 1e-6))
        col1 = int(np.ceil(requested.col_off + requested.width - 1e-6))
        row1 = int(np.ceil(requested.row_off + requested.height - 1e-6))
        if col0 < 0 or row0 < 0 or col1 > dataset.width or row1 > dataset.height:
            event("hd_crop_rejected", level=40, reason="outside_source_coverage", requested_bounds=[south, west, north, east],
                  window=[col0, row0, col1 - col0, row1 - row0], source_shape=[dataset.height, dataset.width])
            raise ValueError("Requested crop lies outside the source image coverage")
        if col1 <= col0 or row1 <= row0:
            raise ValueError("Requested crop is smaller than one source pixel")
        window = Window(col0, row0, col1 - col0, row1 - row0)
        native_shape = (row1 - row0, col1 - col0)  # rows, columns of real source pixels
        scale = max(1.0, native_shape[0] / max_dimension, native_shape[1] / max_dimension)
        out_shape = (max(1, int(round(native_shape[0] / scale))), max(1, int(round(native_shape[1] / scale))))
        resampling = "none_native" if out_shape == native_shape else "average"
        # Windowed read decodes only the crop; any reduction is area averaging, never enlargement.
        values = dataset.read(1, window=window, out_shape=out_shape,
                              resampling=Resampling.average if resampling == "average" else Resampling.nearest)
        crop_transform = window_transform(window, dataset.transform)
        projected = array_bounds(native_shape[0], native_shape[1], crop_transform)
        geo_west, geo_south, geo_east, geo_north = transform_bounds(dataset.crs, MARS_GEOGRAPHIC, *projected, densify_pts=21)
        crs_label = dataset.crs.to_string()
    valid = values != null
    if np.issubdtype(values.dtype, np.floating):
        valid &= np.isfinite(values)
    if not valid.any():
        event("hd_crop_rejected", level=40, reason="no_valid_pixels", window=[col0, row0, native_shape[1], native_shape[0]])
        raise ValueError("Requested crop contains only no-data pixels")
    nodata_fraction = float((~valid).mean())
    if nodata_fraction > 0:
        event("hd_nodata_present", level=30, nodata_fraction=nodata_fraction, rendering="black_excluded_from_stretch")
    gray, low, high = stretch_to_uint8(values, valid, stretch)
    _write_jpeg(gray, output_path, quality)
    if reference_path is not None:
        _write_jpeg(stretch_to_uint8(values, valid, "none")[0], Path(reference_path), quality)
    effective_m = (resolution_m[0] * native_shape[1] / out_shape[1], resolution_m[1] * native_shape[0] / out_shape[0])
    # Projected metres are true only at the standard parallel (lat_ts); east-west ground spacing
    # at the crop centre scales by cos(lat)/cos(lat_ts). ground_m is what a viewer actually sees.
    center_lat = np.radians((geo_south + geo_north) / 2)
    ew_scale = np.cos(center_lat) / np.cos(np.radians(float(parameters.get("lat_ts", 0))))
    ground_m = (float(effective_m[0] * ew_scale), float(effective_m[1]))
    processing = (f"Native HiRISE pixels read in a window from {source_path.name}; no DTM-grid intermediate; "
                  f"no warp (equirectangular is linear in lat/lon); resampling={resampling}; "
                  f"stretch={stretch} [{low:.1f}, {high:.1f}]; JPEG q{int(quality)}; "
                  f"effective {effective_m[0]:.3f} m/pixel projected, ~{ground_m[0]:.3f} m E-W ground; "
                  f"landmark_alignment=not_verified; {label}")
    payload = {"schema_version": "1.0", "south": geo_south, "west": signed_longitude(geo_west),
               "north": geo_north, "east": signed_longitude(geo_east), "source": source_path.stem,
               "processing": processing}
    if payload["west"] >= payload["east"]:
        raise ValueError("Antimeridian overlays must be split before export")
    write_json(output_path.with_suffix(".bounds.json"), payload)
    meta = {"schema_version": "1.0", "source": source_path.name, "source_crs": crs_label,
            "source_resolution_m": list(resolution_m), "source_window_px": [col0, row0, native_shape[1], native_shape[0]],
            "source_pixels": [native_shape[1], native_shape[0]], "output_pixels": [out_shape[1], out_shape[0]],
            "effective_resolution_m": list(effective_m), "ground_sampling_m_ew_ns": list(ground_m),
            "resampling": resampling, "reprojection": "none",
            "stretch": {"method": stretch, "low": low, "high": high}, "jpeg_quality": int(quality),
            "nodata_value": null, "nodata_fraction": nodata_fraction, "requested_bounds": [south, west, north, east],
            "landmark_alignment": "not_verified", "review_state": label,
            "limitations": ("Map-projected 0.25 m sampling is not 0.25 m optical resolution; visible rocks are "
                            "candidates requiring inspection, not verified hazards; the DTM stays ~1 m.")}
    write_json(output_path.with_suffix(".meta.json"), meta)
    event("hd_overlay_exported", filename=output_path.name, dataset_id=source_path.stem,
          source_pixels=meta["source_pixels"], output_pixels=meta["output_pixels"],
          source_resolution_m=list(resolution_m), effective_resolution_m=list(effective_m),
          ground_sampling_m_ew_ns=list(ground_m), crop_bounds=[payload["south"], payload["west"], payload["north"], payload["east"]],
          reprojection="none", resampling=resampling, stretch=stretch, stretch_range=[low, high],
          jpeg_quality=int(quality), output_bytes=output_path.stat().st_size, nodata_fraction=nodata_fraction,
          landmark_alignment="not_verified", review_state=label, duration_ms=(perf_counter() - started) * 1000)
    return payload
