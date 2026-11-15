"""Native-resolution HiRISE export tests on small synthetic georeferenced rasters (no NASA download)."""

import json
import logging

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from pipeline.export import export_hirise_hd
from pipeline.preview_hd import bounds_around, preview

# Same projection family as ESP_071006_2345_RED_A_01_ORTHO: equirectangular, 50 N standard parallel, local radius.
HIRISE_CRS = "+proj=eqc +lat_ts=50 +lon_0=212.12 +R=3384416.5 +units=m +no_defs"
PIXEL_M = 0.25
CENTER = (54.144, -147.894)


def ew_pixels(ground_m, lat=CENTER[0]):
    """Source pixels across ground_m east-west: eqc metres are true only at the 50 N standard parallel."""
    return ground_m * (3384416.5 / 3_389_500) * np.cos(np.radians(50)) / np.cos(np.radians(lat)) / PIXEL_M


def make_source(path, width=4800, height=320, crs=HIRISE_CRS, nodata_block=True):
    """Write a tiled uint8 GeoTIFF at 0.25 m/pixel centred near the mission coordinate.

    width/height: pixels (4800 px = 1,200 projected m, ~1,090 ground m east-west at 54 N). nodata_block zeroes the north-west corner
    (HiRISE CORE_NULL = 0) so crops there exercise no-data handling.
    """
    rng = np.random.default_rng(7)
    data = rng.integers(20, 236, size=(height, width), dtype=np.uint8)
    if nodata_block:
        data[:40, :200] = 0
    x_center = 3384416.5 * np.cos(np.radians(50)) * np.radians(CENTER[1] + 360 - 212.12)
    y_center = 3384416.5 * np.radians(CENTER[0])
    transform = from_origin(x_center - width * PIXEL_M / 2, y_center + height * PIXEL_M / 2, PIXEL_M, PIXEL_M)
    with rasterio.open(path, "w", driver="GTiff", width=width, height=height, count=1, dtype="uint8",
                       crs=crs, transform=transform, tiled=True, blockxsize=256, blockysize=256) as dataset:
        dataset.write(data, 1)
    return path


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    """Shared synthetic 0.25 m source raster."""
    return make_source(tmp_path_factory.mktemp("hd") / "synthetic_hd.tif")


def meta_for(path):
    """Read the .meta.json written next to an exported JPEG."""
    return json.loads(path.with_suffix(".meta.json").read_text())


def test_native_resolution_is_preserved(source, tmp_path):
    """A small crop keeps every source pixel: 0.25 m stays 0.25 m, never the 1 m DTM grid."""
    out = tmp_path / "hirise.jpg"
    export_hirise_hd(source, bounds_around(*CENTER, 100, 50), out)
    meta = meta_for(out)
    assert meta["output_pixels"] == meta["source_pixels"]
    assert abs(meta["source_pixels"][0] - ew_pixels(100)) <= 2 and abs(meta["source_pixels"][1] - 200) <= 2
    assert meta["effective_resolution_m"] == pytest.approx([PIXEL_M, PIXEL_M])
    assert meta["ground_sampling_m_ew_ns"][0] == pytest.approx(PIXEL_M * np.cos(np.radians(54.144)) / np.cos(np.radians(50)), rel=1e-3)
    assert meta["resampling"] == "none_native" and meta["reprojection"] == "none"


def test_500_m_crop_keeps_about_2000_native_pixels(source, tmp_path):
    out = tmp_path / "hirise.jpg"
    export_hirise_hd(source, bounds_around(*CENTER, 500, 50), out)
    assert abs(meta_for(out)["output_pixels"][0] - ew_pixels(500)) <= 2


def test_4096_native_pixels_fit_without_resampling(source, tmp_path):
    """~932 ground m at 54 N holds ~4096 real pixels, exported natively."""
    out = tmp_path / "hirise.jpg"
    ground = 4090 / ew_pixels(1)
    export_hirise_hd(source, bounds_around(*CENTER, ground, 50), out)
    meta = meta_for(out)
    assert 4088 <= meta["source_pixels"][0] <= 4096 and meta["output_pixels"] == meta["source_pixels"]
    with Image.open(out) as image:
        assert image.size == tuple(meta["output_pixels"])


def test_1024_m_crop_is_capped_at_4096_by_area_averaging(source, tmp_path):
    out = tmp_path / "hirise.jpg"
    export_hirise_hd(source, bounds_around(*CENTER, 1024, 50), out)
    meta = meta_for(out)
    assert meta["source_pixels"][0] > 4096 and meta["output_pixels"][0] == 4096
    assert meta["resampling"] == "average_nodata_aware"


