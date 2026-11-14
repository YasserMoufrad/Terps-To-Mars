"""Metric Mars raster validation and conservative terrain measurements."""

from dataclasses import dataclass
import json
import math
import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.windows import Window
from rasterio.warp import transform as transform_coordinates
from scipy.ndimage import maximum_filter, minimum_filter
from pipeline.logging_config import event, operation, traced, fingerprint

MARS_RADIUS_M = 3_389_500.0
MARS_GEOGRAPHIC = CRS.from_string(f"+proj=longlat +R={MARS_RADIUS_M} +no_defs")


@traced("hazard_rules")
def load_rules():
    rules = json.loads(Path(__file__).with_name("hazard_rules.json").read_text())
    event("rules_loaded", schema_version=rules["schema_version"], config_fingerprint=fingerprint(rules), rules=rules["rules"])
    return rules


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
    vertical_uncertainty_m: float | None = None

    @traced("raster_validation")
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
        if self.vertical_uncertainty_m is not None and (not math.isfinite(self.vertical_uncertainty_m) or self.vertical_uncertainty_m < 0):
            raise ValueError("Vertical uncertainty must be nonnegative and finite")
        event("raster_validated", dataset_id=self.source, evidence=self.evidence, crs=str(self.crs),
              radius_m=float(radius), resolution_m=self.resolution, dimensions=list(self.elevation.shape),
              invalid_cells=int((~self.valid).sum()), artifact_cells=int(self.artifact.sum()))

    @property
    def resolution(self):
        return self.transform.a

    @property
    def valid(self):
        return np.isfinite(self.elevation) & ~self.artifact

    @property
    def column_spacing(self):
        # Equirectangular x scale is true only at its standard parallel.
        rows = np.arange(self.elevation.shape[0]) + 0.5
        xs = np.full(rows.shape, self.transform.c + 0.5 * self.resolution)
        ys = self.transform.f + rows * self.transform.e
        _, latitudes = transform_coordinates(self.crs, MARS_GEOGRAPHIC, xs.tolist(), ys.tolist())
        standard_parallel = float(self.crs.to_dict().get("lat_ts", 0))
        return self.resolution * np.cos(np.radians(latitudes)) / math.cos(math.radians(standard_parallel))

    def lonlat(self, row, col, center=True):
        offset = 0.5 if center else 0
        x, y = self.transform * (col + offset, row + offset)
        lon, lat = transform_coordinates(self.crs, MARS_GEOGRAPHIC, [x], [y])
        return [signed_longitude(lon[0]), lat[0]]


@traced("raster_loading")
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
        manifest = Path(path).with_suffix(Path(path).suffix + ".json")
        checksum = json.loads(manifest.read_text()).get("sha256") if manifest.exists() else None
        event("raster_crop", dataset_id=Path(path).name, crop=list(window), nodata=dataset.nodata,
              checksum=checksum, source=str(path), evidence=evidence)
        elevation = dataset.read(1, window=crop, masked=True).astype(float).filled(np.nan)
        return Terrain(elevation, dataset.window_transform(crop), dataset.crs,
                       Path(path).name, evidence, artifact)


def roughness_window(width_m, resolution_m):
    if not math.isfinite(width_m) or width_m <= 0 or not math.isfinite(resolution_m) or resolution_m <= 0:
        raise ValueError("Roughness width and resolution must be positive and finite")
    ratio = width_m / resolution_m
    lower = max(1, 2 * math.floor((ratio - 1) / 2) + 1)
    return min((lower, lower + 2), key=lambda size: (abs(size * resolution_m - width_m), size))


@traced("terrain_analysis")
def analyze(terrain, rules=None):
    rules = rules or load_rules()
    z = np.where(terrain.valid, terrain.elevation, np.nan)
    with operation("slope_computation", dataset_id=terrain.source):
        dy, dx = np.gradient(z, terrain.resolution)
        dx *= terrain.resolution / terrain.column_spacing[:, None]
        slope = np.degrees(np.arctan(np.hypot(dx, dy)))
    window = roughness_window(threshold(rules, "roughness_window_m"), terrain.resolution)
    with operation("roughness_computation", dataset_id=terrain.source):
        roughness = (maximum_filter(np.where(terrain.valid, z, -np.inf), size=window, mode="nearest")
                     - minimum_filter(np.where(terrain.valid, z, np.inf), size=window, mode="nearest"))
        complete = minimum_filter(terrain.valid.astype(np.uint8), size=window, mode="nearest").astype(bool)
    valid = terrain.valid & complete & np.isfinite(slope)
    slope[~valid] = np.nan
    roughness[~valid] = np.nan
    if window < 3:
        roughness[:] = np.nan
        event("roughness_unresolved", logging.WARNING, reason="sampling_too_coarse", resolution_m=terrain.resolution)
    if terrain.vertical_uncertainty_m is None:
        event("roughness_uncertainty", logging.WARNING, reason="vertical_uncertainty_unavailable", threshold_m=threshold(rules, "roughness_m"), classification="provisional_assumption")
    elif terrain.vertical_uncertainty_m >= threshold(rules, "roughness_m"):
        event("roughness_uncertainty", logging.WARNING, reason="uncertainty_at_or_above_threshold", uncertainty_m=terrain.vertical_uncertainty_m)
    event("terrain_summary", dataset_id=terrain.source, evidence=terrain.evidence,
          window_pixels=window, effective_window_m=window * terrain.resolution,
          effective_east_west_m=[float(window * terrain.column_spacing.min()), float(window * terrain.column_spacing.max())],
          valid_cells=int(valid.sum()), invalid_cells=int((~valid).sum()),
          slope_max_deg=float(np.nanmax(slope)) if np.isfinite(slope).any() else None,
          roughness_max_m=float(np.nanmax(roughness)) if np.isfinite(roughness).any() else None)
    return {"slope": slope, "roughness": roughness, "valid": valid,
            "roughness_window_pixels": window, "roughness_window_m": window * terrain.resolution,
            "roughness_uncertain": terrain.vertical_uncertainty_m is None or window < 3 or terrain.vertical_uncertainty_m >= threshold(rules, "roughness_m")}
