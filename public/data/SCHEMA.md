# public/data: contract files

The full contract is section 4 of [docs/IMPLEMENTATION.md](../../docs/IMPLEMENTATION.md). This folder holds the files the app loads.

| File | Status |
| --- | --- |
| `routes.geojson` | Placeholder (Yasser) until Nic's pipeline exports real routes. Least-cost paths on the HiRISE DTM between DTM-checked points (`data/site/`, `tools/site/`); lengths with the pipeline's `mars_distance`. Schema 1.1: crew routes use the optional `legs` (drive 5 km/h, walk 20 m/min) and `walkback_min` (IMPLEMENTATION section 4). The replanned main route and backup pass both budget checks but stay `inspection_required` until a crew-rover traversability model exists |
| `hazards.geojson` | Placeholder file, but the scarp face is measured (DTM slope 64–75°, `nasa_derived`); edge setback and rockfall zone apply the hazard rules to the measured edge, foot and height (`inferred`); simulated soft ground; Geury's southern scarp (`inferred`) |
| `coverage.geojson` | Placeholder |
| `mission.json` | Placeholder; endpoints and drone perch are the DTM-checked candidates in `data/site/site_points_dtm.geojson` (2026-11-14) |
| `hirise.jpg` + `hirise.bounds.json` | Nic (pipeline) |
| `slope.png` + `slope.bounds.json` | Nic (pipeline) |

Placeholder files carry `"placeholder": true`. Their shapes sit around the real scarp (about 54.16°N, −147.905) but are not derived from data. The pipeline overwrites them with real outputs in the same format and drops the `placeholder` flag.

Reminders: GeoJSON coordinates are `[longitude, latitude]`; longitudes are −180..180; every feature has a stable `id`; every file has `schema_version`.
