"""Mission geography: compiled search, scarp zones, audit objectives/fingerprints, published-data consistency."""

import json
import logging
from pathlib import Path

import numpy as np
import pytest

from pipeline import route_audit
from pipeline.hazards import hazard_masks
from pipeline.mission_geography import load_sites, pooled, simplify_cells
from pipeline.route_audit import (ALGORITHM_VERSION, ScarpZones, endpoints_fingerprint, intended_endpoints,
                                  route_fingerprint, scarp_fingerprint)
from pipeline.routing import grid_shortest_path, shortest_path
from pipeline.terrain import Terrain, analyze, load_rules

DATA = Path("public/data")
SITES = Path("pipeline/site/mission_sites.json")


def read(name):
    """Published JSON from public/data."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def path_cost(costs, path, spacing):
    """Edge-weighted cost of a 4-neighbour cell path, same weights as both searches."""
    total = 0.0
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        step = spacing[0] if r0 != r1 else spacing[1][r0]
        total += (costs[r0, c0] + costs[r1, c1]) / 2 * step
    return total


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_compiled_search_matches_reference_cost(seed):
    rng = np.random.default_rng(seed)
    costs = rng.uniform(1, 5, (30, 40))
    costs[rng.random(costs.shape) < 0.2] = np.inf
    costs[0, 0] = costs[-1, -1] = 1.0
    spacing = (1.0, np.linspace(0.9, 1.1, 30))
    reference = shortest_path(costs, (0, 0), (29, 39), spacing)
    fast = grid_shortest_path(costs, (0, 0), (29, 39), spacing)
    assert bool(reference) == bool(fast)
    if reference:
        assert path_cost(costs, fast, spacing) == pytest.approx(path_cost(costs, reference, spacing))
        assert all(np.isfinite(costs[c]) for c in fast)
        assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(fast, fast[1:]))


def test_compiled_search_reports_no_route(caplog):
    costs = np.ones((5, 5))
    costs[:, 2] = np.inf
    with caplog.at_level(logging.WARNING, logger="terps.pipeline"):
        assert grid_shortest_path(costs, (0, 0), (4, 4)) == []
    unavailable = [r for r in caplog.records if getattr(r, "event", None) == "route_search_unavailable"]
    assert unavailable and unavailable[0].fields["status"] == "no_viable_route"
    with pytest.raises(ValueError):
        grid_shortest_path(costs, (0, 0), (0, 0))


def test_rockfall_buffer_grid_overrides_single_buffer():
    from pipeline.tests.test_slope_mvp import synthetic
    terrain = synthetic(np.zeros((20, 20)))
    analysis = analyze(terrain, load_rules())
    shape = terrain.elevation.shape
    foot = np.tile(np.arange(shape[1], dtype=float), (shape[0], 1))
    buffer = np.full(shape, 5.0)
    buffer[:, shape[1] // 2:] = 10.0
    masks = hazard_masks(terrain, analysis, edge_distance=np.full(shape, 1e6), foot_distance=foot,
                         scarp_height=50.0, apron_m=50.0, rockfall_buffer=buffer)
    assert masks["rockfall"][0, 5] and not masks["rockfall"][0, 6]
    assert not masks["inspection_required"].any()
    with pytest.raises(ValueError):
        hazard_masks(terrain, analysis, foot_distance=foot, rockfall_buffer=np.full(shape, np.nan))


def test_scarp_zones_rockfall_only_below_the_face():
    rules = load_rules()
    edge = [[-147.90, 54.1635], [-147.89, 54.1635]]
    foot = [[-147.90, 54.1645], [-147.89, 54.1645]]
    zones = ScarpZones(edge, foot, [{"lon": -147.90, "height_m": 50, "apron_m": 40},
                                    {"lon": -147.89, "height_m": 30, "apron_m": 40}], rules)
    lon = -147.895
    k = 59157.0  # metres per degree latitude on R = 3,389.5 km
    below = 54.1645 + 30 / k  # 30 m north of the foot (pit floor)
    above = 54.1635 - 30 / k  # 30 m south of the edge (plateau)
    at_edge = 54.1635 - 10 / k
    edge_hit, rockfall = zones.classify([lon, lon, lon], [below, above, at_edge])
    assert rockfall.tolist() == [True, False, False]
    assert edge_hit.tolist() == [False, False, True]
    assert zones.buffer_at([-147.90])[0] == 50 and zones.buffer_at([-147.80])[0] == 40


def test_backup_objective_accepts_return_home_and_either_viewpoint():
    mission = {"endpoints": {"habitat": {"lat": 0, "lon": 0}, "observation_primary": {"lat": 1, "lon": 1},
                             "observation_backup": {"lat": 1, "lon": 2}}}
    names = [n for n, _, _ in intended_endpoints({"properties": {"kind": "backup"}}, mission)]
    assert names == ["habitat->observation_backup", "habitat->observation_primary"]
    assert intended_endpoints({"properties": {"kind": "rover_path"}}, mission) == []


def test_fingerprints_change_with_geometry_claims_and_endpoints():
    feature = {"properties": {"id": "r", "kind": "main", "agent": "crew", "version": "after", "status": "inspection_required",
                              "stats": {"length_m": 10.0}}, "geometry": {"coordinates": [[-147.9, 54.1], [-147.8, 54.2]]}}
    base = route_fingerprint(feature)
    moved = json.loads(json.dumps(feature))
    moved["geometry"]["coordinates"][0][1] += 1e-5
    claimed = json.loads(json.dumps(feature))
    claimed["properties"]["status"] = "ok"
    assert len({base, route_fingerprint(moved), route_fingerprint(claimed)}) == 3
    a = endpoints_fingerprint({"endpoints": {"habitat": {"lat": 1.0, "lon": 2.0}}})
    assert a != endpoints_fingerprint({"endpoints": {"habitat": {"lat": 1.0, "lon": 2.0000001}}})
    assert scarp_fingerprint(None) is None


def test_published_audit_fingerprint_matches_published_files():
    """Blocks deploying diagnostics that describe other lines, endpoints, scarp or rules than the ones shipped."""
    audit, routes, mission = read("route_audit.json"), read("routes.geojson"), read("mission.json")
    fp = audit["fingerprint"]
    assert fp["algorithm_version"] == ALGORITHM_VERSION
    assert fp["dtm_id"] == mission["site"]["dtm_id"]
    assert fp["rules_sha256"] == route_audit.canonical_sha256(load_rules())
    assert fp["endpoints"] == endpoints_fingerprint(mission)
    assert fp["scarp"] == scarp_fingerprint(read("scarp_lines.geojson"))
    assert fp["scarp_profiles_sha256"] == route_audit.canonical_sha256(load_sites(SITES)["scarp_profiles"])
    assert fp["routes"] == {f["properties"]["id"]: route_fingerprint(f) for f in routes["features"]}
    assert audit["zone_checks"] == "edge_setback_and_rockfall"


def test_published_geography_is_coherent_and_never_cleared():
    routes, hazards, mission = read("routes.geojson"), read("hazards.geojson"), read("mission.json")
    audit = {a["id"]: a for a in read("route_audit.json")["routes"]}
    assert not routes.get("placeholder") and not hazards.get("placeholder") and not mission.get("placeholder")
    for f in routes["features"]:
        p = f["properties"]
        assert p["status"] != "ok"
        assert audit[p["id"]]["audit_status"] == "candidate_requires_inspection"
        assert audit[p["id"]]["cells_excluded"] == 0 and audit[p["id"]]["cells_in_rockfall_zone"] == 0
        if p["status"] in ("no_viable_route", "backup_unavailable") and f["geometry"]["coordinates"]:
            assert p.get("status_reason"), "a rejected candidate states why"
        for lon, lat in f["geometry"]["coordinates"]:
            assert -180 <= lon <= 180 and 54.0 < lat < 54.3
    ids = {f["properties"]["id"] for f in hazards["features"]}
    assert not ids & {"hz-shadow-001", "hz-soft-001", "hz-nodata-001"}, "placeholder rectangles are gone"
    sim = [f for f in hazards["features"] if f["properties"]["evidence"] == "simulated"]
    assert [f["properties"]["stage"] for f in sim] == ["rover"], "simulated discovery never shows in orbital planning"
    assert all(f["properties"]["stage"] == "orbital" for f in hazards["features"] if f["properties"]["evidence"] != "simulated")
    d = mission["discovery"]
    assert {d["before_route_id"], d["after_route_id"]} <= {f["properties"]["id"] for f in routes["features"]}
    points = load_sites(SITES)["points"]
    for name in ("habitat", "observation_primary", "observation_backup"):
        assert mission["endpoints"][name] == {"lat": points[name]["lat"], "lon": points[name]["lon"]}


def test_sites_validation_rejects_bad_points(tmp_path):
    sites = load_sites(SITES)
    sites["points"]["habitat"]["lon"] = 212.1  # 0-360 east must be converted first
    bad = tmp_path / "sites.json"
    bad.write_text(json.dumps(sites))
    with pytest.raises(ValueError, match="-180..180"):
        load_sites(bad)


def test_helpers_keep_cells_and_conservative_pooling():
    path = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)]
    assert simplify_cells(path) == [(0, 0), (0, 2), (2, 2)]
    mask = np.zeros((4, 4), bool)
    mask[0, 0] = True
    assert pooled(mask, 2, "any").tolist() == [[True, False], [False, False]]
    assert not pooled(mask, 2, "all").any()
