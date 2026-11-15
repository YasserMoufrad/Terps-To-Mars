# public/data: contract files

The full contract is section 4 of [docs/IMPLEMENTATION.md](../../docs/IMPLEMENTATION.md). This folder holds the files the app loads.

| File | Status |
| --- | --- |
| `routes.geojson` | Placeholder (Yasser) until Nic's pipeline exports real routes. Least-cost paths on the HiRISE DTM between DTM-checked points (`data/site/`, `tools/site/`); lengths with the pipeline's `mars_distance`. Schema 1.1: crew routes use the optional `legs` (drive 5 km/h, walk 20 m/min) and `walkback_min` (IMPLEMENTATION section 4). The replanned main route and backup pass both budget checks but stay `inspection_required` until a crew-rover traversability model exists |
| `hazards.geojson` | Placeholder file, but the scarp face is measured (DTM slope 64–75°, `nasa_derived`); edge setback and rockfall zone apply the hazard rules to the measured edge, foot and height (`inferred`); simulated soft ground; Geury's southern scarp (`inferred`) |
| `coverage.geojson` | Placeholder |
| `mission.json` | Placeholder; endpoints and drone perch are the DTM-checked candidates in `data/site/site_points_dtm.geojson` (2026-11-14) |
| `hirise.jpg` + `hirise.bounds.json` + `hirise.meta.json` | **Real** (Nic, 2026-11-14): native 4093×4088 px crop of HiRISE `ESP_071006_2345_RED_A_01_ORTHO` (0.23–0.25 m sampling), centred 54.1635, −147.9045 on Geury's ice bands; published by `pipeline.publish_imagery`; registration vs RED_C: RMS 0.86 m, max 1.05 m (`measured_exceeds_tolerance`) |
| `hirise-tiles/wide/` (`tiles.json` + `{z}/{x}/{y}.webp`) | **Real** (Nic, 2026-11-14): whole RED_A strip, 16× area average (~4 m), zoom 9–11, 54.041–54.253 N, −147.983 to −147.787 (18 tiles, 0.1 MB); keeps the wider view sharp when Esri's CTX server fails |
| `hirise-tiles/context/` (`tiles.json` + `{z}/{x}/{y}.webp`) | **Real** (Nic, 2026-11-14): same RED_A product, 4× area average (~1 m), zoom 12–15, 54.110–54.185 N, −147.945 to −147.863 (habitat to scarp and surroundings); `pipeline.tiles_hd`; optional, the app skips a missing set |
| `hirise-tiles/core/` (`tiles.json` + `{z}/{x}/{y}.webp`) | **Real** (Nic, 2026-11-14): same RED_A product, native pixels, zoom 16–17, habitat→scarp corridor 54.124–54.171 N, −147.922 to −147.886; `pipeline.tiles_hd`; when present the app draws it instead of the single 4K overlay |
| `slope.png` + `slope.bounds.json` | Nic (pipeline) |

Placeholder files carry `"placeholder": true`. Their shapes sit around the real scarp (about 54.16°N, −147.905) but are not derived from data. The pipeline overwrites them with real outputs in the same format and drops the `placeholder` flag.

Reminders: GeoJSON coordinates are `[longitude, latitude]`; longitudes are −180..180; every feature has a stable `id`; every file has `schema_version`.
