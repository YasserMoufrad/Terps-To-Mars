import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from pipeline.terrain import Terrain, analyze, read_terrain, signed_longitude, load_rules, roughness_window
from pipeline.hazards import hazard_masks, export_hazards
from pipeline.validate_contract import validate_collection

CRS = "+proj=eqc +R=3389500 +units=m +no_defs"


def terrain(z=None, **kwargs):
    return Terrain(np.zeros((11, 11)) if z is None else z,
                   from_origin(0, 11, 1, 1), CRS, "synthetic fixture", "simulated", **kwargs)


def test_flat_and_analytic_slope():
    assert np.all(analyze(terrain())["slope"] == 0)
    z = np.tile(np.arange(11) * np.tan(np.radians(18)), (11, 1))
    np.testing.assert_allclose(analyze(terrain(z))["slope"], 18)


def test_equirectangular_scale_corrected_at_high_latitude():
    radius = 3_389_500
    transform = from_origin(0, np.radians(54) * radius, 1, 1)
    z = np.tile(np.arange(11, dtype=float), (11, 1))
    t = Terrain(z, transform, CRS, "synthetic latitude test", "simulated")
    expected = np.degrees(np.arctan(1 / np.cos(np.radians(54))))
    assert analyze(t)["slope"][0, 0] == pytest.approx(expected, abs=1e-4)


def test_no_data_and_artifact_never_filled():
    z = np.zeros((11, 11))
    z[4, 4] = np.nan
    artifact = np.zeros(z.shape, bool)
    artifact[6, 6] = True
    t = terrain(z, artifact=artifact)
    result = analyze(t)
    assert not result["valid"][4, 4]
    assert not result["valid"][6, 6]
    assert np.isnan(result["slope"][4, 4])
    validate_collection(export_hazards(t, hazard_masks(t, result)), "hazards.geojson")


def test_exact_thresholds():
    t = terrain()
    values = analyze(t)
    values["slope"][0, :6] = [14.999, 15, 19.999, 20, 23.999, 24]
    values["roughness"][0, :2] = [0.5, 0.500001]
    masks = hazard_masks(t, values)
    assert list(masks["crew_caution"][0, :4]) == [False, True, True, False]
    assert list(masks["crew_exclude"][0, 2:4]) == [False, True]
    assert list(masks["rover_exclude"][0, 4:6]) == [False, True]
    assert list(masks["roughness"][0, :2]) == [False, True]


def test_setback_and_rockfall_boundaries():
    t = terrain()
    distances = np.full((11, 11), 20.0)
    masks = hazard_masks(t, analyze(t), edge_distance=distances,
                         foot_distance=distances, scarp_height=40, apron_m=12)
    assert masks["edge"].all() and masks["rockfall"].all()
    assert load_rules()["rules"]["eva_reserve_fraction"]["value"] == 0.3


def test_mars_crs_and_signed_longitude():
    assert signed_longitude(212.106) == pytest.approx(-147.894)
    with pytest.raises(ValueError, match="Mars"):
        Terrain(np.zeros((4, 4)), from_origin(0, 4, 1, 1), "EPSG:3857", "bad", "simulated")


def test_read_and_crop_raster(tmp_path):
    path = tmp_path / "synthetic.tif"
    data = np.arange(121, dtype="float32").reshape(11, 11)
    data[3, 3] = -9999
    with rasterio.open(path, "w", driver="GTiff", width=11, height=11,
                       count=1, dtype="float32", crs=CRS,
                       transform=from_origin(0, 11, 1, 1), nodata=-9999) as dst:
        dst.write(data, 1)
    result = read_terrain(path, (2, 2, 5, 5), evidence="simulated")
    assert result.elevation.shape == (5, 5)
    assert np.isnan(result.elevation[1, 1])
    assert result.transform.c == 2
    with pytest.raises(ValueError, match="coverage"):
        read_terrain(path, (8, 8, 5, 5))


@pytest.mark.parametrize("resolution,pixels", [(0.99, 3), (1, 3), (0.5, 5), (1.5, 1), (10, 1)])
def test_nearest_odd_physical_roughness_window(resolution, pixels):
    assert roughness_window(3, resolution) == pixels
    t = Terrain(np.zeros((11, 11)), from_origin(0, 11, resolution, resolution), CRS, "fixture", "simulated")
    result = analyze(t)
    assert result["roughness_window_m"] == pytest.approx(pixels * resolution)
    if pixels < 3:
        assert np.isnan(result["roughness"]).all() and result["roughness_uncertain"]


@pytest.mark.parametrize("missing", ["edge_distance", "foot_distance", "scarp_height", "apron_m"])
def test_missing_scarp_measurements_block_only_risk_area(missing):
    t = terrain()
    risk = np.zeros((11, 11), bool)
    risk[:, 5] = True
    inputs = {"edge_distance": np.full((11, 11), 100.), "foot_distance": np.full((11, 11), 100.),
              "scarp_height": 20., "apron_m": 10.}
    inputs[missing] = None
    masks = hazard_masks(t, analyze(t), scarp_risk=risk, **inputs)
    np.testing.assert_array_equal(masks["inspection_required"], risk)


def test_one_height_rockfall_boundary_and_explicit_cliff_free():
    t = terrain()
    distance = np.full((11, 11), 40.)
    distance[0, 0] += 0.0001
    masks = hazard_masks(t, analyze(t), edge_distance=np.full((11, 11), 100.),
                         foot_distance=distance, scarp_height=40, apron_m=12)
    assert masks["rockfall"][1, 1] and not masks["rockfall"][0, 0]
    assert not masks["inspection_required"].any()
    assert not hazard_masks(t, analyze(t), scarp_risk=np.zeros((11, 11), bool))["inspection_required"].any()
