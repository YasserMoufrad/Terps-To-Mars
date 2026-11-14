"""Measure the Milankovic scarp on the HiRISE DTM and pick flat candidate points.

Uses Nic's pipeline (read_terrain, analyze, hazard_rules.json) so slopes match the
pipeline exactly. Inputs: DTM path, traced scarp lines (imagery), Geury's points.
Outputs a JSON report with per-profile scarp height, apron width, the rockfall buffer
(max(apron, height x rockfall_height_factor) from the foot) and candidate points whose
whole 15 m uncertainty disc has no slope >= crew exclude (20 deg), preferring none >= 15.
Candidates only: nothing here is crew clearance.
"""
import json
import math
import sys
import numpy as np
import rasterio
from rasterio.warp import transform as transform_coordinates
from pipeline.terrain import read_terrain, analyze, load_rules, threshold, MARS_GEOGRAPHIC

dtm_path, lines_path, points_path, out_path = sys.argv[1:5]
rules = load_rules()
CAUTION, EXCLUDE = threshold(rules, "crew_caution_deg"), threshold(rules, "crew_exclude_deg")
FACTOR = threshold(rules, "rockfall_height_factor")
RADIUS_M = 15.0
BOX = {"south": 54.120, "north": 54.182, "west": -147.930, "east": -147.880}

with rasterio.open(dtm_path) as ds:
    crs = ds.crs
    # Corners of the box in the DTM's projected metres (longitude east-positive 0..360 or signed both work in proj).
    xs, ys = transform_coordinates(MARS_GEOGRAPHIC, crs, [BOX["west"], BOX["east"]], [BOX["south"], BOX["north"]])
    inv = ~ds.transform
    c0, r1 = inv * (min(xs), min(ys))
    c1, r0 = inv * (max(xs), max(ys))
    col, row = max(0, int(math.floor(min(c0, c1)))), max(0, int(math.floor(min(r0, r1))))
    width = min(ds.width - col, int(math.ceil(abs(c1 - c0))))
    height = min(ds.height - row, int(math.ceil(abs(r1 - r0))))
window = (col, row, width, height)
terrain = read_terrain(dtm_path, window)
analysis = analyze(terrain, rules)
z, slope, valid = terrain.elevation, analysis["slope"], analysis["valid"]
res = terrain.resolution
H, W = z.shape


def rc(lon, lat):
    """Signed lon/lat to fractional (row, col) in the crop."""
    x, y = transform_coordinates(MARS_GEOGRAPHIC, crs, [lon], [lat])
    c, r = ~terrain.transform * (x[0], y[0])
    return r, c


def ll(r, c):
    """Crop (row, col) to signed [lon, lat]."""
    return terrain.lonlat(int(r), int(c))


def disc(r, c, radius_m=RADIUS_M):
    """Slopes inside the radius_m disc around (r, c); None if the disc leaves the crop."""
    rad = int(math.ceil(radius_m / res)) + 1
    r, c = int(round(r)), int(round(c))
    if r - rad < 0 or c - rad < 0 or r + rad >= H or c + rad >= W:
        return None
    yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
    mask = (yy * res) ** 2 + (xx * res * terrain.column_spacing[r] / res) ** 2 <= radius_m ** 2
    block = slope[r - rad:r + rad + 1, c - rad:c + rad + 1][mask]
    return block


def disc_status(r, c):
    """(n_exclude, n_caution, n_invalid) cells in the uncertainty disc; None if off-crop."""
    block = disc(r, c)
    if block is None:
        return None
    return int((block >= EXCLUDE).sum()), int(((block >= CAUTION) & (block < EXCLUDE)).sum()), int(np.isnan(block).sum())


def median_z(r, c, radius_m=6.0):
    """Median elevation in a small disc (metres), NaN-safe."""
    rad = int(math.ceil(radius_m / res))
    r, c = int(round(r)), int(round(c))
    blk = z[max(0, r - rad):r + rad + 1, max(0, c - rad):c + rad + 1]
    return float(np.nanmedian(blk)) if np.isfinite(blk).any() else float("nan")


# ---- 1-2. Height and apron along each traced profile --------------------------------------
lines = {f["properties"]["id"]: f["geometry"]["coordinates"] for f in json.load(open(lines_path))["features"]}
profiles = []
for (elon, elat), (flon, flat) in zip(lines["scarp-edge"], lines["scarp-foot"]):
    er, ec = rc(elon, elat)
    fr, fc = rc(flon, flat)
    top = median_z(er + 15 / res, ec)  # 15 m south of the edge (rows grow southward)
    floor = median_z(fr - 15 / res, fc)  # 15 m north of the foot
    # Apron: from the foot northward, distance until slope stays below caution for 10 m.
    r, calm, apron_m = int(round(fr)), 0, 0.0
    cc = int(round(fc))
    while r > 0 and calm * res < 10:
        s = slope[r, cc]
        calm = calm + 1 if (np.isfinite(s) and s < CAUTION) else 0
        r -= 1
        apron_m += res
    apron_m = max(0.0, apron_m - calm * res)
    face = slope[int(min(er, fr)):int(max(er, fr)) + 1, max(0, cc - 2):cc + 3]
    profiles.append({"lon": round(flon, 6), "edge_lat": elat, "foot_lat": flat,
                     "top_z": round(top, 1), "floor_z": round(floor, 1), "height_m": round(top - floor, 1),
                     "apron_m": round(apron_m, 1),
                     "face_max_slope_deg": round(float(np.nanmax(face)), 1) if np.isfinite(face).any() else None})
