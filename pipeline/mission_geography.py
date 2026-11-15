"""Rebuild the published mission geography from the HiRISE DTM and the reviewed site candidates.

One authoritative source replaces the hand-drawn placeholders: `pipeline/site/mission_sites.json`
(reviewed candidate points, Geury's first-pass points for comparison, per-profile scarp measurements)
plus `public/data/scarp_lines.geojson` (traced edge and foot, inferred), the DTM and hazard_rules.json.

Writes, staged and then renamed into public/data together (with rollback):
  hazards.geojson   slope exclusions (nasa_derived), traced scarp face, edge setback and rockfall
                    zone (inferred), the simulated rover discovery; no shadow or soft-ground guesses
  routes.geojson    DTM least-cost routes: crew-rover drive + walk (legs), the replanned route,
                    the simulated rover's scouting path and an independent backup
  coverage.geojson  simulated rover corridor, drone view cone and drone-checked area
  mission.json      endpoints, stage texts and stats computed from the routes above
  route_audit.json  pipeline.route_audit on exactly the staged lines, with a freshness fingerprint
and pipeline/site/mission_geography_report.json (point checks, budgets, discrepancies, decisions).

Every route is audited before publication; a generated line that fails its own audit stops the
publication. A budget failure is published as `no_viable_route` with its reason, never as `ok`.
Nothing here is crew clearance.

Usage: python -m pipeline.mission_geography [--dtm ...] [--data-dir public/data]
"""

import argparse
import json
import logging
import math
import shutil
import tempfile
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import rasterio
from affine import Affine
from rasterio.warp import transform as transform_coordinates
from scipy.ndimage import binary_dilation, distance_transform_edt, label

from pipeline.export import write_json
from pipeline.hazards import collection, hazard_masks, mask_features, uncertainty_area_check
from pipeline.itinerary import backup_independence, evaluate_mixed, polyline_m
from pipeline.logging_config import configure_logging, event, operation, traced
from pipeline.route_audit import (SCARPS, ScarpSet, ScarpZones, TerrainGrid, audit_file, point_in_polygon, polyline_distance_m, scarp_face,
                                  supercover)
from pipeline.routing import cost_grid, grid_shortest_path, mars_distance
from pipeline.slope_mvp import ACQUIRE_HINT, DEFAULT_BOUNDS, DEFAULT_DTM, _activate, window_for_bounds
from pipeline.terrain import MARS_GEOGRAPHIC, analyze, load_rules, read_terrain, signed_longitude, threshold

SCHEMA_VERSION = "1.0"
DEFAULT_SITES = Path("pipeline/site/mission_sites.json")
DEFAULT_REPORT = Path("pipeline/site/mission_geography_report.json")
SPEEDS_M_MIN = {"drive": 83.3, "walk": 20.0}  # crew rover 5 km/h, suited walking (itinerary defaults)
SCOUT_SPEED_M_MIN = 10.0  # simulated scouting rover; an assumption for the story, not a rover spec
EVA_MINUTES, SITE_MINUTES = 240, 20
ROUTING_MARGIN_M = 1.0  # routing keeps this much extra from edge/rockfall zones (rasterization slack)
DISCOVERY_FRACTION = 0.45  # simulated soft ground sits this far along the first drive leg
DISCOVERY_RADIUS_M, DISCOVERY_MARGIN_M = 25.0, 10.0
BACKUP_CORRIDOR_M, BACKUP_PENALTY = 30.0, 20.0  # backup search avoids the main route's corridor
SLOPE_MIN_CELLS = 400  # steep clusters smaller than this stay on the slope map only
HAZARD_BLOCK, COVERAGE_BLOCK = 4, 2  # polygon grid in DTM cells: hazards any-cell, coverage all-cells
DRONE_CHECK_RADIUS_M, VIEW_CONE_M, VIEW_CONE_DEG = 120.0, 220.0, 50.0
LIVE_NAMES = ("hazards.geojson", "coverage.geojson", "routes.geojson", "route_audit.json", "mission.json")


def load_sites(path):
    """Read and validate mission_sites.json: named points with finite lat/lon in -180..180, scarp profiles."""
    sites = json.loads(Path(path).read_text())
    required = ("habitat", "parking", "observation_primary", "observation_backup", "drone_perch")
    for name in required:
        point = sites.get("points", {}).get(name)
        if not point or not all(isinstance(point.get(k), (int, float)) and math.isfinite(point[k]) for k in ("lat", "lon")):
            raise ValueError(f"mission_sites.json: point {name} needs finite lat/lon")
        if not (-90 <= point["lat"] <= 90 and -180 <= point["lon"] <= 180):
            raise ValueError(f"mission_sites.json: point {name} outside lat/lon range (longitudes are -180..180)")
    for key in ("scarp_profiles", "upper_scarp_profiles"):
        if key not in sites and key != "scarp_profiles":
            continue
        profiles = sites.get(key, {}).get("profiles") or []
        if len(profiles) < 2 or any(p.get("height_m", -1) < 0 or p.get("apron_m", -1) < 0 for p in profiles):
            raise ValueError(f"mission_sites.json: {key} needs at least two profiles with height_m and apron_m")
    return sites


class Grid:
    """Padded DTM crop with its analysis, cell-centre coordinates and lon/lat <-> cell helpers."""

    def __init__(self, dtm_path, bounds, rules):
        """Read dtm_path around bounds (signed lat/lon) with gradient padding and analyse it."""
        with rasterio.open(dtm_path) as dataset:
            pad = int(math.ceil(threshold(rules, "roughness_window_m") / abs(dataset.transform.a))) + 2
            padded, self.inner = window_for_bounds(dataset, bounds, pad)
        self.terrain = read_terrain(dtm_path, window=padded)
        self.analysis = analyze(self.terrain, rules)
        self.audit_grid = TerrainGrid(self.terrain, self.analysis, rules)
        rows, cols = self.terrain.elevation.shape
        t = self.terrain.transform
        # Equirectangular: longitude depends on the column only, latitude on the row only.
        xs = [t.c + (c + 0.5) * t.a for c in range(cols)]
        ys = [t.f + (r + 0.5) * t.e for r in range(rows)]
        lons, _ = transform_coordinates(self.terrain.crs, MARS_GEOGRAPHIC, xs, [ys[0]] * cols)
        _, lats = transform_coordinates(self.terrain.crs, MARS_GEOGRAPHIC, [xs[0]] * rows, ys)
        self.lon = np.array([signed_longitude(v) for v in lons])
        self.lat = np.array(lats)
        col, row, width, height = self.inner
        self.inside = np.zeros((rows, cols), bool)
        self.inside[row:row + height, col:col + width] = True
        self.spacing = (self.terrain.resolution, self.terrain.column_spacing)

    def cell(self, point):
        """(row, col) of the cell containing {lat, lon}; raises when outside the crop."""
        col, row = self.audit_grid.to_pixel([[point["lon"], point["lat"]]])[0]
        cell = (int(math.floor(row)), int(math.floor(col)))
        if not self.inside[cell]:
            raise ValueError(f"point {point} lies outside the analysed DTM area")
        return cell

    def lonlat(self, cell):
        """[lon, lat] of a cell centre, rounded to 7 decimals (~6 mm) for publication."""
        return [round(float(self.lon[cell[1]]), 7), round(float(self.lat[cell[0]]), 7)]


