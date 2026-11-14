"""Deterministic simulated reconnaissance; human decisions stay explicit."""

import math
import numpy as np
from scipy.ndimage import distance_transform_edt

from pipeline.hazards import collection, mask_features
from pipeline.routing import cost_grid, plan_routes, route_feature
from pipeline.terrain import load_rules, threshold


def rover_decision(wheel_slip_pct, *, critical=False, blocked=False,
                   alternative=False, uncertain=False, communication=True,
                   preapproved=False, rules=None):
    if not math.isfinite(wheel_slip_pct) or not 0 <= wheel_slip_pct <= 100:
        raise ValueError("Wheel slip must be a finite percentage")
    if critical or (not communication and not preapproved):
        return "stop"
    if uncertain or wheel_slip_pct > threshold(rules or load_rules(), "wheel_slip_pct"):
        return "request_input"
    if blocked:
        return "reroute" if alternative else "stop"
    return "continue"


def coverage(terrain, analysis, rover_path, radius_m):
    if not math.isfinite(radius_m) or radius_m < 0:
        raise ValueError("Sensor footprint radius must be finite and nonnegative")
    path_mask = np.zeros(terrain.elevation.shape, bool)
    for cell in rover_path:
        path_mask[cell] = True
    checked = (distance_transform_edt(~path_mask) * terrain.resolution <= radius_m) if path_mask.any() else path_mask
    checked &= analysis["valid"]
    features = []
    for state, mask, simulated, sensor in (
        ("rover_checked", checked, True, "stereo_cam"),
        ("unscouted", analysis["valid"] & ~checked, False, "none"),
        ("inspection_required", ~analysis["valid"], False, "none"),
    ):
        features.extend(mask_features(mask, terrain, f"cov-{state}", {
            "state": state, "simulated": simulated, "sensor": sensor}))
    return collection(features)


def discovery_scenario(terrain, analysis, masks, start, end, discovery_cell,
                       sensor_radius_m, approved=False, eva_minutes=240, speed_m_min=20):
    rules = load_rules()
    routes, before, _ = plan_routes(terrain, analysis, masks, start, end,
                                    eva_minutes=eva_minutes, speed_m_min=speed_m_min)
    discovery_cell = tuple(discovery_cell)
    if discovery_cell not in before[1:-1]:
        raise ValueError("Discovery must lie inside a viable preliminary route")
    blocked = np.zeros(terrain.elevation.shape, bool)
    blocked[discovery_cell] = True
    updated_masks = {key: value.copy() for key, value in masks.items()}
    updated_masks["crew_exclude"] |= blocked
    updated_masks["rover_exclude"] |= blocked
    after_routes, after, _ = plan_routes(terrain, analysis, updated_masks, start, end,
                                       eva_minutes=eva_minutes, speed_m_min=speed_m_min)
    for feature in after_routes["features"]:
        feature["properties"]["version"] = "after"
        feature["properties"]["id"] = feature["properties"]["id"].replace("-v1", "-v2")
    routes["features"].extend(after_routes["features"])
    properties = {"id": "hz-sim-001", "type": "U", "category": "soft_ground",
                  "severity": "exclude", "evidence": "simulated", "agent": "both",
                  "stage": "rover", "source": "disc-001",
                  "note": "Planted demonstration hazard, not an observed NASA terrain feature."}
    # A single-cell scenario gives the discovery its stable, contract-defined ID.
    hazard = mask_features(blocked, terrain, "hz-sim", properties)[0]
    hazard["properties"]["id"] = "hz-sim-001"
    lon, lat = terrain.lonlat(*discovery_cell)
    delta = after_routes["features"][0]["properties"]["stats"]["length_m"] - routes["features"][0]["properties"]["stats"]["length_m"]
    discovery = {
        "id": "disc-001", "hazard_id": "hz-sim-001",
        "before_route_id": "rt-crew-main-v1", "after_route_id": "rt-crew-main-v2",
        "location": {"lat": lat, "lon": lon},
        "sensor_evidence": {"wheel_slip_pct": 38, "thermal": "Simulated low thermal inertia; material interpretation uncertain"},
        "evidence": "simulated", "uncertainty": "high", "decision": rover_decision(38),
        "options": [
            {"id": "opt-reroute", "label": "Reroute around the area", "consequence": f"{delta:+.1f} m modeled one-way" if after else "No viable route; remain stopped"},
            {"id": "opt-drone", "label": "Request drone inspection", "consequence": "Human review required; duration unknown"},
            {"id": "opt-continue", "label": "Review evidence with crew", "consequence": "No autonomous override of hard exclusions"}],
        "chosen_option": "opt-reroute" if approved and after else "",
    }
    # The rover follows only its traversable prefix and stops before discovery.
    rover_costs = cost_grid(terrain, analysis, updated_masks, agent="rover")
    prefix = []
    for cell in before:
        if cell == discovery_cell or not np.isfinite(rover_costs[cell]):
            break
        prefix.append(cell)
    rover_status = "ok" if len(prefix) >= 2 else "inspection_required"
    rover_feature = route_feature(terrain, analysis, prefix if len(prefix) >= 2 else [],
                                  "rt-rover-v1", kind="rover_path", status=rover_status)
    rover_feature["properties"]["agent"] = "rover"
    # Rover route is an executed prefix, not an implied return journey.
    stats = rover_feature["properties"]["stats"]
    stats["round_trip_m"] = stats["length_m"]
    stats["est_time_min"] = stats["length_m"] / speed_m_min
    routes["features"].append(rover_feature)
    return routes, hazard, discovery, coverage(terrain, analysis, prefix, sensor_radius_m)
