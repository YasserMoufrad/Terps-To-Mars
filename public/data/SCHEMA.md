# public/data: contract files

The full contract is section 4 of [docs/IMPLEMENTATION.md](../../docs/IMPLEMENTATION.md). This folder holds the files the app loads.

| File | Status |
| --- | --- |
| `routes.geojson` | Placeholder (Yasser) until Nic's pipeline exports real routes |
| `hazards.geojson` | Placeholder |
| `coverage.geojson` | Placeholder |
| `mission.json` | Placeholder; endpoints are approximate until Geury confirms them |
| `hirise.jpg` + `hirise.bounds.json` | Nic (pipeline) |
| `slope.png` + `slope.bounds.json` | Nic (pipeline) |

Placeholder files carry `"placeholder": true`. Their shapes are positioned near the real site (54.144°N, −147.894) but are not derived from data. The pipeline overwrites them with real outputs in the same format and drops the `placeholder` flag.

Reminders: GeoJSON coordinates are `[longitude, latitude]`; longitudes are −180..180; every feature has a stable `id`; every file has `schema_version`.
