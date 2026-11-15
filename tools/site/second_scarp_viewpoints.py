"""Option 1: is there a safe, reachable viewpoint facing ice-consistent (bluish) cliff?

1. Trace the upper scarp (Geury's ice_upper_band) on the DTM: per column, the run of cells
   >= 30 deg between 54.1660 and 54.1690 N; south boundary = top edge, north boundary = foot.
   Height = plain 10 m south of the edge minus floor 10 m north of the foot.
2. No-go = main scarp (setback 20 m, face, rockfall max(apron, height)) + upper scarp (same rules).
3. Viewpoints: flat (no >= 20 deg cell in the 15 m disc), outside every no-go zone, on the floor
   north of a bluish face (upper scarp, or main face west/middle), within 250 m of that face's foot.
4. Walk distance (crew < 20 deg, no-go impassable) from (a) the current parking point and (b) the
   best rover-reachable flat parking cell (< 24 deg, roughness <= 0.5 m). Budget: walk <= 760 m each way.
Candidates only; nothing here is crew clearance.
"""
import json
import math
import sys
import numpy as np
from scipy.ndimage import maximum_filter, median_filter
from skimage.graph import MCP_Geometric
from rasterio.warp import transform as transform_coordinates
from pipeline.terrain import read_terrain, analyze, load_rules, threshold, MARS_GEOGRAPHIC

dtm, report_path, final_path, out_path = sys.argv[1:5]
rep, fin = json.load(open(report_path)), json.load(open(final_path))
rules = load_rules()
CAUTION, EXCLUDE, ROVER = threshold(rules, "crew_caution_deg"), threshold(rules, "crew_exclude_deg"), threshold(rules, "rover_exclude_deg")
SETBACK, ROUGH = threshold(rules, "cliff_setback_m"), threshold(rules, "roughness_m")
t = read_terrain(dtm, tuple(rep["window"]))
an = analyze(t, rules)
slope, rough, z, res = an["slope"], an["roughness"], t.elevation, t.resolution
H, W = slope.shape
row_lat = np.array([t.lonlat(r, 0)[1] for r in range(H)])
col_lon = np.array([t.lonlat(0, c)[0] for c in range(W)])
EW, DEG_M = float(np.median(t.column_spacing)), 59160.0
LAT = row_lat[:, None]


def rc(lon, lat):
    """Signed lon/lat to (row, col)."""
    x, y = transform_coordinates(MARS_GEOGRAPHIC, t.crs, [lon], [lat])
    c, r = ~t.transform * (x[0], y[0])
    return int(round(r)), int(round(c))


def fix_corners(cells, ok):
    """Remove corner-cutting: where a diagonal step passes the shared corner of a cell that `ok` rejects,
    insert the passable orthogonal neighbour, so the stored line only touches allowed cells (route_audit
    walks every cell a line touches). Returns (cells, unfixed_count)."""
    out, unfixed = [tuple(int(v) for v in cells[0])], 0
    for a, b in zip(cells, cells[1:]):
        a, b = tuple(int(v) for v in a), tuple(int(v) for v in b)
        dr, dc = b[0] - a[0], b[1] - a[1]
        if dr and dc:
            c1, c2 = (a[0] + dr, a[1]), (a[0], a[1] + dc)
            if not (ok(c1) and ok(c2)):
                pick = c1 if ok(c1) else (c2 if ok(c2) else None)
                if pick is None:
                    unfixed += 1
                else:
                    out.append(pick)
        out.append(b)
    return np.array(out), unfixed


