"""P0 regressions: infeasibility is reported, budgets cover full itineraries, uncertainty discs and
unresolved roughness are conservative."""

import json
import logging

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from pipeline import run as run_module
from pipeline.feasibility import audit_from_config, audit_site
from pipeline.hazards import hazard_masks, uncertainty_area_check
from pipeline.routing import (InfeasibleMission, UNRESOLVED_ROUGHNESS_PENALTY, cost_grid, itinerary_budget,
                              mission_budget, plan_routes)
from pipeline.scenario import discovery_scenario
from pipeline.terrain import analyze, load_rules
from pipeline.tests.test_terrain import terrain


def flat(size=41):
    """Simulated flat 1 m grid with its analysis and hazard masks."""
    t = terrain(np.zeros((size, size)))
    a = analyze(t)
    return t, a, hazard_masks(t, a)


def events(caplog, name):
    """Structured records with the given event name."""
    return [r for r in caplog.records if getattr(r, "event", None) == name]


# --- Infeasibility is a finding, not a crash -------------------------------------------------

def test_discovery_raises_specific_infeasible_finding():
    t, a, m = flat()
    with pytest.raises(InfeasibleMission, match="No viable preliminary route"):
        discovery_scenario(t, a, m, (20, 2), (20, 38), (20, 20), sensor_radius_m=10, eva_minutes=1, speed_m_min=1)


def test_discovery_off_route_is_still_a_config_error():
    t, a, m = flat()
    with pytest.raises(ValueError, match="inside a viable") as error:
        discovery_scenario(t, a, m, (20, 2), (20, 38), (5, 5), sensor_radius_m=10)
    assert not isinstance(error.value, InfeasibleMission)


def test_run_writes_feasibility_report_instead_of_crashing(tmp_path, monkeypatch, caplog):
    """An infeasible plan yields a report and hazards, but no fabricated discovery or mission.json."""
    def infeasible(*args, **kwargs):
        raise InfeasibleMission("No viable preliminary route (no_viable_route)")
    monkeypatch.setattr(run_module, "discovery_scenario", infeasible)
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    output = run_module.run(tmp_path / "out")
    names = {p.name for p in output.iterdir()}
    assert names == {"feasibility_report.json", "hazards.geojson"}
    report = json.loads((output / "feasibility_report.json").read_text())
    assert report["crew_clearance"] == "not_established" and "finding" in report
    assert events(caplog, "mission_infeasible_reported")[0].fields["mission_bundle"] == "not_exported"


# --- Budgets: lower bound, shortest-distance fallback, full itineraries ------------------------

def test_straight_line_lower_bound_rejects_without_search(caplog):
    t, a, m = flat()
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    output, primary, _ = plan_routes(t, a, m, (20, 2), (20, 38), eva_minutes=10, speed_m_min=1)
    assert primary == [] and output["features"][0]["properties"]["status"] == "no_viable_route"
    rejected = events(caplog, "route_rejected")[0].fields
    assert rejected["reason"] == "straight_line_lower_bound" and rejected["search_skipped"]
    assert not events(caplog, "route_search_started")


def test_budget_falls_back_to_shortest_distance_path(caplog):
    """A detour that is cheapest by weight but too long must not hide a shorter route that fits."""
    t, a, m = flat()
    unscouted = np.zeros(t.elevation.shape, bool)
    unscouted[20, :] = True  # the straight row costs 3/cell; row 19 detour costs 1/cell but is longer
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    # 36 m straight: 72 m round trip fits 105 * 0.7 = 73.5 min at 1 m/min; the 38 m detour (76 m) does not.
    output, primary, _ = plan_routes(t, a, m, (20, 2), (20, 38), eva_minutes=105, speed_m_min=1,
                                     unscouted=unscouted, corridor_m=0)
    assert primary and all(cell[0] == 20 for cell in primary)
    fallback = events(caplog, "budget_fallback_shortest_distance")[0].fields
    assert fallback["shortest_length_m"] < fallback["least_cost_length_m"]
    assert output["features"][0]["properties"]["status"] == "inspection_required"


