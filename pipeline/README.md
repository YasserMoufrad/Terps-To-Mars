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

## Structured logs and traceability

Standard-library logging emits JSON to stderr at INFO by default. Significant operations have a UTC timestamp, level, shared execution `run_id`, stage, event, duration and applicable source/evidence/entity/threshold fields. Nested operations reuse the same run ID; separate top-level calls get different IDs. No per-cell tracing is emitted. `PIPELINE_LOG_LEVEL=DEBUG` enables diagnostic detail; `PIPELINE_LOG_FILE=pipeline/logs/run.jsonl` adds an ignored JSONL file. For Docker, pass `-e PIPELINE_LOG_LEVEL=DEBUG -e PIPELINE_LOG_FILE=pipeline/logs/run.jsonl` and mount the repository read/write if persisting logs. `configure_logging(human=True)` offers readable console output while JSONL remains JSON. Configuration contents are fingerprinted rather than logged wholesale; never place secrets in scientific metadata.

Acquisition logs source/checksum/bytes, raster validation logs CRS/no-data/crop/quality, analysis logs effective windows/uncertainty, hazard export logs counts/classifications, and validation/export failures carry stack traces and propagate. Formatting/handler failures cannot bypass validation or manufacture success. Tests verify correlation, JSONL, expected warnings/errors, formatter failures, exception propagation and unchanged deterministic outputs. Routing and discovery instrumentation follow in their existing dependent PRs.

## Routing and mission budgets

`routing.plan_routes` takes crop-grid `(row, column)` start/end cells and produces a primary candidate plus backup or explicit failure record. Four-neighbour Dijkstra forbids diagonal corner cutting; row/column ties are deterministic and physical east-west scale is corrected by latitude. Costs model distance, slope, roughness, rockfall proximity and unscouted terrain; infinite exclusions include no-data, artifacts, agent slope limits, rockfall, crew edge setbacks and unresolved scarp-risk cells.

All cells default to unscouted. A geometric path across them retains its geometry but uses `kind: orbital_guess` and `status: inspection_required`. `ok` remains a planning result, not astronaut clearance; even a supplied scouting mask cannot certify the regional hazard model. No-data/scarp failures remain visible, and no path is manufactured. The 15/20/24° thresholds remain provisional and configurable.

`mission_budget(outbound, returning, rules, eva_minutes, speed_m_min, observation_minutes)` uses the actual outbound + return lengths and adds site work: travel + work must fit EVA × (1 − reserve). Defaults are modeled 20 m/min walking, 240 min EVA, zero work unless supplied and 30% reserve. Real configurations must explicitly supply site work time; zero is only a modeling default. `est_time_min` remains travel-only (the route's duplicate-path round trip). Combined main-outbound/backup-return budgeting is separate and logged. Total excursion distance must be strictly <5 km and route length must respect the 10 km cap; no physiology model is implied.

Backup search penalizes the main corridor 100-fold, then requires at most 50% shared edges and corridor cells (excluding endpoints); default corridor width is 2 m. These are tunable assumptions, not independence from shared regional hazards. The actual main/backup combination must fit the work-inclusive mission budget. Failures retain `backup_unavailable` and do not imply backup clearance. Route search, aggregate costs, both route-search durations, unscouted warnings, statistics, overlap, mission budgets and rejection reasons share the execution trace.

Branch cleanup now preserves branches used as the base of an open stacked PR. Retarget downstream PRs to main before deleting their merged parent; deleting such a parent closes the dependent PR on GitHub. Cleanup decisions emit structured diagnostic output and are tested without contacting GitHub.