# ---- 1. Trace the upper scarp ----
upper = []
for c in np.where((col_lon >= -147.9005) & (col_lon <= -147.8910))[0]:
    rows = np.where((row_lat >= 54.1660) & (row_lat <= 54.1690))[0]
    steep = rows[slope[rows, c] >= 30]
    if len(steep) < 3:
        continue
    edge_r, foot_r = steep.max(), steep.min()  # larger row = further south = top edge
    top = float(np.nanmedian(z[edge_r + 8:edge_r + 13, c]))
    floor = float(np.nanmedian(z[max(0, foot_r - 12):foot_r - 7, c]))
    r, calm, apron = foot_r, 0, 0.0
    while r > 0 and calm * res < 10 and apron < 150:
        calm = calm + 1 if slope[r, c] < CAUTION else 0
        r -= 1
        apron += res
    upper.append({"col": int(c), "lon": float(col_lon[c]), "edge_lat": float(row_lat[edge_r]), "foot_lat": float(row_lat[foot_r]),
                  "height_m": top - floor, "apron_m": max(0.0, apron - calm * res)})
up_lon = np.array([u["lon"] for u in upper])
k = 15
smooth = lambda key: median_filter(np.array([u[key] for u in upper]), size=k, mode="nearest")
up_edge, up_foot, up_h, up_ap = smooth("edge_lat"), smooth("foot_lat"), smooth("height_m"), smooth("apron_m")
real = up_h >= 8  # ignore columns where the "scarp" is under 8 m tall (rough ground, not a cliff)

# ---- 2. No-go zones ----
def band_nogo(lons, edges, foots, buffers, valid):
    """Cells between (edge - setback) and (foot + buffer) over the traced longitude extent."""
    lons, edges, foots, buffers = lons[valid], edges[valid], foots[valid], buffers[valid]
    inside = (col_lon >= lons.min() - 0.0004) & (col_lon <= lons.max() + 0.0004)
    e = np.interp(col_lon, lons, edges)
    f = np.interp(col_lon, lons, foots)
    b = np.interp(col_lon, lons, buffers)
    return inside[None, :] & (LAT >= (e - SETBACK / DEG_M)[None, :]) & (LAT <= (f + b / DEG_M)[None, :]), f, b

prof = sorted(rep["profiles"], key=lambda p: p["lon"])
m_lon = np.array([p["lon"] for p in prof])
nogo_main, f_main, b_main = band_nogo(m_lon, np.array([p["edge_lat"] for p in prof]), np.array([p["foot_lat"] for p in prof]),
                                      np.array([max(p["apron_m"], p["height_m"]) for p in prof]), np.ones(len(prof), bool))
up_buffer = np.maximum(np.minimum(up_ap, 100), up_h)  # apron capped at 100 m (rough floor inflates it)
# Optional floor (argv[5]): match the pipeline's single site-wide scarp height (conservative for the shorter second scarp).
up_buffer_draw = up_buffer.copy()
if len(sys.argv) > 5:
    up_buffer = np.maximum(up_buffer, float(sys.argv[5]))  # routing/selection buffer (with safety margin)
if len(sys.argv) > 6:
    up_buffer_draw = np.maximum(up_buffer_draw, float(sys.argv[6]))  # drawn hazard buffer (the pipeline rule)
nogo_up, f_up, b_up = band_nogo(up_lon, up_edge, up_foot, up_buffer, real)
nogo = nogo_main | nogo_up

kk = int(math.ceil(15 / res)) + 1
yy, xx = np.mgrid[-kk:kk + 1, -kk:kk + 1]
FOOT = (yy * res) ** 2 + (xx * EW) ** 2 <= 225
FOOT17 = (yy * res) ** 2 + (xx * EW) ** 2 <= 17 ** 2  # 15 m uncertainty + 2 m so grid rounding cannot tip a point over
flat =~maximum_filter((slope >= EXCLUDE) | ~np.isfinite(slope), footprint=FOOT17) & ~nogo

