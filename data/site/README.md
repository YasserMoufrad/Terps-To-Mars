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

## Second scarp and the viewpoint move (2026-11-14, PR #17)

Geury's color check (`ice_zone_v2.geojson`) showed the east end of the main face is not bluish (0–13% vs 22–89% west/middle) and found a second bluish band. On the DTM that band is a **second north-facing scarp** (`upper-scarp-edge` / `upper-scarp-foot` in `scarp_lines.geojson`; up to 46 m, faces 64–67°). The old east-end viewpoint sat 20.0 m from its edge, so it was moved:

| Point | Position | Why |
| --- | --- | --- |
| Viewpoint | 54.172784°N, −147.894109 | Faces the bluest stretch of the second scarp (Geury: 29–43% bluish, −147.8962 to −147.8941), ~44 m face, 229 m from its foot; 0 cells ≥ 20° within 17 m; ~730 m walk from parking (steepest < 20°) |
| Backup viewpoint | 54.171114°N, −147.892507 | The earlier checked viewpoint, 112 m from the primary; faces the weaker-blue stretch (~16%); ~620 m walk |

Update (#18 integration): routes are stored at every 1 m DTM cell with diagonal corner-cuts across steep cells removed, the backup route runs between the backup viewpoint and the habitat (`pipeline.route_audit` objective for kind `backup`), and `public/data/route_audit.json` was regenerated: every crew and rover route is `candidate_requires_inspection`; the orbital guess is `excluded_terrain` (crosses the scarp face, as intended). Budget 149 of 168 min; walkback 238 of 240 min (tight).

The second scarp's rockfall zone uses the pipeline's single site-wide height (72.6 m, the main face's tallest profile), and routing keeps a further 12 m margin (85 m), so `pipeline.feasibility` agrees with the map; per-scarp heights would loosen it. Budget 135 of 168 min, walkback 221 of 240 min. Nic's audit from parking: `candidate_requires_inspection`, all points `no_mapped_exclusion`. Scripts: `tools/site/second_scarp_viewpoints.py` (args: DTM, site_report, final, out, routing buffer floor 85, drawn buffer floor 72.6), `merge_second_scarp.py`, `site_files_second_scarp.py`.

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
