"""Deterministic four-neighbour Dijkstra search with hard exclusion masks.

Four-neighbour adjacency deliberately forbids diagonal corner cutting. This is
equivalent to minimum-cost grid graph search with geometric edge weights.
"""

import heapq
import math
import logging

import numpy as np
from scipy.ndimage import distance_transform_edt

from pipeline.hazards import collection
from pipeline.terrain import MARS_RADIUS_M, load_rules, threshold
from pipeline.logging_config import event, traced, operation

STAT_KEYS = ("length_m", "round_trip_m", "est_time_min", "elevation_gain_m", "max_slope_deg", "shared_with_main_m")
# Cost added where roughness could not be measured on otherwise valid terrain. Same weight as
# unscouted terrain: unknown is never cheaper than measured-smooth. A modeling choice, not physics.
UNRESOLVED_ROUGHNESS_PENALTY = 2.0


class InfeasibleMission(ValueError):
    """Raised when modeled terrain and budgets leave no viable route; a valid finding, not a crash."""


def unresolved_roughness(analysis):
    """Boolean grid of valid cells whose roughness is NaN (window too coarse or unmeasured)."""
    return analysis["valid"] & ~np.isfinite(analysis["roughness"])


def mars_distance(first, second):
    """Measure metres between signed [lon,lat] first/second on the Mars mean sphere."""
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * MARS_RADIUS_M * math.asin(math.sqrt(min(1, max(0, a))))


@traced("cost_grid")
def cost_grid(terrain, analysis, masks, agent="crew", unscouted=None, rules=None):
    """Build agent-specific costs; masks are hard exclusions and unscouted adds a penalty.

    Unresolved roughness on valid cells costs UNRESOLVED_ROUGHNESS_PENALTY instead of the
    zero a NaN-to-zero conversion would give, so unmeasured terrain never looks smooth.
    """
    if agent not in {"crew", "rover"}:
        raise ValueError("Unknown route agent")
    blocked = (~analysis["valid"] | masks["no_data"] | masks["artifact"]
               | masks[f"{agent}_exclude"] | masks["rockfall"] | masks["inspection_required"])
    if agent == "crew":
        blocked |= masks["edge"]
    if unscouted is None:
        unscouted = np.ones(blocked.shape, bool)
    if np.shape(unscouted) != blocked.shape:
        raise ValueError("Unscouted mask shape mismatch")
    # Weights are modeling choices; hard exclusions stay infinite.
    unresolved = unresolved_roughness(analysis)
    roughness_cost = np.where(unresolved, UNRESOLVED_ROUGHNESS_PENALTY, np.nan_to_num(analysis["roughness"]))
    costs = 1 + np.nan_to_num(analysis["slope"]) / 15 + roughness_cost + np.asarray(unscouted) * 2
    if masks["rockfall"].any():
        distance = distance_transform_edt(~masks["rockfall"]) * terrain.resolution
        costs += 10 / (1 + distance)
    costs[blocked] = np.inf
    if unresolved.any():
        event("unresolved_roughness_penalized", logging.WARNING, agent=agent, cells=int(unresolved.sum()),
              penalty=UNRESOLVED_ROUGHNESS_PENALTY, classification="modeling_choice", evidence=terrain.evidence)
    event("cost_grid_built", agent=agent, evidence=terrain.evidence, excluded_cells=int(blocked.sum()),
          unresolved_scarp_cells=int(masks["inspection_required"].sum()), unresolved_roughness_cells=int(unresolved.sum()),
          slope_threshold_deg=threshold(rules or load_rules(), f"{agent}_exclude_deg"))
    return costs


