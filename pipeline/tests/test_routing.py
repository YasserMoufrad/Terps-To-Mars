import math
import numpy as np
import pytest

from pipeline.terrain import analyze, load_rules
from pipeline.hazards import hazard_masks
from pipeline.routing import shortest_path, plan_routes, cost_grid, mars_distance, route_stats, within_budget
from pipeline.tests.test_terrain import terrain
from pipeline.validate_contract import validate_collection


def test_mars_distance():
    assert mars_distance([0, 0], [1, 0]) == pytest.approx(3_389_500 * math.pi / 180)
    assert mars_distance([179.9, 0], [-179.9, 0]) < 12000


def test_flat_route_stats_and_determinism():
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
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    masks[hazard][:, 5] = True
    output, path, backup = plan_routes(t, a, masks, (5, 0), (5, 10))
    assert path == backup == []
    assert output["features"][0]["properties"]["status"] == "no_viable_route"


def test_actual_no_data_and_artifact_masks():
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
    assert shortest_path(np.array([[1, np.inf], [np.inf, 1]]), (0, 0), (1, 1)) == []


def test_budget_boundaries():
    rules = load_rules()
    stats = {"round_trip_m": 4999, "length_m": 2499.5, "est_time_min": 70}
    assert within_budget(stats, rules, 100, 20)
    stats["round_trip_m"] = 5000
    assert not within_budget(stats, rules, 100, 20)
    stats["round_trip_m"] = 4999
    stats["est_time_min"] = 70.0001
    assert not within_budget(stats, rules, 100, 20)


def test_real_slope_wall_blocks_route():
    z = np.zeros((11, 11))
    z[:, 5:] = 100
    t = terrain(z)
    a = analyze(t)
    result, path, _ = plan_routes(t, a, hazard_masks(t, a), (5, 0), (5, 10))
    assert not path
    assert result["features"][0]["properties"]["status"] == "no_viable_route"


def test_invalid_endpoint_and_inspection_status():
    with pytest.raises(ValueError, match="outside"):
        shortest_path(np.ones((3, 3)), (-1, 0), (2, 2))
    z = np.zeros((11, 11))
    z[5, 0] = np.nan
    t = terrain(z)
    a = analyze(t)
    result, _, _ = plan_routes(t, a, hazard_masks(t, a), (5, 0), (5, 10))
    assert result["features"][0]["properties"]["status"] == "inspection_required"
