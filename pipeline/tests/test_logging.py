import json
import logging
from io import BytesIO
from datetime import datetime

import numpy as np
import pytest
from rasterio.transform import from_origin

from pipeline.logging_config import LOGGER, JsonFormatter, configure_logging, event, fingerprint, operation, traced
from pipeline.terrain import Terrain, analyze
from pipeline.hazards import hazard_masks, export_hazards
from pipeline.tests.test_terrain import terrain, CRS
from pipeline import acquire


def records(caplog, name):
    return [r for r in caplog.records if getattr(r, "event", None) == name]


def test_significant_stages_have_consistent_context(caplog):
    t = terrain()
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=LOGGER.name):
        with operation("pipeline_execution"):
            a = analyze(t)
            export_hazards(t, hazard_masks(t, a))
    entries = [r for r in caplog.records if r.name == LOGGER.name]
    assert len({r.run_id for r in entries}) == 1
    assert {r.stage for r in entries} >= {"slope_computation", "roughness_computation", "hazard_generation", "hazard_export"}
    for record in entries:
        payload = json.loads(JsonFormatter().format(record))
        assert datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
        assert payload["run_id"] != "unscoped" and payload["stage"] and payload["event"]


def test_missing_scarp_measurements_warn(caplog):
    t = terrain()
    risk = np.zeros(t.elevation.shape, bool)
    risk[:, 5] = True
    masks = hazard_masks(t, analyze(t), scarp_risk=risk)
    assert masks["inspection_required"][:, 5].all()
    record = records(caplog, "scarp_measurements_missing")[-1]
    assert record.levelno == logging.WARNING
    assert set(record.fields["missing"]) == {"edge_geometry", "foot_geometry", "scarp_height", "visible_apron"}


def test_invalid_metadata_logs_error_and_propagates(caplog):
    with pytest.raises(ValueError, match="Mars"):
        Terrain(np.zeros((4, 4)), from_origin(0, 4, 1, 1), "EPSG:3857", "bad", "simulated")
    assert any(r.levelno == logging.ERROR and r.exc_info for r in records(caplog, "operation_failed"))


def test_jsonl_and_deterministic_outputs(tmp_path):
    t = terrain()
    first = export_hazards(t, hazard_masks(t, analyze(t)))
    path = tmp_path / "events.jsonl"
    try:
        configure_logging("DEBUG", jsonl=path)
        second = export_hazards(t, hazard_masks(t, analyze(t)))
        for handler in LOGGER.handlers:
            handler.flush()
        entries = [json.loads(line) for line in path.read_text().splitlines()]
        assert entries and all(entry["run_id"] and entry["stage"] and entry["event"] for entry in entries)
        assert first == second
    finally:
        configure_logging()


def test_format_failure_does_not_turn_validation_into_success():
    record = logging.LogRecord(LOGGER.name, logging.ERROR, __file__, 1, "failure", (), None)
    record.event, record.run_id, record.stage = "validation_failed", "test", "validation"
    record.fields = {"invalid": float("nan")}
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "validation_failed" and payload["level"] == "ERROR"
    assert payload["logging_error"]

    class BrokenHandler(logging.Handler):
        def emit(self, record):
            raise RuntimeError("broken handler")
    broken = BrokenHandler()
    LOGGER.addHandler(broken)
    try:
        with pytest.raises(ValueError, match="Mars"):
            Terrain(np.zeros((4, 4)), from_origin(0, 4, 1, 1), "EPSG:3857", "bad", "simulated")
    finally:
        LOGGER.removeHandler(broken)


def test_unexpected_exception_not_suppressed(caplog):
    @traced("example")
    def fail():
        raise RuntimeError("unexpected")
    with pytest.raises(RuntimeError, match="unexpected"):
        fail()
    assert records(caplog, "operation_failed")[-1].exc_info


def test_config_fingerprint_does_not_expose_contents(caplog):
    secret = "example-private-test-value"
    with operation("execution"):
        event("configuration", config_fingerprint=fingerprint({"token": secret}))
    assert secret not in caplog.text


def test_acquisition_integrity_failure_is_observable(tmp_path, monkeypatch, caplog):
    response = BytesIO(b"partial")
    response.headers = {"Content-Length": "1000"}
    monkeypatch.setattr(acquire, "urlopen", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="Incomplete"):
        acquire.download("dtm", tmp_path)
    assert records(caplog, "integrity_failure")
    assert records(caplog, "download_failed")[-1].exc_info
    assert not list(tmp_path.iterdir())
