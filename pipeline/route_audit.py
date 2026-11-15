"""Audit published route lines against the real DTM: python -m pipeline.route_audit.

For every LineString in routes.geojson this measures, without changing the line:
geometric length (Mars sphere, R = 3,389.5 km) against the claimed stats, start and end offsets
from the intended mission endpoints, the elevation/slope profile over every DTM cell the line
crosses (supercover traversal, so a narrow hazard between sparse vertices is not skipped),
caution/exclusion/unknown intersections, crossings of the traced scarp face and whether the
line stays inside the analysed terrain. The verdict is never "ok": the best possible outcome is
candidate_requires_inspection, because model feasibility is not crew clearance.
"""

import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
from time import perf_counter

import numpy as np
import rasterio
from rasterio.warp import transform as transform_coordinates

from pipeline.export import write_json
from pipeline.itinerary import mars_distance, polyline_m
from pipeline.logging_config import configure_logging, event, operation, traced
from pipeline.slope_mvp import DEFAULT_DTM, window_for_bounds
from pipeline.terrain import MARS_GEOGRAPHIC, analyze, load_rules, read_terrain, signed_longitude, threshold

SCHEMA_VERSION = "1.0"
PROFILE_POINTS = 240  # elevation-profile samples kept per route in the JSON
LENGTH_TOLERANCE_M = 15.0  # plus 2 % of the length: claimed stats are rounded
# Which mission endpoint each route kind is meant to reach (None: no declared objective).
OBJECTIVE = {"orbital_guess": "observation_primary", "main": "observation_primary",
             "backup": None, "rover_path": None}
STATUS_ORDER = ("geometry_invalid", "outside_assessed_terrain", "excluded_terrain", "unassessed_terrain",
                "endpoint_mismatch", "candidate_requires_inspection")


def canonical_sha256(payload):
    """SHA-256 of payload as sorted, compact JSON (independent of file line endings and spacing)."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def supercover(x0, y0, x1, y1):
    """Every grid cell a straight segment touches, in order, with the segment fraction where each is entered.

    Coordinates are continuous (col, row) pixel units: cell (c, r) spans [c, c+1) x [r, r+1).
    At an exact corner crossing both side cells are included (conservative). Returns a list of
    ((col, row), t_enter) with t in [0, 1].
    """
    cx, cy = math.floor(x0), math.floor(y0)
    ex, ey = math.floor(x1), math.floor(y1)
    dx, dy = x1 - x0, y1 - y0
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    t_dx = abs(1 / dx) if dx else math.inf
    t_dy = abs(1 / dy) if dy else math.inf
    t_x = ((cx + (sx > 0)) - x0) / dx if dx else math.inf
    t_y = ((cy + (sy > 0)) - y0) / dy if dy else math.inf
    cells = [((cx, cy), 0.0)]
    for _ in range(abs(ex - cx) + abs(ey - cy) + 2):
        if (cx, cy) == (ex, ey):
            break
        if math.isclose(t_x, t_y, abs_tol=1e-12):  # passes exactly through a corner
            if t_x > 1:
                break
            cells.append(((cx + sx, cy), t_x))
            cells.append(((cx, cy + sy), t_y))
            cx, cy, t = cx + sx, cy + sy, t_x
            t_x += t_dx
            t_y += t_dy
        elif t_x < t_y:
            if t_x > 1:
                break
            cx, t = cx + sx, t_x
            t_x += t_dx
        else:
            if t_y > 1:
                break
            cy, t = cy + sy, t_y
            t_y += t_dy
        cells.append(((cx, cy), t))
    return cells


def point_in_polygon(x, y, ring):
    """Even-odd test of points (arrays x, y) against ring [[x, y], ...]; returns a bool array."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    inside = np.zeros(x.shape, dtype=bool)
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        crosses = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xcross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (x < xcross)
    return inside


def scarp_face(scarp):
    """Closed [lon, lat] ring between the traced scarp edge and foot lines, or None if either is missing."""
    lines = {f["properties"]["id"]: f["geometry"]["coordinates"] for f in (scarp or {}).get("features", [])
             if f.get("geometry", {}).get("type") == "LineString"}
    if "scarp-edge" not in lines or "scarp-foot" not in lines:
        return None
    return lines["scarp-edge"] + list(reversed(lines["scarp-foot"]))


