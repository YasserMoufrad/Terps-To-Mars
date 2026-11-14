import math
import numpy as np
import pytest
from skimage.graph import route_through_array

from pipeline.terrain import analyze, load_rules
from pipeline.hazards import hazard_masks
from pipeline.routing import shortest_path, plan_routes, cost_grid, mars_distance, route_stats, within_budget, mission_budget
from pipeline.logging_config import LOGGER
from pipeline.tests.test_terrain import terrain
from pipeline.validate_contract import validate_collection


def test_mars_distance():
    """Compare one degree at the equator against the Mars radius, including longitude wrap."""
    assert mars_distance([0, 0], [1, 0]) == pytest.approx(3_389_500 * math.pi / 180)
    assert mars_distance([179.9, 0], [-179.9, 0]) < 12000


def test_flat_route_stats_and_determinism():
    """Check path determinism and recompute exported travel-only statistics from geometry."""
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    first, path, _ = plan_routes(t, a, masks, (5, 0), (5, 10), corridor_m=0)
    second, _, _ = plan_routes(t, a, masks, (5, 0), (5, 10), corridor_m=0)
    assert first == second
    validate_collection(first, "routes.geojson")
    coords = first["features"][0]["geometry"]["coordinates"]
    length = sum(mars_distance(x, y) for x, y in zip(coords, coords[1:]))
    stats = route_stats(t, a, path)
    assert stats["length_m"] == pytest.approx(length)
    assert stats["round_trip_m"] == pytest.approx(2 * length)
    assert stats["est_time_min"] == pytest.approx(2 * length / 20)


@pytest.mark.parametrize("hazard", ["crew_exclude", "no_data", "artifact", "edge", "rockfall"])
def test_blocked_corridor(hazard):
    """Verify the named hazard wall cannot be crossed by primary or backup routes."""
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    masks[hazard][:, 5] = True
    output, path, backup = plan_routes(t, a, masks, (5, 0), (5, 10))
    assert path == backup == []
    assert output["features"][0]["properties"]["status"] == "no_viable_route"


def test_actual_no_data_and_artifact_masks():
    """Keep real NaN and artifact cells outside every returned route."""
    z = np.zeros((11, 11))
    z[4, 4] = np.nan
    artifact = np.zeros(z.shape, bool)
    artifact[6, 6] = True
    t = terrain(z, artifact=artifact)
    a = analyze(t)
    costs = cost_grid(t, a, hazard_masks(t, a))
    path = shortest_path(costs, (5, 0), (5, 10))
    assert path and all(np.isfinite(costs[cell]) for cell in path)
    assert (4, 4) not in path and (6, 6) not in path


def test_no_independent_backup_and_alternative():
    """Distinguish a single corridor from a genuinely different backup path."""
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    masks["crew_exclude"][:] = True
    masks["crew_exclude"][5, :] = False
    output, path, backup = plan_routes(t, a, masks, (5, 0), (5, 10), corridor_m=0)
    assert path and not backup
    assert output["features"][1]["properties"]["status"] == "backup_unavailable"
    masks["crew_exclude"][:] = False
    output, path, backup = plan_routes(t, a, masks, (5, 0), (5, 10), corridor_m=0)
    assert path and backup and path != backup


def test_diagonal_corner_cannot_cross():
    """Ensure diagonal contact cannot connect two hard-excluded corridors."""
    assert shortest_path(np.array([[1, np.inf], [np.inf, 1]]), (0, 0), (1, 1)) == []


def test_dijkstra_matches_reference_grid_search():
    """Compare the deterministic path cost with scikit-image's four-neighbour reference search."""
    costs = np.array([[1, 5, 1, 1], [1, np.inf, 9, 1], [1, 1, 1, 1]], dtype=float)
    path = shortest_path(costs, (0, 0), (0, 3))
    _, expected_cost = route_through_array(costs, (0, 0), (0, 3), fully_connected=False, geometric=True)
    actual_cost = sum((costs[a] + costs[b]) / 2 for a, b in zip(path, path[1:]))
    assert actual_cost == pytest.approx(expected_cost)


def test_budget_boundaries():
    """Check exact 30% reserve and strict 5 km distance boundaries using coherent stats."""
    rules = load_rules()
    stats = {"round_trip_m": 1400, "length_m": 700, "est_time_min": 70}
    assert within_budget(stats, rules, 100, 20)
    stats["length_m"] = 2500
    assert not within_budget(stats, rules, 100, 20)
    stats["length_m"] = 700.001
    assert not within_budget(stats, rules, 100, 20)


def test_real_slope_wall_blocks_route():
    """A sharp elevation wall must become a hard slope exclusion through analysis."""
    z = np.zeros((11, 11))
    z[:, 5:] = 100
    t = terrain(z)
    a = analyze(t)
    result, path, _ = plan_routes(t, a, hazard_masks(t, a), (5, 0), (5, 10))
    assert not path
    assert result["features"][0]["properties"]["status"] == "no_viable_route"


