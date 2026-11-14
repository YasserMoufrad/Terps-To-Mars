# Terrain pipeline

The processor validates north-up square-pixel Mars equirectangular rasters, crops by pixel window, masks missing and manually flagged artifact cells, computes slope and local elevation range, and exports hazard polygons. Missing neighbours conservatively invalidate terrain measurements. Synthetic tests are not NASA-derived terrain.

From the repository root, use Python 3.11 or newer:

Local Python validation runs in an isolated Docker Desktop container (does not use or alter Capstone Triage):

```sh
docker build -f pipeline/Dockerfile -t terps-pipeline:test .
docker run --rm --name terps-pipeline-tests terps-pipeline:test
```

Python dependencies are managed by `uv` through root `pyproject.toml` and `uv.lock`; the old requirements files are removed. CI uses `uv sync --locked --python 3.11` and `uv run --no-sync`. Docker puts the Linux environment in `/opt/terps-venv`, keeping it separate from any Windows `.venv`. Add dependencies with `uv add`; commit both manifest and lock. `uv lock --check` detects lock drift. Local Python verification for this project uses Docker Desktop.

```sh
uv sync --locked
uv run --no-sync python -m pipeline.validate_contract
uv run --no-sync pytest
```

Put raw source files in `pipeline/raw/`; never commit them.

Acquire official inputs with `python -m pipeline.acquire dtm` and `python -m pipeline.acquire image`. Downloads are atomic, refuse overwrite, and record source, byte count and SHA-256 locally. Checksums detect later changes; they are not publisher-authenticated checksums.

`terrain.read_terrain(path, window=(column, row, width, height))` returns a metric crop. Pass a same-shape boolean artifact mask from human QC. The processor does not claim to automatically identify every seam or stereo artifact. `terrain.analyze`, `hazards.hazard_masks` and `hazards.export_hazards` implement the core. Edge/foot distance arrays, measured scarp height and visible apron distance are explicit inputs, not inferred from the scene center. Without them, edge/rockfall analysis remains pending.

`hazard_rules.json` preserves modeling assumptions and unresolved primary-source verification. Crew caution starts at 15°, exclusion at 20°, and rover exclusion at 24° (`>=`); none is certified clearance. Roughness uses strict `> 0.5 m`, a provisional assumption because the DTM vertical uncertainty has not been established. The 3 m window uses the closest odd pixel count (ties prefer the smaller width): 0.99 m pixels produce 3 pixels / 2.97 m. Effective dimensions, east-west projection scale, uncertainty and missing-data counts are logged. A window below three pixels is unresolved and produces NaN roughness, not a zero-roughness claim. No-data neighbours invalidate affected analysis cells.

The provisional rockfall buffer is `max(visible apron, 1.0 × measured cliff height)`, not a NASA-certified distance. `hazard_masks(..., scarp_risk=mask)` marks a reviewed risk region. Missing edge/foot geometry, height or apron measurements produce `inspection_required` in that region, exported as inferred edge exclusions. Synthetic terrain defaults to cliff-free; NASA-derived terrain with no risk-region input conservatively treats the crop as unresolved. Explicit all-false `scarp_risk` is a reviewed cliff-free declaration, not an automatic inference. Route planning must block unresolved regions (implemented in the dependent routing PR).

## Site feasibility audit (unconfirmed candidates)

`python -m pipeline.feasibility --config audit.json --output pipeline/output/audit` checks candidate habitat/primary/backup points without review flags or a rover scenario. Config: `dtm`, `window`, `points` ({lat, lon} each), `eva_minutes`, `speed_m_min`, `observation_minutes` (per stop); optional QC/scarp arrays as in the full run. For each point it checks the whole `position_uncertainty_m` (15 m) disc, not one cell. It budgets three itineraries: habitat->primary->habitat, habitat->backup->habitat and habitat->primary->backup->habitat (the primary->backup leg is counted). Each is tested first against the great-circle lower bound (proves infeasibility with no search), then against the shortest routed path over the same exclusions. Verdicts are `infeasible`, `no_route_found` or `candidate_requires_inspection`, never clearance. Without scarp measurements, NASA-derived terrain stays unresolved, so routing reports `no_route_found` while the lower-bound result still stands.

