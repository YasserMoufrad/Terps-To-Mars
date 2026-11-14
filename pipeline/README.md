# Terrain pipeline

The processor validates north-up square-pixel Mars equirectangular rasters, crops by pixel window, masks missing and manually flagged artifact cells, computes slope and local elevation range, and exports hazard polygons. Missing neighbours conservatively invalidate terrain measurements. Synthetic tests are not NASA-derived terrain.

From the repository root, use Python 3.11 or newer:

Local Python validation runs in an isolated Docker Desktop container (does not use or alter Capstone Triage):

```sh
docker build -f pipeline/Dockerfile -t terps-pipeline:test .
docker run --rm --name terps-pipeline-tests terps-pipeline:test
```

CI uses the same dependency lock with Python 3.11:

```sh
python -m pip install -r pipeline/requirements.txt
python -m pipeline.validate_contract
python -m pytest pipeline/tests
```

Put raw source files in `pipeline/raw/`; never commit them.

Acquire official inputs with `python -m pipeline.acquire dtm` and `python -m pipeline.acquire image`. Downloads are atomic, refuse overwrite, and record source, byte count and SHA-256 locally. Checksums detect later changes; they are not publisher-authenticated checksums.

`terrain.read_terrain(path, window=(column, row, width, height))` returns a metric crop. Pass a same-shape boolean artifact mask from human QC. The processor does not claim to automatically identify every seam or stereo artifact. `terrain.analyze`, `hazards.hazard_masks` and `hazards.export_hazards` implement the core. Edge/foot distance arrays, measured scarp height and visible apron distance are explicit inputs, not inferred from the scene center. Without them, edge/rockfall analysis remains pending.

`hazard_rules.json` preserves modeling assumptions and unresolved primary-source verification. Exclusion slope equality is conservative (`>=`); roughness and wheel slip use strict `>`. The 3 m roughness window rounds up to an odd pixel count. No-data is never smoothed or interpolated into traversable terrain.

## Route planning

`routing.plan_routes(terrain, analysis, masks, start, end)` accepts integer `(row, column)` endpoints within the validated crop. The deterministic Dijkstra implementation uses positive cell costs, four-neighbour adjacency and infinite hard exclusions. Four-neighbour adjacency forbids diagonal corner cutting; heap ties are broken by row and column. This solves the same minimum-cost grid graph problem as `route_through_array` with four-neighbour adjacency.

Costs model slope, roughness, rockfall proximity, unscouted terrain and length. Weights (1 + slope/15 + roughness + 2 for unscouted, plus 10/(1+rockfall distance)) are assumptions. Every cell is unscouted by default. Hard exclusions always override costs.

Backup search penalizes the primary corridor 100-fold and rejects candidates exceeding 50% shared edges or corridor cells (excluding endpoints). The default corridor is 2 m. These are configurable independence assumptions; common regional hazards can still affect both routes. Identical paths produce `backup_unavailable` with empty geometry.

Successful routes must fit the strict <5 km round-trip budget, the 10 km hard excursion cap, and a modeled EVA duration with at least 30% reserve. Default walking speed is 20 m/min and EVA duration is 240 min; both are configurable modeling inputs, not physiology predictions. Travel time includes the round trip. All reported lengths use a 3,389,500 m Mars sphere. Failure records remain in the GeoJSON with zero stats and an explicit status. Real endpoints must come from Geury.

## End-to-end demonstration and export

From PowerShell, build the image above, then generate the eight contract files without modifying `public/data`:

```powershell
docker run --rm --name terps-demo --mount "type=bind,source=$PWD,target=/app" terps-pipeline:test python -m pipeline.run --output pipeline/output/demo
```

The output directory must be empty. With no config this is an explicitly synthetic flat-grid scenario, not terrain at Milankovič. Images carry a visible SYNTHETIC label; hazard evidence is `simulated`. The command exports `hirise.jpg`, `hirise.bounds.json`, `slope.png`, `slope.bounds.json`, `hazards.geojson`, `routes.geojson`, `coverage.geojson`, and `mission.json`. PNG no-data is transparent. JPEG no-data is black. Bounds describe the geographically reprojected display grid; hazard and route geometry retain full grid precision. The slope display uses a percentile stretch, not absolute color classes.

`disc-001` inserts `hz-sim-001` into the preliminary route and preserves `rt-crew-main-v1` and `rt-crew-main-v2`. A request-input record remains unapproved (`chosen_option` empty) until an explicit human-approved configuration is supplied. The revised route is precomputed for review; it is not authorization to move. No viable post-discovery route remains an explicit failure record. Rover coverage uses a modeled circular sensor footprint on the traversable path prefix, not line-of-sight visibility; drone coverage is pending rather than invented. Unscouted and inspection-required areas remain visible.

For real processing, copy `config.example.json` outside `public/data`, fill every pending field, and add `--config <path>` to the command. Null fields deliberately prevent execution. The input requires a crop window, artifact mask, edge/foot distance grids, measured scarp/apron values, Geury-confirmed endpoints and perch, a scenario discovery point, sensor range, and explicit QC/alignment review. All NumPy masks use the exact crop shape; distances and elevations are metres. Artifact labels require human review because no automatic seam detector is claimed. The discovery point must be inside a viable preliminary route. Do not use the diagnostic center crop as the final scarp selection.

Geographic conversion uses a Mars spherical CRS; equirectangular east-west scale is corrected by latitude for slope and route search. Route lengths are independently recomputed from exported geometry. End-to-end tests compare every byte of two synthetic bundles, check failure states and detect tampered route statistics. Outputs are reproducible with the pinned dependency lock; binary image encoder output can change if dependencies change.

## Real-data progress and remaining handoff

The official DTM and `ESP_071006_2345_RED_C_01_ORTHO.JP2` were downloaded locally and checksummed. A 128×128 diagnostic center crop passed metadata checks, image reprojection and slope export. This is not a manual landmark alignment check. Full source files are ignored and are not distributed by GitHub Pages. Scarp selection, landmark alignment, artifact review, cliff-foot/edge masks, final endpoints and sensor ranges remain team inputs. No real crew route or validated public dataset has been published. Shadow modeling is deferred behind these required checks.
