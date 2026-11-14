"""Run synthetic demonstration or an explicitly configured real raster crop."""

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform as project

from pipeline.terrain import Terrain, MARS_GEOGRAPHIC, analyze, read_terrain
from pipeline.hazards import hazard_masks, export_hazards
from pipeline.routing import plan_routes
from pipeline.scenario import discovery_scenario, coverage
from pipeline.export import aligned_image, export_overlay, write_json
from pipeline.validate_contract import validate_data


def run(output, config=None):
    output = Path(output)
    if output.resolve() == (Path(__file__).resolve().parents[1] / "public/data").resolve():
        raise ValueError("Export to a separate handoff directory; public placeholders belong to Yasser")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    if config is None:
        terrain = Terrain(np.zeros((41, 41)), from_origin(0, 410, 10, 10),
                          "+proj=eqc +R=3389500 +units=m +no_defs", "synthetic-flat-grid", "simulated")
        start, end, discovery_cell = (20, 2), (20, 38), (20, 20)
        image = np.indices(terrain.elevation.shape).sum(axis=0).astype(float)
        config = {"sensor_radius_m": 20, "eva_minutes": 240, "speed_m_min": 20, "approved": False}
    else:
        if config.get("alignment_reviewed") is not True or config.get("qc_reviewed") is not True:
            raise ValueError("Real exports require manual alignment and artifact QC review")
        artifact = np.load(config["artifact_mask"], allow_pickle=False)
        terrain = read_terrain(config["dtm"], tuple(config["window"]), artifact=artifact)
        endpoints = config["endpoints"]
        def cell(endpoint):
            lat, lon = endpoint["lat"], endpoint["lon"]
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError("Endpoint must use signed lat/lon")
            x, y = project(MARS_GEOGRAPHIC, terrain.crs, [lon], [lat])
            return tuple(rasterio.transform.rowcol(terrain.transform, x[0], y[0]))
        start, end = cell(endpoints["habitat"]), cell(endpoints["observation_primary"])
        discovery_cell = cell(config["discovery_location"])
        image = aligned_image(config["image"], terrain)
    analysis = analyze(terrain)
    hazard_inputs = {}
    if terrain.evidence != "simulated":
        hazard_inputs = {"edge_distance": np.load(config["edge_distance"], allow_pickle=False),
                         "foot_distance": np.load(config["foot_distance"], allow_pickle=False),
                         "scarp_height": config["scarp_height_m"], "apron_m": config["apron_m"]}
    masks = hazard_masks(terrain, analysis, **hazard_inputs)
    hazards = export_hazards(terrain, masks)
    if discovery_cell is not None:
        routes, hazard, discovery, cov = discovery_scenario(
            terrain, analysis, masks, start, end, discovery_cell,
            sensor_radius_m=config["sensor_radius_m"], approved=config.get("approved", False),
            eva_minutes=config["eva_minutes"], speed_m_min=config["speed_m_min"])
        hazards["features"].append(hazard)
    else:
        routes, _, _ = plan_routes(terrain, analysis, masks, start, end,
                                  eva_minutes=config["eva_minutes"], speed_m_min=config["speed_m_min"])
        discovery = None
        cov = coverage(terrain, analysis, [], config["sensor_radius_m"])
    center = terrain.lonlat(terrain.elevation.shape[0] // 2, terrain.elevation.shape[1] // 2)
    def location(point):
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
        "drone": {"perch": config["drone_perch"] if terrain.evidence != "simulated" else location(end), "view_cone_id": ""},
        "discovery": discovery,
    }
    for name, payload in (("hazards.geojson", hazards), ("routes.geojson", routes), ("coverage.geojson", cov), ("mission.json", mission)):
        write_json(output / name, payload)
    export_overlay(terrain, image, output / "hirise.jpg", config.get("image", "synthetic-display-grid"))
    export_overlay(terrain, analysis["slope"], output / "slope.png", terrain.source)
    validate_data(output, require_overlays=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="Omit for explicitly synthetic demonstration")
    args = parser.parse_args()
    config = json.loads(args.config.read_text()) if args.config else None
    print(run(args.output, config))
