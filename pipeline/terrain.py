"""Metric Mars raster validation and conservative terrain measurements."""

from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.windows import Window
from rasterio.warp import transform as transform_coordinates
from scipy.ndimage import maximum_filter, minimum_filter

MARS_RADIUS_M = 3_389_500.0
MARS_GEOGRAPHIC = CRS.from_string(f"+proj=longlat +R={MARS_RADIUS_M} +no_defs")


def load_rules():
    return json.loads(Path(__file__).with_name("hazard_rules.json").read_text())


def threshold(rules, name):
    return rules["rules"][name]["value"]


def signed_longitude(value):
    if not math.isfinite(value):
        raise ValueError("Longitude must be finite")
    return (value + 180) % 360 - 180


@dataclass
class Terrain:
    elevation: np.ndarray
    transform: rasterio.Affine
    crs: CRS
    source: str
    evidence: str
    artifact: np.ndarray | None = None

    def __post_init__(self):
        self.elevation = np.asarray(self.elevation, dtype=float)
        if self.elevation.ndim != 2 or min(self.elevation.shape) < 3:
            raise ValueError("Terrain must be a 2D grid at least 3 x 3")
        self.crs = CRS.from_user_input(self.crs)
        parameters = self.crs.to_dict()
        radius = parameters.get("R", parameters.get("a", 0))
        if parameters.get("proj") != "eqc" or not 3_300_000 < float(radius) < 3_500_000:
            raise ValueError("Expected Mars equirectangular CRS, not Earth or unknown datum")
        if self.crs.linear_units != "metre":
            raise ValueError("Terrain units must be metres")
        t = self.transform
        if t.a <= 0 or t.e >= 0 or t.b != 0 or t.d != 0 or not math.isclose(t.a, -t.e):
            raise ValueError("Expected north-up square metric pixels")
        if self.evidence not in {"nasa_derived", "simulated"}:
            raise ValueError("Terrain evidence must be nasa_derived or simulated")
        if self.artifact is None:
            self.artifact = np.zeros(self.elevation.shape, dtype=bool)
        self.artifact = np.asarray(self.artifact, dtype=bool)
        if self.artifact.shape != self.elevation.shape:
            raise ValueError("Artifact mask must match terrain")

    @property
    def resolution(self):
        return self.transform.a

    @property
    def valid(self):
        return np.isfinite(self.elevation) & ~self.artifact

    def lonlat(self, row, col, center=True):
        offset = 0.5 if center else 0
        x, y = self.transform * (col + offset, row + offset)
        lon, lat = transform_coordinates(self.crs, MARS_GEOGRAPHIC, [x], [y])
        return [signed_longitude(lon[0]), lat[0]]


def read_terrain(path, window=None, artifact=None, evidence="nasa_derived"):
    """Crop by integer (column, row, width, height); never interpolate missing cells."""
    with rasterio.open(path) as dataset:
        if dataset.nodata is None:
            raise ValueError("Raster must declare its no-data value")
        if dataset.count != 1:
            raise ValueError("Expected one elevation band")
        if window is None:
            window = (0, 0, dataset.width, dataset.height)
        col, row, width, height = window
        if any(int(v) != v for v in window) or min(col, row) < 0 or min(width, height) < 3:
            raise ValueError("Invalid crop window")
        if col + width > dataset.width or row + height > dataset.height:
            raise ValueError("Crop exceeds raster coverage")
        crop = Window(*window)
        elevation = dataset.read(1, window=crop, masked=True).astype(float).filled(np.nan)
        return Terrain(elevation, dataset.window_transform(crop), dataset.crs,
                       Path(path).name, evidence, artifact)


def analyze(terrain, rules=None):
    rules = rules or load_rules()
    z = np.where(terrain.valid, terrain.elevation, np.nan)
    dy, dx = np.gradient(z, terrain.resolution)
    slope = np.degrees(np.arctan(np.hypot(dx, dy)))
    window = max(1, math.ceil(threshold(rules, "roughness_window_m") / terrain.resolution))
    if window % 2 == 0:
        window += 1
    roughness = (maximum_filter(np.where(terrain.valid, z, -np.inf), size=window, mode="nearest")
                 - minimum_filter(np.where(terrain.valid, z, np.inf), size=window, mode="nearest"))
    complete = minimum_filter(terrain.valid.astype(np.uint8), size=window, mode="nearest").astype(bool)
    valid = terrain.valid & complete & np.isfinite(slope)
    slope[~valid] = np.nan
    roughness[~valid] = np.nan
    return {"slope": slope, "roughness": roughness, "valid": valid}
