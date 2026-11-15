"""Standalone slope map: slope physics, threshold classes, unknown cells, grid/bounds agreement, publishing."""

import json
import logging
import math
import os

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.crs import CRS

from pipeline import slope_mvp
from pipeline.slope_mvp import (BELOW, CAUTION, CREW_EXCLUDED, ROVER_EXCLUDED, UNKNOWN_A, UNKNOWN_B,
                                classify, publish_slope, window_for_bounds)
from pipeline.terrain import Terrain, analyze, load_rules

# Same projection family as the real DTM (eqc, local radius, standard parallel 50 N, 212.12 E).
EQC = CRS.from_string("+proj=eqc +lat_ts=50 +lat_0=0 +lon_0=212.12 +x_0=0 +y_0=0 +R=3384416.5044892 +units=m +no_defs")
ORIGIN = (-3937.67, 3_204_728.95)  # upper-left of the real DTM (x, y metres)
NODATA = -3.4028226550889045e38


def synthetic(elevation, artifact=None):
    """In-memory Terrain on a 1 m eqc grid at ~54 N; evidence 'simulated' (unit tests only)."""
    transform = rasterio.Affine(1.0, 0, ORIGIN[0], 0, -1.0, ORIGIN[1] - 2_000)
    return Terrain(np.asarray(elevation, float), transform, EQC, "synthetic", "simulated", artifact)


def write_dtm(path, elevation):
    """Write elevation (2D, NaN = no-data) as a GeoTIFF DTM with the real CRS and a declared no-data value."""
    data = np.where(np.isfinite(elevation), elevation, NODATA).astype("float32")
    profile = {"driver": "GTiff", "height": data.shape[0], "width": data.shape[1], "count": 1, "dtype": "float32",
               "crs": EQC, "transform": rasterio.Affine(1.0, 0, ORIGIN[0], 0, -1.0, ORIGIN[1] - 2_000), "nodata": NODATA}
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(data, 1)
    return path


def box_of(path, inset=10):
    """Signed lat/lon box inside the DTM at path, inset cells from each edge."""
    with rasterio.open(path) as dataset:
        from rasterio.warp import transform as tr
        from pipeline.terrain import MARS_GEOGRAPHIC, signed_longitude
        t = dataset.transform
        x0, y0 = t * (inset, inset)
        x1, y1 = t * (dataset.width - inset, dataset.height - inset)
        lons, lats = tr(dataset.crs, MARS_GEOGRAPHIC, [x0, x1], [y0, y1])
    return {"south": lats[1], "west": signed_longitude(lons[0]), "north": lats[0], "east": signed_longitude(lons[1])}


def test_flat_terrain_has_zero_slope():
    """A flat plane measures ~0 degrees everywhere it is valid."""
    result = analyze(synthetic(np.full((20, 20), -4000.0)))
    assert np.nanmax(result["slope"]) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("angle", [10.0, 17.5, 30.0])
def test_inclined_plane_measures_its_angle(angle):
    """A north-south plane rising tan(angle) per metre measures angle (metric spacing, not pixel units)."""
    rows = np.arange(30)[:, None] * np.ones((1, 30))
    result = analyze(synthetic(-rows * math.tan(math.radians(angle))))
    assert np.nanmedian(result["slope"]) == pytest.approx(angle, abs=0.05)


def test_classes_follow_rule_boundaries():
    """15, 20 and 24 degrees start caution, crew exclusion and rover exclusion (">=" in hazard_rules.json)."""
    slope = np.array([[0, 14.99, 15, 19.99, 20, 23.99, 24, 80]], float)
    classes = classify(slope, np.ones(slope.shape, bool), load_rules())
    assert classes.tolist() == [[BELOW, BELOW, CAUTION, CAUTION, CREW_EXCLUDED, CREW_EXCLUDED, ROVER_EXCLUDED, ROVER_EXCLUDED]]


def test_thresholds_come_from_rules():
    """Changing the rule value moves the class boundary; no thresholds are hard-coded."""
    rules = load_rules()
    rules["rules"]["crew_caution_deg"]["value"] = 12
    assert classify(np.array([[13.0]]), np.ones((1, 1), bool), rules)[0, 0] == CAUTION


def test_unknown_cells_are_never_a_slope_class():
    """No-data, NaN gradients and artifact cells become the gray pattern, never 'below caution'."""
    slope = np.array([[5.0, np.nan], [5.0, 5.0]])
    valid = np.array([[True, True], [False, True]])
    classes = classify(slope, valid, load_rules())
    assert classes[0, 1] in (UNKNOWN_A, UNKNOWN_B) and classes[1, 0] in (UNKNOWN_A, UNKNOWN_B)
    assert classes[0, 0] == BELOW


def test_artifact_mask_is_unknown():
    """Cells flagged by the artifact mask lose their slope and classify as unknown."""
    artifact = np.zeros((20, 20), bool)
    artifact[10, 10] = True
    result = analyze(synthetic(np.zeros((20, 20)), artifact))
    classes = classify(result["slope"], result["valid"], load_rules())
    assert classes[10, 10] in (UNKNOWN_A, UNKNOWN_B)


