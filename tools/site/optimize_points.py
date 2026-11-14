"""Choose the observation point and crew-rover parking point together to minimise the walk.

1. rover-reachable cells: cumulative drive cost from the habitat on the rover grid (< 24 deg).
2. flat cells: no slope >= 20 deg within the 15 m uncertainty disc.
3. observation candidates: flat, on the pit floor beyond the per-profile rockfall buffer, within
   250 m of the foot, along the traced face.
4. for each candidate: walking distance field (crew grid, < 20 deg, outside no-go zones) and the
   nearest flat rover-reachable cell = parking. Pick the pair with the shortest walk.
Placeholder planning only: Nic's pipeline produces the official routes; nothing is crew clearance.
"""
import json
import math
import sys
import numpy as np
from scipy.ndimage import maximum_filter
from skimage.graph import MCP_Geometric
from rasterio.warp import transform as transform_coordinates
from pipeline.terrain import read_terrain, analyze, load_rules, threshold, MARS_GEOGRAPHIC

dtm_path, report_path, out_path = sys.argv[1:4]
rep = json.load(open(report_path))
rules = load_rules()
CAUTION, EXCLUDE = threshold(rules, "crew_caution_deg"), threshold(rules, "crew_exclude_deg")
ROVER, SETBACK = threshold(rules, "rover_exclude_deg"), threshold(rules, "cliff_setback_m")
terrain = read_terrain(dtm_path, tuple(rep["window"]))
analysis = analyze(terrain, rules)
slope, rough = analysis["slope"], analysis["roughness"]
ROUGH = threshold(rules, "roughness_m")
res, (H, W), DEG_M = terrain.resolution, slope.shape, 59160.0
row_lat = np.array([terrain.lonlat(r, 0)[1] for r in range(H)])
col_lon = np.array([terrain.lonlat(0, c)[0] for c in range(W)])


def rc(lon, lat):
    """Signed lon/lat to integer (row, col)."""
    x, y = transform_coordinates(MARS_GEOGRAPHIC, terrain.crs, [lon], [lat])
    c, r = ~terrain.transform * (x[0], y[0])
    return int(round(r)), int(round(c))


prof = sorted(rep["profiles"], key=lambda p: p["lon"])
p_lon = np.array([p["lon"] for p in prof])
e_col = np.interp(col_lon, p_lon, [p["edge_lat"] for p in prof])
f_col = np.interp(col_lon, p_lon, [p["foot_lat"] for p in prof])
b_col = np.interp(col_lon, p_lon, [max(p["apron_m"], p["height_m"]) for p in prof])
h_col = np.interp(col_lon, p_lon, [p["height_m"] for p in prof])
inside = (col_lon >= p_lon[0] - 0.0004) & (col_lon <= p_lon[-1] + 0.0004)
LAT = row_lat[:, None]
nogo = inside[None, :] & (LAT >= (e_col - SETBACK / DEG_M)[None, :]) & (LAT <= (f_col + b_col / DEG_M)[None, :])

k = int(math.ceil(15 / res))
yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
footprint = (yy ** 2 + (xx * 0.585 / 0.643) ** 2) * res ** 2 <= 15 ** 2  # ~disc (E-W spacing smaller at 54 N)
steep_near = maximum_filter((slope >= EXCLUDE) | ~np.isfinite(slope), footprint=footprint)
flat = ~steep_near & ~nogo

walk_cost = np.where(slope < CAUTION, 1.0, 1.0)  # pure distance for the walk length
walk_cost[(slope >= EXCLUDE) | ~np.isfinite(slope) | nogo] = -1  # negative = impassable in MCP
drive_cost = np.where(slope < CAUTION, 1.0, 2.0)
# Crew rover: slope < 24 deg AND smooth ground (3 m elevation range <= roughness_m); crew can walk rough ground.
drive_cost[(slope >= ROVER) | ~np.isfinite(slope) | nogo | ~(rough <= ROUGH)] = -1

hab = rc(rep["candidates"]["habitat"]["lon"], rep["candidates"]["habitat"]["lat"])
drive_mcp = MCP_Geometric(drive_cost)
drive_cum, _ = drive_mcp.find_costs([hab])
reachable = np.isfinite(drive_cum) & (drive_cum < 1e8) & (drive_cost > 0)
park_ok = flat & reachable

# Observation candidates: every flat floor cell beyond the buffer, within 250 m of the foot.
cand_mask = flat & inside[None, :] & (LAT >= (f_col + (b_col + 15) / DEG_M)[None, :]) & (LAT <= (f_col + 250 / DEG_M)[None, :])
print(f"observation cells: {int(cand_mask.sum())}, rover-reachable flat cells: {int(park_ok.sum())}", file=sys.stderr)

# One multi-source walk from every possible parking cell; traceback gives each observation cell its parking.
park_cells = list(zip(*np.where(park_ok)))
walk_mcp = MCP_Geometric(walk_cost)
walk_cum, _ = walk_mcp.find_costs(park_cells)
results = []
rs, cs = np.where(cand_mask & np.isfinite(walk_cum))
order = np.argsort(walk_cum[rs, cs])
for i in order[:4000:20]:  # the 4000 shortest walks, every 20th, to keep tracebacks cheap
    r, c = int(rs[i]), int(cs[i])
    route = walk_mcp.traceback((r, c))
    results.append({"walk_m": round(float(walk_cum[r, c]) * res, 1), "obs": (r, c), "park": tuple(route[0]),
                    "face_height_m": round(float(h_col[c]), 1),
                    "dist_from_foot_m": round((row_lat[r] - f_col[c]) * DEG_M, 1)})
results.sort(key=lambda x: x["walk_m"])


def as_point(rcpair):
    """(row, col) to {lat, lon, elevation_m}."""
    r, c = rcpair
    return {"lat": round(float(row_lat[r]), 6), "lon": round(float(col_lon[c]), 6),
            "elevation_m": round(float(terrain.elevation[r, c]), 1)}


# Prefer a view of the tall middle of the face: among walks within 150 m of the best, take the tallest face.
best_walk = results[0]["walk_m"]
pool = [x for x in results if x["walk_m"] <= best_walk + 150]
primary = max(pool, key=lambda x: (x["face_height_m"], -x["walk_m"]))
# Backup: shortest walk from the same parking, at least 120 m from the primary.
mcp = MCP_Geometric(walk_cost)
from_park, _ = mcp.find_costs([primary["park"]])
backup = None
for r, c in zip(rs[::5].tolist(), cs[::5].tolist()):
    sep = math.hypot((row_lat[r] - row_lat[primary["obs"][0]]) * DEG_M, (col_lon[c] - col_lon[primary["obs"][1]]) * DEG_M * 0.585)
    d = float(from_park[r, c]) * res
    if sep >= 120 and math.isfinite(d) and (backup is None or d < backup[0]):
        backup = (d, (r, c))
out = {"primary": {**as_point(primary["obs"]), "walk_from_parking_m": primary["walk_m"],
                   "face_height_m": primary["face_height_m"], "distance_from_foot_m": primary["dist_from_foot_m"]},
       "parking": {**as_point(primary["park"]), "drive_cost_from_habitat": round(float(drive_cum[primary["park"]]), 1)},
       "backup": {**as_point(backup[1]), "walk_from_parking_m": round(backup[0], 1)} if backup else None,
       "top5_by_walk": [{"obs": as_point(x["obs"]), "walk_m": x["walk_m"], "face_height_m": x["face_height_m"]} for x in results[:5]],
       "n_candidates": len(results)}
json.dump(out, open(out_path, "w"), indent=1)
print(json.dumps(out, indent=1))
