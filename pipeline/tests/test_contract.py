import json
from pathlib import Path

import pytest

from pipeline.validate_contract import validate_collection, validate_data


DATA_DIR = Path(__file__).resolve().parents[2] / "public" / "data"


def test_placeholder_data_contract():
    """Validate committed DATA_DIR fixtures, including schema and stable IDs."""
    validate_data(DATA_DIR)
    for name in ("hazards.geojson", "routes.geojson", "coverage.geojson", "mission.json"):
        payload = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
        assert payload["schema_version"] in {"1.0", "1.1"}
        if name.endswith(".geojson"):
            assert payload["type"] == "FeatureCollection"
            ids = [feature["properties"]["id"] for feature in payload["features"]]
            assert len(ids) == len(set(ids))
            assert all(ids)


def test_hazard_evidence_labels():
    """Check fixture hazards explicitly classify their evidence source."""
    payload = json.loads((DATA_DIR / "hazards.geojson").read_text(encoding="utf-8"))
    for feature in payload["features"]:
        assert feature["properties"]["evidence"] in {
            "nasa_derived", "inferred", "simulated"
        }


def test_rejects_unsigned_longitude():
    """Reject an east-positive 212° coordinate in signed GeoJSON."""
    payload = json.loads((DATA_DIR / "routes.geojson").read_text(encoding="utf-8"))
    payload["features"][0]["geometry"]["coordinates"][0][0] = 212.106
    with pytest.raises(ValueError, match="signed longitude"):
        validate_collection(payload, "routes.geojson")


def test_rejects_missing_hazard_evidence():
    """Ensure deleting a fixture evidence label fails validation."""
    payload = json.loads((DATA_DIR / "hazards.geojson").read_text(encoding="utf-8"))
    del payload["features"][0]["properties"]["evidence"]
    with pytest.raises(ValueError, match="evidence"):
        validate_collection(payload, "hazards.geojson")


def test_rejects_schema_version_mismatch():
    """Reject a fixture payload claiming an incompatible schema version."""
    payload = json.loads((DATA_DIR / "coverage.geojson").read_text(encoding="utf-8"))
    payload["schema_version"] = "2.0"
    with pytest.raises(ValueError, match="schema_version"):
        validate_collection(payload, "coverage.geojson")


def _route_with_legs():
    """A minimal 1.1 crew route over three positions with a drive leg then a walk leg."""
    stats = {"length_m": 2, "round_trip_m": 4, "est_time_min": 1, "elevation_gain_m": 0, "max_slope_deg": 0, "shared_with_main_m": 0}
    legs = [{"mode": "drive", "from": 0, "to": 1, "length_m": 1, "est_time_min": 1},
            {"mode": "walk", "from": 1, "to": 2, "length_m": 1, "est_time_min": 1}]
    feature = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-147.9, 54.13], [-147.9, 54.14], [-147.9, 54.15]]},
               "properties": {"id": "r", "kind": "main", "agent": "crew", "version": "after", "status": "inspection_required",
                              "stats": stats, "legs": legs, "walkback_min": 5}}
    return {"schema_version": "1.1", "type": "FeatureCollection", "features": [feature]}


def test_route_legs_accepted_in_1_1_and_rejected_in_1_0():
    """Legs are a 1.1 feature; a 1.0 file must stay walk-only."""
    validate_collection(_route_with_legs(), "routes.geojson")
    payload = _route_with_legs()
    payload["schema_version"] = "1.0"
    with pytest.raises(ValueError, match="1.1"):
        validate_collection(payload, "routes.geojson")


def test_rejects_malformed_route_legs():
    """Legs must use drive/walk and run end to end over the whole line."""
    payload = _route_with_legs()
    payload["features"][0]["properties"]["legs"][0]["mode"] = "fly"
    with pytest.raises(ValueError, match="mode"):
        validate_collection(payload, "routes.geojson")
    payload = _route_with_legs()
    payload["features"][0]["properties"]["legs"].pop()
    with pytest.raises(ValueError, match="whole line"):
        validate_collection(payload, "routes.geojson")