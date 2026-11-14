"""Publishing HD imagery into the app's data folder: only validated native-resolution previews pass."""

import json
import logging

import numpy as np
import pytest
from PIL import Image

from pipeline.preview_hd import bounds_around, preview
from pipeline.publish_imagery import publish_hd
from pipeline.tests.test_registration import CENTER, texture, write


@pytest.fixture()
def hd_preview(tmp_path):
    """A real preview_hd output folder built from a synthetic 0.25 m Mars raster (PNG, fully opaque)."""
    source = write(tmp_path / "ESP_000000_0000_RED_A_01_ORTHO.tif", texture(800), 0.25)
    preview(source, tmp_path / "preview", *CENTER, 150, 150, image_format="png")  # ~600 px, above the 512 floor
    return tmp_path / "preview"


def test_publish_writes_jpeg_bounds_and_meta(hd_preview, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    data = tmp_path / "data"
    meta = publish_hd(hd_preview, data)
    with Image.open(data / "hirise.jpg") as image:
        assert image.format == "JPEG" and list(image.size) == meta["output_pixels"]
    bounds = json.loads((data / "hirise.bounds.json").read_text())
    assert bounds["schema_version"] == "1.0" and -180 <= bounds["west"] < bounds["east"] <= 180
    assert "publish_imagery" in bounds["processing"] and "landmark_alignment=not_verified" in bounds["processing"]
    assert "PNG (no-data transparent)" not in bounds["processing"]  # published file is an opaque JPEG
    assert json.loads((data / "hirise.meta.json").read_text())["resampling"] == "none_native"
    logged = [r for r in caplog.records if getattr(r, "event", "") == "imagery_published"][0].fields
    assert logged["evidence"] == "nasa_derived" and logged["landmark_alignment"] == "not_verified"
    assert not list(data.glob("*.tmp"))


def test_publish_refuses_dtm_grid_overlay_and_writes_nothing(hd_preview, tmp_path, caplog):
    """pipeline.run's export_overlay output (reprojected onto the ~1 m DTM grid) must never replace HD imagery."""
    meta_path = hd_preview / "hirise.meta.json"
    meta = json.loads(meta_path.read_text())
    meta_path.write_text(json.dumps({**meta, "resampling": "bilinear", "reprojection": "dtm_grid"}))
    data = tmp_path / "data"
    with pytest.raises(ValueError, match="Refusing"):
        publish_hd(hd_preview, data)
    assert not (data / "hirise.jpg").exists()
    assert any(getattr(r, "event", "") == "imagery_publish_refused" for r in caplog.records)


def test_publish_refuses_upscaled_or_oversized(hd_preview, tmp_path):
    meta_path = hd_preview / "hirise.meta.json"
    meta = json.loads(meta_path.read_text())
    meta_path.write_text(json.dumps({**meta, "source_pixels": [100, 100]}))
    with pytest.raises(ValueError, match="upscaled"):
        publish_hd(hd_preview, tmp_path / "a")
    meta_path.write_text(json.dumps({**meta, "output_pixels": [8192, 8192], "source_pixels": [8192, 8192]}))
    with pytest.raises(ValueError, match="outside"):
        publish_hd(hd_preview, tmp_path / "b")


def test_publish_refuses_transparent_png_for_jpeg_map(hd_preview, tmp_path):
    with Image.open(hd_preview / "hirise.png") as image:
        gray, alpha = (np.asarray(band).copy() for band in image.split())
    alpha[:, :10] = 0
    Image.merge("LA", (Image.fromarray(gray), Image.fromarray(alpha))).save(hd_preview / "hirise.png")
    with pytest.raises(ValueError, match="transparent"):
        publish_hd(hd_preview, tmp_path / "data")


def test_publish_copies_matching_registration_and_rejects_mismatch(hd_preview, tmp_path):
    meta = json.loads((hd_preview / "hirise.meta.json").read_text())
    box = bounds_around(*CENTER, 200, 200)
    report = {"hd_image": meta["source"], "reference_image": "ref.tif", "rms_m": 0.4, "max_m": 0.6,
              "measured_patches": 9, "landmark_alignment": "measured_within_tolerance",
              "bounds": [box["south"], box["west"], box["north"], box["east"]]}
    path = tmp_path / "registration.json"
    path.write_text(json.dumps(report))
    published = publish_hd(hd_preview, tmp_path / "data", path)
    assert published["landmark_alignment"] == "measured_within_tolerance" and published["registration_rms_m"] == 0.4
    processing = json.loads((tmp_path / "data" / "hirise.bounds.json").read_text())["processing"]
    assert "not_verified" not in processing and "RMS 0.40 m" in processing
    path.write_text(json.dumps({**report, "hd_image": "other.JP2"}))
    with pytest.raises(ValueError, match="different image"):
        publish_hd(hd_preview, tmp_path / "data2", path)
