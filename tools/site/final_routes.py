"""Final placeholder geometry for the drive-then-walk plan at the scarp's reachable east end.

Inputs: DTM, site_report.json (scarp profiles, habitat), points_opt.json (primary viewpoint).
Rules (Nic's hazard_rules.json): crew walk < 20 deg; crew rover < 24 deg and roughness <= 0.5 m;
both stay out of the scarp face, the 20 m edge setback and the per-profile rockfall buffer;
every chosen point has no >= 20 deg cell within its 15 m uncertainty disc.
Parking: rover-reachable flat cell 150-300 m walk from the viewpoint, lowest drive cost.
Placeholder planning; Nic's pipeline produces the official routes. Nothing is crew clearance.
"""
import json
import math
import sys
import numpy as np
from scipy.ndimage import maximum_filter
from skimage.graph import MCP_Geometric
from rasterio.warp import transform as transform_coordinates
from pipeline.terrain import read_terrain, analyze, load_rules, threshold, MARS_GEOGRAPHIC

dtm_path, report_path, opt_path, out_path = sys.argv[1:5]
rep, opt = json.load(open(report_path)), json.load(open(opt_path))
rules = load_rules()
CAUTION, EXCLUDE = threshold(rules, "crew_caution_deg"), threshold(rules, "crew_exclude_deg")
ROVER, SETBACK, ROUGH = threshold(rules, "rover_exclude_deg"), threshold(rules, "cliff_setback_m"), threshold(rules, "roughness_m")
terrain = read_terrain(dtm_path, tuple(rep["window"]))
an = analyze(terrain, rules)
slope, rough, z = an["slope"], an["roughness"], terrain.elevation
res, (H, W), DEG_M = terrain.resolution, slope.shape, 59160.0
row_lat = np.array([terrain.lonlat(r, 0)[1] for r in range(H)])
col_lon = np.array([terrain.lonlat(0, c)[0] for c in range(W)])
EW = res * 0.5856 / 0.6428  # metres per column at 54.16 N (standard parallel 50 N)


def rc(lon, lat):
    """Signed lon/lat to integer (row, col)."""
    x, y = transform_coordinates(MARS_GEOGRAPHIC, terrain.crs, [lon], [lat])
    c, r = ~terrain.transform * (x[0], y[0])
    return int(round(r)), int(round(c))


def ll(r, c):
    """(row, col) to [lon, lat] rounded."""
    return [round(float(col_lon[c]), 6), round(float(row_lat[r]), 6)]


prof = sorted(rep["profiles"], key=lambda p: p["lon"])
p_lon = np.array([p["lon"] for p in prof])
e_col = np.interp(col_lon, p_lon, [p["edge_lat"] for p in prof])
f_col = np.interp(col_lon, p_lon, [p["foot_lat"] for p in prof])
b_col = np.interp(col_lon, p_lon, [max(p["apron_m"], p["height_m"]) for p in prof])
inside = (col_lon >= p_lon[0] - 0.0004) & (col_lon <= p_lon[-1] + 0.0004)
LAT = row_lat[:, None]
nogo = inside[None, :] & (LAT >= (e_col - SETBACK / DEG_M)[None, :]) & (LAT <= (f_col + b_col / DEG_M)[None, :])
k = int(math.ceil(15 / res)) + 1
yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
flat = ~maximum_filter((slope >= EXCLUDE) | ~np.isfinite(slope), footprint=(yy * res) ** 2 + (xx * EW) ** 2 <= 225) & ~nogo

walk_cost = np.ones_like(slope)
walk_cost[slope >= CAUTION] = 3.0
walk_cost[(slope >= EXCLUDE) | ~np.isfinite(slope) | nogo] = -1
drive_cost = np.where(slope < CAUTION, 1.0, 2.0)
drive_cost[(slope >= ROVER) | ~np.isfinite(slope) | nogo | ~(rough <= ROUGH)] = -1


def route(cost, a, b):
    """Least-cost cell path a->b (row, col); returns (cells, metres, max slope)."""
    mcp = MCP_Geometric(cost)
    mcp.find_costs([a], [b])
    cells = np.array(mcp.traceback(b))
    steps = np.diff(cells, axis=0)
    metres = float(np.hypot(steps[:, 0] * res, steps[:, 1] * EW).sum())
    return cells, metres, round(float(np.nanmax(slope[cells[:, 0], cells[:, 1]])), 1)


def thin(cells, every_m=12.0):
    """Cells to [lon, lat] vertices about every_m apart (ends kept)."""
    out, last = [ll(*cells[0])], cells[0]
    for cell in cells[1:-1]:
        if math.hypot((cell[0] - last[0]) * res, (cell[1] - last[1]) * EW) >= every_m:
            out.append(ll(*cell))
            last = cell
    out.append(ll(*cells[-1]))
    return out


