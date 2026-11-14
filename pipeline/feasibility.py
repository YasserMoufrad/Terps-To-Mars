"""Site feasibility audit for unconfirmed candidate points; reports infeasibility, never clearance.

Unlike the full mission export, this needs no review flags and no simulated rover discovery,
so a "no viable route" finding is a result, not a software failure.
"""

import argparse
import json
import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as project

from pipeline.export import write_json
from pipeline.hazards import hazard_masks, uncertainty_area_check
from pipeline.logging_config import configure_logging, event, fingerprint, operation, traced
from pipeline.routing import (cost_grid, itinerary_budget, route_stats, shortest_path, straight_line_m,
                              unit_costs, unresolved_roughness)
from pipeline.terrain import MARS_GEOGRAPHIC, analyze, load_rules, read_terrain, threshold

ITINERARIES = {
    "primary_only": ("habitat", "observation_primary", "habitat"),
    "backup_only": ("habitat", "observation_backup", "habitat"),
    "primary_then_backup": ("habitat", "observation_primary", "observation_backup", "habitat"),
}


def _leg(terrain, analysis, costs, spacing, start, end, speed_m_min):
    """Route one leg; returns least-cost and shortest-distance lengths (None when disconnected)."""
    cheapest = shortest_path(costs, start, end, spacing)
    shortest = shortest_path(unit_costs(costs), start, end, spacing) if cheapest else []
    length = lambda path: route_stats(terrain, analysis, path, speed_m_min=speed_m_min)["length_m"] if path else None
    rough = unresolved_roughness(analysis)
    return {"least_cost_m": length(cheapest), "shortest_m": length(shortest),
            "unresolved_roughness_cells": sum(bool(rough[c]) for c in shortest) if shortest else 0}


@traced("feasibility_audit")
def audit_site(terrain, analysis, masks, points, eva_minutes, speed_m_min, observation_minutes,
               rules=None, radius_m=None):
    """Audit candidate points against hazards, distance lower bounds and routed budgets.

    points: {"habitat": (row, col), "observation_primary": (row, col), optional "observation_backup"}.
    observation_minutes: site work per observation stop (minutes); a two-stop itinerary budgets it twice.
    radius_m: position uncertainty checked around every point (default rule, 15 m).
    Verdicts: "infeasible" (proven by the great-circle bound or by the shortest route over the same
    exclusions), "no_route_found" (hard exclusions or unresolved terrain disconnect the points), or
    "candidate_requires_inspection". Unscouted terrain means no verdict is ever crew clearance.
    """
    rules = rules or load_rules()
    if "habitat" not in points or "observation_primary" not in points:
        raise ValueError("Audit needs habitat and observation_primary candidates")
    points = {name: tuple(int(v) for v in cell) for name, cell in points.items()}
    checks = {name: uncertainty_area_check(terrain, analysis, masks, cell, radius_m, rules=rules, point_id=name)
              for name, cell in points.items()}
    costs = cost_grid(terrain, analysis, masks, rules=rules)
    spacing = (terrain.resolution, terrain.column_spacing)
    legs = {}
    itineraries = {}
    for name, stops in ITINERARIES.items():
        if any(stop not in points for stop in stops):
            continue
        pairs = list(zip(stops, stops[1:]))
        stops_work = observation_minutes * sum(stop != "habitat" for stop in stops)
        bound_legs = [straight_line_m(terrain, points[a], points[b]) for a, b in pairs]
        excursion = max(straight_line_m(terrain, points["habitat"], points[s]) for s in stops if s != "habitat")
        bound = itinerary_budget(bound_legs, rules, eva_minutes, speed_m_min, stops_work, excursion,
                                 label=f"{name}_lower_bound")
        result = {"stops": list(stops), "lower_bound": bound, "routed": None}
        if not bound["accepted"]:
            result["verdict"], result["reason"] = "infeasible", "straight_line_lower_bound"
        else:
            for a, b in pairs:
                key = f"{a}->{b}"
                if key not in legs:
                    with operation("feasibility_leg_search", leg=key, evidence=terrain.evidence):
                        legs[key] = _leg(terrain, analysis, costs, spacing, points[a], points[b], speed_m_min)
            routed = [legs[f"{a}->{b}"]["shortest_m"] for a, b in pairs]
            if any(length is None for length in routed):
                result["verdict"] = "no_route_found"
                result["reason"] = ("unresolved_terrain_blocks_route" if masks["inspection_required"].any()
                                    or (~analysis["valid"]).any() else "hard_exclusions_disconnect_points")
            else:
                routed_budget = itinerary_budget(routed, rules, eva_minutes, speed_m_min, stops_work, excursion,
                                                 label=f"{name}_shortest_routed")
                result["routed"] = routed_budget
                if routed_budget["accepted"]:
                    result["verdict"], result["reason"] = "candidate_requires_inspection", "unscouted_terrain"
                else:
                    result["verdict"], result["reason"] = "infeasible", "shortest_route_exceeds_budget"
        itineraries[name] = result
        event("itinerary_audited", logging.INFO if result["verdict"] == "candidate_requires_inspection" else logging.WARNING,
              itinerary=name, verdict=result["verdict"], reason=result["reason"],
              lower_bound_m=bound["distance_m"], evidence=terrain.evidence)
    primary = itineraries["primary_only"]
    if checks["observation_primary"]["status"] == "excluded_terrain_within_uncertainty" or checks["habitat"]["status"] == "excluded_terrain_within_uncertainty":
        verdict = "infeasible"
    else:
        verdict = primary["verdict"]
    report = {"schema_version": "1.0", "report_type": "site_feasibility_audit", "evidence": terrain.evidence,
              "dataset_id": terrain.source, "input_status": "unconfirmed_candidates",
              "points": {name: {"cell": list(cell), "lonlat": terrain.lonlat(*cell), "uncertainty": checks[name]}
                         for name, cell in points.items()},
              "legs": legs, "itineraries": itineraries, "verdict": verdict,
              "inputs": {"eva_minutes": eva_minutes, "speed_m_min": speed_m_min,
                         "observation_minutes_per_stop": observation_minutes,
                         "position_uncertainty_m": checks["habitat"]["radius_m"],
                         "round_trip_limit_m": threshold(rules, "round_trip_limit_m"),
                         "eva_reserve_fraction": threshold(rules, "eva_reserve_fraction")},
              "crew_clearance": "not_established",
              "limitations": ("Candidate points are unconfirmed; all terrain is treated as unscouted; the ~1 m DTM "
                              "cannot resolve sub-metre hazards; routed lengths use a four-neighbour grid.")}
    event("feasibility_verdict", logging.INFO if verdict == "candidate_requires_inspection" else logging.WARNING,
          verdict=verdict, evidence=terrain.evidence, crew_clearance="not_established",
          point_status={name: check["status"] for name, check in checks.items()})
    return report


