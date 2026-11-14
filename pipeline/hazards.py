"""Configurable hazard masks; exclusions always precede costs."""

import numpy as np
from rasterio.features import shapes
from rasterio.warp import transform_geom

from pipeline.terrain import MARS_GEOGRAPHIC, load_rules, threshold, signed_longitude


def collection(features):
    return {"schema_version": "1.0", "type": "FeatureCollection", "features": features}


def mask_features(mask, terrain, prefix, properties):
    features = []
    for geometry, _ in shapes(mask.astype(np.uint8), mask=mask, transform=terrain.transform):
        geometry = transform_geom(terrain.crs, MARS_GEOGRAPHIC, geometry)
        # Rasterio returns tuples; normalize the signed longitude at every position.
        geometry = {"type": geometry["type"], "coordinates": [
            [[signed_longitude(lon), lat] for lon, lat in ring]
            for ring in geometry["coordinates"]]}
        features.append({"type": "Feature", "properties": {
            **properties, "id": f"{prefix}-{len(features):04d}"}, "geometry": geometry})
    return features


def hazard_masks(terrain, analysis, rules=None, edge_distance=None,
                 foot_distance=None, scarp_height=None, apron_m=None):
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
    }
    for value in (edge_distance, foot_distance):
        if value is not None and (np.shape(value) != slope.shape or not np.all(np.isfinite(value)) or np.any(value < 0)):
            raise ValueError("Distance masks must be finite, nonnegative and aligned")
    if edge_distance is not None:
        masks["edge"] = edge_distance <= threshold(rules, "cliff_setback_m")
    if foot_distance is not None:
        if scarp_height is None or apron_m is None or min(scarp_height, apron_m) < 0:
            raise ValueError("Rockfall requires measured height and visible apron")
        buffer = max(apron_m, scarp_height * threshold(rules, "rockfall_height_factor"))
        masks["rockfall"] = foot_distance <= buffer
    return masks


def export_hazards(terrain, masks):
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
    ]
    for key, category, severity, agent in specifications:
        evidence = terrain.evidence if category in {"slope", "roughness", "no_data"} else "inferred"
        if terrain.evidence == "simulated":
            evidence = "simulated"
        features.extend(mask_features(masks[key], terrain, f"hz-{key}", {
            "type": "O" if category == "rockfall" else "U", "category": category,
            "severity": severity, "agent": agent, "evidence": evidence, "stage": "orbital",
            "source": terrain.source, "note": "Modeled terrain assessment; missing or suspect cells require inspection; sub-metre hazards unresolved."
        }))
    return collection(features)