heights = np.array([p["height_m"] for p in profiles if math.isfinite(p["height_m"])])
aprons = np.array([p["apron_m"] for p in profiles])
height_m = float(np.median(heights))
buffer_m = max(float(np.percentile(aprons, 75)), FACTOR * float(np.percentile(heights, 75)))

# ---- 3. Candidate points -------------------------------------------------------------------
def search(center_lon, center_lat, accept, max_m=250.0, step_m=3.0):
    """Nearest cell to the centre whose disc passes; prefers zero caution cells within 1.5x the best distance."""
    r0, c0 = rc(center_lon, center_lat)
    best = None
    steps = int(max_m / step_m)
    for dr in range(-steps, steps + 1):
        for dc in range(-steps, steps + 1):
            dist = math.hypot(dr, dc) * step_m
            if dist > max_m:
                continue
            r, c = r0 + dr * step_m / res, c0 + dc * step_m / res * res / terrain.column_spacing[int(min(max(r0, 0), H - 1))]
            st = disc_status(r, c)
            if st is None or st[0] > 0 or st[2] > 0 or not accept(r, c):
                continue
            score = dist + 40.0 * st[1]  # each caution cell costs like 40 m of extra distance
            if best is None or score < best[0]:
                best = (score, r, c, st, dist)
    if best is None:
        return None
    _, r, c, st, dist = best
    lon, lat = ll(r, c)
    return {"lat": round(lat, 6), "lon": round(lon, 6), "moved_m": round(dist, 1),
            "disc_exclude_cells": st[0], "disc_caution_cells": st[1], "elevation_m": round(float(z[int(r), int(c)]), 1)}


def profile_at(lon):
    """Nearest measured profile to lon."""
    return min(profiles, key=lambda p: abs(p["lon"] - lon))


def buffer_at(lon):
    """Rockfall buffer from the foot at lon: max(apron, factor x height) of that profile (Nic's rule)."""
    p = profile_at(lon)
    return max(p["apron_m"], FACTOR * p["height_m"])


def foot_lat_at(lon):
    """Foot latitude of the nearest traced profile."""
    return profile_at(lon)["foot_lat"]


deg_per_m = 1 / 59160.0
pts = {f["properties"]["id"]: f["geometry"]["coordinates"] for f in json.load(open(points_path))["features"]}
north_of_buffer = lambda r, c: ll(r, c)[1] >= foot_lat_at(ll(r, c)[0]) + (buffer_at(ll(r, c)[0]) + RADIUS_M) * deg_per_m
south_of_setback = lambda r, c: ll(r, c)[1] <= min(p[1] for p in lines["scarp-edge"]) - (threshold(rules, "cliff_setback_m") + RADIUS_M) * deg_per_m

mid_lon = -147.9025  # tallest, cleanest part of the face (height ~70 m, small apron)
target = lambda lon, extra: (lon, foot_lat_at(lon) + (buffer_at(lon) + RADIUS_M + extra) * deg_per_m)
primary = search(*target(mid_lon, 10), accept=north_of_buffer, max_m=250)
far_from_primary = lambda r, c: primary is None or math.hypot((ll(r, c)[1] - primary["lat"]) / deg_per_m,
                                                              (ll(r, c)[0] - primary["lon"]) * 34640) > 120
candidates = {
    "habitat": search(*pts["habitat"], accept=lambda r, c: True),
    "observation_primary": primary,
    "observation_backup": search(*target(-147.8975, 10), accept=lambda r, c: north_of_buffer(r, c) and far_from_primary(r, c), max_m=250),
    "drone_perch": search(*target(-147.9050, 40), accept=north_of_buffer, max_m=250),
    "parking": search(-147.8925, 54.1590, accept=south_of_setback, max_m=120),
}
for name in ("observation_primary", "observation_backup", "drone_perch"):
    cand = candidates[name]
    if cand:
        p = profile_at(cand["lon"])
        cand["distance_from_foot_m"] = round((cand["lat"] - p["foot_lat"]) / deg_per_m, 1)
        cand["rockfall_buffer_here_m"] = round(buffer_at(cand["lon"]), 1)
        cand["scarp_height_here_m"] = p["height_m"]
checks = {name: disc_status(*rc(*coords)) for name, coords in pts.items()}

report = {"dtm": terrain.source, "window": list(window), "resolution_m": res,
          "thresholds_deg": {"caution": CAUTION, "exclude": EXCLUDE}, "uncertainty_radius_m": RADIUS_M,
          "scarp_height_m_median": round(height_m, 1), "scarp_height_m_range": [round(float(heights.min()), 1), round(float(heights.max()), 1)],
          "apron_m_median": round(float(np.median(aprons)), 1), "rockfall_buffer_from_foot_m": round(buffer_m, 1),
          "rockfall_rule": f"max(75th pct apron, {FACTOR} x 75th pct height)",
          "geury_points_disc_status_exclude_caution_invalid": checks,
          "candidates": candidates, "profiles": profiles}
json.dump(report, open(out_path, "w"), indent=1)
print(json.dumps({k: v for k, v in report.items() if k != "profiles"}, indent=1))
