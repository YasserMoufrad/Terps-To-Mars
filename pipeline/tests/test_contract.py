import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[2] / "public" / "data"


def test_placeholder_data_contract():
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
