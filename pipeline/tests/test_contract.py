import json
from pathlib import Path

import pytest

from pipeline.validate_contract import validate_collection, validate_data


DATA_DIR = Path(__file__).resolve().parents[2] / "public" / "data"


def test_placeholder_data_contract():
    validate_data(DATA_DIR)
    for name in ("hazards.geojson", "routes.geojson", "coverage.geojson", "mission.json"):
        payload = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        if name.endswith(".geojson"):
            assert payload["type"] == "FeatureCollection"
            ids = [feature["properties"]["id"] for feature in payload["features"]]
            assert len(ids) == len(set(ids))
            assert all(ids)


def test_hazard_evidence_labels():
    payload = json.loads((DATA_DIR / "hazards.geojson").read_text(encoding="utf-8"))
    for feature in payload["features"]:
        assert feature["properties"]["evidence"] in {
            "nasa_derived", "inferred", "simulated"
        }


def test_rejects_unsigned_longitude():
    payload = json.loads((DATA_DIR / "routes.geojson").read_text(encoding="utf-8"))
    payload["features"][0]["geometry"]["coordinates"][0][0] = 212.106
    with pytest.raises(ValueError, match="signed longitude"):
        validate_collection(payload, "routes.geojson")


def test_rejects_missing_hazard_evidence():
    payload = json.loads((DATA_DIR / "hazards.geojson").read_text(encoding="utf-8"))
    del payload["features"][0]["properties"]["evidence"]
    with pytest.raises(ValueError, match="evidence"):
        validate_collection(payload, "hazards.geojson")


def test_rejects_schema_version_mismatch():
    payload = json.loads((DATA_DIR / "coverage.geojson").read_text(encoding="utf-8"))
    payload["schema_version"] = "2.0"
    with pytest.raises(ValueError, match="schema_version"):
        validate_collection(payload, "coverage.geojson")
