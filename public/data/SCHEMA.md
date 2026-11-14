# public/data: contract files

The full contract is section 4 of [docs/IMPLEMENTATION.md](../../docs/IMPLEMENTATION.md). This folder holds the files the app loads.

| File | Status |
| --- | --- |
| `routes.geojson` | Placeholder (Yasser) until Nic's pipeline exports real routes. Hand-drawn lines around Geury's endpoints; lengths and times computed on the Mars sphere at 20 m/min. All crew routes are `inspection_required` (over the 168 min travel budget) |
| `hazards.geojson` | Placeholder; hand-drawn boxes along Geury's traced ice band, not derived from the DTM |
| `coverage.geojson` | Placeholder |
| `mission.json` | Placeholder; endpoints and drone perch are Geury's first-pass coordinates (2026-11-14, about 15 m accuracy, not DTM-checked) |
| `hirise.jpg` + `hirise.bounds.json` | Nic (pipeline) |
| `slope.png` + `slope.bounds.json` | Nic (pipeline) |

Placeholder files carry `"placeholder": true`. Their shapes sit around the real scarp (about 54.16°N, −147.905) but are not derived from data. The pipeline overwrites them with real outputs in the same format and drops the `placeholder` flag.

Reminders: GeoJSON coordinates are `[longitude, latitude]`; longitudes are −180..180; every feature has a stable `id`; every file has `schema_version`.
