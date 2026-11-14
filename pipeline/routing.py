"""Deterministic four-neighbour Dijkstra search with hard exclusion masks.

Four-neighbour adjacency deliberately forbids diagonal corner cutting. This is
equivalent to minimum-cost grid graph search with geometric edge weights.
"""

import heapq
import math

import numpy as np
from scipy.ndimage import distance_transform_edt

from pipeline.hazards import collection
from pipeline.terrain import MARS_RADIUS_M, load_rules, threshold

STAT_KEYS = ("length_m", "round_trip_m", "est_time_min", "elevation_gain_m", "max_slope_deg", "shared_with_main_m")


def mars_distance(first, second):
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * MARS_RADIUS_M * math.asin(math.sqrt(min(1, max(0, a))))


def cost_grid(terrain, analysis, masks, agent="crew", unscouted=None):
    if agent not in {"crew", "rover"}:
        raise ValueError("Unknown route agent")
    blocked = (~analysis["valid"] | masks["no_data"] | masks["artifact"]
               | masks[f"{agent}_exclude"] | masks["rockfall"])
    if agent == "crew":
        blocked |= masks["edge"]
    if unscouted is None:
        unscouted = np.ones(blocked.shape, bool)
    if np.shape(unscouted) != blocked.shape:
        raise ValueError("Unscouted mask shape mismatch")
    # Weights are modeling choices; hard exclusions stay infinite.
    costs = 1 + np.nan_to_num(analysis["slope"]) / 15 + np.nan_to_num(analysis["roughness"]) + np.asarray(unscouted) * 2
    if masks["rockfall"].any():
        distance = distance_transform_edt(~masks["rockfall"]) * terrain.resolution
        costs += 10 / (1 + distance)
    costs[blocked] = np.inf
    return costs


def shortest_path(costs, start, end):
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
    if not np.isfinite(costs[start]) or not np.isfinite(costs[end]):
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
            return path[::-1]
        row, col = current
        for neighbour in ((row - 1, col), (row, col - 1), (row, col + 1), (row + 1, col)):
            r, c = neighbour
            if not 0 <= r < costs.shape[0] or not 0 <= c < costs.shape[1] or not np.isfinite(costs[neighbour]):
                continue
            candidate = current_cost + (costs[current] / 2 + costs[neighbour] / 2)
            if candidate < distance.get(neighbour, np.inf):
                distance[neighbour] = candidate
                parent[neighbour] = current
                heapq.heappush(queue, (candidate, neighbour))
    return []


def route_stats(terrain, analysis, path, primary=(), speed_m_min=20):
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


def route_feature(terrain, analysis, path, route_id, kind="main", version="before",
                  status="ok", primary=(), speed_m_min=20):
    return {"type": "Feature", "properties": {"id": route_id, "kind": kind,
            "agent": "crew", "version": version, "status": status,
            "stats": route_stats(terrain, analysis, path, primary, speed_m_min)},
            "geometry": {"type": "LineString", "coordinates": [terrain.lonlat(*cell) for cell in path]}}


def within_budget(stats, rules, eva_minutes, speed_m_min):
    if not math.isfinite(eva_minutes) or eva_minutes <= 0:
        raise ValueError("Planned EVA duration must be positive and finite")
    reserve = threshold(rules, "eva_reserve_fraction")
    return (stats["round_trip_m"] < threshold(rules, "round_trip_limit_m")
            and stats["length_m"] <= threshold(rules, "hard_excursion_cap_m")
            and stats["est_time_min"] <= eva_minutes * (1 - reserve))


def plan_routes(terrain, analysis, masks, start, end, rules=None, eva_minutes=240,
                speed_m_min=20, backup_max_shared=0.5, corridor_m=2):
    """Return primary/backup records, including explicit failures.

    Backup independence is modeled: penalize a corridor around the primary,
    then require both shared-edge and corridor-overlap fractions <= threshold.
    This does not certify independence from common regional hazards.
    """
    if not 0 <= backup_max_shared < 1 or corridor_m < 0:
        raise ValueError("Invalid backup independence settings")
    rules = rules or load_rules()
    costs = cost_grid(terrain, analysis, masks)
    primary = shortest_path(costs, start, end)
    status = "ok"
    if not primary:
        status = "inspection_required" if not analysis["valid"][tuple(start)] or not analysis["valid"][tuple(end)] else "no_viable_route"
    elif not within_budget(route_stats(terrain, analysis, primary, speed_m_min=speed_m_min), rules, eva_minutes, speed_m_min):
        primary, status = [], "no_viable_route"
    main = route_feature(terrain, analysis, primary, "rt-crew-main-v1", status=status, speed_m_min=speed_m_min)
    backup = []
    if primary:
        mask = np.zeros(costs.shape, bool)
        for cell in primary:
            mask[cell] = True
        corridor = distance_transform_edt(~mask) * terrain.resolution <= corridor_m
        penalized = costs.copy()
        penalized[corridor & np.isfinite(penalized)] *= 100
        candidate = shortest_path(penalized, start, end)
        if candidate:
            stats = route_stats(terrain, analysis, candidate, primary, speed_m_min)
            corridor_fraction = sum(bool(corridor[cell]) for cell in candidate[1:-1]) / max(1, len(candidate) - 2)
            edge_fraction = stats["shared_with_main_m"] / max(stats["length_m"], 1e-12)
            if max(corridor_fraction, edge_fraction) <= backup_max_shared and within_budget(stats, rules, eva_minutes, speed_m_min):
                backup = candidate
    fallback = route_feature(terrain, analysis, backup, "rt-crew-backup-v1", kind="backup",
                             status="ok" if backup else "backup_unavailable", primary=primary, speed_m_min=speed_m_min)
    return collection([main, fallback]), primary, backup