def distance_to_polyline_m(point, line):
    """Approximate shortest distance in metres from [lon, lat] point to a [lon, lat] polyline (local tangent plane)."""
    lat0 = math.radians(point[1])
    k = math.radians(1) * 3_389_500.0
    px, py = 0.0, 0.0
    best = math.inf
    for a, b in zip(line, line[1:]):
        ax, ay = (a[0] - point[0]) * k * math.cos(lat0), (a[1] - point[1]) * k
        bx, by = (b[0] - point[0]) * k * math.cos(lat0), (b[1] - point[1]) * k
        vx, vy = bx - ax, by - ay
        t = 0.0 if vx == vy == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
        best = min(best, math.hypot(ax + t * vx - px, ay + t * vy - py))
    return best


class TerrainGrid:
    """DTM crop plus its analysis, addressed by signed [lon, lat]; built once for all routes."""

    def __init__(self, terrain, analysis, rules):
        """terrain: pipeline.terrain.Terrain crop; analysis: terrain.analyze output; rules: hazard rules."""
        self.terrain, self.slope, self.valid = terrain, analysis["slope"], analysis["valid"]
        self.roughness = analysis.get("roughness")
        self.lon0 = float(terrain.crs.to_dict().get("lon_0", 0))
        self.caution = float(threshold(rules, "crew_caution_deg"))
        self.limits = {"crew": float(threshold(rules, "crew_exclude_deg")), "rover": float(threshold(rules, "rover_exclude_deg"))}

    def to_pixel(self, coords):
        """Continuous (col, row) pixel positions for [lon, lat] pairs; longitude wraps near the CRS meridian."""
        lons = [self.lon0 + signed_longitude(c[0] - self.lon0) for c in coords]
        xs, ys = transform_coordinates(MARS_GEOGRAPHIC, self.terrain.crs, lons, [c[1] for c in coords])
        inverse = ~self.terrain.transform
        return [inverse * (x, y) for x, y in zip(xs, ys)]

    def cell_lonlat(self, col, row):
        """Signed [lon, lat] of a cell centre."""
        return self.terrain.lonlat(row, col)


@traced("route_audit_terrain")
def load_grid(dtm_path, coords, rules, margin_deg=0.003):
    """Read and analyse the DTM around every coordinate in coords (plus margin); returns a TerrainGrid."""
    lons, lats = [c[0] for c in coords], [c[1] for c in coords]
    bounds = {"south": min(lats) - margin_deg, "west": min(lons) - margin_deg,
              "north": max(lats) + margin_deg, "east": max(lons) + margin_deg}
    with rasterio.open(dtm_path) as dataset:
        pad = int(math.ceil(threshold(rules, "roughness_window_m") / abs(dataset.transform.a))) + 2
        padded, _ = window_for_bounds(dataset, bounds, pad, clip=True)
    terrain = read_terrain(dtm_path, window=padded)
    return TerrainGrid(terrain, analyze(terrain, rules), rules)


def segment_modes(feature):
    """Travel mode per segment: legs' drive/walk where declared, else the route agent (crew walks, rover drives)."""
    props = feature.get("properties", {})
    count = len(feature["geometry"]["coordinates"]) - 1
    default = "drive" if props.get("agent") == "rover" else "walk"
    modes = [default] * count
    for leg in props.get("legs") or []:
        if leg.get("mode") in ("drive", "walk") and isinstance(leg.get("from"), int) and isinstance(leg.get("to"), int):
            for index in range(max(0, leg["from"]), min(count, leg["to"])):
                modes[index] = leg["mode"]
    return modes


