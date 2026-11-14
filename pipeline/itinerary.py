"""Mixed drive/walk itinerary evaluation for crew routes that carry `legs` (contract 1.1).

The walking-only budget (`routing.itinerary_budget`) stays unchanged for walking routes. This module
evaluates a route whose legs mix crew-rover driving and walking:

* leg validation: order, contiguity, modes, and recomputed lengths/times on the Mars sphere
  (R = 3,389,500 m) must match what the file claims;
* the round-trip distance rule (`round_trip_limit_m`, strict `<`) applied to the whole itinerary,
  because nobody has yet decided that drive metres are exempt; the walking-only distance is reported
  beside it so the team can make that decision explicitly;
* EVA time with the 30 % reserve (outbound + site work + return <= EVA x 0.7);
* emergency walkback, modeled separately: the crew rover fails at the farthest point, the crew walks
  the whole way home. Fitting inside the EVA but not inside the reserve allowance is reported as
  `walkback_uses_reserve`, never as keeping the reserve;
* backup independence: metres a backup shares with the main route are a common-mode dependency.

Nothing here can set a route to `ok`: passing every budget is geometry and arithmetic, not crew
clearance, so the suggested status is at best `inspection_required`.
"""

import argparse
import json
import logging
import math
from pathlib import Path

from pipeline.logging_config import configure_logging, event, traced
from pipeline.routing import mars_distance
from pipeline.terrain import load_rules, threshold

LEG_MODES = ("drive", "walk")
LENGTH_TOLERANCE_M = 5.0  # plus 1 % of the leg: file values are rounded, recomputation is exact
TIME_TOLERANCE_MIN = 1.5  # file times are rounded to whole minutes
BACKUP_MAX_SHARED = 0.5  # same default as routing.plan_routes


def polyline_m(coords):
    """Length in metres of a [lon, lat] polyline on the Mars mean sphere."""
    return sum(mars_distance(a, b) for a, b in zip(coords, coords[1:]))


def validate_legs(feature, speeds_m_min):
    """Return (legs with recomputed lengths, problems) for a route feature with `legs`.

    speeds_m_min: {"drive": m/min, "walk": m/min} used to check each leg's est_time_min.
    A problem list that is not empty means the route's numbers cannot be trusted.
    """
    coords = feature.get("geometry", {}).get("coordinates") or []
    legs = feature.get("properties", {}).get("legs")
    problems = []
    if not isinstance(legs, list) or not legs:
        return [], ["route has no legs"]
    checked = []
    expected_from = 0
    for i, leg in enumerate(legs):
        start, end, mode = leg.get("from"), leg.get("to"), leg.get("mode")
        if mode not in LEG_MODES:
            problems.append(f"leg {i} mode {mode!r} is not drive/walk")
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end < len(coords)):
            problems.append(f"leg {i} indexes {start}..{end} invalid for {len(coords)} vertices")
            continue
        if start != expected_from:
            problems.append(f"leg {i} starts at vertex {start}, expected {expected_from} (gap or overlap)")
        expected_from = end
        length = polyline_m(coords[start:end + 1])
        claimed = leg.get("length_m")
        if not (isinstance(claimed, (int, float)) and math.isfinite(claimed)):
            problems.append(f"leg {i} length_m is not a finite number")
        elif abs(claimed - length) > LENGTH_TOLERANCE_M + 0.01 * length:
            problems.append(f"leg {i} claims {claimed} m, geometry measures {length:.0f} m")
        speed = speeds_m_min.get(mode)
        claimed_min = leg.get("est_time_min")
        if speed and isinstance(claimed_min, (int, float)) and abs(claimed_min - length / speed) > TIME_TOLERANCE_MIN:
            problems.append(f"leg {i} claims {claimed_min} min, {length:.0f} m at {speed} m/min is {length / speed:.1f} min")
        checked.append({"mode": mode, "from": start, "to": end, "length_m": length})
    if coords and expected_from != len(coords) - 1:
        problems.append(f"legs end at vertex {expected_from}, route has {len(coords)} vertices")
    return checked, problems


def _segments(coords, digits=6):
    """Undirected rounded segments of a polyline, with their lengths, for shared-corridor matching."""
    out = {}
    for a, b in zip(coords, coords[1:]):
        key = tuple(sorted((tuple(round(v, digits) for v in a), tuple(round(v, digits) for v in b))))
        out[key] = mars_distance(a, b)
    return out


def shared_length_m(first, second):
    """Metres of identical (undirected) segments two route geometries share."""
    a, b = _segments(first), _segments(second)
    return sum(length for key, length in a.items() if key in b)


