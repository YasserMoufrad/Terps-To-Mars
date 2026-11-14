"""Run synthetic demonstration or an explicitly configured real raster crop."""

import argparse
import json
import math
import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform as project

from pipeline.terrain import Terrain, MARS_GEOGRAPHIC, analyze, read_terrain
from pipeline.hazards import hazard_masks, export_hazards
from pipeline.scenario import discovery_scenario
from pipeline.routing import InfeasibleMission
from pipeline.feasibility import audit_site
from pipeline.export import aligned_image, export_overlay, write_json
from pipeline.validate_contract import validate_data
from pipeline.logging_config import traced, event, fingerprint, configure_logging, operation


@traced("real_input_validation")
def validate_real_config(config):
    """Require confirmed endpoints, reviewed measurements and explicit modeled mission inputs."""
    for flag in ("alignment_reviewed", "qc_reviewed", "endpoints_confirmed", "scarp_measurements_reviewed"):
        if config.get(flag) is not True:
            event("real_input_unconfirmed", logging.WARNING, missing_confirmation=flag, status="inspection_required")
            raise ValueError(f"Real exports require {flag}; no site route will be manufactured")
    for key in ("dtm", "image", "artifact_mask", "edge_distance", "foot_distance", "scarp_risk"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError(f"Real exports require {key}")
    for key in ("scarp_height_m", "apron_m", "sensor_radius_m", "observation_minutes"):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Real exports require measured/configured nonnegative {key}")
    window = config.get("window")
    if not isinstance(window, list) or len(window) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in window):
        raise ValueError("Real exports require an integer crop window")
    endpoints = config.get("endpoints", {})
    for name, coordinate in [(key, endpoints.get(key)) for key in ("habitat", "observation_primary", "observation_backup")] + [
        ("discovery_location", config.get("discovery_location")), ("drone_perch", config.get("drone_perch"))]:
        if not isinstance(coordinate, dict) or any(isinstance(coordinate.get(key), bool) or not isinstance(coordinate.get(key), (int,float)) or not math.isfinite(coordinate[key]) for key in ("lat", "lon")):
            raise ValueError(f"Confirmed coordinate required for {name}")
        if not -90 <= coordinate["lat"] <= 90 or not -180 <= coordinate["lon"] <= 180:
            raise ValueError(f"Signed latitude/longitude required for {name}")
    event("real_inputs_declared_reviewed", config_fingerprint=fingerprint(config), evidence="nasa_derived",
          source_dtm=Path(config["dtm"]).name, source_image=Path(config["image"]).name,
          scope="caller_review_declarations_not_automatic_scientific_verification")


