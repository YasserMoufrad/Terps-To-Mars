# public/data: contract files

The full contract is section 4 of [docs/IMPLEMENTATION.md](../../docs/IMPLEMENTATION.md). This folder holds the files the app loads.

| File | Status |
| --- | --- |
| `routes.geojson` | **Real** (Nic, 2026-11-15): `pipeline.mission_geography` DTM routes with drive/walk `legs` and optional `status_reason`; candidates only, budget-rejected under the current rule |
| `hazards.geojson` | **Real** (Nic, 2026-11-15): DTM slope clusters (nasa_derived), traced scarp face, edge setback, rockfall zone (inferred), simulated discovery (rover stage) |
| `coverage.geojson` | Nic, 2026-11-15: simulated rover corridor and drone areas from the generated routes; orbit-only box = DTM area |
| `mission.json` | **Real** (Nic, 2026-11-15): endpoints from `pipeline/site/mission_sites.json`, stage texts/stats computed from the routes |
| `hirise.jpg` + `hirise.bounds.json` + `hirise.meta.json` | **Real** (Nic, 2026-11-14): native 4093×4088 px crop of HiRISE `ESP_071006_2345_RED_A_01_ORTHO` (0.23–0.25 m sampling), centred 54.1635, −147.9045 on Geury's ice bands; published by `pipeline.publish_imagery`; registration vs RED_C: RMS 0.86 m, max 1.05 m (`measured_exceeds_tolerance`) |
| `hirise-tiles/wide/` (`tiles.json` + `{z}/{x}/{y}.webp`) | **Real** (Nic, 2026-11-14): whole RED_A strip, 16× area average (~4 m), zoom 9–11, 54.041–54.253 N, −147.983 to −147.787 (18 tiles, 0.1 MB); keeps the wider view sharp when Esri's CTX server fails |
| `hirise-tiles/context/` (`tiles.json` + `{z}/{x}/{y}.webp`) | **Real** (Nic, 2026-11-14): same RED_A product, 4× area average (~1 m), zoom 12–15, 54.110–54.185 N, −147.945 to −147.863 (habitat to scarp and surroundings); `pipeline.tiles_hd`; optional, the app skips a missing set |
| `hirise-tiles/core/` (`tiles.json` + `{z}/{x}/{y}.webp`) | **Real** (Nic, 2026-11-14): same RED_A product, native pixels, zoom 16–17, habitat→scarp corridor 54.124–54.171 N, −147.922 to −147.886; `pipeline.tiles_hd`; when present the app draws it instead of the single 4K overlay |
| `slope.png` + `slope.bounds.json` + `slope.meta.json` | **Real** (Nic, 2026-11-14): NASA HiRISE DTM `DTEEC_071085_2345_071006_2345_A01` slope, one PNG pixel per ~1 m DTM cell (1,715 × 3,260), 54.120–54.175 N, −147.925 to −147.880; classes from `hazard_rules.json` (15/20/24°), unknown cells gray-checkered; `pipeline.slope_mvp` |
| `scarp_lines.geojson` | **Inferred** (2026-11-14): traced scarp edge and foot from PR #15 (`data/site/scarp_lines.geojson`, Yasser's agent's HiRISE trace, unreviewed); drives "Inspect scarp" |
| `route_audit.json` | **Real measurement** (Nic, 2026-11-14): `pipeline.route_audit` on the current `routes.geojson` (placeholder lines) against the real DTM; re-run whenever routes change (the `routes_sha256` field must match); now written by `pipeline.mission_geography` with a `fingerprint` (routes, endpoints, scarp, DTM, rules, algorithm) the app recomputes and rejects when stale |

Placeholder files carry `"placeholder": true`. Their shapes sit around the real scarp (about 54.16°N, −147.905) but are not derived from data. The pipeline overwrites them with real outputs in the same format and drops the `placeholder` flag.

Reminders: GeoJSON coordinates are `[longitude, latitude]`; longitudes are −180..180; every feature has a stable `id`; every file has `schema_version`.