In the full run, a missing preliminary route raises `InfeasibleMission`; `run()` then writes `feasibility_report.json` and `hazards.geojson` and no mission bundle or simulated discovery.

`plan_routes` now rejects on the great-circle bound before searching, and when the least-cost path is over budget it tries the shortest-distance path over the same exclusions before reporting `no_viable_route`. Valid cells with unmeasured roughness cost the same as unscouted terrain (never zero) and make a route `inspection_required`.

## Native-resolution HiRISE imagery (visual layer only)

`python -m pipeline.acquire image_hd` downloads `ESP_071006_2345_RED_A_01_ORTHO.JP2` (390,402,430 bytes; 30081 x 50631 px, 8-bit, equirectangular, 50 N standard parallel, 3,384.4 km local sphere, 0.249 m/pixel, null 0) into ignored `pipeline/raw/` with a checksum manifest; `image_hd_label` fetches its `.LBL`. The Docker image's GDAL 3.9.3 decodes it with JP2OpenJPEG.

`pipeline.export.export_hirise_hd` reads only the requested window straight from the source. It never passes imagery through the ~1 m DTM grid and never upscales. Equirectangular pixels map linearly to the map's lat/lon grid, so no warp is applied. Crops wider than `max_dimension` (default 4096) are area-averaged; JPEG quality is 95; a 2-98 % display stretch and an unenhanced reference are written. Projected metres are true only at 50 N: at 54.1 N an east-west pixel spans ~0.228 m of ground, so ~932 ground m gives 4096 native pixels. The 0.25 m map sampling is not 0.25 m optical resolution; visible rocks are candidates, not verified hazards. Alignment to the DTM is `not_verified` until landmark review.

```bash
docker run --rm -v "$PWD/pipeline:/app/pipeline" terps-pipeline:uv python -m pipeline.preview_hd --center-lat 54.144 --center-lon -147.894 --width-m 930 --height-m 1020 --output pipeline/output/hirise-hd-preview
```

The centre is a diagnostic coordinate, not the confirmed scarp. Output goes to an ignored directory (never `public/data/`). Decoding a ~4K window takes about four minutes. Tile pyramid and map zoom changes are a separate patch.

## Structured logs and traceability

Standard-library logging emits JSON to stderr at INFO by default. Significant operations have a UTC timestamp, level, shared execution `run_id`, stage, event, duration and applicable source/evidence/entity/threshold fields. Nested operations reuse the same run ID; separate top-level calls get different IDs. No per-cell tracing is emitted. `PIPELINE_LOG_LEVEL=DEBUG` enables diagnostic detail; `PIPELINE_LOG_FILE=pipeline/logs/run.jsonl` adds an ignored JSONL file. For Docker, pass `-e PIPELINE_LOG_LEVEL=DEBUG -e PIPELINE_LOG_FILE=pipeline/logs/run.jsonl` and mount the repository read/write if persisting logs. `configure_logging(human=True)` offers readable console output while JSONL remains JSON. Configuration contents are fingerprinted rather than logged wholesale; never place secrets in scientific metadata.

Acquisition logs source/checksum/bytes, raster validation logs CRS/no-data/crop/quality, analysis logs effective windows/uncertainty, hazard export logs counts/classifications, and validation/export failures carry stack traces and propagate. Formatting/handler failures cannot bypass validation or manufacture success. Tests verify correlation, JSONL, expected warnings/errors, formatter failures, exception propagation and unchanged deterministic outputs. Routing and discovery instrumentation follow in their existing dependent PRs.

## Routing and mission budgets

`routing.plan_routes` takes crop-grid `(row, column)` start/end cells and produces a primary candidate plus backup or explicit failure record. Four-neighbour Dijkstra forbids diagonal corner cutting; row/column ties are deterministic and physical east-west scale is corrected by latitude. Costs model distance, slope, roughness, rockfall proximity and unscouted terrain; infinite exclusions include no-data, artifacts, agent slope limits, rockfall, crew edge setbacks and unresolved scarp-risk cells.

All cells default to unscouted. A geometric path across them retains its geometry but uses `kind: orbital_guess` and `status: inspection_required`. `ok` remains a planning result, not astronaut clearance; even a supplied scouting mask cannot certify the regional hazard model. No-data/scarp failures remain visible, and no path is manufactured. The 15/20/24° thresholds remain provisional and configurable.