@traced("pipeline_execution")
def run(output, config=None):
    """Export a complete bundle to output; absent config selects a labeled synthetic fixture."""
    output = Path(output)
    public_data = (Path(__file__).resolve().parents[1] / "public/data").resolve()
    if output.resolve() == public_data or public_data in output.resolve().parents:
        raise ValueError("Export to a separate handoff directory; public placeholders belong to Yasser")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    if config is None:
        terrain = Terrain(np.zeros((41, 41)), from_origin(0, 41, 1, 1),
                          "+proj=eqc +R=3389500 +units=m +no_defs", "synthetic-flat-grid", "simulated")
        start, end, discovery_cell = (20, 2), (20, 38), (20, 20)
        image = np.indices(terrain.elevation.shape).sum(axis=0).astype(float)
        config = {"sensor_radius_m": 10, "eva_minutes": 240, "speed_m_min": 20, "observation_minutes": 20, "approved": False}
    else:
        validate_real_config(config)
        artifact = np.load(config["artifact_mask"], allow_pickle=False)
        terrain = read_terrain(config["dtm"], tuple(config["window"]), artifact=artifact)
        endpoints = config["endpoints"]
        def cell(endpoint):
            """Convert confirmed endpoint lat/lon to an in-crop row/column cell."""
            lat, lon = endpoint["lat"], endpoint["lon"]
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError("Endpoint must use signed lat/lon")
            x, y = project(MARS_GEOGRAPHIC, terrain.crs, [lon], [lat])
            result = tuple(rasterio.transform.rowcol(terrain.transform, x[0], y[0]))
            if not 0 <= result[0] < terrain.elevation.shape[0] or not 0 <= result[1] < terrain.elevation.shape[1]:
                raise ValueError("Confirmed endpoint/perch/discovery lies outside the reviewed crop")
            return result
        start, end = cell(endpoints["habitat"]), cell(endpoints["observation_primary"])
        discovery_cell = cell(config["discovery_location"])
        cell(endpoints["observation_backup"])
        cell(config["drone_perch"])
        image = aligned_image(config["image"], terrain)
    analysis = analyze(terrain)
    hazard_inputs = {}
    if terrain.evidence != "simulated":
        hazard_inputs = {"edge_distance": np.load(config["edge_distance"], allow_pickle=False),
                         "foot_distance": np.load(config["foot_distance"], allow_pickle=False),
                         "scarp_height": config["scarp_height_m"], "apron_m": config["apron_m"],
                         "scarp_risk": np.load(config["scarp_risk"], allow_pickle=False)}
    masks = hazard_masks(terrain, analysis, **hazard_inputs)
    hazards = export_hazards(terrain, masks)
    event("execution_inputs", evidence=terrain.evidence, dataset_id=terrain.source, config_fingerprint=fingerprint(config))
    try:
        routes, hazard, discovery, cov = discovery_scenario(
            terrain, analysis, masks, start, end, discovery_cell,
            sensor_radius_m=config["sensor_radius_m"], approved=config.get("approved", False),
            eva_minutes=config["eva_minutes"], speed_m_min=config["speed_m_min"], observation_minutes=config["observation_minutes"])
    except InfeasibleMission as finding:
        # A valid "no viable route" finding: write the audit, never a fabricated discovery or mission bundle.
        points = {"habitat": start, "observation_primary": end}
        if terrain.evidence != "simulated":
            points["observation_backup"] = cell(config["endpoints"]["observation_backup"])
        report = audit_site(terrain, analysis, masks, points, config["eva_minutes"], config["speed_m_min"],
                            config["observation_minutes"])
        report["finding"] = str(finding)
        write_json(output / "feasibility_report.json", report)
        write_json(output / "hazards.geojson", hazards)
        event("mission_infeasible_reported", logging.WARNING, directory=str(output), verdict=report["verdict"],
              evidence=terrain.evidence, mission_bundle="not_exported", crew_clearance="not_established")
        return output
    hazards["features"].append(hazard)
    center = terrain.lonlat(terrain.elevation.shape[0] // 2, terrain.elevation.shape[1] // 2)
    def location(point):
        """Convert a row/column point to the contract's named lat/lon object."""
        lon, lat = terrain.lonlat(*point)
        return {"lat": lat, "lon": lon}
    mission = {
        "schema_version": "1.0", "site": {"name": terrain.source, "lon": center[0], "lat": center[1],
            "dtm_id": terrain.source, "image_id": config.get("image", "synthetic-display-grid")},
        "sun": {"ls_deg": 101.2, "local_time": "15:26", "elevation_deg": 42,
                "source": "Reference ESP_071006_2345 metadata; no shadow simulation"},
        "endpoints": {"habitat": location(start), "observation_primary": location(end),
                      "observation_backup": config["endpoints"]["observation_backup"] if terrain.evidence != "simulated" else location(end)},
        "stages": [{"id": stage, "title": title, "text": text, "stats": {}} for stage, title, text in [
            ("orbital", "Orbital planning", f"Terrain evidence: {terrain.evidence}. Speed {config['speed_m_min']} m/min is modeled; 30% EVA reserve."),
            ("rover", "Rover reconnaissance", "Simulated observations; stop and request human input. Alternative routes are precomputed, not authorized movement."),
            ("drone", "Drone inspection", "Drone coverage pending; no flight simulated."),
            ("eva", "Crew review", "Review evidence, route status and unscouted terrain before approval.")]],
        "alerts": {"eva": ["Planning demonstration; unscouted terrain is not certified safe"]},
        "drone": {"perch": config["drone_perch"] if terrain.evidence != "simulated" else location(end), "view_cone_id": "cov-drone-perch"},
        "discovery": discovery,
    }
    # Preserve the required reference without manufacturing a flight or field of view.
    # This nominal grid cell is an inspection marker at the proposed perch only.
    from pipeline.hazards import mask_features
    perch_cell = cell(config["drone_perch"]) if terrain.evidence != "simulated" else end
    perch_mask = np.zeros(terrain.elevation.shape, bool)
    perch_mask[perch_cell] = True
    marker = mask_features(perch_mask, terrain, "cov-drone-perch", {
        "state": "inspection_required", "simulated": True, "sensor": "none"})[0]
    marker["properties"]["id"] = "cov-drone-perch"
    cov["features"].append(marker)
    mission["stages"][2]["text"] = "No drone flight or view cone modeled. The proposed-perch grid cell marks inspection required, not checked coverage."
    for name, payload in (("hazards.geojson", hazards), ("routes.geojson", routes), ("coverage.geojson", cov), ("mission.json", mission)):
        write_json(output / name, payload)
    export_overlay(terrain, image, output / "hirise.jpg", config.get("image", "synthetic-display-grid"))
    export_overlay(terrain, analysis["slope"], output / "slope.png", terrain.source)
    validate_data(output, require_overlays=True)
    event("bundle_exported", directory=str(output), schema_version="1.0", evidence=terrain.evidence, files=sorted(path.name for path in output.iterdir()))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="Omit for explicitly synthetic demonstration")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    parser.add_argument("--log-file", type=Path, help="Optional JSONL path, normally pipeline/logs/run.jsonl")
    parser.add_argument("--human-log", action="store_true")
    args = parser.parse_args()
    configure_logging(args.log_level, args.log_file, args.human_log)
    with operation("cli_execution"):
        config = json.loads(args.config.read_text()) if args.config else None
        print(run(args.output, config))
