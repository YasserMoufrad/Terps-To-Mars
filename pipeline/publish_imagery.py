"""Publish a validated native-resolution HiRISE preview into public/data/ for the map.

This is the only sanctioned way real HD imagery reaches the app. It refuses DTM-grid display
images (pipeline.run's `export_overlay` output), upscaled or oversized images, and anything
without export_hirise_hd provenance, so the low-resolution overlay can never replace the 4K one.
The map loads `hirise.jpg`, so a fully opaque PNG preview is re-encoded as JPEG; a PNG with
transparent no-data is refused until the app supports PNG overlays (no black edges are introduced).

Publication is staged and rollback-safe, not multi-file atomic: every output is written and
re-validated in a staging folder first; the live set is then replaced file by file (image, meta,
and bounds last, because the app only draws the overlay once bounds exist). If any replacement
fails, the previous files are restored from backups, so a failed publish never leaves a mixed set.
"""

import argparse
import json
import logging
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.crs import CRS

from pipeline.export import validate_geographic_bounds, write_json
from pipeline.logging_config import configure_logging, event, traced

PUBLIC_DATA = Path(__file__).resolve().parents[1] / "public" / "data"
ALLOWED_RESAMPLING = {"none_native", "average_nodata_aware"}
# HiRISE RDR orthoimage product names, e.g. ESP_071006_2345_RED_A_01_ORTHO.JP2 (GeoTIFF conversions allowed).
SOURCE_PATTERN = re.compile(r"^ESP_\d{6}_\d{4}_RED_[A-Z]_\d{2}_ORTHO\.(JP2|jp2|tif|tiff)$")
SOURCE_RESOLUTION_RANGE_M = (0.2, 0.6)  # HiRISE RED orthoimages are 0.25 m or 0.5 m
MARS_RADIUS_RANGE_M = (3_300_000, 3_500_000)
MIN_DIMENSION, MAX_DIMENSION = 512, 4096
MAX_BYTES = 12_000_000  # keep the deployed page loadable; ~4K JPEG q95 is ~5 MB
JPEG_QUALITY = 95
REGISTRATION_METHOD = "phase cross-correlation"
REGISTRATION_STATES = {"measured_within_tolerance", "measured_exceeds_tolerance"}
MIN_REGISTRATION_PATCHES = 4
MAX_REGISTRATION_TOLERANCE_M = 2.0
LIVE_FILES = ("hirise.jpg", "hirise.meta.json", "hirise.bounds.json")  # activation order; bounds last