def traverse(grid, coords, modes=None):
    """Walk every DTM cell crossed by the polyline coords; returns per-cell rows with distance along the line.

    modes: per-segment "drive"/"walk" (default walk); drive cells use the rover limit, walk cells the crew limit.
    """
    pixels = grid.to_pixel(coords)
    rows, along = [], 0.0
    height, width = grid.slope.shape
    modes = modes or ["walk"] * (len(coords) - 1)
    for segment_index, ((a, b), (pa, pb), mode) in enumerate(zip(zip(coords, coords[1:]), zip(pixels, pixels[1:]), modes)):
        seg_m = mars_distance(a, b)
        for (col, row), t in supercover(pa[0], pa[1], pb[0], pb[1]):
            inside = 0 <= row < height and 0 <= col < width
            known = inside and bool(grid.valid[row, col])
            rows.append({"segment_index": segment_index, "coordinates": grid.cell_lonlat(col, row),
                         "roughness_m": float(grid.roughness[row, col]) if known and getattr(grid, "roughness", None) is not None and np.isfinite(grid.roughness[row, col]) else None,
                         "col": col, "row": row, "distance_m": along + t * seg_m, "inside": inside, "known": known,
                         "limit": grid.limits["rover" if mode == "drive" else "crew"], "mode": mode,
                         "slope": float(grid.slope[row, col]) if known else None,
                         "elevation": float(grid.terrain.elevation[row, col]) if known else None})
        along += seg_m
    return rows


def intended_endpoints(feature, mission):
    """(start, end) [lon, lat] the route is meant to join, or None for an undeclared objective."""
    endpoints = mission.get("endpoints", {})
    objective = feature["properties"].get("objective_endpoint") or OBJECTIVE.get(feature["properties"].get("kind"))
    habitat = endpoints.get("habitat")
    if objective is None or habitat is None or objective not in endpoints:
        return None
    return [habitat["lon"], habitat["lat"]], [endpoints[objective]["lon"], endpoints[objective]["lat"]]


