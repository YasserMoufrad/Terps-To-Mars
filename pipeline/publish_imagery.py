"""Publish a validated native-resolution HiRISE preview into public/data/ for the map.

This is the only sanctioned way real HD imagery reaches the app. It refuses DTM-grid display
images (pipeline.run's `export_overlay` output), upscaled or oversized images, and anything
without export_hirise_hd provenance, so the low-resolution overlay can never replace the 4K one.
The map loads `hirise.jpg`, so a fully opaque PNG preview is re-encoded as JPEG; a PNG with
transparent no-data is refused until the app supports PNG overlays (no black edges are introduced).
"""

import argparse
import json
import logging
import os
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from pipeline.export import validate_geographic_bounds, write_json
from pipeline.logging_config import configure_logging, event, traced

PUBLIC_DATA = Path(__file__).resolve().parents[1] / "public" / "data"
ALLOWED_RESAMPLING = {"none_native", "average_nodata_aware"}
MAX_DIMENSION = 4096
MAX_BYTES = 12_000_000  # keep the deployed page loadable; ~4K JPEG q95 is ~5 MB
JPEG_QUALITY = 95


def _atomic_save_jpeg(image, path, quality):
    """Write a JPEG to a temporary name in the same folder, then rename into place (Vite EBUSY rule)."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(handle)
    try:
        image.save(temporary, "JPEG", quality=quality, optimize=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


@traced("imagery_publish")
def publish_hd(preview_dir, data_dir=PUBLIC_DATA, registration=None):
    """Copy one validated HD preview (hirise.jpg|png + .bounds.json + .meta.json) into data_dir.

    preview_dir: an output folder of `pipeline.preview_hd`.
    registration: optional `pipeline.registration` report path; its alignment state, RMS and max
    offset (metres) are copied into the published metadata so the map can state them.
    Returns the published metadata. Nothing is written unless every check passes.
    """
    preview_dir, data_dir = Path(preview_dir), Path(data_dir)
    meta = json.loads((preview_dir / "hirise.meta.json").read_text())
    bounds = json.loads((preview_dir / "hirise.bounds.json").read_text())
    image_path = preview_dir / f"hirise.{meta.get('format', 'jpg')}"
    reasons = []
    if not str(meta.get("source", "")).startswith("ESP_") or "RED" not in str(meta.get("source", "")):
        reasons.append("source is not a HiRISE RED orthoimage")
    if meta.get("resampling") not in ALLOWED_RESAMPLING:
        reasons.append(f"resampling {meta.get('resampling')!r} is not native or no-data-aware average")
    if meta.get("reprojection") != "none":
        reasons.append("image was reprojected (DTM-grid overlay?)")
    pixels = meta.get("output_pixels") or [0, 0]
    if max(pixels) > MAX_DIMENSION or min(pixels) < 512:
        reasons.append(f"output pixels {pixels} outside 512..{MAX_DIMENSION}")
    if any(o > s for o, s in zip(pixels, meta.get("source_pixels") or [0, 0])):
        reasons.append("output is larger than its source window (upscaled)")
    if not image_path.exists():
        reasons.append(f"{image_path.name} missing")
    south, west, north, east = validate_geographic_bounds(bounds)
    report = None
    if registration:
        report = json.loads(Path(registration).read_text())
        overlap = (report["bounds"][0] < north and report["bounds"][2] > south
                   and report["bounds"][1] < east and report["bounds"][3] > west)
        if report.get("hd_image") != meta.get("source") or not overlap:
            reasons.append("registration report is for a different image or area")
    if not reasons and image_path.suffix == ".png":
        with Image.open(image_path) as png:
            if png.mode in ("LA", "RGBA") and np.asarray(png.getchannel("A")).min() < 255:
                reasons.append("PNG has transparent no-data; the map overlay is JPEG-only")
    if reasons:
        event("imagery_publish_refused", logging.ERROR, preview=str(preview_dir), reasons=reasons,
              source=meta.get("source"), resampling=meta.get("resampling"), output_pixels=pixels)
        raise ValueError("Refusing to publish HD imagery: " + "; ".join(reasons))

    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "hirise.jpg"
    with Image.open(image_path) as image:
        image.load()
        gray = image.convert("L")
    _atomic_save_jpeg(gray, target, JPEG_QUALITY)
    size = target.stat().st_size
    if size > MAX_BYTES:
        target.unlink()
        event("imagery_publish_refused", logging.ERROR, reasons=[f"JPEG is {size} bytes > {MAX_BYTES}"])
        raise ValueError(f"Published JPEG too large ({size} bytes)")

    alignment = {"landmark_alignment": meta.get("landmark_alignment", "not_verified")}
    if report:
        alignment = {"landmark_alignment": report["landmark_alignment"], "registration_rms_m": report["rms_m"],
                     "registration_max_m": report["max_m"], "registration_reference": report["reference_image"],
                     "registration_patches": report["measured_patches"]}
    published = {**meta, **alignment, "format": "jpg", "jpeg_quality": JPEG_QUALITY,
                 "nodata_rendering": "black" if meta.get("nodata_fraction", 0) else "none_present",
                 "published_bytes": size}
    sampling = meta.get("ground_sampling_m_ew_ns", meta.get("effective_resolution_m"))
    # Rewrite the preview's own format/alignment phrases so the published provenance states one truth.
    processing = bounds["processing"].replace(
        f"landmark_alignment={meta.get('landmark_alignment', 'not_verified')}",
        f"landmark_alignment={alignment['landmark_alignment']}")
    processing = processing.replace("PNG (no-data transparent)", f"JPEG q{JPEG_QUALITY} (re-encoded from opaque PNG)")
    if report:
        processing += (f"; registration vs {report['reference_image']}: RMS {report['rms_m']:.2f} m, "
                       f"max {report['max_m']:.2f} m over {report['measured_patches']} patches")
    published_bounds = {**bounds, "processing": f"{processing}; published by pipeline.publish_imagery; "
                                                f"{pixels[0]}x{pixels[1]} px"}
    write_json(data_dir / "hirise.bounds.json", published_bounds)
    write_json(data_dir / "hirise.meta.json", published)
    event("imagery_published", evidence="nasa_derived", source=meta.get("source"), output_pixels=pixels,
          ground_sampling_m_ew_ns=sampling, bytes=size, bounds=[south, west, north, east],
          review_state=meta.get("review_state"), **alignment)
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
