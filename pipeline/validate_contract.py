"""Validate the JSON handoff between the Python pipeline and React app."""

import json
import math
from pipeline.logging_config import traced, event
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "public" / "data"
COLLECTIONS = ("hazards.geojson", "routes.geojson", "coverage.geojson")
ROUTE_STATUSES = {"ok", "no_viable_route", "backup_unavailable", "inspection_required"}
EVIDENCE = {"nasa_derived", "inferred", "simulated"}


def _enum(properties, field, values):
    if properties.get(field) not in values:
        raise ValueError(f"Invalid or missing {field}")


def _geometry(geometry):
    coordinates = geometry["coordinates"]
    if geometry["type"] == "Point":
        _position(coordinates)
    elif geometry["type"] == "LineString":
        if len(coordinates) < 2:
            raise ValueError("LineString requires at least two positions")
        for point in coordinates:
            _position(point)
    else:
        if not coordinates:
            raise ValueError("Polygon requires rings")
        for ring in coordinates:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("Polygon requires closed rings")
            for point in ring:
                _position(point)


def _position(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("GeoJSON position must be [longitude, latitude]")
    lon, lat = value
    if (isinstance(lon, bool) or isinstance(lat, bool)
            or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float))
            or not -180 <= lon <= 180 or not -90 <= lat <= 90):
        raise ValueError("GeoJSON position is outside signed longitude/latitude bounds")


def _coordinates(value):
    if not isinstance(value, list) or not value:
        raise ValueError("GeoJSON coordinates must be nonempty")
    if isinstance(value[0], (int, float)):
        _position(value)
    else:
        for child in value:
            _coordinates(child)


@traced("schema_validation")
def validate_collection(payload, name):
    if payload.get("schema_version") != "1.0":
        raise ValueError(f"{name}: expected schema_version 1.0")
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError(f"{name}: expected FeatureCollection")

    seen = set()
    for feature in payload["features"]:
        properties = feature.get("properties", {})
        feature_id = properties.get("id")
        if not isinstance(feature_id, str) or not feature_id or feature_id in seen:
            raise ValueError(f"{name}: missing or duplicate feature id")
        seen.add(feature_id)
        if feature.get("type") != "Feature":
            raise ValueError(f"{name}: expected Feature")
        geometry = feature.get("geometry", {})
        expected_types = {
            "hazards.geojson": {"Point", "Polygon"},
            "routes.geojson": {"LineString"},
            "coverage.geojson": {"Polygon"},
        }
        if geometry.get("type") not in expected_types[name]:
            raise ValueError(f"{name}: invalid geometry type")
        coordinates = geometry.get("coordinates")
        if name == "routes.geojson" and properties.get("status") != "ok" and coordinates == []:
            pass
        else:
            _coordinates(coordinates)
            _geometry(geometry)

        if name == "hazards.geojson" and properties.get("evidence") not in EVIDENCE:
            raise ValueError(f"{name}: missing hazard evidence label")
        if name == "hazards.geojson":
            _enum(properties, "type", {"U", "O", "S"})
            _enum(properties, "category", {"slope", "roughness", "rockfall", "edge", "soft_ground", "void", "shadow", "no_data", "artifact"})
            _enum(properties, "severity", {"exclude", "caution"})
            _enum(properties, "agent", {"crew", "rover", "both"})
            _enum(properties, "stage", {"orbital", "rover", "drone", "eva"})
            if not all(isinstance(properties.get(key), str) and properties[key] for key in ("source", "note")):
                raise ValueError("Hazard source and note required")
        if name == "routes.geojson" and properties.get("status") not in ROUTE_STATUSES:
            raise ValueError(f"{name}: invalid route status")
        if name == "routes.geojson":
            _enum(properties, "kind", {"orbital_guess", "main", "backup", "rover_path"})
            _enum(properties, "agent", {"crew", "rover"})
            _enum(properties, "version", {"before", "after"})
            stats = properties.get("stats", {})
            for key in ("length_m", "round_trip_m", "est_time_min", "elevation_gain_m", "max_slope_deg", "shared_with_main_m"):
                value = stats.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"Invalid route statistic {key}")
        if name == "coverage.geojson":
            _enum(properties, "state", {"orbit_only", "rover_checked", "drone_checked", "unscouted", "inspection_required"})
            _enum(properties, "sensor", {"stereo_cam", "hazard_cam", "thermal", "drone_cam", "none"})
            if not isinstance(properties.get("simulated"), bool):
                raise ValueError("Coverage simulated flag must be boolean")
        if name == "coverage.geojson" and properties.get("state") in {"rover_checked", "drone_checked"}:
            if properties.get("simulated") is not True:
                raise ValueError(f"{name}: robot coverage must be simulated")


def _validate_lat_lon_objects(value):
    if isinstance(value, dict):
        if "lat" in value or "lon" in value:
            lat, lon = value.get("lat"), value.get("lon")
            if (isinstance(lat, bool) or isinstance(lon, bool)
                    or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
                    or not -90 <= lat <= 90 or not -180 <= lon <= 180):
                raise ValueError("JSON coordinate object must use valid lat/lon")
        for child in value.values():
            _validate_lat_lon_objects(child)
    elif isinstance(value, list):
        for child in value:
            _validate_lat_lon_objects(child)


@traced("bundle_validation")
def validate_data(data_dir=DATA_DIR, require_overlays=False):
    data_dir = Path(data_dir)
    for name in COLLECTIONS:
        payload = json.loads((data_dir / name).read_text(encoding="utf-8"))
        validate_collection(payload, name)
    mission = json.loads((data_dir / "mission.json").read_text(encoding="utf-8"))
    if mission.get("schema_version") != "1.0":
        raise ValueError("mission.json: expected schema_version 1.0")
    _validate_lat_lon_objects(mission)
    if mission.get("discovery", {}).get("evidence") != "simulated":
        raise ValueError("mission.json: rover discovery must be simulated")
    if require_overlays:
        from PIL import Image
        for basename, extension in (("hirise", "jpg"), ("slope", "png")):
            with Image.open(data_dir / f"{basename}.{extension}") as image:
                image.verify()
            bounds = json.loads((data_dir / f"{basename}.bounds.json").read_text())
            if bounds.get("schema_version") != "1.0":
                raise ValueError("Overlay schema version mismatch")
            if not (-180 <= bounds["west"] < bounds["east"] <= 180 and -90 <= bounds["south"] < bounds["north"] <= 90):
                raise ValueError("Invalid overlay bounds")
            if not bounds.get("source") or not bounds.get("processing"):
                raise ValueError("Overlay provenance required")
    event("data_contract_validated", schema_version="1.0", directory=str(data_dir), require_overlays=require_overlays)


if __name__ == "__main__":
    validate_data()
    print("Data contract valid")
