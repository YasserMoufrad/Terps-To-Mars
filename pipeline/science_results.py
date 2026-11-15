"""Publish offline analytical results with exact input/artifact digests."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from pipeline.export import write_json
from pipeline.route_audit import audit_file, load_grid
from pipeline.terrain import analyze, load_rules
from pipeline.hazards import hazard_masks
from pipeline.feasibility import audit_site, _cell
from pipeline.itinerary import evaluate_file, evaluate_mixed, backup_independence, polyline_m
from pipeline.logging_config import configure_logging, event, operation

INPUTS = ("routes.geojson", "mission.json", "hazards.geojson", "coverage.geojson",
          "scarp_lines.geojson", "science_targets.json", "slope.meta.json", "slope.bounds.json",
          "analysis_rules.json", "terrain_source.json", "slope.png")
ALGORITHMS = ("science_results.py", "route_audit.py", "terrain.py", "hazards.py", "feasibility.py", "itinerary.py", "routing.py")
REPORT_INPUTS = {"route_audit.json":["routes.geojson","mission.json","hazards.geojson","coverage.geojson","scarp_lines.geojson","science_targets.json","slope.meta.json","slope.bounds.json","slope.png","analysis_rules.json","terrain_source.json","route_audit.json"],"terrain_samples.json":["terrain_source.json","analysis_rules.json","terrain_samples.json"],"feasibility_report.json":["mission.json","scarp_lines.geojson","analysis_rules.json","terrain_source.json","feasibility_report.json"],"itinerary_report.json":["routes.geojson","mission.json","analysis_rules.json","itinerary_report.json"]}
ARTIFACTS = ("route_audit.json", "terrain_samples.json", "feasibility_report.json", "itinerary_report.json")


def digest(path):
    """Hash exact bytes at path; streaming keeps raw DTM hashing bounded."""
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify(data_dir):
    """Refuse stale publications; data_dir contains inputs and analytical artifacts."""
    root = Path(data_dir)
    manifest = json.loads((root / "analysis_manifest.json").read_text())
    expected = set(INPUTS) | set(ARTIFACTS)
    algorithms = manifest.get("algorithms", {})
    if set(algorithms) != set(ALGORITHMS) or any(digest(Path(__file__).parent / name) != sha for name, sha in algorithms.items()):
        raise ValueError("Analysis generator changed — regenerate science results")
    if manifest.get("schema_version") != "1.0" or manifest.get("report_inputs") != REPORT_INPUTS or set(manifest.get("files", {})) != expected:
        raise ValueError("Incomplete analysis manifest")
    changed = [name for name, sha in manifest["files"].items()
               if not (root / name).is_file() or digest(root / name) != sha]
    rules = json.loads((root / "analysis_rules.json").read_text())
    if rules != load_rules():
        changed.append("pipeline/hazard_rules.json")
    if changed:
        event("analysis_stale", changed=changed, outcome="rejected")
        raise ValueError("Stale analysis — regenerate: " + ", ".join(changed))
    event("analysis_verified", files=len(expected), outcome="current")
    return manifest


def publish(data_dir, dtm, eva_minutes=240, walk_speed=20, site_minutes=20, sites=Path("pipeline/site/mission_sites.json")):
    """Publish current mission analyses; DTM is immutable NASA input, times are modeled minutes.

    sites: mission_sites.json whose scarp profiles drive the audit's edge-setback/rockfall checks, so this audit
    matches the one pipeline.mission_geography publishes (same zones, same fingerprint).
    """
    root = Path(data_dir)
    rules = load_rules()
    mission = json.loads((root / "mission.json").read_text())
    routes = json.loads((root / "routes.geojson").read_text())
    write_json(root / "analysis_rules.json", rules)
    write_json(root / "terrain_source.json", {"schema_version": "1.0", "source": Path(dtm).name,
               "sha256": digest(dtm), "evidence": "nasa_derived",
               "artifact_review": "not_reviewed", "vertical_uncertainty_m": None})
    audit = audit_file(root / "routes.geojson", root / "mission.json", dtm,
                       root / "scarp_lines.geojson", rules, sites_path=sites if Path(sites).is_file() else None)
    write_json(root / "route_audit.json", audit)
    coords = [c for f in routes["features"] for c in f["geometry"]["coordinates"]]
    coords += [[p["lon"], p["lat"]] for p in mission["endpoints"].values()]
    # Include published scarp geometry in numeric inspection coverage.
    scarp = json.loads((root / "scarp_lines.geojson").read_text())
    coords += [c for f in scarp["features"] for c in f["geometry"]["coordinates"]]
    grid = load_grid(dtm, coords, rules)
    analysis = analyze(grid.terrain, rules)
    height, width = grid.slope.shape
    stride = max(1, math.ceil(max(height, width) / 128))
    samples = []
    for row in range(0, height, stride):
        for col in range(0, width, stride):
            known = bool(grid.valid[row, col])
            rough = analysis["roughness"][row, col]
            samples.append([*grid.cell_lonlat(col, row),
                            float(grid.terrain.elevation[row, col]) if known else None,
                            float(grid.slope[row, col]) if known else None,
                            float(rough) if known and np.isfinite(rough) else None,
                            "valid_unreviewed" if known else "unknown", col, row])
    write_json(root / "terrain_samples.json", {
        "schema_version": "1.0", "evidence": "nasa_derived", "source": Path(dtm).name,
        "stride_cells": stride, "columns": ["lon", "lat", "elevation_m", "slope_deg", "roughness_m", "quality", "col", "row"],
        "bounds": {"west": min(c[0] for c in coords), "east": max(c[0] for c in coords),
                   "south": min(c[1] for c in coords), "north": max(c[1] for c in coords)},
        "artifact_review": "not_reviewed", "vertical_uncertainty_m": None,
        "limitations": "Sparse native-cell samples, never interpolation. Report sample coordinate and offset. No reviewed artifact mask; valid does not mean artifact-free.",
        "samples": samples})
    points = {name: _cell(grid.terrain, point, name) for name, point in mission["endpoints"].items()
              if name in ("habitat", "observation_primary", "observation_backup")}
    masks = hazard_masks(grid.terrain, analysis, rules)
    feasibility = audit_site(grid.terrain, analysis, masks, points, eva_minutes, walk_speed, site_minutes, rules)
    write_json(root / "feasibility_report.json", feasibility)
    write_json(root / "itinerary_report.json", {
        "schema_version": "1.0", "evidence": "inferred", "crew_clearance": "not_established",
        "inputs": {"eva_minutes": eva_minutes, "walk_speed_m_min": walk_speed, "site_minutes": site_minutes},
        "limitations": "Mixed-mode budgets are computed only for routes with declared legs. Empty results mean not measured.",
        "results": itinerary_results(routes, root, rules, eva_minutes, walk_speed, site_minutes)})
    # Pin LF and compact scientific arrays before exact-byte digest generation.
    for name in INPUTS + ARTIFACTS:
        if name.endswith('.png'):
            continue
        path = root / name
        payload = json.loads(path.read_text())
        path.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    manifest = {"schema_version": "1.0", "report_inputs": REPORT_INPUTS, "algorithms": {name: digest(Path(__file__).parent / name) for name in ALGORITHMS}, "files": {name: digest(root / name) for name in INPUTS + ARTIFACTS}}
    write_json(root / "analysis_manifest.json", manifest)
    verify(root)
    event("science_results_published", files=len(manifest["files"]), samples=len(samples),
          feasibility=feasibility["verdict"], artifact_review="not_reviewed", crew_clearance="not_established")


def itinerary_results(routes, root, rules, eva_minutes, walk_speed, site_minutes):
    """Evaluate declared mixed legs or explicit crew walk-only semantics; never invent parking."""
    results = evaluate_file(root / "routes.geojson", rules, eva_minutes, {"drive": 83.3, "walk": walk_speed}, site_minutes)
    crew = [f for f in routes["features"] if f["properties"].get("agent") == "crew"
            and len(f["geometry"]["coordinates"]) >= 2]
    for feature in crew:
        if not feature["properties"].get("legs"):
            adapted = json.loads(json.dumps(feature))
            adapted["properties"]["legs"] = [{"mode": "walk", "from": 0, "to": len(feature["geometry"]["coordinates"]) - 1, "length_m": polyline_m(feature["geometry"]["coordinates"])}]
            result = evaluate_mixed(adapted, rules, eva_minutes, {"drive": 83.3, "walk": walk_speed}, site_minutes)
            result["mode_basis"] = "schema 1.0 crew route assumed walk-only; two-way retrace arithmetic, not a declared return objective"
            results.append(result)
    for version in ("before", "after"):
        main = next((f for f in crew if f["properties"].get("kind") == "main" and f["properties"].get("version") == version), None)
        backup = next((f for f in crew if f["properties"].get("kind") == "backup" and f["properties"].get("version") == version), None)
        if main and backup and not any(r.get("main_id") == main["properties"]["id"] for r in results):
            results.append(backup_independence(main, backup))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("public/data"))
    parser.add_argument("--dtm", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    configure_logging()
    with operation("science_results"):
        if args.verify:
            verify(args.data_dir)
        elif args.dtm:
            publish(args.data_dir, args.dtm)
        else:
            parser.error("--dtm is required to regenerate results")