def audit_route(feature, mission, grid, rules, face=None, scarp_foot=None, faces=None):
    """Measure one route feature; returns its diagnostic dict (never modifies the feature)."""
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates") or []
    agent = props.get("agent", "crew")
    tolerance = float(threshold(rules, "position_uncertainty_m"))
    result = {"input_route": feature, "id": props.get("id"), "agent": agent, "kind": props.get("kind"), "claimed_status": props.get("status"),
              "evidence": "inferred", "terrain_evidence": "nasa_derived",
              "exclude_threshold_deg": {"walk": grid.limits["crew"], "drive": grid.limits["rover"]}, "reasons": []}
    reasons = result["reasons"]
    finite = all(isinstance(c, (list, tuple)) and len(c) >= 2 and all(math.isfinite(float(v)) for v in c[:2]) for c in coords)
    if len(coords) < 2 or not finite:
        reasons.append("geometry_invalid: fewer than two finite vertices")
        result["audit_status"] = "geometry_invalid"
        return result
    measured = polyline_m(coords)
    claimed = props.get("stats", {}).get("length_m")
    result.update(vertices=len(coords), length_m=round(measured, 1), claimed_length_m=claimed)
    if isinstance(claimed, (int, float)):
        result["length_mismatch_m"] = round(measured - claimed, 1)
        if abs(measured - claimed) > LENGTH_TOLERANCE_M + 0.02 * measured:
            reasons.append(f"stats_mismatch: claims {claimed:.0f} m, line measures {measured:.0f} m")
    intended = intended_endpoints(feature, mission)
    if intended:
        result["objective"] = props.get("objective_endpoint") or OBJECTIVE.get(props.get("kind"))
        result["intended_endpoints"] = intended
        forward = (mars_distance(coords[0], intended[0]), mars_distance(coords[-1], intended[1]))
        reverse = (mars_distance(coords[0], intended[1]), mars_distance(coords[-1], intended[0]))
        offsets, orientation = (forward, "outbound") if max(forward) <= max(reverse) else (reverse, "return")
        result.update(start_offset_m=round(offsets[0], 1), end_offset_m=round(offsets[1], 1), orientation=orientation)
        if max(offsets) > tolerance:
            reasons.append(f"endpoint_mismatch: ends {offsets[1]:.0f} m / starts {offsets[0]:.0f} m from the intended "
                           f"points (tolerance {tolerance:.0f} m)")
    else:
        result["objective"] = "undeclared"
    if scarp_foot:
        # The objective end: the last vertex outbound, the first on a return route.
        objective_end = coords[0] if result.get("orientation") == "return" else coords[-1]
        result["end_to_scarp_foot_m"] = round(distance_to_polyline_m(objective_end, scarp_foot), 1)
    cells = traverse(grid, coords, segment_modes(feature))
    outside = [c for c in cells if not c["inside"]]
    unknown = [c for c in cells if c["inside"] and not c["known"]]
    known = [c for c in cells if c["known"]]
    slopes = np.array([c["slope"] for c in known]) if known else np.array([])
    excluded = [c for c in known if c["slope"] >= c["limit"]]
    result.update(cells_crossed=len(cells), cells_outside=len(outside), cells_unknown=len(unknown),
                  max_slope_deg=round(float(slopes.max()), 1) if known else None,
                  cells_caution=int((slopes >= grid.caution).sum()), cells_excluded=len(excluded),
                  modes=sorted({c["mode"] for c in cells}))
    if excluded:
        first = excluded[0]
        result["first_exclusion_at_m"] = round(first["distance_m"], 1)
        result["first_exclusion"] = first
        by_mode = {m: sum(1 for c in excluded if c["mode"] == m) for m in ("drive", "walk")}
        detail = ", ".join(f"{n} {m} cells ≥ {grid.limits['rover' if m == 'drive' else 'crew']:g}°" for m, n in by_mode.items() if n)
        reasons.append(f"excluded_terrain: {detail} (first {first['distance_m']:.0f} m along, max {result['max_slope_deg']}°)")
    if outside:
        reasons.append(f"outside_assessed_terrain: {len(outside)} crossed cells outside the analysed DTM crop")
    if unknown:
        reasons.append(f"unassessed_terrain: {len(unknown)} crossed cells have no valid DTM slope")
    face_rings = faces if faces is not None else ([face] if face else [])
    if face_rings:
        centres = [grid.cell_lonlat(c["col"], c["row"]) for c in cells if c["inside"]]
        hits = np.zeros(len(centres), dtype=bool)
        for ring in face_rings:
            hits |= point_in_polygon([p[0] for p in centres], [p[1] for p in centres], ring)
        for cell, hit in zip([c for c in cells if c["inside"]], hits):
            cell["on_scarp_face"] = bool(hit)
        face_cells = [c for c in cells if c.get("on_scarp_face")]
        if face_cells:
            first = min(face_cells + excluded, key=lambda c: c["distance_m"])
            result["first_exclusion"] = first
            result["first_exclusion_at_m"] = round(first["distance_m"], 1)
        result["cells_on_scarp_face"] = int(hits.sum())
        if hits.any():
            reasons.append(f"excluded_terrain: crosses the traced scarp face ({int(hits.sum())} cells)")
    result["cells"] = cells
    result["artifact_review"] = "not_reviewed"
    step = max(1, math.ceil(len(cells) / PROFILE_POINTS))
    sample = cells[::step] + ([cells[-1]] if (len(cells) - 1) % step else [])
    result["profile"] = [[round(c["distance_m"], 1), None if c["elevation"] is None else round(c["elevation"], 2),
                          None if c["slope"] is None else round(c["slope"], 1), c["limit"], c["mode"]] for c in sample]
    kinds = {reason.split(":")[0] for reason in reasons}
    result["audit_status"] = next((s for s in STATUS_ORDER if s in kinds), "candidate_requires_inspection")
    # A route may claim "inspection_required", "no_viable_route" or "backup_unavailable"; "ok" is never
    # consistent, since slope below a planning threshold is not crew clearance.
    result["status_consistent"] = props.get("status") != "ok"
    if not result["status_consistent"]:
        reasons.append("status_overclaims: file says ok; terrain evidence supports at most inspection_required")
    return result