@traced("mixed_itinerary")
def evaluate_mixed(feature, rules, eva_minutes, speeds_m_min, site_minutes=0):
    """Budget one drive/walk crew route out and back over the same legs.

    rules: hazard_rules.json; eva_minutes: total EVA; speeds_m_min: {"drive", "walk"} in m/min;
    site_minutes: work at the destination. The geometry may run habitat -> site or site -> habitat
    (#15's backup is drawn scarp-first); the farthest point is the site either way.
    Returns a report dict with every number, the reasons for rejection, and a suggested status.
    """
    props = feature["properties"]
    for mode in LEG_MODES:
        if not (math.isfinite(speeds_m_min.get(mode, float("nan"))) and speeds_m_min[mode] > 0):
            raise ValueError(f"{mode} speed must be positive and finite")
    if not (math.isfinite(eva_minutes) and eva_minutes > 0 and math.isfinite(site_minutes) and site_minutes >= 0):
        raise ValueError("EVA and site-work minutes must be finite (EVA positive)")
    legs, problems = validate_legs(feature, speeds_m_min)
    reserve = threshold(rules, "eva_reserve_fraction")
    limit = threshold(rules, "round_trip_limit_m")
    one_way = sum(leg["length_m"] for leg in legs)
    by_mode = {mode: sum(leg["length_m"] for leg in legs if leg["mode"] == mode) for mode in LEG_MODES}
    travel_one_way = sum(leg["length_m"] / speeds_m_min[leg["mode"]] for leg in legs)
    available = eva_minutes * (1 - reserve)
    total = 2 * travel_one_way + site_minutes
    round_trip = 2 * one_way
    reasons = []
    if problems:
        reasons.append("leg_validation_failed")
    if not round_trip < limit:  # the rule's comparison is strict "<": exactly the limit fails
        reasons.append("round_trip_distance_limit")
    if one_way > threshold(rules, "hard_excursion_cap_m"):
        reasons.append("hard_excursion_cap")
    if total > available + 1e-9:
        reasons.append("eva_time_limit")
    # Emergency walkback: rover fails at the farthest point after outbound travel and site work.
    outbound_elapsed = travel_one_way + site_minutes
    walkback = one_way / speeds_m_min["walk"]
    walkback_total = outbound_elapsed + walkback
    if walkback_total <= available + 1e-9:
        walkback_state = "walkback_within_reserve"
    elif walkback_total <= eva_minutes + 1e-9:
        walkback_state = "walkback_uses_reserve"
    else:
        walkback_state = "walkback_exceeds_eva"
        reasons.append("walkback_exceeds_eva")
    report = {
        "route_id": props.get("id"), "accepted_budget": not reasons, "reasons": reasons, "leg_problems": problems,
        "one_way_m": round(one_way, 1), "round_trip_m": round(round_trip, 1),
        "drive_one_way_m": round(by_mode["drive"], 1), "walk_one_way_m": round(by_mode["walk"], 1),
        "walk_round_trip_m": round(2 * by_mode["walk"], 1), "round_trip_limit_m": limit,
        "travel_min": round(2 * travel_one_way, 1), "site_min": site_minutes, "total_min": round(total, 1),
        "available_min": round(available, 1), "eva_min": eva_minutes, "reserve_fraction": reserve,
        "walkback_min": round(walkback, 1), "walkback_total_min": round(walkback_total, 1),
        "walkback_state": walkback_state, "speeds_m_min": speeds_m_min,
        "claimed_round_trip_m": props.get("stats", {}).get("round_trip_m"),
        "suggested_status": "inspection_required",  # never "ok": arithmetic is not crew clearance
        "evidence": "inferred",
    }
    level = logging.INFO if not reasons else logging.WARNING
    event("mixed_itinerary_evaluated", level, **report)
    return report


@traced("backup_independence")
def backup_independence(main, backup, max_shared=BACKUP_MAX_SHARED):
    """Report how much of `backup` repeats `main`; above max_shared it is not an independent backup."""
    shared = shared_length_m(main["geometry"]["coordinates"], backup["geometry"]["coordinates"])
    length = polyline_m(backup["geometry"]["coordinates"])
    fraction = shared / length if length else 1.0
    report = {"main_id": main["properties"]["id"], "backup_id": backup["properties"]["id"],
              "shared_m": round(shared, 1), "backup_m": round(length, 1), "shared_fraction": round(fraction, 3),
              "max_shared_fraction": max_shared, "independent": fraction <= max_shared,
              "common_mode": "shared drive corridor" if shared > 0 else None}
    event("backup_independence_evaluated", logging.INFO if report["independent"] else logging.WARNING, **report)
    return report


def evaluate_file(routes_path, rules, eva_minutes=240, speeds_m_min=None, site_minutes=20):
    """Evaluate every crew main/backup route with legs in a routes.geojson; returns a list of reports."""
    speeds_m_min = speeds_m_min or {"drive": 83.3, "walk": 20.0}
    features = json.loads(Path(routes_path).read_text())["features"]
    crew = [f for f in features if f["properties"].get("agent") == "crew" and f["properties"].get("legs")]
    reports = []
    for f in crew:
        reports.append(evaluate_mixed(f, rules, eva_minutes, speeds_m_min, site_minutes))
    for version in ("before", "after"):
        main = next((f for f in crew if f["properties"]["kind"] == "main" and f["properties"].get("version") == version), None)
        backup = next((f for f in crew if f["properties"]["kind"] == "backup" and f["properties"].get("version") == version), None)
        if main and backup:
            reports.append(backup_independence(main, backup))
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--routes", type=Path, default=Path("public/data/routes.geojson"))
    parser.add_argument("--eva-minutes", type=float, default=240)
    parser.add_argument("--drive-speed", type=float, default=83.3, help="crew rover, m/min (5 km/h)")
    parser.add_argument("--walk-speed", type=float, default=20.0, help="suited walking, m/min")
    parser.add_argument("--site-minutes", type=float, default=20)
    arguments = parser.parse_args()
    configure_logging()
    output = evaluate_file(arguments.routes, load_rules(), arguments.eva_minutes,
                           {"drive": arguments.drive_speed, "walk": arguments.walk_speed}, arguments.site_minutes)
    print(json.dumps(output, indent=2))