def test_small_crop_is_never_upscaled(source, tmp_path):
    """A 130 m crop gives ~570 real pixels at 54 N; it is not enlarged to claim 4K."""
    out = tmp_path / "hirise.jpg"
    export_hirise_hd(source, bounds_around(*CENTER, 130, 50), out, max_dimension=4096)
    meta = meta_for(out)
    assert meta["output_pixels"] == meta["source_pixels"]
    assert abs(meta["output_pixels"][0] - ew_pixels(130)) <= 2


def test_reduction_uses_area_average_and_preserves_aspect(source, tmp_path):
    out = tmp_path / "hirise.jpg"
    export_hirise_hd(source, bounds_around(*CENTER, 200, 50), out, max_dimension=200)
    meta = meta_for(out)
    assert meta["resampling"] == "average_nodata_aware"
    source_ratio = meta["source_pixels"][0] / meta["source_pixels"][1]
    output_ratio = meta["output_pixels"][0] / meta["output_pixels"][1]
    assert output_ratio == pytest.approx(source_ratio, rel=0.02)
    assert max(meta["output_pixels"]) == 200
    assert meta["effective_resolution_m"][0] == pytest.approx(PIXEL_M * meta["source_pixels"][0] / 200)


def test_bounds_match_request_and_image_grid(source, tmp_path):
    """Exported bounds lie within one source pixel of the request and divide evenly into output pixels."""
    requested = bounds_around(*CENTER, 100, 50)
    out = tmp_path / "hirise.jpg"
    payload = export_hirise_hd(source, requested, out)
    pixel_lat = np.degrees(PIXEL_M / 3384416.5)
    pixel_lon = np.degrees(PIXEL_M / (3384416.5 * np.cos(np.radians(50))))
    for key, tolerance in (("south", pixel_lat), ("north", pixel_lat), ("west", pixel_lon), ("east", pixel_lon)):
        assert abs(payload[key] - requested[key]) <= tolerance * 1.01, key
    width, height = meta_for(out)["output_pixels"]
    assert (payload["east"] - payload["west"]) / width == pytest.approx(pixel_lon, rel=1e-6)
    assert (payload["north"] - payload["south"]) / height == pytest.approx(pixel_lat, rel=1e-6)
    saved = json.loads(out.with_suffix(".bounds.json").read_text())
    assert saved == payload and saved["schema_version"] == "1.0"
    assert "landmark_alignment=not_verified" in saved["processing"]


@pytest.mark.parametrize("bounds", [
    {"south": 54.2, "west": -147.9, "north": 54.1, "east": -147.8},
    {"south": 54.1, "west": -147.8, "north": 54.2, "east": -147.9},
    {"south": 54.1, "west": -147.9, "north": float("nan"), "east": -147.8},
    {"south": 54.1, "west": -147.9},
])
def test_invalid_bounds_fail(source, tmp_path, bounds):
    with pytest.raises(ValueError):
        export_hirise_hd(source, bounds, tmp_path / "hirise.jpg")


def test_crop_outside_coverage_fails_without_output(source, tmp_path):
    out = tmp_path / "hirise.jpg"
    with pytest.raises(ValueError, match="outside the source"):
        export_hirise_hd(source, bounds_around(*CENTER, 3000, 50), out)
    assert not out.exists()


def test_non_mars_crs_is_rejected(tmp_path):
    earth = make_source(tmp_path / "earth.tif", width=400, height=200,
                        crs="+proj=eqc +lat_ts=50 +lon_0=212.12 +R=6371000 +units=m +no_defs")
    with pytest.raises(ValueError, match="Mars"):
        export_hirise_hd(earth, bounds_around(*CENTER, 20, 20), tmp_path / "hirise.jpg")


def test_nodata_is_reported_and_all_nodata_crop_fails(source, tmp_path, caplog):
    """Null (0) pixels are excluded and reported; a crop of only nulls is refused."""
    with rasterio.open(source) as dataset:
        left, top = dataset.transform.c, dataset.transform.f
    from rasterio.warp import transform_bounds
    from pipeline.terrain import MARS_GEOGRAPHIC
    w, s, e, n = transform_bounds(HIRISE_CRS, MARS_GEOGRAPHIC, left, top - 60 * PIXEL_M, left + 400 * PIXEL_M, top, densify_pts=21)
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    out = tmp_path / "partial.jpg"
    export_hirise_hd(source, {"south": s, "west": w, "north": n, "east": e}, out)
    assert 0 < meta_for(out)["nodata_fraction"] < 1
    assert any(getattr(r, "event", "") == "hd_nodata_present" for r in caplog.records)
    w, s, e, n = transform_bounds(HIRISE_CRS, MARS_GEOGRAPHIC, left, top - 30 * PIXEL_M, left + 150 * PIXEL_M, top, densify_pts=21)
    with pytest.raises(ValueError, match="no-data"):
        export_hirise_hd(source, {"south": s, "west": w, "north": n, "east": e}, tmp_path / "empty.jpg")