@traced("scarp_zones")
def scarp_inputs(grid, zones, face_ring, rules):
    """Distance grids (edge, foot), per-cell rockfall buffer and the traced face mask, near the scarp only.

    Distances use the same local-plane polyline distance as the route audit; cells farther than the
    largest buffer + 100 m from the lines get a large distance. Routing subtracts ROUTING_MARGIN_M.
    """
    shape = grid.terrain.elevation.shape
    edge_d = np.full(shape, 1e6)
    foot_d = np.full(shape, 1e6)
    face = np.zeros(shape, bool)
    reach_m = float(zones.buffers.max()) + 100.0
    line_pts = np.array(zones.edge + zones.foot)
    k = math.radians(1) * 3_389_500.0
    lat_pad = reach_m / k
    lon_pad = reach_m / (k * math.cos(math.radians(float(line_pts[:, 1].mean()))))
    rows = np.where((grid.lat >= line_pts[:, 1].min() - lat_pad) & (grid.lat <= line_pts[:, 1].max() + lat_pad))[0]
    cols = np.where((grid.lon >= line_pts[:, 0].min() - lon_pad) & (grid.lon <= line_pts[:, 0].max() + lon_pad))[0]
    block = (slice(rows.min(), rows.max() + 1), slice(cols.min(), cols.max() + 1))
    lons, lats = np.meshgrid(grid.lon[block[1]], grid.lat[block[0]])
    edge_d[block] = polyline_distance_m(lons.ravel(), lats.ravel(), zones.edge).reshape(lons.shape)
    foot_d[block] = polyline_distance_m(lons.ravel(), lats.ravel(), zones.foot).reshape(lons.shape)
    face[block] = point_in_polygon(lons.ravel(), lats.ravel(), face_ring).reshape(lons.shape)
    # Rockfall lands below the face: cells nearer the top edge than the foot are not rockfall terrain.
    foot_d = np.where(foot_d <= edge_d, foot_d, 1e6)
    buffer = zones.buffer_at(np.broadcast_to(grid.lon[None, :], shape))
    event("scarp_zones_built", evidence="inferred", block_cells=int(lons.size), face_cells=int(face.sum()),
          setback_m=zones.setback_m, rockfall_buffer_m=[float(zones.buffers.min()), float(zones.buffers.max())],
          routing_margin_m=ROUTING_MARGIN_M)
    return edge_d, foot_d, buffer, face


def combine_scarps(inputs):
    """Merge per-scarp (edge_d, foot_d, buffer, face) grids into one set hazard_masks can take.

    Edge distance is the nearest edge; rockfall becomes one margin: a cell is in a rockfall zone when
    foot_d - buffer <= 0 for any scarp, expressed as foot distance (margin + B) against a constant buffer B.
    """
    edge_d = np.minimum.reduce([i[0] for i in inputs])
    margin = np.minimum.reduce([i[1] - i[2] for i in inputs])
    top = float(max(i[2].max() for i in inputs))
    face = np.logical_or.reduce([i[3] for i in inputs])
    event("scarp_zones_combined", evidence="inferred", scarps=len(inputs), rockfall_buffer_max_m=top,
          face_cells=int(face.sum()))
    return edge_d, np.maximum(margin + top, 0.0), np.full(edge_d.shape, top), face


def disc_mask(grid, centre_cell, radius_m):
    """Cells whose centres lie within radius_m of centre_cell (row spacing and latitude-corrected columns)."""
    row, col = centre_cell
    dy, dx = grid.terrain.resolution, float(grid.terrain.column_spacing[row])
    reach_r, reach_c = int(math.ceil(radius_m / dy)) + 1, int(math.ceil(radius_m / dx)) + 1
    mask = np.zeros(grid.terrain.elevation.shape, bool)
    r0, r1 = max(0, row - reach_r), min(mask.shape[0], row + reach_r + 1)
    c0, c1 = max(0, col - reach_c), min(mask.shape[1], col + reach_c + 1)
    rr, cc = np.mgrid[r0:r1, c0:c1]
    mask[r0:r1, c0:c1] = ((rr - row) * dy) ** 2 + ((cc - col) * dx) ** 2 <= radius_m ** 2
    return mask


def crossed(grid, path):
    """Every DTM cell (row, col) the straight segments between path cells cross (audit supercover)."""
    pixels = grid.audit_grid.to_pixel([grid.lonlat(c) for c in path])
    out = []
    for a, b in zip(pixels, pixels[1:]):
        for (col, row), _ in supercover(a[0], a[1], b[0], b[1]):
            if not out or out[-1] != (row, col):
                out.append((row, col))
    return out


def simplify_cells(path):
    """Drop vertices inside straight runs of a 4-neighbour cell path; the line covers exactly the same cells."""
    if len(path) < 3:
        return list(path)
    kept = [path[0]]
    for before, here, after in zip(path, path[1:], path[2:]):
        if (here[0] - before[0], here[1] - before[1]) != (after[0] - here[0], after[1] - here[1]):
            kept.append(here)
    kept.append(path[-1])
    return kept


MAX_SHORTCUT_CELLS = 400  # longest straight segment tried when replacing the staircase