hab = rc(rep["candidates"]["habitat"]["lon"], rep["candidates"]["habitat"]["lat"])
obs = rc(opt["primary"]["lon"], opt["primary"]["lat"])
drive_cum, _ = MCP_Geometric(drive_cost).find_costs([hab])
walk_from_obs, _ = MCP_Geometric(np.where(walk_cost > 0, 1.0, -1.0)).find_costs([obs])
walk_m = walk_from_obs * res
park_mask = flat & (drive_cost > 0) & np.isfinite(drive_cum) & (walk_m >= 150) & (walk_m <= 300)
pr, pc = np.unravel_index(np.argmin(np.where(park_mask, drive_cum, np.inf)), slope.shape)
park = (int(pr), int(pc))

# Backup viewpoint: flat, beyond the buffer, >= 120 m from the primary, shortest walk from the parking.
walk_from_park, _ = MCP_Geometric(np.where(walk_cost > 0, 1.0, -1.0)).find_costs([park])
view_mask = flat & inside[None, :] & (LAT >= (f_col + (b_col + 15) / DEG_M)[None, :]) & (LAT <= (f_col + 250 / DEG_M)[None, :])
rr, cc = np.mgrid[0:H, 0:W]
sep = np.hypot((rr - obs[0]) * res, (cc - obs[1]) * EW)
backup_view, backup_rule = None, None
for min_sep, max_walk in ((60, 500), (40, 800), (30, 1200)):
    bk = np.where(view_mask & (sep >= min_sep) & (walk_from_park * res <= max_walk), walk_from_park, np.inf)
    if np.isfinite(bk).any():
        br, bc = np.unravel_index(np.argmin(bk), slope.shape)
        backup_view, backup_rule = (int(br), int(bc)), {"min_separation_m": min_sep, "max_walk_m": max_walk}
        break
print("viewpoint cells reachable within 1200 m walk of parking:", int((view_mask & (walk_from_park * res <= 1200)).sum()), file=sys.stderr)

drive1, d1, s1 = route(drive_cost, hab, park)
sim = tuple(drive1[int(len(drive1) * 0.45)])
blocked = drive_cost.copy()
h = int(100 / res)
blocked[max(0, sim[0] - h):sim[0] + h, max(0, sim[1] - h):sim[1] + h] = -1
drive2, d2, s2 = route(blocked, hab, park)
walk1, w1, ws1 = route(walk_cost, park, obs)
near = np.zeros_like(slope, dtype=bool)
g = int(25 / res)
for r, c in walk1:
    near[max(0, r - g):r + g, max(0, c - g):c + g] = True
alt = walk_cost.copy()
alt[near & (alt > 0)] *= 6
walk2, w2, ws2 = route(alt, obs, park)
shared = float(near[walk2[:, 0], walk2[:, 1]].mean())
sim_box = [ll(sim[0] + h, sim[1] - h), ll(sim[0] - h, sim[1] + h)]  # [SW, NE] corners

FOOT = (yy * res) ** 2 + (xx * EW) ** 2 <= 225
disc = lambda p: int(((slope[p[0] - k:p[0] + k + 1, p[1] - k:p[1] + k + 1] >= EXCLUDE) & FOOT).sum())
point = lambda p: {"lon": ll(*p)[0], "lat": ll(*p)[1], "elevation_m": round(float(z[p]), 1)}
fprof = min(prof, key=lambda p: abs(p["lon"] - col_lon[obs[1]]))
out = {"note": __doc__.strip().splitlines()[0],
       "points": {"habitat": point(hab), "parking": point(park), "observation_primary": point(obs),
                  "observation_backup": point(backup_view) if backup_view else None},
       "backup_rule": backup_rule,
       "view": {"face_height_m": fprof["height_m"], "distance_from_foot_m": round((row_lat[obs[0]] - fprof["foot_lat"]) * DEG_M, 1),
                "rockfall_buffer_m": max(fprof["apron_m"], fprof["height_m"])},
       "sim_discovery": {"center": ll(*sim), "box_sw_ne": sim_box},
       "drive_v1": {"coords": thin(drive1), "length_m": round(d1, 1), "max_slope_deg": s1},
       "drive_v2": {"coords": thin(drive2), "length_m": round(d2, 1), "max_slope_deg": s2},
       "walk_main": {"coords": thin(walk1, 8), "length_m": round(w1, 1), "max_slope_deg": ws1},
       "walk_backup": {"coords": thin(walk2, 8), "length_m": round(w2, 1), "max_slope_deg": ws2, "fraction_within_25m_of_main": round(shared, 2)},
       "backup_view_walk_from_parking_m": round(float(walk_from_park[backup_view]) * res, 1) if backup_view else None,
       "steep_cells_in_15m_disc": {"parking": disc(park), "observation_primary": disc(obs),
                                   "observation_backup": disc(backup_view) if backup_view else None}}
json.dump(out, open(out_path, "w"), indent=1)
print(json.dumps({k2: ({kk: vv for kk, vv in v.items() if kk != "coords"} if isinstance(v, dict) else v) for k2, v in out.items()}, indent=1))