def test_shortest_route_over_budget_is_proven_infeasible(caplog):
    t, a, m = flat()
    m["crew_exclude"][5:36, 20] = True  # wall forces a detour longer than the straight-line bound
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    _, primary, _ = plan_routes(t, a, m, (20, 2), (20, 38), eva_minutes=105, speed_m_min=1, corridor_m=0)
    assert primary == []
    rejected = events(caplog, "route_rejected")[-1].fields
    assert rejected["reason"] == "mission_budget"
    assert rejected["proof"] == "shortest_distance_path_over_same_exclusions_exceeds_budget"


def test_itinerary_budget_counts_primary_to_backup_leg():
    """Omitting the primary->backup leg undercounts: 1500 + 1700 + 1422 = 4622 m."""
    rules = load_rules()
    full = itinerary_budget([1500, 1700, 1422], rules, 600, 20, 40, max_excursion_m=1700)
    assert full["distance_m"] == pytest.approx(4622) and full["legs_m"] == [1500, 1700, 1422]
    assert full["accepted"]
    too_far = itinerary_budget([2000, 1500, 1600], rules, 600, 20, 40)
    assert "round_trip_distance_limit" in too_far["reasons"]
    capped = itinerary_budget([100, 100], rules, 600, 20, 0, max_excursion_m=10_001)
    assert "hard_excursion_cap" in capped["reasons"]


def test_mission_budget_keeps_two_leg_behaviour():
    rules = load_rules()
    result = mission_budget({"length_m": 600}, {"length_m": 700}, rules, 100 / .7, 20, 35)
    assert result["accepted"] and result["distance_m"] == 1300 and result["max_excursion_m"] == 700


# --- Uncertainty disc ---------------------------------------------------------------------------

def test_uncertainty_disc_catches_hazard_beside_the_cell():
    t, a, m = flat()
    m["crew_exclude"][20, 30] = True  # 10 m east of the candidate cell, which itself is clear
    near = uncertainty_area_check(t, a, m, (20, 20))
    assert near["radius_m"] == 15 and near["status"] == "excluded_terrain_within_uncertainty"
    assert near["counts"]["slope_exclude"] == 1
    assert uncertainty_area_check(t, a, m, (20, 20), radius_m=5)["status"] == "no_mapped_exclusion"


def test_uncertainty_disc_leaving_crop_requires_inspection():
    t, a, m = flat()
    result = uncertainty_area_check(t, a, m, (2, 20))
    assert result["disc_leaves_crop"] and result["status"] == "inspection_required"
    assert result["crew_clearance"] == "not_established"


def test_uncertainty_disc_reports_unresolved_scarp():
    t, a, m = flat()
    m["inspection_required"][25, 20] = True
    assert uncertainty_area_check(t, a, m, (20, 20))["status"] == "inspection_required"


# --- Unresolved roughness -------------------------------------------------------------------------

def test_unresolved_roughness_is_penalized_and_flagged(caplog):
    t, a, m = flat()
    a = {**a, "roughness": a["roughness"].copy()}
    a["roughness"][:, :] = np.nan  # e.g. window too coarse: measured nowhere, valid everywhere
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    costs = cost_grid(t, a, m, unscouted=np.zeros(t.elevation.shape, bool))
    assert np.all(costs[a["valid"]] == pytest.approx(1 + UNRESOLVED_ROUGHNESS_PENALTY))
    assert events(caplog, "unresolved_roughness_penalized")[0].fields["cells"] == int(a["valid"].sum())
    output, primary, _ = plan_routes(t, a, m, (20, 2), (20, 38), unscouted=np.zeros(t.elevation.shape, bool))
    assert primary and output["features"][0]["properties"]["status"] == "inspection_required"
    assert events(caplog, "unresolved_roughness_on_route")


# --- Site audit ----------------------------------------------------------------------------------

def test_audit_site_reports_itineraries_and_never_clearance(caplog):
    t, a, m = flat()
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    caplog.clear()  # only the audit's own records, not the fixture setup runs
    points = {"habitat": (20, 20), "observation_primary": (20, 34), "observation_backup": (34, 20)}
    report = audit_site(t, a, m, points, eva_minutes=240, speed_m_min=20, observation_minutes=20)
    assert set(report["itineraries"]) == {"primary_only", "backup_only", "primary_then_backup"}
    chain = report["itineraries"]["primary_then_backup"]
    assert len(chain["lower_bound"]["legs_m"]) == 3 and chain["routed"]["observation_min"] == 40
    assert report["verdict"] == "candidate_requires_inspection"
    assert "safe" not in json.dumps(report).lower().replace("unsafe", "")
    assert len({r.run_id for r in caplog.records if hasattr(r, "event")}) == 1