def test_jpeg_format_quality_and_reference(source, tmp_path):
    """Output is a grayscale JPEG at quality 95; the reference is the unstretched same crop."""
    out, reference = tmp_path / "hirise.jpg", tmp_path / "reference.jpg"
    export_hirise_hd(source, bounds_around(*CENTER, 60, 40), out, reference_path=reference)
    expected = tmp_path / "q95.jpg"
    Image.new("L", (16, 16), 128).save(expected, format="JPEG", quality=95)
    with Image.open(out) as image, Image.open(expected) as probe, Image.open(reference) as ref:
        assert image.format == "JPEG" and image.mode == "L"
        assert image.quantization == probe.quantization
        assert ref.size == image.size
    meta = meta_for(out)
    assert meta["jpeg_quality"] == 95 and meta["stretch"]["method"] == "percentile"


def test_export_is_deterministic(source, tmp_path):
    first, second = tmp_path / "a" / "hirise.jpg", tmp_path / "b" / "hirise.jpg"
    for path in (first, second):
        export_hirise_hd(source, bounds_around(*CENTER, 80, 40), path)
    assert first.read_bytes() == second.read_bytes()
    assert first.with_suffix(".bounds.json").read_bytes() == second.with_suffix(".bounds.json").read_bytes()


def test_windowed_read_covers_only_the_crop(source, tmp_path):
    out = tmp_path / "hirise.jpg"
    export_hirise_hd(source, bounds_around(*CENTER, 100, 50), out)
    col, row, width, height = meta_for(out)["source_window_px"]
    with rasterio.open(source) as dataset:
        assert 0 <= col and 0 <= row and col + width <= dataset.width and row + height <= dataset.height
        assert width * height < dataset.width * dataset.height / 4


def test_structured_logs_share_one_run_id(source, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    preview(source, tmp_path / "preview", *CENTER, 100, 50)
    records = [r for r in caplog.records if hasattr(r, "event")]
    assert len({r.run_id for r in records}) == 1
    exported = next(r for r in records if r.event == "hd_overlay_exported")
    for field in ("source_pixels", "output_pixels", "source_resolution_m", "effective_resolution_m", "crop_bounds",
                  "reprojection", "resampling", "stretch_range", "jpeg_quality", "output_bytes", "duration_ms"):
        assert field in exported.fields, field
    assert exported.fields["landmark_alignment"] == "not_verified"
    inspected = next(r for r in records if r.event == "hd_source_inspected")
    assert inspected.fields["sphere_radius_m"] == pytest.approx(3384416.5)


def test_preview_refuses_public_data_and_non_empty_output(source, tmp_path):
    from pathlib import Path
    public = Path(__file__).resolve().parents[2] / "public" / "data" / "preview"
    with pytest.raises(ValueError, match="public/data"):
        preview(source, public, *CENTER, 50, 50)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "keep").write_text("x")
    with pytest.raises(FileExistsError):
        preview(source, busy, *CENTER, 50, 50)
    result = preview(source, tmp_path / "ok", *CENTER, 50, 50)
    assert (tmp_path / "ok" / "hirise_reference.jpg").exists()
    assert result["meta"]["review_state"] == "diagnostic_unverified"


def test_preview_png_format_writes_transparent_capable_images(source, tmp_path):
    result = preview(source, tmp_path / "png", *CENTER, 50, 50, image_format="png")
    assert (tmp_path / "png" / "hirise.png").exists() and (tmp_path / "png" / "hirise_reference.png").exists()
    assert result["meta"]["format"] == "png" and result["meta"]["nodata_rendering"] == "transparent"
    with pytest.raises(ValueError, match="image_format"):
        preview(source, tmp_path / "bad", *CENTER, 50, 50, image_format="tiff")


def test_bounds_around_uses_mars_radius():
    box = bounds_around(54.144, -147.894, 1000, 1000)
    height_m = np.radians(box["north"] - box["south"]) * 3_389_500
    width_m = np.radians(box["east"] - box["west"]) * 3_389_500 * np.cos(np.radians(54.144))
    assert height_m == pytest.approx(1000) and width_m == pytest.approx(1000)
    with pytest.raises(ValueError):
        bounds_around(54.1, -147.9, -5, 10)