def test_invalid_endpoint_and_inspection_status():
    """Reject out-of-grid cells and mark a no-data endpoint for inspection."""
    with pytest.raises(ValueError, match="outside"):
        shortest_path(np.ones((3, 3)), (-1, 0), (2, 2))
    z = np.zeros((11, 11))
    z[5, 0] = np.nan
    t = terrain(z)
    a = analyze(t)
    result, _, _ = plan_routes(t, a, hazard_masks(t, a), (5, 0), (5, 10))
    assert result["features"][0]["properties"]["status"] == "inspection_required"


def test_observation_work_and_actual_backup_return():
    """Budget 400 m outbound plus 900 m return and site work, not duplicate-path travel."""
    rules = load_rules()
    outbound, returning = {"length_m": 400}, {"length_m": 900}
    combined = mission_budget(outbound, returning, rules, 100 / .7, 20, 35)
    assert combined["accepted"] and combined["total_min"] == pytest.approx(100)
    assert not mission_budget(outbound, returning, rules, 100 / .7, 20, 35.001)["accepted"]
    assert mission_budget(outbound, returning, rules, 100 / .7, 40, 35)["travel_min"] == pytest.approx(32.5)
    assert not mission_budget(returning, returning, rules, 100 / .7, 20, 35)["accepted"]


@pytest.mark.parametrize("eva,speed,work", [(0,20,0), (-1,20,0), (100,0,0), (100,-1,0), (100,20,-1), (float('nan'),20,0)])
def test_invalid_mission_durations(eva, speed, work):
    """Invalid eva/speed/work inputs must fail even before route search finds a path."""
    with pytest.raises(ValueError):
        mission_budget({"length_m": 10}, {"length_m": 10}, load_rules(), eva, speed, work)


def test_unresolved_scarp_area_cannot_be_routed(caplog):
    """Unmeasured risk cells exclude a wall and emit an inspection-required rejection."""
    t = terrain()
    a = analyze(t)
    risk = np.zeros((11, 11), bool)
    risk[:, 5] = True
    masks = hazard_masks(t, a, scarp_risk=risk)
    output, path, _ = plan_routes(t, a, masks, (5, 0), (5, 10))
    assert not path and output["features"][0]["properties"]["status"] == "inspection_required"
    assert any(getattr(r, "event", None) == "route_rejected" and r.fields["reason"] == "unresolved_scarp_or_invalid_terrain" for r in caplog.records)


def test_route_decision_tracing_and_unscouted_interpretation(caplog):
    """Observe route stats and budget/backup decisions without treating unscouted cells as cleared."""
    t = terrain()
    a = analyze(t)
    caplog.clear()
    output, path, backup = plan_routes(t, a, hazard_masks(t, a), (5, 0), (5, 10), corridor_m=0)
    assert path and output["features"][0]["properties"]["kind"] == "orbital_guess"
    assert output["features"][0]["properties"]["status"] == "inspection_required"
    entries = [r for r in caplog.records if r.name == LOGGER.name and r.stage != "hazard_generation" and r.stage != "hazard_rules"]
    assert any(r.event == "route_result" and r.fields["statistics"]["length_m"] > 0 for r in entries)
    assert any(r.event == "backup_evaluated" and "combined_budget" in r.fields for r in entries)
    assert any(r.event == "unscouted_corridor" for r in entries)


def test_hard_exclusion_and_backup_failure_are_logged(caplog):
    """Capture both missing-route and missing-backup outcomes from an excluded corridor."""
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    masks["crew_exclude"][:, 5] = True
    plan_routes(t, a, masks, (5, 0), (5, 10))
    events = {getattr(r, "event", None) for r in caplog.records}
    assert {"route_rejected", "route_search_unavailable", "backup_unavailable"} <= events


def test_combined_return_budget_can_reject_backup_only():
    """A primary duplicate return fits, but a longer backup plus site work may not."""
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    _, path, backup = plan_routes(t, a, masks, (5, 0), (5, 10), corridor_m=0,
                                  eva_minutes=5/.7, observation_minutes=4, speed_m_min=20)
    assert path and not backup
    _, path, backup = plan_routes(t, a, masks, (5, 0), (5, 10), corridor_m=0,
                                  eva_minutes=5/.7, observation_minutes=4, speed_m_min=40)
    assert path and backup


def test_rover_exclusions_always_override_costs():
    """A rover slope-limit wall cannot be crossed even though crew masks differ."""
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    masks["rover_exclude"][:, 5] = True
    assert not shortest_path(cost_grid(t, a, masks, agent="rover"), (5, 0), (5, 10))


@pytest.mark.parametrize("agent", ["crew", "rover"])
def test_unresolved_hazards_block_both_agents(agent):
    """The named agent must not cross scarp-risk cells with missing measurements."""
    t = terrain()
    a = analyze(t)
    risk = np.zeros((11, 11), bool)
    risk[:, 5] = True
    masks = hazard_masks(t, a, scarp_risk=risk)
    costs = cost_grid(t, a, masks, agent=agent)
    assert np.isinf(costs[:, 5]).all()
    assert not shortest_path(costs, (5, 0), (5, 10))
