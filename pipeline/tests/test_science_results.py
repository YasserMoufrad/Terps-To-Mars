"""Offline publication freshness and location traceability."""
import json
import shutil
from pathlib import Path
import pytest
from pipeline.science_results import verify, INPUTS, ARTIFACTS
from pipeline.tests.test_route_audit import grid_with_wall, lonlat, route, mission_for, RULES
from pipeline.route_audit import audit_route

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", INPUTS + ARTIFACTS)
def test_any_changed_input_or_report_is_rejected(tmp_path, name):
    """One-byte edits to any input/report must invalidate the entire analytical publication."""
    for file in INPUTS + ARTIFACTS + ("analysis_manifest.json",):
        shutil.copyfile(ROOT / "public/data" / file, tmp_path / file)
    with (tmp_path / name).open("a") as output:
        output.write(" ")
    with pytest.raises(ValueError, match="Stale analysis"):
        verify(tmp_path)


def test_current_publication_is_verified(caplog):
    """Verification emits a correlated aggregate event without per-cell logs."""
    with caplog.at_level("INFO"):
        verify(ROOT / "public/data")
    assert any("analysis_verified" in r.message for r in caplog.records)


def test_first_exclusion_is_an_actual_crossed_native_cell():
    """First exclusion retains coordinate, segment and local slope rather than route maximum."""
    grid = grid_with_wall()
    coords = [lonlat(grid, 10), lonlat(grid, 90)]
    result = audit_route(route(coords), mission_for(coords[0], coords[1]), grid, RULES)
    cell = result["first_exclusion"]
    crossed = {k: cell[k] for k in ("segment_index", "coordinates", "col", "row", "slope", "limit")}
    assert any(all(c[k] == v for k, v in crossed.items()) for c in result["cells"]), "first exclusion is a crossed cell"
    assert cell["coordinates"] == pytest.approx(grid.cell_lonlat(cell["col"], cell["row"]), abs=1e-7)
    assert [cell["lon"], cell["lat"]] == cell["coordinates"] and cell["kind"] == "slope"
    assert cell["slope"] >= cell["limit"] and cell["segment_index"] == 0
    assert cell["distance_m"] == pytest.approx(result["first_exclusion_at_m"], abs=.1)


def test_backup_objective_is_a_declared_mission_pair():
    """A backup joins the habitat with a declared viewpoint (main #19: either one); never an invented point."""
    grid = grid_with_wall()
    coords = [lonlat(grid, 10), lonlat(grid, 40)]
    result = audit_route(route(coords, kind="backup"), mission_for(coords[0], coords[1]), grid, RULES)
    assert result["objective"] in ("habitat->observation_backup", "habitat->observation_primary")
    no_viewpoints = {"endpoints": {"habitat": mission_for(coords[0], coords[1])["endpoints"]["habitat"]}}
    undeclared = audit_route(route(coords, kind="backup"), no_viewpoints, grid, RULES)
    assert undeclared["objective"] == "undeclared" and "end_offset_m" not in undeclared


def test_walk_only_adapter_has_measured_leg_length(tmp_path):
    """A short walk-only schema-1.0 route must not fail fabricated-leg validation."""
    from pipeline.science_results import itinerary_results
    feature = {"type": "Feature", "properties": {"id": "walk", "agent": "crew", "kind": "main", "version": "before", "stats": {}},
               "geometry": {"type": "LineString", "coordinates": [[0, 0], [.001, 0]]}}
    routes = {"features": [feature]}
    (tmp_path / "routes.geojson").write_text(json.dumps(routes))
    results = itinerary_results(routes, tmp_path, RULES, 240, 20, 20)
    assert results[0]["accepted_budget"] is True
    assert results[0]["leg_problems"] == []
    assert "legs" not in feature["properties"]
