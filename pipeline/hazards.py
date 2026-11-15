"""Configurable hazard masks; exclusions always precede costs."""

import numpy as np
import logging
from rasterio.features import shapes
from rasterio.warp import transform_geom

from pipeline.terrain import MARS_GEOGRAPHIC, load_rules, threshold, signed_longitude
from pipeline.logging_config import event, traced


def collection(features):
    """Wrap the feature records in the shared schema 1.0 GeoJSON envelope."""
    return {"schema_version": "1.0", "type": "FeatureCollection", "features": features}


@traced("geojson_export")
def mask_features(mask, terrain, prefix, properties):
    """Polygonize boolean mask on terrain's grid; prefix gives stable output IDs."""
    features = []
    for geometry, _ in shapes(mask.astype(np.uint8), mask=mask, transform=terrain.transform):
        geometry = transform_geom(terrain.crs, MARS_GEOGRAPHIC, geometry)
        # Rasterio returns tuples; normalize the signed longitude at every position.
        geometry = {"type": geometry["type"], "coordinates": [
            [[signed_longitude(lon), lat] for lon, lat in ring]
            for ring in geometry["coordinates"]]}
        features.append({"type": "Feature", "properties": {
            **properties, "id": f"{prefix}-{len(features):04d}"}, "geometry": geometry})
    event("features_exported", id_prefix=prefix, feature_count=len(features), evidence=properties.get("evidence"), source=terrain.source)
    return features


@traced("hazard_generation")
def hazard_masks(terrain, analysis, rules=None, edge_distance=None,
                 foot_distance=None, scarp_height=None, apron_m=None, scarp_risk=None, rockfall_buffer=None):
    """Classify analysis; distances/heights are metres and scarp_risk bounds unresolved risk.

    rockfall_buffer: optional per-cell grid (metres) replacing the single max(apron, height x factor)
    buffer, for scarps whose height and apron vary along the foot; it must already apply the rule.
    """
    rules = rules or load_rules()
    slope = analysis["slope"]
    masks = {
        "crew_exclude": slope >= threshold(rules, "crew_exclude_deg"),
        "crew_caution": (slope >= threshold(rules, "crew_caution_deg")) & (slope < threshold(rules, "crew_exclude_deg")),
        "rover_exclude": slope >= threshold(rules, "rover_exclude_deg"),
        "roughness": analysis["roughness"] > threshold(rules, "roughness_m"),
        "no_data": ~analysis["valid"] & ~terrain.artifact,
        "artifact": terrain.artifact.copy(),
        "edge": np.zeros(slope.shape, dtype=bool),
        "rockfall": np.zeros(slope.shape, dtype=bool),
        "inspection_required": np.zeros(slope.shape, dtype=bool),
    }
    for value in (edge_distance, foot_distance):
        if value is not None and (np.shape(value) != slope.shape or not np.all(np.isfinite(value)) or np.any(value < 0)):
            raise ValueError("Distance masks must be finite, nonnegative and aligned")
    if scarp_risk is None:
        has_risk = terrain.evidence == "nasa_derived" or any(v is not None for v in (edge_distance, foot_distance, scarp_height, apron_m))
        scarp_risk = np.full(slope.shape, has_risk, dtype=bool)
    scarp_risk = np.asarray(scarp_risk, dtype=bool)
    if scarp_risk.shape != slope.shape:
        raise ValueError("Scarp risk mask must match terrain")
    missing = [name for name, value in (("edge_geometry", edge_distance), ("foot_geometry", foot_distance),
                                       ("scarp_height", scarp_height), ("visible_apron", apron_m)) if value is None]
    for name, value in (("scarp_height", scarp_height), ("visible_apron", apron_m)):
        if value is not None and (not np.isfinite(value) or value < 0):
            raise ValueError(f"Invalid {name}")
    if missing and scarp_risk.any():
        masks["inspection_required"] = scarp_risk.copy()
        event("scarp_measurements_missing", logging.WARNING, missing=missing,
              unresolved_cells=int(scarp_risk.sum()), status="inspection_required", evidence=terrain.evidence)
    if edge_distance is not None:
        masks["edge"] = edge_distance <= threshold(rules, "cliff_setback_m")
    if rockfall_buffer is not None:
        if foot_distance is None:
            raise ValueError("A rockfall buffer needs the foot distance grid")
        rockfall_buffer = np.broadcast_to(np.asarray(rockfall_buffer, dtype=float), slope.shape)
        if not np.all(np.isfinite(rockfall_buffer)) or np.any(rockfall_buffer < 0):
            raise ValueError("Rockfall buffer must be finite and nonnegative")
        masks["rockfall"] = foot_distance <= rockfall_buffer
        event("rockfall_buffer_applied", buffer_m=[float(rockfall_buffer.min()), float(rockfall_buffer.max())],
              varies_along_foot=True, classification="scenario_assumption", source=terrain.source)
    elif foot_distance is not None and scarp_height is not None and apron_m is not None:
        buffer = max(apron_m, scarp_height * threshold(rules, "rockfall_height_factor"))
        masks["rockfall"] = foot_distance <= buffer
        event("rockfall_buffer_applied", buffer_m=buffer, classification="scenario_assumption", source=terrain.source)
    event("hazard_mask_summary", dataset_id=terrain.source, evidence=terrain.evidence,
          cell_counts={key: int(value.sum()) for key, value in masks.items()})
    return masks