def _finite(value):
    """True when value is a real finite number (bools and strings are rejected)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _pair(value, integer=False):
    """Return value as a 2-item list of finite numbers (ints when integer=True), or None."""
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(_finite(v) for v in value):
        return None
    if integer and not all(float(v).is_integer() for v in value):
        return None
    return [int(v) for v in value] if integer else [float(v) for v in value]


def _check_meta(meta):
    """Return refusal reasons for the preview metadata: identity, CRS, sampling, pixel counts, finiteness."""
    reasons = []
    source = str(meta.get("source", ""))
    if not SOURCE_PATTERN.match(source):
        reasons.append(f"source {source!r} is not a HiRISE RED orthoimage product name")
    if meta.get("resampling") not in ALLOWED_RESAMPLING:
        reasons.append(f"resampling {meta.get('resampling')!r} is not native or no-data-aware average")
    if meta.get("reprojection") != "none":
        reasons.append("image was reprojected (DTM-grid overlay?)")
    try:
        crs = CRS.from_user_input(meta.get("source_crs")).to_dict() if meta.get("source_crs") else {}
    except Exception:  # noqa: BLE001 - any unparsable CRS is a refusal reason, not a crash
        crs = None
    radius = float((crs or {}).get("R", (crs or {}).get("a", 0)) or 0)
    if not crs or crs.get("proj") != "eqc" or not MARS_RADIUS_RANGE_M[0] <= radius <= MARS_RADIUS_RANGE_M[1]:
        reasons.append("source CRS is not a Mars equirectangular projection")
    resolution = _pair(meta.get("source_resolution_m"))
    if resolution is None or not all(SOURCE_RESOLUTION_RANGE_M[0] <= r <= SOURCE_RESOLUTION_RANGE_M[1] for r in resolution):
        reasons.append(f"source resolution {meta.get('source_resolution_m')!r} is not HiRISE RED sampling")
    pixels, source_pixels = _pair(meta.get("output_pixels"), True), _pair(meta.get("source_pixels"), True)
    if pixels is None or source_pixels is None:
        reasons.append("output_pixels/source_pixels must be two finite integers")
    else:
        if max(pixels) > MAX_DIMENSION or min(pixels) < MIN_DIMENSION:
            reasons.append(f"output pixels {pixels} outside {MIN_DIMENSION}..{MAX_DIMENSION}")
        if any(o > s for o, s in zip(pixels, source_pixels)):
            reasons.append("output is larger than its source window (upscaled)")
        if meta.get("resampling") == "none_native" and pixels != source_pixels:
            reasons.append("none_native resampling but output and source pixel counts differ")
    nodata = meta.get("nodata_fraction", 0)
    if not _finite(nodata) or not 0 <= nodata <= 1:
        reasons.append("nodata_fraction must be a finite fraction")
    stretch = meta.get("stretch") or {}
    if any(k in stretch and not _finite(stretch[k]) for k in ("low", "high")):
        reasons.append("stretch limits must be finite")
    return reasons


def _check_registration(report, meta, bounds):
    """Return refusal reasons for a registration report: same image, overlapping area, method, patches, numbers."""
    south, west, north, east = bounds
    reasons = []
    box = report.get("bounds")
    if not (isinstance(box, list) and len(box) == 4 and all(_finite(v) for v in box)):
        return ["registration report has no finite bounds"]
    if report.get("hd_image") != meta.get("source"):
        reasons.append("registration report is for a different image")
    if not (box[0] < north and box[2] > south and box[1] < east and box[3] > west):
        reasons.append("registration report covers a different area")
    if REGISTRATION_METHOD not in str(report.get("method", "")):
        reasons.append(f"registration method {report.get('method')!r} is not {REGISTRATION_METHOD}")
    reference = str(report.get("reference_image", ""))
    if not reference or reference == report.get("hd_image"):
        reasons.append("registration reference must be a different image")
    patches, tolerance = report.get("measured_patches"), report.get("tolerance_m")
    if not _finite(patches) or patches < MIN_REGISTRATION_PATCHES:
        reasons.append(f"registration measured {patches!r} patches (< {MIN_REGISTRATION_PATCHES})")
    if not _finite(tolerance) or not 0 < tolerance <= MAX_REGISTRATION_TOLERANCE_M:
        reasons.append(f"registration tolerance {tolerance!r} m outside (0, {MAX_REGISTRATION_TOLERANCE_M}]")
    rms, worst = report.get("rms_m"), report.get("max_m")
    if not (_finite(rms) and _finite(worst) and 0 <= rms <= worst):
        reasons.append("registration RMS/max must be finite with 0 <= RMS <= max")
    state = report.get("landmark_alignment")
    if state not in REGISTRATION_STATES:
        reasons.append(f"registration state {state!r} is not a measured state")
    elif not reasons:
        within = rms <= tolerance and worst <= tolerance
        if (state == "measured_within_tolerance") != within:
            reasons.append("registration state disagrees with its own RMS/max and tolerance")
    return reasons


def _refuse(preview_dir, meta, reasons, stage):
    """Log one structured refusal and raise; nothing in the live data folder has changed."""
    event("imagery_publish_refused", logging.ERROR, preview=str(preview_dir), stage=stage, reasons=reasons,
          source=meta.get("source"), resampling=meta.get("resampling"), output_pixels=meta.get("output_pixels"))
    raise ValueError("Refusing to publish HD imagery: " + "; ".join(reasons))


def _activate(staging, data_dir):
    """Move staged files into data_dir in LIVE_FILES order; on any failure restore the previous set.

    Backups of existing live files are kept beside them until every replacement succeeded.
    Returns the list of activated names. Re-raises the original error after rollback.
    """
    backups, activated = {}, []
    try:
        for name in LIVE_FILES:
            live = data_dir / name
            if live.exists():
                backup = data_dir / f".{name}.previous"
                shutil.copy2(live, backup)
                backups[name] = backup
            os.replace(staging / name, live)
            activated.append(name)
    except Exception as error:
        for name in activated:
            if name in backups:
                os.replace(backups.pop(name), data_dir / name)
            else:
                (data_dir / name).unlink(missing_ok=True)
        event("imagery_publish_rolled_back", logging.ERROR, failed_after=activated, reason=repr(error),
              restored=[n for n in activated])
        raise
    finally:
        for backup in backups.values():
            backup.unlink(missing_ok=True)
    return activated


@traced("imagery_publish")
def publish_hd(preview_dir, data_dir=PUBLIC_DATA, registration=None):
    """Copy one validated HD preview (hirise.jpg|png + .bounds.json + .meta.json) into data_dir.

    preview_dir: an output folder of `pipeline.preview_hd`.
    registration: optional `pipeline.registration` report path; its alignment state, RMS and max
    offset (metres) are copied into the published metadata so the map can state them.
    Returns the published metadata. The live files change only if every check passes, and a
    failure part-way through activation restores the previous set.
    """
    preview_dir, data_dir = Path(preview_dir), Path(data_dir)
    meta = json.loads((preview_dir / "hirise.meta.json").read_text())
    bounds = json.loads((preview_dir / "hirise.bounds.json").read_text())
    image_path = preview_dir / f"hirise.{meta.get('format', 'jpg')}"
    reasons = _check_meta(meta)
    try:
        south, west, north, east = validate_geographic_bounds(bounds)
    except ValueError as error:
        reasons.append(str(error))
        south = west = north = east = None
    if not image_path.exists():
        reasons.append(f"{image_path.name} missing")
    report = None
    if registration and south is not None:
        report = json.loads(Path(registration).read_text())
        reasons += _check_registration(report, meta, (south, west, north, east))
    if reasons:
        _refuse(preview_dir, meta, reasons, "metadata")

    pixels = meta["output_pixels"]
    with Image.open(image_path) as image:
        image.load()
        if list(image.size) != list(pixels):
            _refuse(preview_dir, meta, [f"decoded image is {list(image.size)} px, metadata says {pixels}"], "decode")
        if image.mode in ("LA", "RGBA") and np.asarray(image.getchannel("A")).min() < 255:
            _refuse(preview_dir, meta, ["PNG has transparent no-data; the map overlay is JPEG-only"], "decode")
        gray = image.convert("L")

    data_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".publish-", dir=data_dir))
    try:
        gray.save(staging / "hirise.jpg", "JPEG", quality=JPEG_QUALITY, optimize=True)
        size = (staging / "hirise.jpg").stat().st_size
        with Image.open(staging / "hirise.jpg") as written:
            written.load()
            decoded = list(written.size)
        if size > MAX_BYTES or decoded != list(pixels):
            _refuse(preview_dir, meta, [f"staged JPEG is {size} bytes, {decoded} px (limit {MAX_BYTES} bytes, "
                                        f"expected {pixels})"], "staging")

        alignment = {"landmark_alignment": meta.get("landmark_alignment", "not_verified")}
        if report:
            alignment = {"landmark_alignment": report["landmark_alignment"], "registration_rms_m": report["rms_m"],
                         "registration_max_m": report["max_m"], "registration_reference": report["reference_image"],
                         "registration_patches": report["measured_patches"],
                         "registration_tolerance_m": report["tolerance_m"]}
        published = {**meta, **alignment, "format": "jpg", "jpeg_quality": JPEG_QUALITY,
                     "nodata_rendering": "black" if meta.get("nodata_fraction", 0) else "none_present",
                     "published_bytes": size}
        # Rewrite the preview's own format/alignment phrases so the published provenance states one truth.
        processing = bounds["processing"].replace(
            f"landmark_alignment={meta.get('landmark_alignment', 'not_verified')}",
            f"landmark_alignment={alignment['landmark_alignment']}")
        processing = processing.replace("PNG (no-data transparent)",
                                        f"JPEG q{JPEG_QUALITY} (re-encoded from opaque PNG)")
        if report:
            processing += (f"; registration vs {report['reference_image']}: RMS {report['rms_m']:.2f} m, "
                           f"max {report['max_m']:.2f} m over {report['measured_patches']} patches")
        published_bounds = {**bounds, "processing": f"{processing}; published by pipeline.publish_imagery; "
                                                    f"{pixels[0]}x{pixels[1]} px"}
        write_json(staging / "hirise.meta.json", published)
        write_json(staging / "hirise.bounds.json", published_bounds)
        activated = _activate(staging, data_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    sampling = meta.get("ground_sampling_m_ew_ns", meta.get("effective_resolution_m"))
    event("imagery_published", evidence="nasa_derived", source=meta.get("source"), output_pixels=pixels,
          ground_sampling_m_ew_ns=sampling, bytes=size, bounds=[south, west, north, east],
          review_state=meta.get("review_state"), activated=activated, **alignment)
    return published


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path, required=True, help="Output folder of pipeline.preview_hd")
    parser.add_argument("--registration", type=Path, help="registration.json for the same area")
    parser.add_argument("--data-dir", type=Path, default=PUBLIC_DATA)
    arguments = parser.parse_args()
    configure_logging()
    result = publish_hd(arguments.preview, arguments.data_dir, arguments.registration)
    print(json.dumps({k: result[k] for k in ("output_pixels", "landmark_alignment", "published_bytes")}, indent=2))
