"""Registration measurement and no-data rendering tests on synthetic Mars rasters."""

import logging

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin
from scipy.ndimage import gaussian_filter

from pipeline.export import export_hirise_hd
from pipeline.preview_hd import bounds_around
from pipeline.registration import measure_registration, phase_correlation
from pipeline.terrain import MARS_GEOGRAPHIC

CRS = "+proj=eqc +lat_ts=50 +lon_0=212.12 +R=3384416.5 +units=m +no_defs"
CENTER = (54.144, -147.894)
X0 = 3384416.5 * np.cos(np.radians(50)) * np.radians(CENTER[1] + 360 - 212.12)
Y0 = 3384416.5 * np.radians(CENTER[0])


def write(path, data, res, origin_shift_east_m=0.0, crs=CRS, nodata=None):
    """Write data (2D) as a GeoTIFF centred on CENTER at res metres/pixel; origin_shift moves its georeference."""
    h, w = data.shape
    transform = from_origin(X0 - w * res / 2 + origin_shift_east_m, Y0 + h * res / 2, res, res)
    with rasterio.open(path, "w", driver="GTiff", width=w, height=h, count=1, dtype=data.dtype,
                       crs=crs, transform=transform, nodata=nodata) as dataset:
        dataset.write(data, 1)
    return path


def texture(size, seed=3):
    """Smooth random terrain-like texture as uint8 (values 1-255, so 0 stays the null value)."""
    field = gaussian_filter(np.random.default_rng(seed).normal(size=(size, size)), 6)
    field = (field - field.min()) / (field.max() - field.min())
    return (1 + field * 254).astype(np.uint8)


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    """0.25 m HD texture and its exact 1 m block-mean reference on the same footprint."""
    root = tmp_path_factory.mktemp("reg")
    hd = texture(1600)
    reference = hd.reshape(400, 4, 400, 4).mean(axis=(1, 3)).astype(np.uint8)
    return root, write(root / "hd.tif", hd, 0.25), reference


def test_phase_correlation_recovers_shift_and_sign():
    reference = gaussian_filter(np.random.default_rng(1).normal(size=(96, 96)), 3)
    moving = np.roll(reference, (3, -2), axis=(0, 1))
    dy, dx, error = phase_correlation(reference, moving)
    assert dy == pytest.approx(3, abs=0.1) and dx == pytest.approx(-2, abs=0.1) and error < 0.1
    from scipy.ndimage import fourier_shift
    half = np.real(np.fft.ifft2(fourier_shift(np.fft.fft2(reference), (0.5, 0))))
    assert phase_correlation(reference, half)[0] == pytest.approx(0.5, abs=0.1)  # sub-pixel, not rounded


def test_aligned_images_measure_near_zero(pair, caplog):
    root, hd, reference = pair
    ref = write(root / "ref_aligned.tif", reference, 1.0)
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    report = measure_registration(hd, ref, bounds_around(*CENTER, 300, 300), grid=3, patch_px=64)
    assert report["measured_patches"] >= 3
    assert report["rms_m"] < 0.3 and report["landmark_alignment"] == "measured_within_tolerance"
    logged = [r for r in caplog.records if getattr(r, "event", "") == "registration_measured"][0].fields
    assert logged["landmark_alignment"] == "measured_within_tolerance" and logged["rms_m"] == report["rms_m"]


def test_known_georeference_error_is_measured_in_metres(pair):
    """Shift the reference's georeference 2 m east: the HD image must read about 2 m west of it."""
    root, hd, reference = pair
    ref = write(root / "ref_shifted.tif", reference, 1.0, origin_shift_east_m=2.0)
    report = measure_registration(hd, ref, bounds_around(*CENTER, 250, 250), grid=3, patch_px=64)
    assert report["mean_offset_east_m"] == pytest.approx(-2.0 * np.cos(np.radians(54.144)) / np.cos(np.radians(50)), abs=0.3)
    assert abs(report["mean_offset_north_m"]) < 0.3
    assert report["landmark_alignment"] == "measured_exceeds_tolerance"


def test_featureless_images_are_not_counted_as_agreement(tmp_path):
    flat_hd = write(tmp_path / "hd.tif", np.full((800, 800), 120, np.uint8), 0.25)
    flat_ref = write(tmp_path / "ref.tif", np.full((200, 200), 120, np.uint8), 1.0)
    report = measure_registration(flat_hd, flat_ref, bounds_around(*CENTER, 120, 120), grid=2, patch_px=48)
    assert report["measured_patches"] == 0 and report["landmark_alignment"] == "insufficient_landmarks"
    assert report["rms_m"] is None


def test_non_mars_reference_rejected(pair, tmp_path):
    _, hd, reference = pair
    earth = write(tmp_path / "earth.tif", reference, 1.0, crs=CRS.replace("3384416.5", "6371000"))
    with pytest.raises(ValueError, match="Mars"):
        measure_registration(hd, earth, bounds_around(*CENTER, 100, 100))


def test_png_export_makes_nodata_transparent_without_dark_seams(tmp_path):
    """Constant 200 surface with a null block: reduced PNG keeps 200 on every valid pixel, alpha 0 on nulls."""
    data = np.full((800, 800), 200, np.uint8)
    data[:, :300] = 0  # HiRISE CORE_NULL strip
    source = write(tmp_path / "edge.tif", data, 0.25)
    out = tmp_path / "hirise.png"
    export_hirise_hd(source, bounds_around(*CENTER, 150, 150), out, max_dimension=150, stretch="none")
    with Image.open(out) as image:
        assert image.mode == "LA"
        gray, alpha = (np.asarray(band) for band in image.split())
    assert (alpha == 0).any() and (alpha == 255).any()
    assert gray[alpha == 255].min() >= 199  # a plain average would blend 0 into edge pixels
    meta = __import__("json").loads(out.with_suffix(".meta.json").read_text())
    assert meta["nodata_rendering"] == "transparent" and meta["format"] == "png"