# ---- 3. Viewpoint candidates facing bluish faces ----
up_ext = (col_lon >= up_lon[real].min()) & (col_lon <= up_lon[real].max())
# Face only the bluish part: Geury's ice_upper_band spans -147.8998 to -147.8916; keep ~60 m inside its east end.
facing_wide = up_ext & (col_lon >= -147.8976) & (col_lon <= -147.8934)  # Geury: 25-43% bluish (backup)
up_ext &= (col_lon >= -147.8962) & (col_lon <= -147.8941)  # Geury: bluest stretch, 29-43% (primary)
facing_up = up_ext[None, :] & (LAT >= (f_up + (b_up + 15) / DEG_M)[None, :]) & (LAT <= (f_up + 250 / DEG_M)[None, :])
wm = (col_lon >= -147.916) & (col_lon <= -147.9002)  # Geury's bluish west/middle of the main face
facing_main = wm[None, :] & (LAT >= (f_main + (b_main + 15) / DEG_M)[None, :]) & (LAT <= (f_main + 250 / DEG_M)[None, :])

walk_cost = np.where((slope >= EXCLUDE) | ~np.isfinite(slope) | nogo, -1.0, 1.0)
park = rc(fin["points"]["parking"]["lon"], fin["points"]["parking"]["lat"])
from_park, _ = MCP_Geometric(walk_cost).find_costs([park])
drive_cost = np.where(slope < CAUTION, 1.0, 2.0)
drive_cost[(slope >= ROVER) | ~np.isfinite(slope) | nogo | ~(rough <= ROUGH)] = -1
hab = rc(fin["points"]["habitat"]["lon"], fin["points"]["habitat"]["lat"])
drive_cum, _ = MCP_Geometric(drive_cost).find_costs([hab])
park_ok = flat & np.isfinite(drive_cum) & (drive_cum < 1e8) & (drive_cost > 0)
park_cells = list(zip(*np.where(park_ok)))
walk_mcp = MCP_Geometric(walk_cost)
from_any_park, _ = walk_mcp.find_costs(park_cells)


def best(mask, field, label):
    """Closest-walk flat candidate inside mask using the walk field; with its parking via traceback."""
    vals = np.where(mask & flat, field, np.inf)
    if not np.isfinite(vals).any():
        return {"target": label, "found": False, "flat_cells": int((mask & flat).sum())}
    r, c = np.unravel_index(np.argmin(vals), vals.shape)
    out = {"target": label, "found": True, "lat": round(float(row_lat[r]), 6), "lon": round(float(col_lon[c]), 6),
           "elevation_m": round(float(z[r, c]), 1), "walk_m": round(float(vals[r, c]) * res, 1), "flat_cells": int((mask & flat).sum())}
    return out, (r, c)


res_out = {"upper_scarp": {"columns": int(real.sum()), "lon_range": [round(float(up_lon[real].min()), 5), round(float(up_lon[real].max()), 5)],
                           "edge_lat_range": [round(float(up_edge[real].min()), 5), round(float(up_edge[real].max()), 5)],
                           "foot_lat_range": [round(float(up_foot[real].min()), 5), round(float(up_foot[real].max()), 5)],
                           "height_m_median": round(float(np.median(up_h[real])), 1), "height_m_max": round(float(up_h[real].max()), 1),
                           "rockfall_buffer_m_median": round(float(np.median(up_buffer[real])), 1)}}
vp = fin["points"]["observation_primary"]
r0, c0 = rc(vp["lon"], vp["lat"])
res_out["old_viewpoint_in_new_nogo"] = bool(nogo_up[r0, c0])
res_out["old_viewpoint_dist_to_upper_edge_m"] = round(float((np.interp(vp["lon"], up_lon[real], up_edge[real]) - vp["lat"]) * DEG_M), 1)
for label, mask in (("upper_scarp", facing_up), ("main_face_west_middle", facing_main)):
    for src, field in (("current_parking", from_park), ("best_parking", from_any_park)):
        got = best(mask, field, label)
        if isinstance(got, tuple):
            info, (r, c) = got
            if src == "best_parking":
                trace = walk_mcp.traceback((r, c))
                pr, pc = trace[0]
                info["parking"] = {"lat": round(float(row_lat[pr]), 6), "lon": round(float(col_lon[pc]), 6),
                                   "drive_cost": round(float(drive_cum[pr, pc]), 1)}
            res_out[f"{label}__{src}"] = info
        else:
            res_out[f"{label}__{src}"] = got