@traced("route_search")
def shortest_path(costs, start, end, spacing=None):
    """Find a deterministic 4-neighbour path; start/end are cells, spacing is metric row/column scale."""
    costs = np.asarray(costs, dtype=float)
    if costs.ndim != 2 or np.isnan(costs).any() or (costs <= 0).any():
        raise ValueError("Costs must be positive or infinity in a 2D grid")
    start, end = tuple(start), tuple(end)
    for point in (start, end):
        if len(point) != 2 or any(isinstance(v, bool) or int(v) != v for v in point):
            raise ValueError("Endpoints must be integer row/column pairs")
        if not 0 <= point[0] < costs.shape[0] or not 0 <= point[1] < costs.shape[1]:
            raise ValueError("Endpoint outside terrain")
    if start == end:
        raise ValueError("Route endpoints must differ")
    event("route_search_started", start=start, destination=end, excluded_cells=int((~np.isfinite(costs)).sum()))
    if not np.isfinite(costs[start]) or not np.isfinite(costs[end]):
        event("route_search_unavailable", logging.WARNING, reason="endpoint_excluded", status="no_viable_route")
        return []
    distance = {start: 0.0}
    parent = {}
    queue = [(0.0, start)]
    while queue:
        current_cost, current = heapq.heappop(queue)
        if current_cost != distance[current]:
            continue
        if current == end:
            path = [end]
            while path[-1] != start:
                path.append(parent[path[-1]])
            result = path[::-1]
            event("route_search_completed", cells=len(result), geometric_cost=current_cost)
            return result
        row, col = current
        for neighbour in ((row - 1, col), (row, col - 1), (row, col + 1), (row + 1, col)):
            r, c = neighbour
            if not 0 <= r < costs.shape[0] or not 0 <= c < costs.shape[1] or not np.isfinite(costs[neighbour]):
                continue
            step = 1.0 if spacing is None else (spacing[0] if r != row else spacing[1][row])
            candidate = current_cost + (costs[current] / 2 + costs[neighbour] / 2) * step
            if candidate < distance.get(neighbour, np.inf):
                distance[neighbour] = candidate
                parent[neighbour] = current
                heapq.heappush(queue, (candidate, neighbour))
    event("route_search_unavailable", logging.WARNING, reason="disconnected_or_excluded", status="no_viable_route")
    return []


def route_stats(terrain, analysis, path, primary=(), speed_m_min=20):
    """Measure path geometry; primary defines shared edges and speed_m_min models travel."""
    if not math.isfinite(speed_m_min) or speed_m_min <= 0:
        raise ValueError("Modeled speed must be positive and finite")
    if not path:
        return dict.fromkeys(STAT_KEYS, 0.0)
    coordinates = [terrain.lonlat(*cell) for cell in path]
    lengths = [mars_distance(a, b) for a, b in zip(coordinates, coordinates[1:])]
    primary_edges = {frozenset((a, b)) for a, b in zip(primary, primary[1:])}
    shared = sum(length for a, b, length in zip(path, path[1:], lengths) if frozenset((a, b)) in primary_edges)
    length = sum(lengths)
    elevation = [terrain.elevation[cell] for cell in path]
    return dict(zip(STAT_KEYS, (length, 2 * length, 2 * length / speed_m_min,
                               sum(max(0, b - a) for a, b in zip(elevation, elevation[1:])),
                               max(float(analysis["slope"][cell]) for cell in path), shared)))


@traced("route_export")
def route_feature(terrain, analysis, path, route_id, kind="main", version="before",
                  status="ok", primary=(), speed_m_min=20, agent="crew"):
    """Build the schema 1.0 record for route_id; status describes planning, not crew clearance."""
    if agent not in {"crew", "rover"}:
        raise ValueError("Unknown route agent")
    feature = {"type": "Feature", "properties": {"id": route_id, "kind": kind,
            "agent": agent, "version": version, "status": status,
            "stats": route_stats(terrain, analysis, path, primary, speed_m_min)},
            "geometry": {"type": "LineString", "coordinates": [terrain.lonlat(*cell) for cell in path]}}
    if agent == "rover":
        feature["properties"]["stats"]["round_trip_m"] = feature["properties"]["stats"]["length_m"]
        feature["properties"]["stats"]["est_time_min"] = feature["properties"]["stats"]["length_m"] / speed_m_min
    event("route_result", route_id=route_id, status=status, geometric_feasibility=bool(path),
          evidence=terrain.evidence, statistics=feature["properties"]["stats"], crew_clearance="not_established")
    return feature


def itinerary_budget(leg_lengths_m, rules, eva_minutes, speed_m_min, observation_minutes=0,
                     max_excursion_m=None, label="itinerary"):
    """Budget a complete multi-leg EVA (e.g. habitat -> primary -> backup -> habitat).

    leg_lengths_m: every leg in metres, including any primary-to-backup leg, so nothing is omitted.
    observation_minutes: total site work across all stops (minutes).
    max_excursion_m: farthest distance from the habitat; defaults to the longest leg.
    Applies the round-trip distance limit, the hard excursion cap and EVA time with reserve.
    """
    for name, value, allow_zero in (("EVA duration", eva_minutes, False), ("walking speed", speed_m_min, False),
                                     ("observation duration", observation_minutes, True)):
        if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
            raise ValueError(f"{name} must be finite and {'nonnegative' if allow_zero else 'positive'}")
    reserve = threshold(rules, "eva_reserve_fraction")
    if not 0 <= reserve < 1:
        raise ValueError("Reserve fraction must be in [0,1)")
    lengths = [float(value) for value in leg_lengths_m]
    if not lengths or any(not math.isfinite(value) or value < 0 for value in lengths):
        raise ValueError("Route lengths must be finite and nonnegative")
    excursion = max(lengths) if max_excursion_m is None else float(max_excursion_m)
    distance = sum(lengths)
    travel_minutes = distance / speed_m_min
    available = eva_minutes * (1 - reserve)
    reasons = []
    if distance >= threshold(rules, "round_trip_limit_m"):
        reasons.append("round_trip_distance_limit")
    if excursion > threshold(rules, "hard_excursion_cap_m"):
        reasons.append("hard_excursion_cap")
    if travel_minutes + observation_minutes > available + 1e-9:
        reasons.append("eva_time_limit")
    result = {"accepted": not reasons, "reasons": reasons, "distance_m": distance, "legs_m": lengths,
              "max_excursion_m": excursion, "travel_min": travel_minutes, "observation_min": observation_minutes,
              "total_min": travel_minutes + observation_minutes, "available_min": available,
              "reserve_fraction": reserve, "speed_m_min": speed_m_min}
    event("mission_budget_evaluated", logging.INFO if not reasons else logging.WARNING, itinerary=label, **result)
    return result


