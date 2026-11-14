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