@traced("route_audit")
def audit_file(routes_path, mission_path, dtm_path=DEFAULT_DTM, scarp_path=None, rules=None):
    """Audit every route in routes_path against dtm_path; returns the route_audit.json payload."""
    started = perf_counter()
    rules = rules or load_rules()
    routes_text = Path(routes_path).read_text()
    routes, mission = json.loads(routes_text), json.loads(Path(mission_path).read_text())
    if not Path(dtm_path).exists():
        event("route_audit_input_missing", logging.ERROR, path=str(dtm_path))
        raise FileNotFoundError(f"{dtm_path} not found; download the HiRISE DTM first (pipeline/README.md)")
    scarp = json.loads(Path(scarp_path).read_text()) if scarp_path and Path(scarp_path).exists() else None
    face = scarp_face(scarp)
    traced = {f["properties"]["id"]: f["geometry"]["coordinates"] for f in (scarp or {}).get("features", [])
              if f.get("geometry", {}).get("type") == "LineString"}
    faces = [line + list(reversed(traced[key[:-5] + "-foot"])) for key, line in traced.items()
             if key.endswith("-edge") and key[:-5] + "-foot" in traced]
    foot = next((f["geometry"]["coordinates"] for f in (scarp or {}).get("features", []) if f["properties"].get("id") == "scarp-foot"), None)
    lines = [f for f in routes["features"] if len(f["geometry"].get("coordinates") or []) >= 2]
    coords = [c for f in lines for c in f["geometry"]["coordinates"]]
    coords += [[p["lon"], p["lat"]] for p in mission.get("endpoints", {}).values()]
    grid = load_grid(dtm_path, coords, rules)
    audits = []
    for feature in routes["features"]:
        audit = audit_route(feature, mission, grid, rules, face, foot, faces)
        level = logging.WARNING if audit["audit_status"] != "candidate_requires_inspection" or not audit.get("status_consistent", True) else logging.INFO
        event("route_audited", level, route_id=audit["id"], agent=audit["agent"], audit_status=audit["audit_status"],
              claimed_status=audit["claimed_status"], reasons=audit["reasons"], max_slope_deg=audit.get("max_slope_deg"),
              cells_crossed=audit.get("cells_crossed"), cells_excluded=audit.get("cells_excluded"),
              evidence=audit["evidence"], terrain_evidence="nasa_derived", exclude_threshold_deg=audit["exclude_threshold_deg"])
        audits.append(audit)
    payload = {
        "schema_version": SCHEMA_VERSION, "evidence": "inferred", "terrain_evidence": "nasa_derived",
        "dtm": Path(dtm_path).name, "routes_sha256": canonical_sha256(routes),
        "input_context": {"mission": mission, "scarp_lines": scarp, "rules": rules},
        "mission_placeholder": bool(mission.get("placeholder")), "routes_placeholder": bool(routes.get("placeholder")),
        "scarp_source": Path(scarp_path).name if scarp else None,
        "thresholds_deg": {"crew_caution": grid.caution, "crew_exclude": grid.limits["crew"], "rover_exclude": grid.limits["rover"]},
        "endpoint_tolerance_m": float(threshold(rules, "position_uncertainty_m")),
        "method": ("Supercover traversal of every DTM cell each segment touches; slope from pipeline.terrain.analyze; "
                   "lengths on the Mars sphere R = 3,389.5 km; route lines are never modified."),
        "limitations": ("Planning model only: never crew clearance. ~1 m DTM misses sub-metre rocks and loose ground. "
                        "Scarp face from an image trace (inferred), not reviewed ground truth."),
        "routes": audits,
    }
    event("route_audit_completed", routes=len(audits), statuses={a["id"]: a["audit_status"] for a in audits},
          mission_placeholder=payload["mission_placeholder"], duration_ms=(perf_counter() - started) * 1000)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--routes", type=Path, default=Path("public/data/routes.geojson"))
    parser.add_argument("--mission", type=Path, default=Path("public/data/mission.json"))
    parser.add_argument("--scarp", type=Path, default=Path("public/data/scarp_lines.geojson"))
    parser.add_argument("--dtm", type=Path, default=DEFAULT_DTM)
    parser.add_argument("--output", type=Path, help="write route_audit.json here (default: print a summary only)")
    arguments = parser.parse_args()
    configure_logging()
    with operation("route_audit_cli", dataset_id=arguments.dtm.name):
        result = audit_file(arguments.routes, arguments.mission, arguments.dtm, arguments.scarp)
    if arguments.output:
        write_json(arguments.output, result)
    for audit in result["routes"]:
        print(f"{audit['id']}: {audit['audit_status']} | " + "; ".join(audit["reasons"]))
