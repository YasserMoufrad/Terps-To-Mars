"""Mixed drive/walk itinerary budgets: distance rule boundary, time + reserve, walkback, legs, backup sharing."""

import copy
import logging
import math

import pytest

from pipeline.itinerary import backup_independence, evaluate_mixed, polyline_m, validate_legs
from pipeline.routing import itinerary_budget
from pipeline.terrain import MARS_RADIUS_M, load_rules

SPEEDS = {"drive": 83.3, "walk": 20.0}
LAT = 54.13
METRES_PER_DEG_LAT = math.radians(1) * MARS_RADIUS_M


def north_line(lengths_m, lon=-147.903):
    """Straight northward [lon, lat] polyline whose consecutive segments have the given lengths (Mars sphere)."""
    coords, lat = [[lon, LAT]], LAT
    for length in lengths_m:
        lat += length / METRES_PER_DEG_LAT
        coords.append([lon, lat])
    return coords


def route(drive_m, walk_m, route_id="rt-test", kind="main", **leg_overrides):
    """Crew route: one drive leg (vertices 0-1) then one walk leg (1-2), with exact claimed lengths and times."""
    legs = [{"mode": "drive", "from": 0, "to": 1, "length_m": drive_m, "est_time_min": drive_m / SPEEDS["drive"]},
            {"mode": "walk", "from": 1, "to": 2, "length_m": walk_m, "est_time_min": walk_m / SPEEDS["walk"]}]
    legs[0].update(leg_overrides)
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": north_line([drive_m, walk_m])},
            "properties": {"id": route_id, "agent": "crew", "kind": kind, "version": "after", "legs": legs,
                           "stats": {"round_trip_m": round(2 * (drive_m + walk_m))}}}


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def test_geometry_is_measured_on_the_mars_sphere():
    assert polyline_m(north_line([1000.0, 500.0])) == pytest.approx(1500.0, abs=0.01)


def test_round_trip_limit_is_strict_at_exactly_5000_m(rules):
    # Geometry is recomputed in floating point, so the boundary is pinned to within 2 mm either side.
    under = evaluate_mixed(route(1999.999, 500.0), rules, 240, SPEEDS, 20)
    at_limit = evaluate_mixed(route(2000.001, 500.0), rules, 240, SPEEDS, 20)
    assert "round_trip_distance_limit" not in under["reasons"]
    assert at_limit["round_trip_m"] == pytest.approx(5000, abs=0.1)
    assert "round_trip_distance_limit" in at_limit["reasons"]  # rule comparison is "<": 5,000 m itself fails


def test_pr15_main_v2_shape_is_rejected_at_5335_m_not_relabelled(rules, caplog):
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    report = evaluate_mixed(route(1986.0, 681.0, "rt-crew-main-v2"), rules, 240, SPEEDS, 20)
    assert report["round_trip_m"] == pytest.approx(5334, abs=1)
    assert report["reasons"] == ["round_trip_distance_limit"]
    assert report["suggested_status"] == "inspection_required"
    assert report["walk_round_trip_m"] == pytest.approx(1362, abs=1)  # reported for the team's decision
    logged = [r for r in caplog.records if getattr(r, "event", "") == "mixed_itinerary_evaluated"][0]
    assert logged.levelno == logging.WARNING and logged.fields["evidence"] == "inferred"


def test_time_and_distance_are_both_checked(rules):
    # Short distance but slow: 2.4 km walking-only takes 240 min > 168 available.
    slow = evaluate_mixed(route(1.0, 1200.0), rules, 240, {"drive": 83.3, "walk": 10.0}, 0)
    assert "eva_time_limit" in slow["reasons"]
    assert "round_trip_distance_limit" not in slow["reasons"]


@pytest.mark.parametrize("site, state", [(40, "walkback_within_reserve"), (100, "walkback_uses_reserve"), (160, "walkback_exceeds_eva")])
def test_emergency_walkback_states(rules, site, state):
    # 1,000 m drive + 300 m walk: outbound 12 + 15 = 27 min, walkback 65 min; reserve allowance 168, EVA 240.
    report = evaluate_mixed(route(1000.0, 300.0), rules, 240, SPEEDS, site)
    assert report["walkback_state"] == state
    if state == "walkback_uses_reserve":
        assert "walkback_exceeds_eva" not in report["reasons"]  # fits the EVA, but is not described as keeping reserve
    if state == "walkback_exceeds_eva":
        assert "walkback_exceeds_eva" in report["reasons"]


def test_never_suggests_ok_even_when_every_budget_passes(rules):
    report = evaluate_mixed(route(800.0, 200.0), rules, 240, SPEEDS, 20)
    assert report["accepted_budget"] and report["suggested_status"] == "inspection_required"


@pytest.mark.parametrize("change, message", [
    ({"length_m": 1500.0}, "geometry measures"),
    ({"est_time_min": 60}, "min"),
    ({"mode": "fly"}, "mode"),
    ({"to": 2}, "starts at vertex"),
    ({"from": 1, "to": 1}, "invalid"),
])
def test_malformed_legs_are_reported(change, message):
    _, problems = validate_legs(route(1000.0, 300.0, **change), SPEEDS)
    assert any(message in p for p in problems), problems


def test_malformed_legs_block_budget_acceptance(rules):
    report = evaluate_mixed(route(1000.0, 300.0, length_m=10.0), rules, 240, SPEEDS, 0)
    assert "leg_validation_failed" in report["reasons"] and not report["accepted_budget"]


def test_missing_legs_and_bad_inputs(rules):
    feature = route(1000.0, 300.0)
    feature["properties"]["legs"] = []
    assert validate_legs(feature, SPEEDS)[1] == ["route has no legs"]
    with pytest.raises(ValueError):
        evaluate_mixed(route(1000.0, 300.0), rules, 240, {"drive": 0, "walk": 20}, 0)
    with pytest.raises(ValueError):
        evaluate_mixed(route(1000.0, 300.0), rules, float("nan"), SPEEDS, 0)


def test_shared_drive_corridor_makes_backup_dependent(caplog):
    caplog.set_level(logging.INFO, logger="terps.pipeline")
    main = route(1986.0, 681.0, "main")
    backup = copy.deepcopy(main)
    backup["properties"]["id"] = "backup"
    backup["geometry"]["coordinates"] = main["geometry"]["coordinates"][:2] + [[-147.8959, LAT + 2809 / METRES_PER_DEG_LAT]]
    report = backup_independence(main, backup)
    assert report["shared_m"] == pytest.approx(1986, abs=1) and not report["independent"]
    assert report["common_mode"] == "shared drive corridor"
    reversed_backup = copy.deepcopy(backup)
    reversed_backup["geometry"]["coordinates"].reverse()  # #15 draws its backup scarp-first
    assert backup_independence(main, reversed_backup)["shared_m"] == pytest.approx(1986, abs=1)


def test_walking_only_budget_is_unchanged(rules):
    """Backward compatibility: walking routes still use routing.itinerary_budget as before."""
    result = itinerary_budget([1500, 1500], rules, 240, 20, 0)  # 150 min of 168
    assert result["accepted"] is True and result["available_min"] == pytest.approx(168)
    assert itinerary_budget([2500, 2500], rules, 240, 20)["reasons"][0] == "round_trip_distance_limit"