def test_audit_site_proves_infeasible_by_lower_bound():
    t, a, m = flat()
    report = audit_site(t, a, m, {"habitat": (20, 2), "observation_primary": (20, 38)},
                        eva_minutes=10, speed_m_min=1, observation_minutes=0)
    assert report["verdict"] == "infeasible"
    assert report["itineraries"]["primary_only"]["reason"] == "straight_line_lower_bound"


def test_audit_from_config_needs_no_review_flags(tmp_path):
    """Real-style GeoTIFF + unconfirmed candidates: audit runs; missing scarp data stays unresolved."""
    crs = "+proj=eqc +lat_ts=0 +R=3389500 +units=m +no_defs"
    dtm = tmp_path / "dtm.tif"
    with rasterio.open(dtm, "w", driver="GTiff", width=60, height=60, count=1, dtype="float32", crs=crs,
                       transform=from_origin(0, 60, 1, 1), nodata=-9999) as dataset:
        dataset.write(np.zeros((60, 60), "float32"), 1)
    from pipeline.terrain import read_terrain
    grid = read_terrain(dtm, (0, 0, 60, 60))
    point = lambda r, c: dict(zip(("lon", "lat"), grid.lonlat(r, c)))
    config = {"dtm": str(dtm), "window": [0, 0, 60, 60], "eva_minutes": 240, "speed_m_min": 20,
              "observation_minutes": 20, "points": {"habitat": point(30, 20), "observation_primary": point(30, 40)}}
    report = audit_from_config(config, tmp_path / "audit")
    assert (tmp_path / "audit" / "feasibility_report.json").exists()
    assert report["input_status"] == "unconfirmed_candidates" and report["evidence"] == "nasa_derived"
    # No scarp inputs on NASA-derived terrain: the crop is unresolved, so no route can be claimed.
    assert report["verdict"] == "no_route_found"
    assert report["points"]["habitat"]["uncertainty"]["status"] == "inspection_required"
    with pytest.raises(FileExistsError):
        audit_from_config(config, tmp_path / "audit")


def test_window_latlon_resolves_to_covering_pixel_window(tmp_path, caplog):
    """A lat/lon box (as in data/site/feasibility_audit*.json) replaces a hand-computed pixel window."""
    from pipeline.feasibility import window_from_latlon
    from pipeline.terrain import read_terrain
    crs = "+proj=eqc +lat_ts=0 +R=3389500 +units=m +no_defs"
    dtm = tmp_path / "dtm.tif"
    with rasterio.open(dtm, "w", driver="GTiff", width=60, height=60, count=1, dtype="float32", crs=crs,
                       transform=from_origin(0, 60, 1, 1), nodata=-9999) as dataset:
        dataset.write(np.zeros((60, 60), "float32"), 1)
    grid = read_terrain(dtm, (0, 0, 60, 60))
    (west, north), (east, south) = grid.lonlat(10, 5), grid.lonlat(40, 50)
    window = window_from_latlon(dtm, {"south": south, "west": west, "north": north, "east": east})
    col, row, width, height = window
    assert col <= 5 and row <= 10 and col + width >= 51 and row + height >= 41  # covers both corner cells
    point = lambda r, c: dict(zip(("lon", "lat"), grid.lonlat(r, c)))
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    report = audit_from_config({"dtm": str(dtm), "window": None, "eva_minutes": 240, "speed_m_min": 20,
                                "observation_minutes": 20,
                                "window_latlon": {"south": south, "west": west, "north": north, "east": east},
                                "points": {"habitat": point(20, 15), "observation_primary": point(30, 40)}},
                               tmp_path / "audit")
    assert report["verdict"] == "no_route_found"
    assert events(caplog, "feasibility_window_resolved")[0].fields["window"] == window
    with pytest.raises(ValueError, match="outside the DTM"):
        window_from_latlon(dtm, {"south": 50, "west": 10, "north": 51, "east": 11})
    with pytest.raises(ValueError, match="window or window_latlon"):
        audit_from_config({"dtm": str(dtm), "eva_minutes": 240, "speed_m_min": 20, "observation_minutes": 20,
                           "points": {}}, tmp_path / "audit2")
