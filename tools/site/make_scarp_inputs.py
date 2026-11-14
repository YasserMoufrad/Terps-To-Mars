"""Turn the traced scarp lines into the pipeline's scarp inputs for one audit config.

Writes, on exactly the crop the config resolves to (pipeline.feasibility.window_from_latlon):
  edge_distance.npy  metres from each cell to the traced scarp top edge (float32)
  foot_distance.npy  metres from each cell to the traced scarp foot (float32)
  scarp_risk.npy     True within 250 m of either line, over the traced extent (bool)
and a copy of the config pointing at them, with scarp_height_m and apron_m from
data/site/scarp_measurements.json. Output goes under pipeline/output/ (git-ignored).

Inputs are Yasser's agent's measurements (imagery-traced lines, DTM heights), not yet
reviewed by Nic. Usage:
  python tools/site/make_scarp_inputs.py data/site/feasibility_audit_from_parking.json pipeline/output/si/park
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from rasterio.warp import transform as transform_coordinates

from pipeline.feasibility import window_from_latlon
from pipeline.logging_config import event
from pipeline.terrain import MARS_GEOGRAPHIC, read_terrain

ROOT = Path(__file__).resolve().parents[2]
RISK_RADIUS_M = 250.0


def line_cells(terrain, coords, shape):
    """Rasterise a [lon, lat] polyline onto the crop as a boolean mask (dense sampling per segment)."""
    mask = np.zeros(shape, dtype=bool)
    lons, lats = zip(*coords)
    xs, ys = transform_coordinates(MARS_GEOGRAPHIC, terrain.crs, list(lons), list(lats))
    inv = ~terrain.transform
    pix = [inv * (x, y) for x, y in zip(xs, ys)]  # (col, row) floats
    for (c0, r0), (c1, r1) in zip(pix, pix[1:]):
        n = int(max(abs(c1 - c0), abs(r1 - r0)) * 2) + 2
        for t in np.linspace(0, 1, n):
            r, c = int(round(r0 + (r1 - r0) * t)), int(round(c0 + (c1 - c0) * t))
            if 0 <= r < shape[0] and 0 <= c < shape[1]:
                mask[r, c] = True
    return mask


def main(config_path, out_dir):
    """Build scarp inputs for config_path's crop; out_dir receives the arrays and an updated config."""
    config = json.loads(Path(config_path).read_text())
    measurements = json.loads((ROOT / "data/site/scarp_measurements.json").read_text())
    lines = {f["properties"]["id"]: f["geometry"]["coordinates"]
             for f in json.loads((ROOT / "data/site/scarp_lines.geojson").read_text())["features"]}
    dtm = str(ROOT / config["dtm"])
    window = window_from_latlon(dtm, config["window_latlon"])
    terrain = read_terrain(dtm, tuple(window))
    shape = terrain.elevation.shape
    # Anisotropic sampling: rows are `resolution` metres, columns are the latitude-corrected spacing.
    sampling = (terrain.resolution, float(np.median(terrain.column_spacing)))
    edge = line_cells(terrain, lines["scarp-edge"], shape)
    foot = line_cells(terrain, lines["scarp-foot"], shape)
    if not edge.any() or not foot.any():
        raise ValueError("Traced scarp lines do not fall inside this config's crop")
    edge_distance = distance_transform_edt(~edge, sampling=sampling).astype(np.float32)
    foot_distance = distance_transform_edt(~foot, sampling=sampling).astype(np.float32)
    scarp_risk = (edge_distance <= RISK_RADIUS_M) | (foot_distance <= RISK_RADIUS_M)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, array in (("edge_distance", edge_distance), ("foot_distance", foot_distance), ("scarp_risk", scarp_risk)):
        np.save(out / f"{name}.npy", array, allow_pickle=False)
    profiles = measurements["profiles"]
    # One site-wide value each (the pipeline takes scalars): conservative tallest height, median apron.
    scarp_height = max(p["height_m"] for p in profiles)
    apron = float(np.median([p["apron_m"] for p in profiles]))
    updated = {**config, "window": list(window), "edge_distance": str(out / "edge_distance.npy"),
               "foot_distance": str(out / "foot_distance.npy"), "scarp_risk": str(out / "scarp_risk.npy"),
               "scarp_height_m": scarp_height, "apron_m": round(apron, 1),
               "_scarp_inputs": "tools/site/make_scarp_inputs.py from data/site/scarp_lines.geojson + scarp_measurements.json (unreviewed)"}
    updated.pop("window_latlon", None)
    (out / "config.json").write_text(json.dumps(updated, indent=2) + "\n")
    event("scarp_inputs_written", window=list(window), edge_cells=int(edge.sum()), foot_cells=int(foot.sum()),
          risk_cells=int(scarp_risk.sum()), scarp_height_m=scarp_height, apron_m=round(apron, 1),
          evidence="inferred", review_status="unreviewed")
    print(json.dumps({"window": list(window), "edge_cells": int(edge.sum()), "foot_cells": int(foot.sum()),
                      "scarp_height_m": scarp_height, "apron_m": round(apron, 1), "config": str(out / "config.json")}))


if __name__ == "__main__":
    main(*sys.argv[1:3])