def _cell(terrain, point, name):
    """Convert a signed {lat, lon} candidate to an in-crop (row, col); refuse points outside the crop."""
    lat, lon = float(point["lat"]), float(point["lon"])
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"{name} needs finite signed lat/lon")
    x, y = project(MARS_GEOGRAPHIC, terrain.crs, [lon], [lat])
    row, col = rasterio.transform.rowcol(terrain.transform, x[0], y[0])
    if not (0 <= row < terrain.elevation.shape[0] and 0 <= col < terrain.elevation.shape[1]):
        raise ValueError(f"{name} lies outside the DTM crop")
    return int(row), int(col)


@traced("feasibility_audit_run")
def audit_from_config(config, output):
    """Read the DTM crop and candidate points from config, audit them and write feasibility_report.json.

    config keys: dtm, window [col, row, width, height], points {habitat, observation_primary,
    optional observation_backup} as {lat, lon}, eva_minutes, speed_m_min, observation_minutes.
    Optional: artifact_mask, edge_distance, foot_distance, scarp_risk (.npy), scarp_height_m, apron_m.
    No review flags are required; missing scarp measurements keep the crop unresolved (conservative).
    """
    output = Path(output)
    public_data = (Path(__file__).resolve().parents[1] / "public/data").resolve()
    if output.resolve() == public_data or public_data in output.resolve().parents:
        raise ValueError("Write audits to an ignored directory, not public/data")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Output directory must be empty")
    for key in ("dtm", "window", "points", "eva_minutes", "speed_m_min", "observation_minutes"):
        if key not in config:
            raise ValueError(f"Audit config requires {key}")
    event("feasibility_inputs", config_fingerprint=fingerprint(config), source_dtm=Path(config["dtm"]).name,
          input_status="unconfirmed_candidates", points=sorted(config["points"]))
    artifact = np.load(config["artifact_mask"], allow_pickle=False) if config.get("artifact_mask") else None
    terrain = read_terrain(config["dtm"], tuple(config["window"]), artifact=artifact)
    analysis = analyze(terrain)
    load = lambda key: np.load(config[key], allow_pickle=False) if config.get(key) else None
    masks = hazard_masks(terrain, analysis, edge_distance=load("edge_distance"), foot_distance=load("foot_distance"),
                         scarp_height=config.get("scarp_height_m"), apron_m=config.get("apron_m"),
                         scarp_risk=load("scarp_risk"))
    points = {name: _cell(terrain, point, name) for name, point in config["points"].items()}
    report = audit_site(terrain, analysis, masks, points, config["eva_minutes"], config["speed_m_min"],
                        config["observation_minutes"], radius_m=config.get("position_uncertainty_m"))
    report["points_input"] = config["points"]
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "feasibility_report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    configure_logging()
    result = audit_from_config(json.loads(arguments.config.read_text()), arguments.output)
    print(json.dumps({"verdict": result["verdict"],
                      "itineraries": {k: v["verdict"] for k, v in result["itineraries"].items()}}, indent=2))