def shortcut(path, passable, grid):
    """Replace a 4-neighbour staircase by straight segments whose crossed cells are all passable.

    Each segment joins published (rounded) cell-centre coordinates and is tested with the audit's own
    supercover traversal, so the audit later crosses exactly the cells checked here. Greedy: from each
    kept vertex, extend to the farthest path cell before the first blocked segment (bounded lookahead).
    Returns the kept cells (a subsequence of path, same endpoints).
    """
    if len(path) < 3:
        return list(path)
    pixels = grid.audit_grid.to_pixel([grid.lonlat(c) for c in path])
    height, width = passable.shape

    def clear(i, j):
        for (col, row), _ in supercover(pixels[i][0], pixels[i][1], pixels[j][0], pixels[j][1]):
            if not (0 <= row < height and 0 <= col < width and passable[row, col]):
                return False
        return True

    kept, i = [0], 0
    while i < len(path) - 1:
        best = i + 1
        for j in range(i + 2, min(len(path), i + MAX_SHORTCUT_CELLS)):
            if not clear(i, j):
                break
            best = j
        kept.append(best)
        i = best
    return [path[k] for k in kept]


def search(costs, start, end, grid, label_id):
    """Least-cost 4-neighbour path between cells, straightened over passable cells; [] when none exists."""
    with operation("route_search", route_id=label_id, evidence="nasa_derived"):
        path = grid_shortest_path(costs, start, end, grid.spacing)
    if not path:
        event("route_leg_unavailable", logging.WARNING, route_id=label_id, status="no_viable_route",
              reason="hard_exclusions_or_disconnected")
        return path
    straight = shortcut(path, np.isfinite(costs), grid)
    event("route_straightened", route_id=label_id, grid_cells=len(path), vertices=len(straight),
          staircase_m=round(polyline_m([grid.lonlat(c) for c in path]), 1),
          straightened_m=round(polyline_m([grid.lonlat(c) for c in straight]), 1))
    return straight