def test_publish_matches_grid_and_bounds(tmp_path, caplog):
    """Published PNG has one pixel per DTM cell; bounds and pixel centres transform consistently, north up, west < east."""
    rows = np.arange(80)[:, None] * np.ones((1, 60))
    dtm = write_dtm(tmp_path / "dtm.tif", -4000 - rows * math.tan(math.radians(22)))
    box = box_of(dtm)
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    meta = publish_slope(dtm, tmp_path / "data", box)
    data = tmp_path / "data"
    bounds = json.loads((data / "slope.bounds.json").read_text())
    with Image.open(data / "slope.png") as image:
        assert image.mode == "P" and list(image.size) == meta["grid"]["pixels"]
        pixels = np.asarray(image)
    assert bounds["north"] > bounds["south"] and bounds["east"] > bounds["west"]
    assert -180 <= bounds["west"] < bounds["east"] <= 180
    assert abs(bounds["south"] - box["south"]) < 2e-5 and abs(bounds["west"] - box["west"]) < 2e-5
    # Pixel centres: cell (0,0) is half a cell inside the north-west corner.
    width, height = meta["grid"]["pixels"]
    with rasterio.open(dtm) as dataset:
        window, _ = window_for_bounds(dataset, box, 0)
    from pipeline.terrain import read_terrain
    terrain = read_terrain(dtm, window=window)
    lon, lat = terrain.lonlat(0, 0)
    assert lon == pytest.approx(bounds["west"] + (bounds["east"] - bounds["west"]) / width / 2, abs=1e-9)
    assert lat == pytest.approx(bounds["north"] - (bounds["north"] - bounds["south"]) / height / 2, abs=1e-9)
    assert (pixels == CREW_EXCLUDED).mean() > 0.9  # a 22 degree plane is crew-excluded, not rover-excluded
    assert not list(data.glob(".slope-*"))
    published = [r for r in caplog.records if getattr(r, "event", "") == "slope_published"]
    assert published and published[0].fields["evidence"] == "nasa_derived"


def test_publish_needs_no_routes_and_ignores_mission(tmp_path):
    """The slope map is produced in an empty data folder: no routes, mission or scenario are read."""
    dtm = write_dtm(tmp_path / "dtm.tif", np.zeros((40, 40)))
    publish_slope(dtm, tmp_path / "empty", box_of(dtm))
    assert sorted(p.name for p in (tmp_path / "empty").iterdir()) == ["slope.bounds.json", "slope.meta.json", "slope.png"]


def test_nodata_inside_footprint_is_unknown_pattern(tmp_path):
    """A no-data hole inside the crop is published as the unknown pattern, never as flat terrain."""
    elevation = np.zeros((40, 40))
    elevation[18:22, 18:22] = np.nan
    dtm = write_dtm(tmp_path / "dtm.tif", elevation)
    meta = publish_slope(dtm, tmp_path / "data", box_of(dtm, inset=5))
    assert meta["class_cells"]["unknown"] >= 16 and meta["unknown_fraction"] > 0


def test_missing_dtm_fails_with_instructions(tmp_path, caplog):
    """No real DTM: a clear error naming the acquisition step, and nothing published."""
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    with pytest.raises(FileNotFoundError, match="pipeline.acquire"):
        publish_slope(tmp_path / "missing.IMG", tmp_path / "data")
    assert not (tmp_path / "data").exists()
    assert any(getattr(r, "event", "") == "slope_input_missing" for r in caplog.records)


def test_failed_activation_restores_previous_set(tmp_path, monkeypatch, caplog):
    """If replacing slope.bounds.json fails, the previous PNG/meta/bounds come back and the failure is logged."""
    dtm = write_dtm(tmp_path / "dtm.tif", np.zeros((40, 40)))
    data = tmp_path / "data"
    publish_slope(dtm, data, box_of(dtm))
    before = {name: (data / name).read_bytes() for name in slope_mvp.LIVE_FILES}
    real_replace = os.replace
    failed = []

    def flaky(source, target):
        """Fail once, when the staged bounds file replaces the live one (the rollback itself succeeds)."""
        if (not failed and str(target).endswith("slope.bounds.json")
                and ".slope-" in str(source) and ".slope-" not in str(target)):
            failed.append(target)
            raise PermissionError("injected")
        return real_replace(source, target)

    monkeypatch.setattr(slope_mvp.os, "replace", flaky)
    write_dtm(tmp_path / "dtm.tif", np.arange(1600, dtype=float).reshape(40, 40) * 0.5)
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    with pytest.raises(PermissionError):
        publish_slope(dtm, data, box_of(dtm))
    assert {name: (data / name).read_bytes() for name in slope_mvp.LIVE_FILES} == before
    assert any(getattr(r, "event", "") == "slope_publish_rolled_back" for r in caplog.records)


def test_window_requires_signed_longitudes(tmp_path):
    """Bounds use the contract's signed longitudes; a 0-360 east box is refused instead of misread."""
    dtm = write_dtm(tmp_path / "dtm.tif", np.zeros((40, 40)))
    box = box_of(dtm)
    east = {**box, "west": box["west"] + 360, "east": box["east"] + 360}
    with rasterio.open(dtm) as dataset:
        signed = window_for_bounds(dataset, box, 0)
        with pytest.raises(ValueError):  # validate_geographic_bounds rejects > 180; signed input is the contract
            window_for_bounds(dataset, east, 0)
    assert signed[0][2] >= 3


def test_bounds_outside_dtm_are_refused(tmp_path):
    """A box beyond the raster is an error, not a silently clipped map."""
    dtm = write_dtm(tmp_path / "dtm.tif", np.zeros((40, 40)))
    box = box_of(dtm)
    with pytest.raises(ValueError, match="leave the DTM"):
        publish_slope(dtm, tmp_path / "data", {**box, "north": box["north"] + 0.01})
