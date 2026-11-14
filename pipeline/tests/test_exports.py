import json

import pytest

from pipeline.run import run, validate_real_config
from pipeline.export import write_json
from pipeline.logging_config import configure_logging
from pipeline.validate_contract import validate_data


def test_end_to_end_deterministic_exports(tmp_path):
    """Compare all eight exported files byte-for-byte across two executions under tmp_path."""
    first = run(tmp_path / "first")
    second = run(tmp_path / "second")
    expected = {"hirise.jpg", "hirise.bounds.json", "slope.png", "slope.bounds.json",
                "hazards.geojson", "routes.geojson", "coverage.geojson", "mission.json"}
    assert {path.name for path in first.iterdir()} == expected
    for name in expected:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
    validate_data(first, require_overlays=True)


def test_refuses_overwrite_and_unreviewed_real_data(tmp_path):
    """Existing output and missing real-data review must fail without inventing inputs."""
    output = tmp_path / "existing"
    output.mkdir()
    (output / "file").write_text("keep")
    with pytest.raises(FileExistsError):
        run(output)
    with pytest.raises(ValueError, match="review"):
        run(tmp_path / "unreviewed", config={})


def test_rejects_tampered_route_statistics(tmp_path):
    """Tampering an inspection-required candidate's length must fail Mars-geometry validation."""
    output = run(tmp_path / "data")
    path = output / "routes.geojson"
    payload = json.loads(path.read_text())
    payload["features"][0]["properties"]["stats"]["length_m"] += 100
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Mars geometry"):
        validate_data(output, require_overlays=True)


@pytest.mark.parametrize("flag", ["alignment_reviewed", "qc_reviewed", "endpoints_confirmed", "scarp_measurements_reviewed"])
def test_real_review_gates_precede_file_io(flag):
    """Remove one confirmation flag; validation must stop before any source file is opened."""
    config = dict.fromkeys(("alignment_reviewed", "qc_reviewed", "endpoints_confirmed", "scarp_measurements_reviewed"), True)
    config[flag] = False
    with pytest.raises(ValueError, match=flag):
        validate_real_config(config)


def test_full_run_logging_preserves_outputs_and_references(tmp_path, caplog):
    """DEBUG/JSONL traces must share one run ID and leave data bytes/reference semantics unchanged."""
    first = run(tmp_path / "first")
    caplog.clear()
    try:
        configure_logging("DEBUG", jsonl=tmp_path / "run.jsonl")
        second = run(tmp_path / "second")
        for path in first.iterdir():
            assert path.read_bytes() == (second / path.name).read_bytes()
        records = [r for r in caplog.records if hasattr(r, "event")]
        assert len({r.run_id for r in records}) == 1
        assert {r.stage for r in records} >= {"pipeline_execution", "terrain_analysis", "discovery_simulation", "route_planning", "bundle_validation"}
        mission = json.loads((second / "mission.json").read_text())
        cov = json.loads((second / "coverage.geojson").read_text())
        marker = next(f for f in cov["features"] if f["properties"]["id"] == mission["drone"]["view_cone_id"])
        assert marker["properties"]["state"] == "inspection_required" and marker["properties"]["sensor"] == "none"
    finally:
        configure_logging()


def test_failed_json_export_does_not_truncate_existing_file(tmp_path):
    """Nonfinite payload must not replace the last valid JSON at the destination path."""
    path = tmp_path / "data.json"
    write_json(path, {"schema_version": "1.0"})
    original = path.read_bytes()
    with pytest.raises(ValueError):
        write_json(path, {"invalid": float("nan")})
    assert path.read_bytes() == original
