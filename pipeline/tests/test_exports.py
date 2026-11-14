import json

import pytest

from pipeline.run import run
from pipeline.validate_contract import validate_data


def test_end_to_end_deterministic_exports(tmp_path):
    first = run(tmp_path / "first")
    second = run(tmp_path / "second")
    expected = {"hirise.jpg", "hirise.bounds.json", "slope.png", "slope.bounds.json",
                "hazards.geojson", "routes.geojson", "coverage.geojson", "mission.json"}
    assert {path.name for path in first.iterdir()} == expected
    for name in expected:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
    validate_data(first, require_overlays=True)


def test_refuses_overwrite_and_unreviewed_real_data(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "file").write_text("keep")
    with pytest.raises(FileExistsError):
        run(output)
    with pytest.raises(ValueError, match="review"):
        run(tmp_path / "unreviewed", config={})


def test_rejects_tampered_route_statistics(tmp_path):
    output = run(tmp_path / "data")
    path = output / "routes.geojson"
    payload = json.loads(path.read_text())
    payload["features"][0]["properties"]["stats"]["length_m"] += 100
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Mars geometry"):
        validate_data(output, require_overlays=True)