@traced("uncertainty_area_check")
def uncertainty_area_check(terrain, analysis, masks, cell, radius_m=None, agent="crew", rules=None, point_id="point"):
    """Check every cell within radius_m of a candidate position, not just the chosen DTM cell.

    cell: (row, col) of the candidate centre. radius_m: horizontal position uncertainty in metres
    (default rule position_uncertainty_m = 15). Distances use row spacing and the latitude-corrected
    east-west column spacing. Status is never "safe":
      excluded_terrain_within_uncertainty - a hard exclusion (slope, rockfall, edge) lies inside the disc;
      inspection_required - unresolved cells (no-data, artifact, unresolved scarp) or the disc leaves the crop;
      no_mapped_exclusion - nothing mapped inside the disc (sub-DTM hazards remain possible).
    """
    rules = rules or load_rules()
    radius_m = threshold(rules, "position_uncertainty_m") if radius_m is None else float(radius_m)
    if not np.isfinite(radius_m) or radius_m < 0:
        raise ValueError("Uncertainty radius must be finite and nonnegative")
    if agent not in {"crew", "rover"}:
        raise ValueError("Unknown agent")
    row, col = (int(v) for v in cell)
    rows, cols = terrain.elevation.shape
    if not (0 <= row < rows and 0 <= col < cols):
        raise ValueError("Candidate cell outside terrain")
    dy = terrain.resolution
    dx = float(terrain.column_spacing[row])
    reach_r, reach_c = int(np.ceil(radius_m / dy)), int(np.ceil(radius_m / dx))
    outside_crop = row - reach_r < 0 or col - reach_c < 0 or row + reach_r >= rows or col + reach_c >= cols
    r0, r1 = max(0, row - reach_r), min(rows, row + reach_r + 1)
    c0, c1 = max(0, col - reach_c), min(cols, col + reach_c + 1)
    rr, cc = np.mgrid[r0:r1, c0:c1]
    disc = np.zeros(terrain.elevation.shape, bool)
    disc[rr, cc] = ((rr - row) * dy) ** 2 + ((cc - col) * dx) ** 2 <= radius_m ** 2
    hard = {"slope_exclude": masks[f"{agent}_exclude"], "rockfall": masks["rockfall"]}
    if agent == "crew":
        hard["edge"] = masks["edge"]
    unresolved = {"no_data": masks["no_data"], "artifact": masks["artifact"],
                  "unresolved_scarp": masks["inspection_required"], "invalid_analysis": ~analysis["valid"]}
    counts = {name: int((mask & disc).sum()) for name, mask in {**hard, **unresolved}.items()}
    counts["crew_caution"] = int((masks["crew_caution"] & disc).sum())
    if any(counts[name] for name in hard):
        status = "excluded_terrain_within_uncertainty"
    elif outside_crop or any(counts[name] for name in unresolved):
        status = "inspection_required"
    else:
        status = "no_mapped_exclusion"
    result = {"point_id": point_id, "cell": [row, col], "radius_m": radius_m, "cells_checked": int(disc.sum()),
              "disc_leaves_crop": bool(outside_crop), "counts": counts, "status": status,
              "crew_clearance": "not_established"}
    event("uncertainty_area_checked", logging.INFO if status == "no_mapped_exclusion" else logging.WARNING,
          evidence=terrain.evidence, agent=agent, **result)
    return result


@traced("hazard_export")
def export_hazards(terrain, masks):
    """Export classified masks with terrain provenance and stable category IDs."""
    features = []
    specifications = [
        ("crew_exclude", "slope", "exclude", "crew"),
        ("crew_caution", "slope", "caution", "crew"),
        ("rover_exclude", "slope", "exclude", "rover"),
        ("roughness", "roughness", "caution", "both"),
        ("no_data", "no_data", "exclude", "both"),
        ("artifact", "artifact", "exclude", "both"),
        ("edge", "edge", "exclude", "crew"),
        ("rockfall", "rockfall", "exclude", "both"),
        ("inspection_required", "edge", "exclude", "both"),
    ]
    for key, category, severity, agent in specifications:
        evidence = terrain.evidence if category in {"slope", "roughness", "no_data"} else "inferred"
        if terrain.evidence == "simulated":
            evidence = "simulated"
        features.extend(mask_features(masks[key], terrain, f"hz-{key}", {
            "type": "O" if category == "rockfall" else "U", "category": category,
            "severity": severity, "agent": agent, "evidence": evidence, "stage": "orbital",
            "source": terrain.source, "note": (
                "Unresolved scarp measurements require inspection; absence of geometry is not absence of risk."
                if key == "inspection_required" else
                "Provisional roughness model; DTM vertical uncertainty is unverified; variations may be measurement error."
                if category == "roughness" else
                "Modeled terrain assessment; missing or suspect cells require inspection; sub-metre hazards unresolved.")
        }))
    event("hazards_exported", feature_count=len(features), counts={category: sum(f["properties"]["category"] == category for f in features) for category in {f["properties"]["category"] for f in features}})
    return collection(features)