res_out["_upper_profiles"] = [{"lon": round(float(up_lon[i]), 5), "edge": round(float(up_edge[i]), 5), "foot": round(float(up_foot[i]), 5),
                               "h": round(float(up_h[i]), 1), "buf": round(float(up_buffer[i]), 1)} for i in range(0, len(up_lon), 10) if real[i]]
json.dump(res_out, open(out_path, "w"), indent=1)
print(json.dumps({k2: v for k2, v in res_out.items() if not k2.startswith("_")}, indent=1))

# ---- Backup viewpoint and the walk geometry for the chosen primary ----
prim = rc(res_out["upper_scarp__current_parking"]["lon"], res_out["upper_scarp__current_parking"]["lat"])
rr, cc = np.mgrid[0:H, 0:W]
sep = np.hypot((rr - prim[0]) * res, (cc - prim[1]) * EW)
walk_m = from_park * res
facing_up_wide = facing_wide[None, :] & (LAT >= (f_up + (b_up + 15) / DEG_M)[None, :]) & (LAT <= (f_up + 250 / DEG_M)[None, :])
cand = facing_up_wide & flat & (sep >= 100) & (walk_m <= 760)
if cand.any():
    vals = np.where(cand, walk_m, np.inf)
    br, bc = np.unravel_index(np.argmin(vals), vals.shape)
    res_out["backup_facing_upper"] = {"lat": round(float(row_lat[br]), 6), "lon": round(float(col_lon[bc]), 6), "walk_m": round(float(vals[br, bc]), 1),
                                      "separation_m": round(float(sep[br, bc]), 1), "elevation_m": round(float(z[br, bc]), 1)}
else:
    res_out["backup_facing_upper"] = None
mcp = MCP_Geometric(walk_cost)
mcp.find_costs([park], [prim])
cells, res_out["main_walk_unfixed_corners"] = fix_corners(np.array(mcp.traceback(prim)), lambda c: bool(np.isfinite(slope[c]) and slope[c] < EXCLUDE and not nogo[c]))
res_out["primary_walk"] = {"length_m": round(float(np.hypot(np.diff(cells[:, 0]) * res, np.diff(cells[:, 1]) * EW).sum()), 1),
                           "max_slope_deg": round(float(np.nanmax(slope[cells[:, 0], cells[:, 1]])), 1),
                           "coords": [[round(float(col_lon[c]), 6), round(float(row_lat[r]), 6)] for r, c in cells]}  # every DTM cell: no simplification (route_audit checks every cell)
i = int(np.argmin(np.abs(up_lon - col_lon[prim[1]])))
res_out["primary_view"] = {"face_height_m": round(float(up_h[i]), 1), "foot_lat": round(float(up_foot[i]), 5),
                           "distance_from_foot_m": round(float((row_lat[prim[0]] - up_foot[i]) * DEG_M), 1), "rockfall_buffer_m": round(float(up_buffer[i]), 1),
                           "in_geury_upper_band_lon": bool(-147.8998 <= col_lon[prim[1]] <= -147.8916)}
up_lines = {"edge": [[round(float(up_lon[j]), 6), round(float(up_edge[j]), 6)] for j in range(0, len(up_lon), 6) if real[j]],
            "foot": [[round(float(up_lon[j]), 6), round(float(up_foot[j]), 6)] for j in range(0, len(up_lon), 6) if real[j]]}
