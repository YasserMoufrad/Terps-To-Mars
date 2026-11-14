# data/site: site inputs and measurements

Inputs for Nic's pipeline and for the placeholder map. The app does not load these files (they are not part of the `public/data/` contract). Nothing here is crew clearance.

| File | What | How it was made |
| --- | --- | --- |
| `scarp_lines.geojson` | The real ice-scarp **top edge** and **foot** (about 54.1636°N and 54.1645°N, −147.9175 to −147.8939) | Traced in Nic's 0.25 m HiRISE crop (ESP_071006_2345 RED_A): the shadowed north-facing face is a dark strip (brightness < 95 vs 115–140 on the plain). `tools/site/trace_scarp.py` |
| `scarp_measurements.json` | Per-profile scarp height, apron, steepest face slope; Geury's first-pass point checks; DTM route stats | HiRISE DTM `DTEEC_071085_2345_071006_2345_A01` with the pipeline's own `read_terrain`/`analyze`. Height median **59 m** (23–73 m), face 64–75°. `tools/site/measure_site.py` |
| `site_points_dtm.geojson` | **DTM-checked candidate points**: habitat, crew-rover parking, viewpoint, backup viewpoint, drone perch | No cell ≥ 20° within each point's 15 m uncertainty disc. `tools/site/optimize_points.py`, `final_routes.py` |
| `site_points.geojson` | Geury's first-pass points (kept for reference) | Rebuilt from his site-pack tables |
| `ice_zone.geojson` | Geury's ice zones (kept for reference) | Rebuilt from his site-pack tables. **His "main band" (54.1608–54.1619) sits on featureless plain; the real face is about 200 m north, inside his "upper band"** |
| `feasibility_audit.json` | Nic's `pipeline.feasibility` config: DTM-checked points, walking the whole way | Expected `infeasible` (about 4 km straight-line round trip) |
| `feasibility_audit_from_parking.json` | Same audit for the walking part of drive-then-walk, starting at the crew-rover parking point | `eva_minutes` reduced so the audit's 70% equals what is left after the drive |

## Key findings (2026-11-14)

- The tall middle of the face (60–72 m) sits above an enclosed, rough pit floor. The crew rover (< 24°, roughness ≤ 0.5 m) cannot get near it; the nearest parking is about 1.9 km on foot from a safe viewpoint, so it does not fit the EVA budget. The **east end** (23–35 m tall) is reachable: drive 2.3 km to the plain beside it, then walk about 290 m around the end to a bench viewpoint 145 m from the foot (rockfall zone there 101 m).
- The drone perch is on the pit floor facing the tallest face (131 m from the foot), the part the crew cannot reach.
- Budget for the placeholder trip: 83 min travel + 20 min site work = 103 of 168 min; walkback (rover fails at parking) 189 of 240 min EVA.

## Nic's feasibility audit with these scarp inputs

`tools/site/make_scarp_inputs.py <config> <out_dir>` turns the traced lines and measurements into the pipeline's scarp inputs (`edge_distance.npy`, `foot_distance.npy`, `scarp_risk.npy`, `scarp_height_m` 72.6 = tallest profile, `apron_m` 55.3 = median) on exactly the crop the config resolves to, and writes `config.json` next to them under git-ignored `pipeline/output/`. Results on the real DTM (2026-11-14, after #13 merged):

| Config | Verdict | Detail |
| --- | --- | --- |
| `feasibility_audit.json` (walk all the way) | `infeasible` | straight-line lower bound 249–272 min |
| `feasibility_audit_from_parking.json` (walking part) | `candidate_requires_inspection` | routed 56–81 min per itinerary; remaining reason `unscouted_terrain`; every point `no_mapped_exclusion` |

```bash
uv run python tools/site/make_scarp_inputs.py data/site/feasibility_audit_from_parking.json pipeline/output/si/park
uv run python -m pipeline.feasibility --config pipeline/output/si/park/config.json --output pipeline/output/audit-park
```

The scarp inputs are Yasser's agent's measurements, not yet reviewed by Nic.

Re-run (needs the DTM in `pipeline/raw/`, see `pipeline/README.md`; set `PYTHONPATH` to the repo root):

```bash
uv run python tools/site/measure_site.py pipeline/raw/DTEEC_071085_2345_071006_2345_A01.IMG data/site/scarp_lines.geojson data/site/site_points.geojson site_report.json
```

Then `optimize_points.py`, `final_routes.py`, `build_contract.py` and `site_files.py` in that order (each prints its arguments in its docstring).

Coordinates are GeoJSON `[longitude, latitude]` with longitude in −180..180. Blue tones in HiRISE color are consistent with ice but are not proof; cite Dundas et al. (2018) and CRISM results (`docs/IMPLEMENTATION.md`, section 2).
