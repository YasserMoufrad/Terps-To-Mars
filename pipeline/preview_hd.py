"""Standalone native-resolution HiRISE preview; imagery only, no routes or mission approval."""

import argparse
import json
import math
from pathlib import Path

from pipeline.export import export_hirise_hd
from pipeline.logging_config import configure_logging, event, traced
from pipeline.terrain import MARS_RADIUS_M


def bounds_around(center_lat, center_lon, width_m, height_m):
    """Geographic box around a centre (signed degrees) with ground size width_m x height_m.

    Uses the project Mars radius (3,389.5 km); east-west degrees are scaled by cos(latitude).
    """
    values = (center_lat, center_lon, width_m, height_m)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        raise ValueError("Centre and size must be finite numbers")
    if width_m <= 0 or height_m <= 0:
        raise ValueError("Crop size must be positive")
    if not -90 < center_lat < 90 or not -180 <= center_lon <= 180:
        raise ValueError("Centre must be signed latitude/longitude")
    half_lat = math.degrees(height_m / 2 / MARS_RADIUS_M)
    half_lon = math.degrees(width_m / 2 / (MARS_RADIUS_M * math.cos(math.radians(center_lat))))
    return {"south": center_lat - half_lat, "west": center_lon - half_lon,
            "north": center_lat + half_lat, "east": center_lon + half_lon}


@traced("hd_preview")
def preview(source, output, center_lat, center_lon, width_m, height_m, max_dimension=4096, quality=95,
            image_format="jpg"):
    """Write a display image and an unenhanced reference for one crop into an empty output directory.

    output: ignored directory (never public/data); produces hirise.<fmt> (2-98 % stretch),
    hirise_reference.<fmt> (no stretch) and their .bounds.json / .meta.json files.
    image_format: "jpg" (null pixels black) or "png" (null pixels transparent, no black seams).
    The centre is a diagnostic coordinate, not a confirmed scarp or mission area.
    """
    if image_format not in {"jpg", "png"}:
        raise ValueError("image_format must be jpg or png")
    output = Path(output)
    public_data = (Path(__file__).resolve().parents[1] / "public/data").resolve()
    if output.resolve() == public_data or public_data in output.resolve().parents:
        raise ValueError("Write previews to an ignored directory; public/data placeholders belong to Yasser")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Output directory must be empty")
    bounds = bounds_around(center_lat, center_lon, width_m, height_m)
    event("hd_preview_requested", center=[center_lat, center_lon], size_m=[width_m, height_m],
          requested_bounds=bounds, max_dimension=max_dimension, jpeg_quality=quality, image_format=image_format,
          review_state="diagnostic_unverified", landmark_alignment="not_verified")
    display = export_hirise_hd(source, bounds, output / f"hirise.{image_format}", max_dimension, quality, "percentile",
                               reference_path=output / f"hirise_reference.{image_format}")
    meta = json.loads((output / "hirise.meta.json").read_text())
    return {"bounds": display, "meta": meta}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("pipeline/raw/ESP_071006_2345_RED_A_01_ORTHO.JP2"))
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True, help="Signed longitude (-180..180)")
    parser.add_argument("--width-m", type=float, default=1024)
    parser.add_argument("--height-m", type=float, default=1024)
    parser.add_argument("--max-dimension", type=int, default=4096)
    parser.add_argument("--quality", type=int, default=95)
    parser.add_argument("--format", choices=["jpg", "png"], default="jpg",
                        help="png makes HiRISE null pixels transparent")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    configure_logging()
    result = preview(arguments.source, arguments.output, arguments.center_lat, arguments.center_lon,
                     arguments.width_m, arguments.height_m, arguments.max_dimension, arguments.quality,
                     arguments.format)
    print(json.dumps(result["meta"], indent=2))