def route_feature(grid, rid, kind, agent, version, status, legs):
    """Route record from ordered legs [(mode, cell path)]; legs (crew only) carry contiguous vertex indexes.

    stats: one-way length (Mars sphere), round trip (crew) or one-way (rover), time at SPEEDS_M_MIN
    (scouting speed for the rover), positive elevation gain, max DTM slope over every cell.
    """
    coords, out_legs, cells, minutes = [], [], [], 0.0
    for mode, path in legs:
        part = [grid.lonlat(c) for c in simplify_cells(path)]
        start = 0 if not coords else len(coords) - 1
        coords += part if not coords else part[1:]
        dense = crossed(grid, path)
        cells += dense if not cells else dense[1:]
        length = polyline_m(part)
        speed = SCOUT_SPEED_M_MIN if agent == "rover" else SPEEDS_M_MIN[mode]
        minutes += length / speed
        out_legs.append({"mode": mode, "from": start, "to": len(coords) - 1, "length_m": round(length, 1),
                         "est_time_min": round(length / speed, 1)})
    length = polyline_m(coords)
    elevation = [float(grid.terrain.elevation[c]) for c in cells]
    stats = {"length_m": round(length, 1), "round_trip_m": round(length if agent == "rover" else 2 * length, 1),
             "est_time_min": round(minutes if agent == "rover" else 2 * minutes, 1),
             "elevation_gain_m": round(sum(max(0.0, b - a) for a, b in zip(elevation, elevation[1:])), 1),
             "max_slope_deg": round(max(float(grid.analysis["slope"][c]) for c in cells), 1), "shared_with_main_m": 0}
    props = {"id": rid, "kind": kind, "agent": agent, "version": version, "status": status, "stats": stats}
    if agent == "crew":
        props["legs"] = out_legs
        drive = sum(l["length_m"] for l in out_legs if l["mode"] == "drive")
        if drive:
            # Walkback (PR #15 contract): minutes on foot from the farthest drive point (the parked rover) home.
            props["walkback_min"] = round(drive / SPEEDS_M_MIN["walk"], 1)
    return {"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}}


def empty_route(rid, kind, agent, version, status):
    """A route record with no line: a failed search is published in words, never as a drawn line."""
    stats = dict.fromkeys(("length_m", "round_trip_m", "est_time_min", "elevation_gain_m", "max_slope_deg", "shared_with_main_m"), 0)
    return {"type": "Feature", "properties": {"id": rid, "kind": kind, "agent": agent, "version": version,
                                              "status": status, "stats": stats},
            "geometry": {"type": "LineString", "coordinates": []}}


def pooled(mask, factor, mode):
    """Block-reduce a boolean grid by factor: 'any' (hazards: never smaller) or 'all' (coverage: never larger)."""
    rows, cols = mask.shape
    pr, pc = -rows % factor, -cols % factor
    padded = np.pad(mask, ((0, pr), (0, pc)), constant_values=(mode == "all"))
    blocks = padded.reshape(padded.shape[0] // factor, factor, padded.shape[1] // factor, factor)
    return blocks.any(axis=(1, 3)) if mode == "any" else blocks.all(axis=(1, 3))


def polygons(mask, grid, factor, mode, prefix, properties):
    """GeoJSON polygons of mask on a factor-coarsened grid (rounded to 7 decimals)."""
    coarse = pooled(mask & grid.inside, factor, mode)
    frame = SimpleNamespace(transform=grid.terrain.transform * Affine.scale(factor), crs=grid.terrain.crs,
                            source=grid.terrain.source)
    features = mask_features(coarse, frame, prefix, properties) if coarse.any() else []
    for feature in features:
        feature["geometry"]["coordinates"] = [[[round(x, 7), round(y, 7)] for x, y in ring]
                                              for ring in feature["geometry"]["coordinates"]]
    return features


def circle(centre, radius_m, points=48):
    """Closed [lon, lat] ring of a circle radius_m around {lat, lon} on the Mars sphere (local plane)."""
    k = math.radians(1) * 3_389_500.0
    ring = [[round(centre["lon"] + radius_m * math.cos(a) / (k * math.cos(math.radians(centre["lat"]))), 7),
             round(centre["lat"] + radius_m * math.sin(a) / k, 7)]
            for a in (2 * math.pi * i / points for i in range(points))]
    return ring + ring[:1]


def sector(apex, toward, length_m, width_deg, points=12):
    """Closed [lon, lat] ring of a view cone from apex {lat, lon} aimed at toward [lon, lat]."""
    k = math.radians(1) * 3_389_500.0
    sx = k * math.cos(math.radians(apex["lat"]))
    bearing = math.atan2((toward[1] - apex["lat"]) * k, (toward[0] - apex["lon"]) * sx)
    half = math.radians(width_deg) / 2
    arc = [[round(apex["lon"] + length_m * math.cos(a) / sx, 7), round(apex["lat"] + length_m * math.sin(a) / k, 7)]
           for a in np.linspace(bearing - half, bearing + half, points)]
    tip = [round(apex["lon"], 7), round(apex["lat"], 7)]
    return [tip] + arc + [tip]


def feature(fid, geometry_type, coordinates, **properties):
    """Plain GeoJSON feature with properties.id = fid."""
    return {"type": "Feature", "properties": {"id": fid, **properties},
            "geometry": {"type": geometry_type, "coordinates": coordinates}}


def point_along(path, grid, fraction):
    """Cell at `fraction` of a cell path's length (metres)."""
    coords = [grid.lonlat(c) for c in path]
    steps = [mars_distance(a, b) for a, b in zip(coords, coords[1:])]
    target, along = fraction * sum(steps), 0.0
    for cell, step in zip(path[1:], steps):
        along += step
        if along >= target:
            return cell
    return path[-1]


@traced("mission_geography")
def build(dtm_path=DEFAULT_DTM, data_dir=Path("public/data"), sites_path=DEFAULT_SITES, report_path=DEFAULT_REPORT,
          bounds=None, rules=None, drive_counts_toward_limit=False):
    """Compute, stage, audit and publish the mission geography; returns the report dict.

    drive_counts_toward_limit: apply the 5,000 m round-trip rule to drive + walk metres. Default False: the
    team decided (STATUS 2026-11-14, Nic + Yasser) the limit applies to walking only; both are reported.
    """
    started = perf_counter()
    dtm_path, data_dir = Path(dtm_path), Path(data_dir)
    if not dtm_path.exists():
        event("mission_geography_input_missing", logging.ERROR, path=str(dtm_path), reason="dtm_not_found")
        raise FileNotFoundError(f"{dtm_path} not found. {ACQUIRE_HINT}")
    rules = rules or load_rules()
    sites = load_sites(sites_path)
    scarp_path = data_dir / "scarp_lines.geojson"
    scarp = json.loads(scarp_path.read_text())
    lines = {f["properties"]["id"]: f["geometry"]["coordinates"] for f in scarp["features"]}
    face_ring = scarp_face(scarp)
    if face_ring is None:
        raise ValueError("scarp_lines.geojson needs scarp-edge and scarp-foot")
    # Every traced scarp with profile measurements (main scarp, then PR #17's upper scarp) gets zones.
    members, rings = [], []
    for edge_id, foot_id, key in SCARPS:
        if edge_id in lines and foot_id in lines and sites.get(key, {}).get("profiles"):
            members.append(ScarpZones(lines[edge_id], lines[foot_id], sites[key]["profiles"], rules))
            rings.append(lines[edge_id] + list(reversed(lines[foot_id])))
    zones = ScarpSet(members)
    profiles = [p for _, _, key in SCARPS for p in sites.get(key, {}).get("profiles", [])]
    points = sites["points"]

    grid = Grid(dtm_path, dict(bounds or DEFAULT_BOUNDS), rules)
    terrain, analysis = grid.terrain, grid.analysis
    edge_d, foot_d, buffer, face = combine_scarps([scarp_inputs(grid, z, r, rules) for z, r in zip(members, rings)])
    # Published masks use the rules exactly; routing masks keep ROUTING_MARGIN_M extra.
    masks = hazard_masks(terrain, analysis, rules, edge_distance=edge_d, foot_distance=foot_d,
                         scarp_height=float(max(p["height_m"] for p in profiles)),
                         apron_m=float(max(p["apron_m"] for p in profiles)), rockfall_buffer=buffer)
    routing = hazard_masks(terrain, analysis, rules, edge_distance=np.maximum(edge_d - ROUTING_MARGIN_M, 0),
                           foot_distance=np.maximum(foot_d - ROUTING_MARGIN_M, 0),
                           scarp_height=float(max(p["height_m"] for p in profiles)),
                           apron_m=float(max(p["apron_m"] for p in profiles)), rockfall_buffer=buffer)
    # The traced face is excluded for both agents; outside the published box nothing is assessed.
    routing["inspection_required"] = routing["inspection_required"] | face | ~grid.inside
    crew_costs = cost_grid(terrain, analysis, routing, "crew", rules=rules)
    rover_costs = cost_grid(terrain, analysis, routing, "rover", rules=rules)

    cells = {name: grid.cell(points[name]) for name in points}
    checks = {name: uncertainty_area_check(terrain, analysis, masks, cells[name], agent="rover" if name == "parking" else "crew",
                                           rules=rules, point_id=name)
              for name in ("habitat", "parking", "observation_primary", "observation_backup")}
    checks["parking_crew"] = uncertainty_area_check(terrain, analysis, masks, cells["parking"], agent="crew", rules=rules,
                                                    point_id="parking")

    # Walking-only reference: habitat to the primary viewpoint on foot the whole way.
    walk_only = search(crew_costs, cells["habitat"], cells["observation_primary"], grid, "walk_only_reference")
    walk_only_m = polyline_m([grid.lonlat(c) for c in walk_only]) if walk_only else None

    drive1 = search(rover_costs, cells["habitat"], cells["parking"], grid, "rt-orbital-guess-v1:drive")
    walk1 = search(crew_costs, cells["parking"], cells["observation_primary"], grid, "rt-orbital-guess-v1:walk")
    if not (drive1 and walk1):
        raise RuntimeError("no drive/walk candidate between the reviewed points; publish no_viable_route by hand after review")

    # Simulated discovery on the first drive leg; the replanned drive avoids it with a margin.
    dense1 = crossed(grid, drive1)
    discovery_cell = point_along(dense1, grid, DISCOVERY_FRACTION)
    discovery_point = dict(zip(("lon", "lat"), grid.lonlat(discovery_cell)))
    blocked = disc_mask(grid, discovery_cell, DISCOVERY_RADIUS_M + DISCOVERY_MARGIN_M)
    rover_costs2 = rover_costs.copy()
    rover_costs2[blocked] = np.inf
    drive2 = search(rover_costs2, cells["habitat"], cells["parking"], grid, "rt-crew-main-v2:drive")
    # The scouting rover stops just before the soft ground, then drives the replanned leg and the walk leg.
    # The rover drives drive1 up to the last crossed cell before the soft ground, then detours.
    k = dense1.index(discovery_cell)
    stop_cell = dense1[max(i for i in range(k) if not blocked[dense1[i]])]
    # Cut drive1's dense cell trace (every cell it crosses) at the stop and re-straighten it with the same
    # passability test as every other leg: joining drive1's last kept vertex straight to stop_cell could cut
    # a corner across a cell the rover may not enter (seen after the habitat move: one 26 deg cell).
    scouted = shortcut(dense1[:dense1.index(stop_cell) + 1], np.isfinite(rover_costs), grid)
    scout_detour = search(rover_costs2, stop_cell, cells["parking"], grid, "rt-rover-v2:detour")
    # Backup: separate drive and descent where the terrain allows (main corridor penalized, not forbidden).
    corridor_main = np.zeros(blocked.shape, bool)
    for c in crossed(grid, drive2) + crossed(grid, walk1):
        corridor_main[c] = True
    corridor_main = binary_dilation(corridor_main, iterations=int(BACKUP_CORRIDOR_M))
    rover_costs3, crew_costs3 = rover_costs2.copy(), crew_costs.copy()
    for costs in (rover_costs3, crew_costs3):
        costs[corridor_main & np.isfinite(costs)] *= BACKUP_PENALTY
    drive_b = search(rover_costs3, cells["habitat"], cells["parking"], grid, "rt-crew-backup-v2:drive")
    walk_b = search(crew_costs3, cells["parking"], cells["observation_backup"], grid, "rt-crew-backup-v2:walk")

    features = {
        "guess": route_feature(grid, "rt-orbital-guess-v1", "orbital_guess", "crew", "before", "inspection_required",
                               [("drive", drive1), ("walk", walk1)]),
        "main2": route_feature(grid, "rt-crew-main-v2", "main", "crew", "after", "inspection_required",
                               [("drive", drive2), ("walk", walk1)]) if drive2 else
                 empty_route("rt-crew-main-v2", "main", "crew", "after", "no_viable_route"),
        "rover": route_feature(grid, "rt-rover-v2", "rover_path", "rover", "after", "inspection_required",
                               [("drive", scouted + scout_detour[1:] + walk1[1:])]) if scout_detour else
                 empty_route("rt-rover-v2", "rover_path", "rover", "after", "no_viable_route"),
        # Drawn viewpoint-first (return orientation, PR #17 convention): walk back to the rover, then drive home.
        "backup": route_feature(grid, "rt-crew-backup-v2", "backup", "crew", "after", "inspection_required",
                                [("walk", walk_b[::-1]), ("drive", drive_b[::-1])]) if drive_b and walk_b else
                  empty_route("rt-crew-backup-v2", "backup", "crew", "after", "backup_unavailable"),
    }
    # Budgets from pipeline.itinerary; failures become no_viable_route (backup_unavailable) with reasons.
    budgets = {}
    for key in ("guess", "main2", "backup"):
        route = features[key]
        if not route["geometry"]["coordinates"]:
            continue
        report = evaluate_mixed(route, rules, EVA_MINUTES, SPEEDS_M_MIN, SITE_MINUTES)
        reasons = list(report["reasons"])
        # Walking-only rule: drop the distance reason when the walked round trip is within the limit;
        # every other budget reason (EVA time, walkback) still applies.
        if not drive_counts_toward_limit and report["walk_round_trip_m"] < threshold(rules, "round_trip_limit_m"):
            reasons = [r for r in reasons if r != "round_trip_distance_limit"]
        report["applied_reasons"] = reasons
        budgets[route["properties"]["id"]] = report
        if reasons:
            route["properties"]["status"] = "backup_unavailable" if key == "backup" else "no_viable_route"
            route["properties"]["status_reason"] = ", ".join(BUDGET_NAMES.get(r, r) for r in reasons)
            event("route_rejected", logging.WARNING, route_id=route["properties"]["id"], status=route["properties"]["status"],
                  reason="mission_budget", budget_reasons=reasons, round_trip_m=report["round_trip_m"],
                  walk_round_trip_m=report["walk_round_trip_m"], evidence="inferred", crew_clearance="not_established")
    independence = None
    if features["main2"]["geometry"]["coordinates"] and features["backup"]["geometry"]["coordinates"]:
        independence = backup_independence(features["main2"], features["backup"])
        features["backup"]["properties"]["stats"]["shared_with_main_m"] = independence["shared_m"]
        if not independence["independent"]:
            features["backup"]["properties"]["status"] = "backup_unavailable"
            features["backup"]["properties"]["status_reason"] = "shares more than half its length with the main route"

    # Hazards: NASA-derived slope clusters, inferred scarp zones, the simulated discovery.
    source = f"HiRISE {terrain.source}"
    steep = masks["crew_exclude"] & grid.inside
    labels, count = label(steep, structure=np.ones((3, 3), bool))
    sizes = np.bincount(labels.ravel())
    big = np.isin(labels, np.where(sizes >= SLOPE_MIN_CELLS)[0][1:]) if count else np.zeros(steep.shape, bool)
    hazards = polygons(big, grid, HAZARD_BLOCK, "any", "hz-slope", {
        "type": "U", "category": "slope", "severity": "exclude", "evidence": "nasa_derived", "agent": "crew",
        "stage": "orbital", "source": source,
        "note": (f"DTM slope of 20° or more (crew limit; 24° and above also excludes the rover). Outline drawn on a "
                 f"{HAZARD_BLOCK} m grid around clusters of at least {SLOPE_MIN_CELLS} m²; the slope map shows every 1 m cell.")})
    hazards.append(feature("hz-scarp-face", "Polygon", [[[round(x, 7), round(y, 7)] for x, y in face_ring + face_ring[:1]]],
                           type="U", category="edge", severity="exclude", evidence="inferred", agent="both", stage="orbital",
                           source="scarp_lines.geojson (HiRISE image trace, unreviewed)",
                           note="Traced ice-scarp face between top edge and foot; DTM face slopes 64-75°. Excluded for crew and rover."))
    for ring, member in zip(rings[1:], members[1:]):
        hazards.append(feature("hz-upper-scarp-face", "Polygon", [[[round(x, 7), round(y, 7)] for x, y in ring + ring[:1]]],
                               type="U", category="edge", severity="exclude", evidence="inferred", agent="both", stage="orbital",
                               source="scarp_lines.geojson upper-scarp lines (DTM cells >= 30°, PR #17; unreviewed)",
                               note="Second (upper) scarp face the crew observes from the viewpoints; excluded for crew and rover."))
    hazards += polygons(masks["edge"], grid, 2, "any", "hz-edge", {
        "type": "U", "category": "edge", "severity": "exclude", "evidence": "inferred", "agent": "crew", "stage": "orbital",
        "source": "scarp_lines.geojson + hazard_rules.json cliff_setback_m",
        "note": f"Within {zones.setback_m:g} m of the traced top edge (collapse setback); edge position is an image trace."})
    hazards += polygons(masks["rockfall"], grid, 2, "any", "hz-rockfall", {
        "type": "O", "category": "rockfall", "severity": "exclude", "evidence": "inferred", "agent": "both", "stage": "orbital",
        "source": "scarp_lines.geojson + scarp profiles (PR #15) + hazard_rules.json rockfall_height_factor",
        "note": (f"Below the scarp: within max(visible apron, 1 x scarp height) of the traced foot, per profile "
                 f"({zones.buffers.min():.0f}-{zones.buffers.max():.0f} m). A scenario rule, not a rockfall model.")})
    no_data = ~analysis["valid"] & grid.inside
    if no_data.any():
        hazards += polygons(no_data, grid, HAZARD_BLOCK, "any", "hz-nodata", {
            "type": "U", "category": "no_data", "severity": "exclude", "evidence": "nasa_derived", "agent": "both",
            "stage": "orbital", "source": source, "note": "No valid DTM slope here; inspection required before anyone crosses it."})
    hazards.append(feature("hz-sim-001", "Polygon", [circle(discovery_point, DISCOVERY_RADIUS_M)], type="U",
                           category="soft_ground", severity="exclude", evidence="simulated", agent="both", stage="rover",
                           source="Simulated rover observation, discovery scenario disc-001",
                           note="Simulated: rover wheel slip of 38 percent on ground that looked firm from orbit."))

    # Coverage: simulated robot coverage only; orbit-only is the published DTM box.
    inner_bounds = grid_bounds(grid)
    rover_cells = np.zeros(blocked.shape, bool)
    for c in crossed(grid, scouted) + crossed(grid, scout_detour) + crossed(grid, walk1):
        rover_cells[c] = True
    corridor = distance_transform_edt(~rover_cells, sampling=(terrain.resolution, float(np.median(terrain.column_spacing)))) <= 10.0
    coverage = [feature("cov-orbit-001", "Polygon", [box_ring(inner_bounds)], state="orbit_only", simulated=False, sensor="none")]
    # Ground no robot has seen yet at orbital planning: the walk leg and both viewpoints, padded 60 m.
    walk_pts = [grid.lonlat(c) for c in walk1] + [[points[k]["lon"], points[k]["lat"]] for k in ("observation_primary", "observation_backup")]
    pad_lat = 60.0 / (math.radians(1) * 3_389_500.0)
    pad_lon = pad_lat / math.cos(math.radians(points["observation_primary"]["lat"]))
    unscouted = {"south": min(p[1] for p in walk_pts) - pad_lat, "north": max(p[1] for p in walk_pts) + pad_lat,
                 "west": min(p[0] for p in walk_pts) - pad_lon, "east": max(p[0] for p in walk_pts) + pad_lon}
    coverage.append(feature("cov-unscouted-001", "Polygon", [box_ring({k: round(v, 7) for k, v in unscouted.items()})],
                            state="unscouted", simulated=False, sensor="none"))
    coverage += polygons(corridor, grid, COVERAGE_BLOCK, "all", "cov-rover",
                         {"state": "rover_checked", "simulated": True, "sensor": "stereo_cam"})
    viewpoints = {"lat": (points["observation_primary"]["lat"] + points["observation_backup"]["lat"]) / 2,
                  "lon": (points["observation_primary"]["lon"] + points["observation_backup"]["lon"]) / 2}
    coverage.append(feature("cov-drone-001", "Polygon", [circle(viewpoints, DRONE_CHECK_RADIUS_M)], state="drone_checked",
                            simulated=True, sensor="drone_cam"))
    foot = np.array(lines["scarp-foot"])
    perch = points["drone_perch"]
    aim = foot[int(np.argmin(polyline_distance_m(foot[:, 0], foot[:, 1], [[perch["lon"], perch["lat"]]] * 2)))].tolist()
    coverage.append(feature("cov-drone-perch", "Polygon", [sector(perch, aim, VIEW_CONE_M, VIEW_CONE_DEG)],
                            state="drone_checked", simulated=True, sensor="drone_cam"))

    route_list = [features[k] for k in ("guess", "rover", "main2", "backup")]
    mission = mission_record(sites, features, budgets, independence, discovery_point, drive1, drive2, rules,
                             walk_only_m, drive_counts_toward_limit)
    staging = Path(tempfile.mkdtemp(prefix=".mission-", dir=data_dir))
    try:
        write_json(staging / "hazards.geojson", {**collection(hazards), "placeholder": False})
        write_json(staging / "coverage.geojson", {**collection(coverage), "placeholder": False})
        write_json(staging / "routes.geojson", {**collection(route_list), "schema_version": "1.1", "placeholder": False})  # 1.1: legs
        write_json(staging / "mission.json", mission)
        # Audit exactly the staged files with the same analysed grid; refuse to publish a line that fails.
        shutil.copy2(scarp_path, staging / "scarp_lines.geojson")
        audit = audit_file(staging / "routes.geojson", staging / "mission.json", dtm_path, staging / "scarp_lines.geojson",
                           rules, sites_path=sites_path, grid=grid.audit_grid)
        audit["scarp_source"] = "scarp_lines.geojson"
        failed = {a["id"]: a["reasons"] for a in audit["routes"]
                  if a["audit_status"] not in ("candidate_requires_inspection",) and route_has_line(route_list, a["id"])}
        if failed:
            event("mission_geography_refused", logging.ERROR, reason="generated_route_failed_audit", routes=failed)
            raise RuntimeError(f"generated routes failed their own audit: {failed}")
        write_json(staging / "route_audit.json", audit)
        _activate(staging, data_dir, LIVE_NAMES)
    except Exception as error:
        event("mission_geography_publish_refused", logging.ERROR, reason=str(error))
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    report = report_record(sites, grid, cells, checks, features, budgets, independence, walk_only_m, discovery_point,
                           hazards, audit, zones, drive_counts_toward_limit, rules)
    write_json(report_path, report)
    event("mission_geography_published", evidence="inferred", terrain_evidence="nasa_derived",
          routes={r["properties"]["id"]: r["properties"]["status"] for r in route_list},
          hazards=len(hazards), coverage=len(coverage), duration_ms=(perf_counter() - started) * 1000,
          crew_clearance="not_established")
    return report


def route_has_line(routes, rid):
    """True when route rid has a drawable line (an empty route is reported in words, not audited as a line)."""
    return any(r["properties"]["id"] == rid and len(r["geometry"]["coordinates"]) >= 2 for r in routes)


def grid_bounds(grid):
    """Signed south/west/north/east of the inner (unpadded) crop."""
    col, row, width, height = grid.inner
    west, north = grid.terrain.lonlat(row, col, center=False)
    east, south = grid.terrain.lonlat(row + height, col + width, center=False)
    return {"south": south, "west": west, "north": north, "east": east}


def box_ring(b):
    """Closed [lon, lat] ring of a south/west/north/east box."""
    ring = [[b["west"], b["south"]], [b["east"], b["south"]], [b["east"], b["north"]], [b["west"], b["north"]]]
    return [[round(x, 7), round(y, 7)] for x, y in ring + ring[:1]]


def _leg_m(route, mode):
    """One-way metres of a route's legs in `mode` (0 for a route without a line)."""
    return sum(l["length_m"] for l in route["properties"].get("legs", []) if l["mode"] == mode)


BUDGET_NAMES = {"round_trip_distance_limit": "over the 5 km round-trip rule",
                "eva_time_limit": "over the EVA time with reserve", "walkback_exceeds_eva": "walkback exceeds the EVA",
                "hard_excursion_cap": "beyond the excursion cap", "leg_validation_failed": "leg numbers inconsistent"}


def _budget_text(report):
    """Short budget verdict for stage stats: within budget, or which rule fails."""
    if report is None:
        return "No route to budget"
    if not report["applied_reasons"]:
        return f"Within budget ({report['round_trip_m'] / 1000:.2f} km round trip)"
    return "Rejected: " + ", ".join(BUDGET_NAMES.get(r, r) for r in report["applied_reasons"])


def mission_record(sites, features, budgets, independence, discovery_point, drive1, drive2, rules,
                   walk_only_m, drive_counts_toward_limit):
    """mission.json computed from the generated routes; every number on screen comes from them."""
    points = sites["points"]
    guess, main2, backup, rover = features["guess"], features["main2"], features["backup"], features["rover"]
    gp, mp = guess["properties"], main2["properties"]
    drive_g, walk_g = _leg_m(guess, "drive"), _leg_m(guess, "walk")
    detour = _leg_m(main2, "drive") - drive_g
    report_main, report_guess = budgets.get(mp["id"]), budgets.get(gp["id"])
    has_main = bool(main2["geometry"]["coordinates"])
    rule_note = ("drive metres counted toward the 5,000 m rule (--drive-counts)" if drive_counts_toward_limit
                 else "5,000 m rule on walking distance only (team decision 2026-11-14)")
    stages = [
        {"id": "orbital", "title": "Orbital planning",
         "text": (f"From NASA orbital data only: drive the crew rover {drive_g / 1000:.1f} km north across the crater floor to a "
                  f"parking spot above the scarp's low east end, then walk {walk_g:.0f} m down to the viewpoint below the ice "
                  f"face. Slope comes from the HiRISE DTM; the scarp edge, foot and rockfall zone are traced from imagery "
                  f"(inferred). Rocks under 1 m, loose ground and shadow are not assessed."),
         "stats": {"Detail": "1 m DTM, 25 cm imagery", "Drive + walk (one way)": f"{drive_g / 1000:.2f} km + {walk_g:.0f} m",
                   "Steepest cell": f"{gp['stats']['max_slope_deg']:.1f}° (drive limit 24°, walk 20°)", "Budget": _budget_text(report_guess)}},
        {"id": "rover", "title": "Rover reconnaissance",
         "text": (f"The day before the walk, the simulated rover drives the candidate route. About "
                  f"{DISCOVERY_FRACTION * drive_g / 1000:.1f} km out it reports soft ground the orbit could not see "
                  f"(simulated) and stops; the drive is replanned around it ({detour:+.0f} m)."),
         "stats": {"Underground (U)": "1 found (simulated)", "Replanned drive": f"{detour:+.0f} m",
                   "Rover path": f"{rover['properties']['stats']['length_m'] / 1000:.1f} km (simulated)"}},
        {"id": "drone", "title": "Drone inspection",
         "text": ("The simulated drone images the scarp face from the pit floor and checks the ground around the viewpoints. "
                  "The rockfall zone shown is the traced-foot rule, not something the drone measured."),
         "stats": {"Overhead (O)": "Rockfall zone from traced foot (inferred)", "Viewpoints": "Outside the modeled rockfall zone",
                   "Coverage": "Simulated"}},
        {"id": "eva", "title": "Astronaut mission review",
         "text": ("Review the replanned route two astronauts would take to the viewpoint, the evidence behind it and the "
                  "backup. Budgets use pipeline.itinerary with " + rule_note + ". None of this is crew clearance."),
         "stats": {"Round trip": (f"{mp['stats']['round_trip_m'] / 1000:.2f} km ({2 * _leg_m(main2, 'walk'):.0f} m walking)"
                                  if has_main else "No route"),
                   "Time": f"{report_main['total_min']:.0f} of {report_main['available_min']:.0f} min" if report_main else "n/a",
                   "Steepest cell": f"{mp['stats']['max_slope_deg']:.1f}° (drive limit 24°, walk 20°)" if has_main else "n/a",
                   "Budget": _budget_text(report_main)}},
    ]
    alerts = {"orbital": ["Candidate from orbit only: not crew clearance"],
              "rover": ["Simulated: rover stopped, wheel slip 38 percent, requesting input"],
              "drone": ["Simulated drone concept: rockfall zone traced from imagery, not verified"],
              "eva": []}
    for stage, report in (("orbital", report_guess), ("eva", report_main)):
        if report and report["applied_reasons"]:
            alerts[stage].append(f"No viable route under the current rules: "
                                 + ", ".join(BUDGET_NAMES.get(r, r) for r in report["applied_reasons"])
                                 + f" ({report['round_trip_m'] / 1000:.2f} km incl. drive; walking {report['walk_round_trip_m']:.0f} m)")
    if backup["properties"]["status"] == "backup_unavailable":
        alerts["eva"].append("Backup unavailable: " + backup["properties"].get("status_reason", "no independent candidate"))
    elif independence:
        alerts["eva"].append(f"Backup shares {independence['shared_m']:.0f} m with the main route")
    return {
        "schema_version": SCHEMA_VERSION, "placeholder": False,
        "site": {"name": "Scarps in Milankovic Crater", "lat": 54.144, "lon": -147.894,
                 "dtm_id": sites["dtm_id"], "image_id": "ESP_071006_2345"},
        "sun": {"ls_deg": 101.2, "local_time": "15:26", "elevation_deg": 42, "source": "ESP_071006_2345 metadata"},
        "endpoints": {k: {"lat": points[k]["lat"], "lon": points[k]["lon"]}
                      for k in ("habitat", "observation_primary", "observation_backup")},
        "stages": stages, "alerts": alerts,
        "drone": {"perch": {"lat": points["drone_perch"]["lat"], "lon": points["drone_perch"]["lon"]},
                  "view_cone_id": "cov-drone-perch"},
        "discovery": {
            "id": "disc-001", "hazard_id": "hz-sim-001", "before_route_id": gp["id"], "after_route_id": mp["id"],
            "location": {"lat": discovery_point["lat"], "lon": discovery_point["lon"]},
            "sensor_evidence": {"wheel_slip_pct": 38,
                                "thermal": "simulated thermal camera: surface cooler than surroundings (possible loose material)",
                                "orbital_prior": "Looked firm in HiRISE imagery"},
            "evidence": "simulated", "uncertainty": "high", "decision": "request_input",
            "options": [
                {"id": "opt-reroute", "label": "Reroute around the area",
                 "consequence": f"{detour:+.0f} m drive, {detour / SPEEDS_M_MIN['drive']:+.1f} min each way"},
                {"id": "opt-drone", "label": "Send the drone to inspect", "consequence": "+15 min, may clear the area (simulated)"},
                {"id": "opt-continue", "label": "Continue slowly", "consequence": "Risk accepted by crew"}],
            "chosen_option": ""},
    }


def report_record(sites, grid, cells, checks, features, budgets, independence, walk_only_m, discovery_point,
                  hazards, audit, zones, drive_counts_toward_limit, rules):
    """Provenance report: point checks, first-pass discrepancies, budgets, audit statuses, open questions."""
    points, first = sites["points"], sites.get("first_pass_points", {})
    discrepancies = {}
    for name, point in points.items():
        if name in first:
            d = mars_distance([point["lon"], point["lat"]], [first[name]["lon"], first[name]["lat"]])
            discrepancies[name] = {"reviewed": {"lat": point["lat"], "lon": point["lon"]},
                                   "first_pass": {"lat": first[name]["lat"], "lon": first[name]["lon"]}, "distance_m": round(d, 1)}
    # Smallest margin over every scarp (zones: ScarpSet); negative would mean inside a rockfall buffer.
    margin = {k: round(min(float(polyline_distance_m([points[k]["lon"]], [points[k]["lat"]], z.foot)[0]
                                 - z.buffer_at([points[k]["lon"]])[0]) for z in zones.members), 1)
              for k in ("observation_primary", "observation_backup")}
    limit = threshold(rules, "round_trip_limit_m")
    return {
        "schema_version": SCHEMA_VERSION, "evidence": "inferred", "terrain_evidence": "nasa_derived",
        "crew_clearance": "not_established", "dtm": grid.terrain.source, "bounds": grid_bounds(grid),
        "point_checks": checks, "first_pass_discrepancies": discrepancies,
        "viewpoint_margin_outside_rockfall_m": margin,
        "walk_only_reference": {"length_m": None if walk_only_m is None else round(walk_only_m, 1),
                                "round_trip_m": None if walk_only_m is None else round(2 * walk_only_m, 1),
                                "within_round_trip_rule": walk_only_m is not None and 2 * walk_only_m < limit},
        "drive_counts_toward_limit": drive_counts_toward_limit,
        "routes": {r["properties"]["id"]: {"status": r["properties"]["status"], "reason": r["properties"].get("status_reason"),
                                           "stats": r["properties"]["stats"]} for r in features.values()},
        "budgets": budgets, "backup_independence": independence, "discovery_location": discovery_point,
        "hazard_counts": {c: sum(h["properties"]["category"] == c for h in hazards)
                          for c in sorted({h["properties"]["category"] for h in hazards})},
        "not_assessed": ["shadow (no illumination model for the EVA time)", "soft ground (no thermal-inertia layer)",
                         "rocks under ~1 m (below DTM resolution)", "scarp continuation beyond the traced 1.5 km"],
        "audit_statuses": {a["id"]: a["audit_status"] for a in audit["routes"]},
        "open_questions": [
            "Scarp lines and profiles are Yasser's agent's image trace: review before relying on edge/rockfall zones.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dtm", type=Path, default=DEFAULT_DTM)
    parser.add_argument("--data-dir", type=Path, default=Path("public/data"))
    parser.add_argument("--sites", type=Path, default=DEFAULT_SITES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--drive-counts", action="store_true",
                        help="also count drive metres toward the 5,000 m round-trip rule (default: walking only, team decision)")
    arguments = parser.parse_args()
    configure_logging()
    with operation("mission_geography_cli", dataset_id=arguments.dtm.name):
        result = build(arguments.dtm, arguments.data_dir, arguments.sites, arguments.report,
                       drive_counts_toward_limit=arguments.drive_counts)
    for rid, route in result["routes"].items():
        print(f"{rid}: {route['status']} {route['reason'] or ''} | {route['stats']['length_m']} m")
    print("audit:", result["audit_statuses"])