res_out["_upper_lines"] = up_lines
json.dump(res_out, open(out_path, "w"), indent=1)
print(json.dumps({k2: res_out[k2] for k2 in ("backup_facing_upper", "primary_view")}, indent=1))
print(json.dumps({k2: v for k2, v in res_out["primary_walk"].items() if k2 != "coords"}))
# ---- Backup viewpoint (fallback if the search found none) ----
if res_out["backup_facing_upper"] is None and len(sys.argv) > 7:
    # Fallback backup (argv[7] = "lat,lon"): a previously checked viewpoint, re-verified here.
    blat, blon = map(float, sys.argv[7].split(","))
    br0, bc0 = rc(blon, blat)
    # Snap to the nearest flat cell within 6 m (grid rounding can tip the exact cell over the 17 m rule).
    w6 = int(math.ceil(6 / res))
    near_cells = [(math.hypot(dr * res, dc * EW), br0 + dr, bc0 + dc) for dr in range(-w6, w6 + 1) for dc in range(-w6, w6 + 1)
                  if flat[br0 + dr, bc0 + dc] and math.hypot(dr * res, dc * EW) <= 6]
    if not near_cells:
        raise ValueError("fallback backup has no flat cell within 6 m")
    _, br0, bc0 = min(near_cells)
    blon, blat = float(col_lon[bc0]), float(row_lat[br0])
    res_out["backup_facing_upper"] = {"lat": blat, "lon": blon, "walk_m": round(float(walk_m[br0, bc0]), 1),
                                      "separation_m": round(float(sep[br0, bc0]), 1), "elevation_m": round(float(z[br0, bc0]), 1),
                                      "note": "fallback: earlier checked viewpoint facing the weaker-blue east stretch (~16%)"}
bk = rc(res_out["backup_facing_upper"]["lon"], res_out["backup_facing_upper"]["lat"])
# ---- Backup route: an independent walk between the BACKUP viewpoint and the parked rover (route_audit objective) ----
near = np.zeros_like(slope, dtype=bool)
g = int(25 / res)
for r, c in cells:
    near[max(0, r - g):r + g, max(0, c - g):c + g] = True
# Shortest legal walk to the backup viewpoint (a different destination, so sharing the first stretch is fine).
alt = np.where(walk_cost > 0, 1.0, -1.0)
mcp2 = MCP_Geometric(alt)
mcp2.find_costs([bk], [park])
cells2, res_out["backup_walk_unfixed_corners"] = fix_corners(np.array(mcp2.traceback(park)), lambda c: bool(np.isfinite(slope[c]) and slope[c] < EXCLUDE and not nogo[c]))
res_out["backup_walk"] = {"length_m": round(float(np.hypot(np.diff(cells2[:, 0]) * res, np.diff(cells2[:, 1]) * EW).sum()), 1),
                          "max_slope_deg": round(float(np.nanmax(slope[cells2[:, 0], cells2[:, 1]])), 1),
                          "fraction_within_25m_of_main": round(float(near[cells2[:, 0], cells2[:, 1]].mean()), 2),
                          "coords": [[round(float(col_lon[c]), 6), round(float(row_lat[r]), 6)] for r, c in cells2]}
res_out["upper_profiles"] = [{"lon": round(float(up_lon[i]), 6), "edge_lat": round(float(up_edge[i]), 6), "foot_lat": round(float(up_foot[i]), 6),
                              "height_m": round(float(up_h[i]), 1), "apron_m": round(float(min(up_ap[i], 100)), 1), "buffer_m": round(float(up_buffer_draw[i]), 1), "routing_buffer_m": round(float(up_buffer[i]), 1)}
                             for i in range(0, len(up_lon), 8) if real[i]]
disc_cells = lambda p: int(((slope[p[0] - kk:p[0] + kk + 1, p[1] - kk:p[1] + kk + 1] >= EXCLUDE) & FOOT).sum())
res_out["steep_cells_in_15m_disc"] = {"primary": disc_cells(prim), "backup": disc_cells(bk)}
res_out["points_elevation_m"] = {"primary": round(float(z[prim]), 1), "backup": round(float(z[bk]), 1)}
json.dump(res_out, open(out_path, "w"), indent=1)
print(json.dumps({k2: ({kk2: vv for kk2, vv in v.items() if kk2 != "coords"} if isinstance(v, dict) else v) for k2, v in res_out.items()
                  if k2 in ("backup_walk", "steep_cells_in_15m_disc", "points_elevation_m")}, indent=1))
print("upper profiles:", len(res_out["upper_profiles"]))
