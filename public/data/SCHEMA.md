# public/data: contract files

The full contract is section 4 of [docs/IMPLEMENTATION.md](../../docs/IMPLEMENTATION.md). This folder holds the files the app loads.

| File | Status |
| --- | --- |
| `routes.geojson` | Placeholder (Yasser) until Nic's pipeline exports real routes |
| `hazards.geojson` | Placeholder |
| `coverage.geojson` | Placeholder |
| `mission.json` | Placeholder; endpoints are approximate until Geury confirms them |
| `hirise.jpg` + `hirise.bounds.json` + `hirise.meta.json` | **Real** (Nic, 2026-11-14): native 4093×4088 px crop of HiRISE `ESP_071006_2345_RED_A_01_ORTHO` (0.23–0.25 m sampling), centred 54.1635, −147.9045 on Geury's ice bands; published by `pipeline.publish_imagery`; registration vs RED_C: RMS 0.86 m, max 1.05 m (`measured_exceeds_tolerance`) |
| `slope.png` + `slope.bounds.json` | Nic (pipeline) |

Placeholder files carry `"placeholder": true`. Their shapes are positioned near the real site (54.144°N, −147.894) but are not derived from data. The pipeline overwrites them with real outputs in the same format and drops the `placeholder` flag.

Reminders: GeoJSON coordinates are `[longitude, latitude]`; longitudes are −180..180; every feature has a stable `id`; every file has `schema_version`.
