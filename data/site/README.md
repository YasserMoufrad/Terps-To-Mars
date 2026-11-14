# data/site: Geury's site inputs

Inputs for Nic's pipeline and for placing the placeholder data. The app does not load these files (they are not part of the `public/data/` contract).

| File | What | Accuracy |
| --- | --- | --- |
| `ice_zone.geojson` | Exposed-ice zones (main band, upper band, southern scarp) from HiRISE enhanced color | about ±15 m; stored as bounding rectangles |
| `site_points.geojson` | Habitat, scarp foot, primary and backup observation points, drone perch, Plan B drill point | about ±15 m; not yet snapped to the DTM |

Both files were rebuilt on 2026-11-14 from the tables in Geury's site and data pack, because his original files were not shared with the repo. If Geury's originals (traced shapes) differ, replace these files with them and note it in `docs/STATUS.md`.

Coordinates are GeoJSON `[longitude, latitude]` with longitude in −180..180 (147.9°W = −147.9). Blue tones in HiRISE color are consistent with ice but are not proof of it; cite Dundas et al. (2018) and CRISM results (see `docs/IMPLEMENTATION.md`, section 2).
