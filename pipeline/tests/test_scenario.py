import numpy as np
import pytest

from pipeline.terrain import analyze
from pipeline.hazards import hazard_masks
from pipeline.scenario import rover_decision, discovery_scenario, coverage
from pipeline.tests.test_terrain import terrain
from pipeline.validate_contract import validate_collection


@pytest.mark.parametrize("slip,state", [(35, "continue"), (35.00001, "request_input"), (38, "request_input")])
def test_slip_boundary(slip, state):
    assert rover_decision(slip) == state


def test_rover_states():
    assert rover_decision(0, blocked=True, alternative=True) == "reroute"
    assert rover_decision(0, blocked=True) == "stop"
    assert rover_decision(38, critical=True) == "stop"
    assert rover_decision(0, communication=False) == "stop"


def test_discovery_changes_route_and_preserves_evidence():
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    output = discovery_scenario(t, a, masks, (5, 0), (5, 10), (5, 5), sensor_radius_m=1)
    routes, hazard, discovery, cov = output
    assert output == discovery_scenario(t, a, masks, (5, 0), (5, 10), (5, 5), sensor_radius_m=1)
    before, after = routes["features"][0], routes["features"][2]
    assert before["geometry"] != after["geometry"]
    assert t.lonlat(5, 5) not in after["geometry"]["coordinates"]
    assert hazard["properties"]["evidence"] == discovery["evidence"] == "simulated"
    assert discovery["decision"] == "request_input" and discovery["chosen_option"] == ""
    assert not masks["crew_exclude"][5, 5]
    validate_collection(routes, "routes.geojson")
    validate_collection(cov, "coverage.geojson")


def test_no_path_means_no_scouted_coverage():
    t = terrain()
    result = coverage(t, analyze(t), [], 5)
    assert all(f["properties"]["state"] != "rover_checked" for f in result["features"])


def test_discovery_can_make_route_unavailable():
    t = terrain()
    a = analyze(t)
    masks = hazard_masks(t, a)
    masks["crew_exclude"][:] = True
    masks["crew_exclude"][5, :] = False
    routes, _, discovery, _ = discovery_scenario(t, a, masks, (5, 0), (5, 10), (5, 5), sensor_radius_m=1, approved=True)
    assert routes["features"][2]["properties"]["status"] == "no_viable_route"
    assert routes["features"][2]["geometry"]["coordinates"] == []
    assert discovery["chosen_option"] == ""
