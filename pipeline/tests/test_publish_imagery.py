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
    report = registration_report(meta)
    path = tmp_path / "registration.json"
    path.write_text(json.dumps(report))
    published = publish_hd(hd_preview, tmp_path / "data", path)
    assert published["landmark_alignment"] == "measured_within_tolerance" and published["registration_rms_m"] == 0.4
    processing = json.loads((tmp_path / "data" / "hirise.bounds.json").read_text())["processing"]
    assert "not_verified" not in processing and "RMS 0.40 m" in processing
    path.write_text(json.dumps({**report, "hd_image": "other.JP2"}))
    with pytest.raises(ValueError, match="different image"):
        publish_hd(hd_preview, tmp_path / "data2", path)


def registration_report(meta, **extra):
    """A registration report for the fixture image that passes every check unless `extra` overrides fields."""
    box = bounds_around(*CENTER, 200, 200)
    return {"hd_image": meta["source"], "reference_image": "ESP_000000_0000_RED_C_01_ORTHO.tif", "rms_m": 0.4,
            "max_m": 0.6, "measured_patches": 9, "tolerance_m": 1.0, "landmark_alignment": "measured_within_tolerance",
            "method": "upsampled phase cross-correlation on area-averaged HD (measurement only)",
            "bounds": [box["south"], box["west"], box["north"], box["east"]], **extra}


@pytest.mark.parametrize("extra, message", [
    ({"measured_patches": 2}, "patches"),
    ({"method": "eyeballed"}, "method"),
    ({"tolerance_m": 50}, "tolerance"),
    ({"rms_m": float("nan")}, "RMS"),
    ({"max_m": 3.0}, "disagrees"),  # says within tolerance while max exceeds it
    ({"reference_image": "ESP_000000_0000_RED_A_01_ORTHO.tif"}, "different image"),
    ({"bounds": [0, 0, 1, 1]}, "different area"),
])
def test_publish_rejects_weak_or_inconsistent_registration(hd_preview, tmp_path, extra, message):
    meta = json.loads((hd_preview / "hirise.meta.json").read_text())
    path = tmp_path / "registration.json"
    path.write_text(json.dumps(registration_report(meta, **extra)))
    with pytest.raises(ValueError, match=message):
        publish_hd(hd_preview, tmp_path / "data", path)
    assert not (tmp_path / "data" / "hirise.jpg").exists()


@pytest.mark.parametrize("change, message", [
    ({"source": "ESP_RED_anything.png"}, "product name"),
    ({"source": "PSP_000000_0000_COLOR.JP2"}, "product name"),
    ({"source_crs": "EPSG:4326"}, "Mars equirectangular"),
    ({"source_resolution_m": [1.0, 1.0]}, "resolution"),
    ({"source_resolution_m": [float("nan"), 0.25]}, "resolution"),
    ({"nodata_fraction": float("inf")}, "nodata_fraction"),
    ({"output_pixels": [600.5, 600]}, "finite integers"),
])
def test_publish_rejects_bad_identity_crs_or_numbers(hd_preview, tmp_path, change, message):
    meta_path = hd_preview / "hirise.meta.json"
    meta_path.write_text(json.dumps({**json.loads(meta_path.read_text()), **change}))
    with pytest.raises(ValueError, match=message):
        publish_hd(hd_preview, tmp_path / "data")


def test_decoded_size_must_match_metadata(hd_preview, tmp_path):
    with Image.open(hd_preview / "hirise.png") as image:
        image.crop((0, 0, image.width - 4, image.height)).save(hd_preview / "hirise.png")
    with pytest.raises(ValueError, match="decoded image"):
        publish_hd(hd_preview, tmp_path / "data")


def _snapshot(folder):
    """Bytes of every live HiRISE file in folder, for before/after comparison."""
    return {name: (folder / name).read_bytes() for name in ("hirise.jpg", "hirise.meta.json", "hirise.bounds.json")}


def test_failure_after_staging_keeps_previous_set(hd_preview, tmp_path, monkeypatch, caplog):
    """Failure injection: the third file's activation fails -> the first two are rolled back to the old set."""
    data = tmp_path / "data"
    publish_hd(hd_preview, data)
    before = _snapshot(data)
    meta_path = hd_preview / "hirise.meta.json"
    meta_path.write_text(json.dumps({**json.loads(meta_path.read_text()), "review_state": "second_publish"}))
    real_replace = __import__("os").replace

    def flaky_replace(source, target):
        """Fail only when the bounds file (activated last) is moved into the live folder."""
        if str(target).endswith("hirise.bounds.json") and ".publish-" not in str(target):
            raise OSError("injected failure")
        return real_replace(source, target)

    monkeypatch.setattr("pipeline.publish_imagery.os.replace", flaky_replace)
    with pytest.raises(OSError, match="injected"):
        publish_hd(hd_preview, data)
    assert _snapshot(data) == before
    assert not [p for p in data.iterdir() if p.name.startswith(".")]  # no staging or backup left behind
    assert any(getattr(r, "event", "") == "imagery_publish_rolled_back" for r in caplog.records)


def test_oversized_staged_jpeg_never_replaces_live_files(hd_preview, tmp_path, monkeypatch):
    data = tmp_path / "data"
    publish_hd(hd_preview, data)
    before = _snapshot(data)
    monkeypatch.setattr("pipeline.publish_imagery.MAX_BYTES", 10)
    with pytest.raises(ValueError, match="staged JPEG"):
        publish_hd(hd_preview, data)
    assert _snapshot(data) == before
    assert not [p for p in data.iterdir() if p.name.startswith(".")]
