"""Deterministic simulated reconnaissance; human decisions stay explicit."""

import math
import logging
import numpy as np
from scipy.ndimage import distance_transform_edt

from pipeline.hazards import collection, mask_features
from pipeline.routing import InfeasibleMission, cost_grid, plan_routes, route_feature
from pipeline.terrain import load_rules, threshold
from pipeline.logging_config import traced, event


@traced("rover_decision")
def rover_decision(wheel_slip_pct, *, critical=False, blocked=False,
                   alternative=False, uncertain=False, communication=True,
                   preapproved=False, rules=None):
    """Choose a deterministic state; slip is simulated percent and flags bound the operating envelope."""
    if not math.isfinite(wheel_slip_pct) or not 0 <= wheel_slip_pct <= 100:
        raise ValueError("Wheel slip must be a finite percentage")
    limit = threshold(rules or load_rules(), "wheel_slip_pct")
    if critical or (not communication and not preapproved):
        state, reason = "stop", "critical_or_outside_authorized_envelope"
    elif uncertain or wheel_slip_pct > limit:
        state, reason = "request_input", "uncertain_or_slip_threshold_exceeded"
    elif blocked:
        state, reason = ("reroute" if alternative else "stop"), "blocked_terrain"
    else:
        state, reason = "continue", "within_modeled_envelope"
    event("rover_state", logging.WARNING if state in {"stop", "request_input"} else logging.INFO,
          state=state, reason=reason, wheel_slip_pct=wheel_slip_pct, threshold_pct=limit, evidence="simulated")
    return state


@traced("coverage_simulation")
def coverage(terrain, analysis, rover_path, radius_m, inspection_mask=None):
    """Model radius_m around rover_path cells; valid terrain limits footprint, not crew clearance."""
    if not math.isfinite(radius_m) or radius_m < 0:
        raise ValueError("Sensor footprint radius must be finite and nonnegative")
    inspection = ~analysis["valid"] if inspection_mask is None else ~analysis["valid"] | np.asarray(inspection_mask, dtype=bool)
    if inspection.shape != terrain.elevation.shape:
        raise ValueError("Inspection mask shape mismatch")
    path_mask = np.zeros(terrain.elevation.shape, bool)
    for cell in rover_path:
        path_mask[cell] = True
    checked = (distance_transform_edt(~path_mask) * terrain.resolution <= radius_m) if path_mask.any() else path_mask
    checked &= ~inspection
    features = []
    for state, mask, simulated, sensor in (
        ("rover_checked", checked, True, "stereo_cam"),
        ("unscouted", ~inspection & ~checked, False, "none"),
        ("inspection_required", inspection, False, "none"),
    ):
        features.extend(mask_features(mask, terrain, f"cov-{state}", {
            "state": state, "simulated": simulated, "sensor": sensor}))
    event("coverage_generated", evidence="simulated", radius_m=radius_m,
          checked_cells=int(checked.sum()), feature_count=len(features), visibility="not_line_of_sight_verified")
    return collection(features)


@traced("discovery_simulation")
def discovery_scenario(terrain, analysis, masks, start, end, discovery_cell,
                       sensor_radius_m, approved=False, eva_minutes=240, speed_m_min=20, observation_minutes=0):
    """Insert a simulated hazard at discovery_cell; approved records explicit human scenario approval."""
    event("simulation_started", scenario_id="disc-001", evidence="simulated", start=start, destination=end)
    if not isinstance(approved, bool):
        raise ValueError("Human approval must be an explicit boolean")
    rules = load_rules()
    routes, before, _ = plan_routes(terrain, analysis, masks, start, end,
                                    eva_minutes=eva_minutes, speed_m_min=speed_m_min, observation_minutes=observation_minutes)
    discovery_cell = tuple(discovery_cell)
    if not before:
        # No viable preliminary route is a planning finding; the caller reports it instead of crashing.
        status = routes["features"][0]["properties"]["status"]
        event("simulation_skipped", logging.WARNING, scenario_id="disc-001", reason="no_viable_preliminary_route",
              route_status=status, evidence="simulated")
        raise InfeasibleMission(f"No viable preliminary route ({status}); discovery scenario not simulated")
    if discovery_cell not in before[1:-1]:
        raise ValueError("Discovery must lie inside a viable preliminary route")
    blocked = np.zeros(terrain.elevation.shape, bool)
    blocked[discovery_cell] = True
    updated_masks = {key: value.copy() for key, value in masks.items()}
    updated_masks["crew_exclude"] |= blocked
    updated_masks["rover_exclude"] |= blocked
    event("simulated_hazard_inserted", hazard_id="hz-sim-001", scenario_id="disc-001", cell=discovery_cell, evidence="simulated")
    after_routes, after, _ = plan_routes(terrain, analysis, updated_masks, start, end,
                                       eva_minutes=eva_minutes, speed_m_min=speed_m_min, observation_minutes=observation_minutes, version="after")
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
        "sensor_evidence": {"wheel_slip_pct": 38, "thermal": "Simulated thermal-camera context only; no thermal-inertia measurement. Soft ground is suspected from simulated wheel slip."},
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
                                  "rt-rover-v1", kind="rover_path", status=rover_status, agent="rover", version="after", speed_m_min=speed_m_min)
    routes["features"].append(rover_feature)
    event("discovery_comparison", scenario_id="disc-001", evidence="simulated", before_route_id="rt-crew-main-v1",
          after_route_id="rt-crew-main-v2", candidate_available=bool(after), delta_length_m=delta if after else None,
          decision=discovery["decision"], human_approval=bool(discovery["chosen_option"]), rover_prefix_cells=len(prefix))
    return routes, hazard, discovery, coverage(terrain, analysis, prefix, sensor_radius_m, masks["inspection_required"])