@traced("mission_budget")
def mission_budget(outbound, returning, rules, eva_minutes, speed_m_min, observation_minutes=0):
    """Budget outbound/returning lengths plus observation_minutes without changing travel-only stats."""
    return itinerary_budget([outbound["length_m"], returning["length_m"]], rules, eva_minutes,
                            speed_m_min, observation_minutes, label="out_and_back")


def within_budget(stats, rules, eva_minutes, speed_m_min, observation_minutes=0):
    """Check a same-route return using stats length, walking speed and site work duration."""
    return mission_budget(stats, stats, rules, eva_minutes, speed_m_min, observation_minutes)["accepted"]


def straight_line_m(terrain, start, end):
    """Great-circle metres between cell centres start/end on the Mars sphere: a lower bound on any route."""
    return mars_distance(terrain.lonlat(*start), terrain.lonlat(*end))


def unit_costs(costs):
    """Same exclusions as costs but every passable cell costs 1, so search minimizes distance only."""
    return np.where(np.isfinite(costs), 1.0, np.inf)


@traced("route_planning")
def plan_routes(terrain, analysis, masks, start, end, rules=None, eva_minutes=240,
                speed_m_min=20, backup_max_shared=0.5, corridor_m=2, observation_minutes=0, unscouted=None, version="before"):
    """Plan start/end candidates; observation_minutes budgets work, unscouted limits interpretation.

    Budget checks run in order: great-circle lower bound (proves infeasibility without search),
    least-cost path, then the shortest-distance path over the same exclusions when the
    least-cost path is too long. Only when that also fails is the result no_viable_route.
    Unscouted or unresolved-roughness cells on a route make it inspection_required.

    Backup independence is modeled: penalize a corridor around the primary,
    then require both shared-edge and corridor-overlap fractions <= threshold.
    This does not certify independence from common regional hazards.
    """
    if not 0 <= backup_max_shared < 1 or not math.isfinite(corridor_m) or corridor_m < 0:
        raise ValueError("Invalid backup independence settings")
    if version not in {"before", "after"}:
        raise ValueError("Invalid route version")
    main_id = "rt-crew-main-v1" if version == "before" else "rt-crew-main-v2"
    backup_id = "rt-crew-backup-v1" if version == "before" else "rt-crew-backup-v2"
    rules = rules or load_rules()
    mission_budget({"length_m": 0}, {"length_m": 0}, rules, eva_minutes, speed_m_min, observation_minutes)
    unscouted = np.ones(terrain.elevation.shape, bool) if unscouted is None else np.asarray(unscouted, dtype=bool)
    costs = cost_grid(terrain, analysis, masks, unscouted=unscouted, rules=rules)
    spacing = (terrain.resolution, terrain.column_spacing)
    status = "ok"
    # Lower bound: no route on Mars is shorter than the great circle, so failing here proves infeasibility.
    lower_bound = straight_line_m(terrain, start, end)
    bound = itinerary_budget([lower_bound, lower_bound], rules, eva_minutes, speed_m_min,
                             observation_minutes, label="straight_line_lower_bound")
    primary = []
    if bound["accepted"]:
        with operation("primary_route_search", route_id=main_id, evidence=terrain.evidence):
            primary = shortest_path(costs, start, end, spacing)
    if not bound["accepted"]:
        status = "no_viable_route"
        event("route_rejected", logging.WARNING, route_id=main_id, status=status, reason="straight_line_lower_bound",
              lower_bound_m=lower_bound, budget_reasons=bound["reasons"], evidence=terrain.evidence, search_skipped=True)
    elif not primary:
        status = "inspection_required" if not analysis["valid"][tuple(start)] or not analysis["valid"][tuple(end)] or masks["inspection_required"].any() else "no_viable_route"
        event("route_rejected", logging.WARNING, route_id=main_id, status=status,
              reason="unresolved_scarp_or_invalid_terrain" if status == "inspection_required" else "hard_exclusions_or_disconnected", evidence=terrain.evidence,
              threshold_deg=threshold(rules, "crew_exclude_deg"), excluded_cells=int((~np.isfinite(costs)).sum()))
    elif not within_budget(route_stats(terrain, analysis, primary, speed_m_min=speed_m_min), rules, eva_minutes, speed_m_min, observation_minutes):
        # The least-cost path minimizes weighted cost, not length. Before declaring the mission
        # infeasible, test the shortest-distance path over the same hard exclusions.
        cost_length = route_stats(terrain, analysis, primary, speed_m_min=speed_m_min)["length_m"]
        with operation("budget_fallback_search", route_id=main_id, evidence=terrain.evidence):
            shortest = shortest_path(unit_costs(costs), start, end, spacing)
        shortest_length = route_stats(terrain, analysis, shortest, speed_m_min=speed_m_min)["length_m"]
        if shortest and within_budget(route_stats(terrain, analysis, shortest, speed_m_min=speed_m_min), rules, eva_minutes, speed_m_min, observation_minutes):
            primary = shortest
            event("budget_fallback_shortest_distance", logging.WARNING, route_id=main_id, least_cost_length_m=cost_length,
                  shortest_length_m=shortest_length, reason="least_cost_path_exceeded_budget", evidence=terrain.evidence)
        else:
            primary, status = [], "no_viable_route"
            event("route_rejected", logging.WARNING, route_id=main_id, status=status, reason="mission_budget",
                  least_cost_length_m=cost_length, shortest_length_m=shortest_length,
                  proof="shortest_distance_path_over_same_exclusions_exceeds_budget", evidence=terrain.evidence)
    if primary and any(unscouted[cell] for cell in primary):
        status = "inspection_required"
        event("unscouted_corridor", logging.WARNING, route_id=main_id, status=status, evidence=terrain.evidence, reason="geometric_candidate_only")
    rough_unknown = unresolved_roughness(analysis)
    if primary and any(rough_unknown[cell] for cell in primary):
        status = "inspection_required"
        event("unresolved_roughness_on_route", logging.WARNING, route_id=main_id, status=status,
              cells=sum(bool(rough_unknown[cell]) for cell in primary), evidence=terrain.evidence)
    main = route_feature(terrain, analysis, primary, main_id, kind="orbital_guess" if primary and status == "inspection_required" else "main", status=status, speed_m_min=speed_m_min, version=version)
    backup = []
    if primary:
        mask = np.zeros(costs.shape, bool)
        for cell in primary:
            mask[cell] = True
        corridor = distance_transform_edt(~mask) * terrain.resolution <= corridor_m
        penalized = costs.copy()
        penalized[corridor & np.isfinite(penalized)] *= 100
        with operation("backup_route_search", route_id=backup_id, evidence=terrain.evidence):
            candidate = shortest_path(penalized, start, end, spacing)
        if candidate:
            stats = route_stats(terrain, analysis, candidate, primary, speed_m_min)
            corridor_fraction = sum(bool(corridor[cell]) for cell in candidate[1:-1]) / max(1, len(candidate) - 2)
            edge_fraction = stats["shared_with_main_m"] / max(stats["length_m"], 1e-12)
            combined = mission_budget(route_stats(terrain, analysis, primary, speed_m_min=speed_m_min), stats,
                                      rules, eva_minutes, speed_m_min, observation_minutes)
            event("backup_evaluated", route_id=backup_id, corridor_fraction=corridor_fraction,
                  shared_edge_fraction=edge_fraction, allowed_fraction=backup_max_shared, combined_budget=combined,
                  regional_independence="not_assessed")
            if max(corridor_fraction, edge_fraction) <= backup_max_shared and combined["accepted"]:
                backup = candidate
    backup_status = ("inspection_required" if backup and any(unscouted[cell] or rough_unknown[cell] for cell in backup)
                     else "ok" if backup else "backup_unavailable")
    if not backup:
        event("backup_unavailable", logging.WARNING, route_id=backup_id, reason="no_independent_budgeted_candidate", status=backup_status, evidence=terrain.evidence)
    fallback = route_feature(terrain, analysis, backup, backup_id, kind="backup",
                             status=backup_status, primary=primary, speed_m_min=speed_m_min, version=version)
    return collection([main, fallback]), primary, backup