`mission_budget(outbound, returning, rules, eva_minutes, speed_m_min, observation_minutes)` uses the actual outbound + return lengths and adds site work: travel + work must fit EVA × (1 − reserve). Defaults are modeled 20 m/min walking, 240 min EVA, zero work unless supplied and 30% reserve. Real configurations must explicitly supply site work time; zero is only a modeling default. `est_time_min` remains travel-only (the route's duplicate-path round trip). Combined main-outbound/backup-return budgeting is separate and logged. Total excursion distance must be strictly <5 km and route length must respect the 10 km cap; no physiology model is implied.

Backup search penalizes the main corridor 100-fold, then requires at most 50% shared edges and corridor cells (excluding endpoints); default corridor width is 2 m. These are tunable assumptions, not independence from shared regional hazards. The actual main/backup combination must fit the work-inclusive mission budget. Failures retain `backup_unavailable` and do not imply backup clearance. Route search, aggregate costs, both route-search durations, unscouted warnings, statistics, overlap, mission budgets and rejection reasons share the execution trace.

Branch cleanup now preserves branches used as the base of an open stacked PR. Retarget downstream PRs to main before deleting their merged parent; deleting such a parent closes the dependent PR on GitHub. Cleanup decisions emit structured diagnostic output and are tested without contacting GitHub.

## Discovery and complete export walkthrough

Build the dedicated image, then use PowerShell to generate the eight contract files in a new ignored handoff directory:

```powershell
docker build -f pipeline/Dockerfile -t terps-pipeline:uv .
docker run --rm --name terps-demo --mount "type=bind,source=$PWD,target=/app" terps-pipeline:uv uv run --no-sync python -m pipeline.run --output pipeline/output/demo
```

Without `--config`, this is a synthetic 1 m flat-grid fixture, not Milankovič terrain. Its images are visibly watermarked SYNTHETIC. It emits `hirise.jpg`, `hirise.bounds.json`, `slope.png`, `slope.bounds.json`, `hazards.geojson`, `routes.geojson`, `coverage.geojson` and `mission.json`. Outputs refuse overwrite and never write into `public/data`; JSON/images use temporary files plus atomic replacement. Bounds are geographically reprojected; slope display uses a percentile stretch rather than absolute color classes; no-data is transparent in PNG and black in JPEG.

`disc-001` inserts `hz-sim-001` on the preliminary route and preserves both versioned crew routes. Simulated 38% wheel slip triggers `request_input`; loose/soft ground is suspected, not measured thermal inertia. `chosen_option` remains empty until an explicit boolean human approval is configured. Precomputed alternatives are not authorization to move. The rover follows only a traversable prefix and stops before the discovery. No new hardware or thermal-inertia simulation is introduced.

Coverage is a modeled circular sensor footprint, not verified line of sight; unresolved scarp regions override checked coverage. No drone flight/view cone is invented. The required `cov-drone-perch` reference identifies a single proposed-perch grid cell with `inspection_required` and sensor `none`, not a measured field of view or checked region. UI #8 supports pending choices; its separate follow-up will label candidate geometry and the proposed perch accordingly.

For real inputs copy `pipeline/config.example.json` and fill the deliberately null measurements, masks, sensor range, observation work and confirmed coordinates. All four review flags must be explicitly true: alignment, artifact QC, endpoints and scarp measurements. Supply crop-aligned artifact/risk/edge/foot arrays and measured height/apron. Every endpoint/perch/discovery must lie inside the crop. A discovery point must lie inside a viable preliminary route. These flags are caller declarations, not automated scientific verification. Real routes remain pending Geury/Brianna/Samar inputs and manual scarp/landmark review.

Use `--log-level DEBUG --log-file pipeline/logs/run.jsonl` (or environment variables), optionally `--human-log`, to inspect one execution's correlated trace. The CLI wraps config loading through validation/export in a shared run ID. Scenario logs include the simulated evidence, wheel-slip threshold/state, hazard insertion, actual before/after route IDs and stats, coverage, budget decisions and approval state. Tests compare bundle bytes across INFO/DEBUG+JSONL and validate lengths even for inspection-required candidate geometry. Logs/generated bundles remain ignored.
