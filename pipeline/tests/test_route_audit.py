"""Route audit: cell traversal, narrow hazards, per-leg limits, endpoints, stats, unknown terrain, status honesty."""

import json
import logging

import numpy as np
import pytest

from pipeline.route_audit import TerrainGrid, audit_file, audit_route, point_in_polygon, scarp_face, supercover
from pipeline.terrain import analyze, load_rules
from pipeline.tests.test_slope_mvp import synthetic, write_dtm

RULES = load_rules()


def grid_with_wall(wall_col=50, height=12.0, size=(40, 100), unknown=None):
    """Flat 1 m terrain with a one-cell-wide wall at wall_col (steep sides); unknown: (row, col) no-data cells."""
    z = np.zeros(size)
    z[:, wall_col] = height
    for row, col in unknown or []:
        z[row, col] = np.nan
    terrain = synthetic(z)
    return TerrainGrid(terrain, analyze(terrain, RULES), RULES)


def lonlat(grid, col, row=20):
    """[lon, lat] of a cell centre in grid."""
    return grid.cell_lonlat(col, row)


def route(coords, agent="crew", kind="main", status="inspection_required", length=None, legs=None, rid="rt-test"):
    """Minimal route feature; length defaults to the true geometric length."""
    from pipeline.itinerary import polyline_m
    props = {"id": rid, "agent": agent, "kind": kind, "status": status,
             "stats": {"length_m": polyline_m(coords) if length is None else length}}
    if legs:
        props["legs"] = legs
    return {"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}}


def mission_for(start, end):
    """Mission with habitat at start and the primary observation point at end."""
    return {"endpoints": {"habitat": {"lon": start[0], "lat": start[1]},
                          "observation_primary": {"lon": end[0], "lat": end[1]}}}


def test_supercover_horizontal_and_reverse():
    """A horizontal segment visits every column once, in order, in either direction."""
    forward = [cell for cell, _ in supercover(0.5, 0.5, 5.5, 0.5)]
    backward = [cell for cell, _ in supercover(5.5, 0.5, 0.5, 0.5)]
    assert forward == [(c, 0) for c in range(6)] and backward == list(reversed(forward))


def test_supercover_corner_crossing_includes_both_neighbours():
    """An exact diagonal through cell corners also lists both side cells (no diagonal leap past a hazard)."""
    cells = {cell for cell, _ in supercover(0.5, 0.5, 2.5, 2.5)}
    assert {(1, 0), (0, 1), (1, 1), (2, 1), (1, 2), (2, 2)} <= cells


def test_supercover_steep_segment_has_no_gaps():
    """Consecutive cells always share an edge or (at corners) both neighbours are present."""
    cells = [cell for cell, _ in supercover(0.2, 0.3, 3.7, 9.9)]
    for (c0, r0), (c1, r1) in zip(cells, cells[1:]):
        assert abs(c1 - c0) + abs(r1 - r0) <= 2


def test_narrow_wall_between_sparse_vertices_is_found():
    """Two vertices 80 m apart either side of a 1-cell wall: vertex-only sampling would miss it, the audit does not."""
    grid = grid_with_wall()
    coords = [lonlat(grid, 10), lonlat(grid, 90)]
    audit = audit_route(route(coords), mission_for(coords[0], coords[1]), grid, RULES)
    assert audit["audit_status"] == "excluded_terrain"
    assert audit["cells_excluded"] >= 1 and 35 < audit["first_exclusion_at_m"] < 45
    assert audit["max_slope_deg"] > 70


def test_route_on_flat_ground_is_only_a_candidate():
    """No hazard crossed and matching endpoints still yields candidate_requires_inspection, never ok."""
    grid = grid_with_wall()
    coords = [lonlat(grid, 10), lonlat(grid, 40)]
    audit = audit_route(route(coords), mission_for(coords[0], coords[1]), grid, RULES)
    assert audit["audit_status"] == "candidate_requires_inspection" and audit["reasons"] == []
    assert audit["status_consistent"] is True


def test_claimed_ok_is_flagged_as_overclaim():
    """A file status 'ok' is never consistent with terrain evidence alone."""
    grid = grid_with_wall()
    coords = [lonlat(grid, 10), lonlat(grid, 40)]
    audit = audit_route(route(coords, status="ok"), mission_for(coords[0], coords[1]), grid, RULES)
    assert audit["status_consistent"] is False and any("status_overclaims" in r for r in audit["reasons"])


def test_endpoint_mismatch_is_reported_not_fixed():
    """A line ending 30 m short of its objective is flagged; the geometry is not moved."""
    grid = grid_with_wall()
    coords = [lonlat(grid, 10), lonlat(grid, 40)]
    feature = route(coords)
    audit = audit_route(feature, mission_for(coords[0], lonlat(grid, 40, row=20 - 30)), grid, RULES)
    assert audit["audit_status"] == "endpoint_mismatch" and audit["end_offset_m"] == pytest.approx(30, abs=1)
    assert feature["geometry"]["coordinates"] == coords


def test_stats_mismatch_is_reported():
    """Claimed length that disagrees with the measured line is reported with both numbers."""
    grid = grid_with_wall()
    coords = [lonlat(grid, 10), lonlat(grid, 40)]
    audit = audit_route(route(coords, length=900), mission_for(coords[0], coords[1]), grid, RULES)
    assert audit["length_mismatch_m"] < -800 and any("stats_mismatch" in r for r in audit["reasons"])


def test_drive_legs_use_rover_limit_and_walk_legs_crew_limit():
    """A 22 degree ramp blocks walking (>= 20) but not driving (< 24)."""
    z = np.zeros((40, 100))
    z[:, 45:56] = np.tan(np.radians(22)) * np.arange(11) * 1.0  # east-facing ramp
    terrain = synthetic(z)
    # Make the ramp exactly 22 degrees in ground metres: east-west spacing differs from 1 m at 54 N.
    spacing = float(terrain.column_spacing[20])
    z[:, 45:56] = np.tan(np.radians(22)) * np.arange(11) * spacing
    z[:, 56:] = z[:, 55:56]  # plateau after the ramp, no drop-off
    terrain = synthetic(z)
    grid = TerrainGrid(terrain, analyze(terrain, RULES), RULES)
    coords = [lonlat(grid, 30), lonlat(grid, 70)]
    walk = audit_route(route(coords), mission_for(coords[0], coords[1]), grid, RULES)
    drive = audit_route(route(coords, legs=[{"mode": "drive", "from": 0, "to": 1}]), mission_for(coords[0], coords[1]), grid, RULES)
    assert walk["audit_status"] == "excluded_terrain"
    assert drive["audit_status"] == "candidate_requires_inspection" and drive["modes"] == ["drive"]


def test_unknown_cells_make_terrain_unassessed():
    """A no-data cell on the path is unassessed terrain, not safe ground."""
    grid = grid_with_wall(unknown=[(20, 25)])
    coords = [lonlat(grid, 10), lonlat(grid, 40)]
    audit = audit_route(route(coords), mission_for(coords[0], coords[1]), grid, RULES)
    assert audit["audit_status"] == "unassessed_terrain" and audit["cells_unknown"] >= 1


def test_leaving_the_crop_is_outside_assessed_terrain():
    """Cells beyond the analysed crop are reported, never assumed flat."""
    grid = grid_with_wall()
    inside, beyond = lonlat(grid, 10), lonlat(grid, 10, row=-15)
    audit = audit_route(route([inside, beyond]), mission_for(inside, beyond), grid, RULES)
    assert audit["cells_outside"] > 0 and "outside_assessed_terrain" in {r.split(":")[0] for r in audit["reasons"]}


def test_invalid_geometry():
    """Fewer than two finite vertices is geometry_invalid."""
    grid = grid_with_wall()
    audit = audit_route(route([lonlat(grid, 10)]), {"endpoints": {}}, grid, RULES)
    assert audit["audit_status"] == "geometry_invalid"


def test_signed_and_east_longitudes_hit_the_same_cell():
    """-147.9 style and 212.1 east inputs map to the same DTM pixel."""
    grid = grid_with_wall()
    lon, lat = lonlat(grid, 30)
    a, b = grid.to_pixel([[lon, lat], [lon + 360, lat]])
    assert a == pytest.approx(b)


def test_scarp_face_crossing():
    """A route crossing the polygon between edge and foot lines is flagged."""
    grid = grid_with_wall()
    west, east = lonlat(grid, 20), lonlat(grid, 30)
    north, south = lonlat(grid, 25, row=15), lonlat(grid, 25, row=25)
    scarp = {"features": [
        {"properties": {"id": "scarp-edge"}, "geometry": {"type": "LineString", "coordinates": [[west[0], south[1]], [east[0], south[1]]]}},
        {"properties": {"id": "scarp-foot"}, "geometry": {"type": "LineString", "coordinates": [[west[0], north[1]], [east[0], north[1]]]}}]}
    face = scarp_face(scarp)
    assert point_in_polygon([lonlat(grid, 25)[0]], [lonlat(grid, 25)[1]], face)[0]
    coords = [lonlat(grid, 10), lonlat(grid, 40)]
    audit = audit_route(route(coords), mission_for(coords[0], coords[1]), grid, RULES, face)
    assert audit["cells_on_scarp_face"] > 0 and audit["audit_status"] == "excluded_terrain"


def test_audit_file_logs_each_route(tmp_path, caplog):
    """audit_file reads a DTM file, logs route_audited per route with evidence, and is deterministic."""
    z = np.zeros((60, 120))
    z[:, 60] = 12.0
    dtm = write_dtm(tmp_path / "dtm.tif", z)
    from pipeline.terrain import read_terrain
    terrain = read_terrain(dtm)
    a, b = terrain.lonlat(30, 30), terrain.lonlat(30, 90)
    (tmp_path / "routes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [route([a, b])]}))
    (tmp_path / "mission.json").write_text(json.dumps(mission_for(a, b)))
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    first = audit_file(tmp_path / "routes.geojson", tmp_path / "mission.json", dtm)
    second = audit_file(tmp_path / "routes.geojson", tmp_path / "mission.json", dtm)
    assert first == second and first["routes"][0]["audit_status"] == "excluded_terrain"
    logged = [r for r in caplog.records if getattr(r, "event", "") == "route_audited"]
    assert logged and logged[0].fields["evidence"] == "inferred" and logged[0].fields["terrain_evidence"] == "nasa_derived"
    assert logged[0].levelno == logging.WARNING


def test_missing_dtm_is_a_clear_error(tmp_path):
    """No DTM: FileNotFoundError, no audit file."""
    (tmp_path / "routes.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    (tmp_path / "mission.json").write_text("{}")
    with pytest.raises(FileNotFoundError, match="DTM"):
        audit_file(tmp_path / "routes.geojson", tmp_path / "mission.json", tmp_path / "none.IMG")


def test_published_audit_matches_published_routes():
    """public/data/route_audit.json was produced from the current routes.geojson and never says ok."""
    from pathlib import Path
    from pipeline.route_audit import canonical_sha256
    data = Path(__file__).resolve().parents[2] / "public" / "data"
    audit = json.loads((data / "route_audit.json").read_text())
    routes = json.loads((data / "routes.geojson").read_text())
    assert audit["routes_sha256"] == canonical_sha256(routes)
    assert [a["id"] for a in audit["routes"]] == [f["properties"]["id"] for f in routes["features"]]
    assert all(a["audit_status"] != "ok" for a in audit["routes"])
