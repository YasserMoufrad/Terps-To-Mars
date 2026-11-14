# Status

Live log shared by the team and both agents. Update it whenever you start or finish meaningful work, and before ending a session. One line per item, newest first, with a name.

## Current focus

| Person | Working on | Next |
| --- | --- | --- |
| Nic | Terrain, routing, discovery and UI follow-up merged | Paused until real endpoints and DTM QC land |
| Yasser | Map app PR #8 merged with wording, placeholder evidence and candidate drawing fixes | Branch protection for main; further visual/scientific review |
| Geury | Exact endpoints: scarp foot, habitat, primary and backup observation points (inside the color strip) | Ice evidence specific to this scarp; evidence panel text |
| Samar / Yasser's agent | Hazard rules v1 done (in IMPLEMENTATION.md section 5) | Sensor ranges for coverage; decision states; discovery scenario |
| Brianna | Rover CAD on the JPL Open Source Rover base: dock, mast | Specs to Samar; hold the drill until "observation only" is confirmed |

## In progress

- Nic: PR #5 merged after explicit approval and exact-head green checks; PR #6 conflicts resolved against reviewed main; PR #8 remains with Yasser; separate UI follow-up requested
- 2026-11-14 · Nic: logging policy PR #7 merged with all checks passing; open pipeline PRs being corrected and instrumented before merge; frontend logging gaps handed to Yasser

## Done

- 2026-11-14 · Yasser's agent: integration check after #13 merged: `ui/real-site` and `ui/drive-walk` merged with `main` (no code conflicts); 39 JS + 114 Python tests, build and `validate_data` pass. `tools/site/make_scarp_inputs.py` builds edge/foot distance, scarp-risk mask, height and apron for #13's audit: from the parking point the audit returns `candidate_requires_inspection` (routed 56–81 min, reason `unscouted_terrain`), walk-only stays `infeasible`
- 2026-11-14 · Yasser's agent (`ui/drive-walk`, PR #15), covering Geury's open site tasks: traced the real scarp edge and foot in the 0.25 m HiRISE crop; downloaded the DTM with `pipeline.acquire` (checksum matches Nic's) and measured it with the pipeline's slope code: height median 59 m (23–73), face 64–75°. Confirmed Nic's flag: Geury's "main band" is on plain, the face is about 200 m north. DTM-checked points (0 cells ≥ 20° in each 15 m disc): habitat moved 59 m, crew-rover parking, viewpoint and backup on the bench at the scarp's east end, drone perch facing the 70 m face. Placeholder data rebuilt on DTM least-cost paths: 103 of 168 min, walkback 189 of 240. Files: `data/site/` (scarp_lines, scarp_measurements, site_points_dtm, audit configs with `window_latlon`), scripts in `tools/site/`
- 2026-11-14 · Yasser's agent (`ui/drive-walk`, PR #15): schema 1.1 per Nic's review: app and `pipeline/validate_contract.py` accept 1.0 and 1.1, legs only in 1.1 (validator checks mode and end-to-end indexes; 2 new Python tests in `test_contract.py`, Nic's area, small change logged here); placeholder files bumped to 1.1; drive-leg routes back to `inspection_required`, drawn amber (drive as dots) with a "Route status" line explaining why; JS tests for both budget checks and the walking-only 5 km rule. 39 JS tests; 98 Python tests passed locally with uv (not Docker)
- 2026-11-14 · Yasser's agent (branch `ui/drive-walk`, on top of `ui/real-site`): drive-then-walk crew routes: optional route `legs` + `walkback_min` (proposed contract addition, section 4), drive leg drawn light blue with a "crew rover parks" marker, loader warns on malformed legs, `tests/routeLegs.test.mjs`; placeholder trip now 116 min travel + 20 min site work (136 of 168 min budget), walkback 211 of 240 min EVA; `data/site/feasibility_audit*.json` configs for Nic's feasibility audit (walk-only baseline, and the walking part from the parking point); Geury's southern scarp added as a hazard; Geury's `ice_zone.geojson` and `site_points.geojson` added under `data/site/` (rebuilt from his site-pack tables)
- 2026-11-14 · Nic: second-pass audit P0 fixes (branch `pipeline/feasibility-and-routing-hardening`): `run()` reports `InfeasibleMission` as `feasibility_report.json` instead of crashing; new `pipeline/feasibility.py` audits unconfirmed candidates (no review flags) over 15 m uncertainty discs and full itineraries incl. primary->backup leg; great-circle lower bound and shortest-distance fallback before `no_viable_route`; unresolved roughness costs like unscouted and flags routes `inspection_required`. 111 Docker Python tests (15 new); synthetic bundle byte-identical to main. Not done: Geury's GeoJSON not in repo (audit waits on it); alternate-destination routing in the mission bundle; frontend display of infeasibility (Yasser)
- 2026-11-14 · Nic: Patch A native-resolution HiRISE (branch `pipeline/high-resolution-hirise-overlay`): downloaded `ESP_071006_2345_RED_A_01_ORTHO.JP2` (390,402,430 bytes, SHA-256 `ab1d5f6c…1d12`, 0.249 m/pixel, 30081×50631, 8-bit); `export_hirise_hd` + `python -m pipeline.preview_hd`; real diagnostic preview at 54.144, −147.894 = 4091×4088 native pixels (~930 m × 1020 m ground; 0.227 m E-W / 0.249 m N-S ground sampling), no resampling or warp, JPEG q95 4.2 MB, 254 s decode; visibly sharper than the 1 m ORTHO on the same area. 96 Docker Python tests (20 new), 20 frontend tests. Not done: tile pyramid, map zoom > 15, `run.py` integration, landmark alignment (`not_verified`); preview centre is not the confirmed scarp
- 2026-11-14 · Yasser's agent (branch `ui/real-site`): placeholder data moved onto Geury's first-pass endpoints (habitat, observation points, drone perch); hazards, routes, coverage and discovery redrawn around the traced ice band; route stats computed on the Mars sphere; post-discovery crew backup added; test `tests/placeholderData.test.mjs` checks replanned routes avoid exclude hazards and over-budget routes are never `ok`. Nic's `reviewPresentation` test adjusted to strip the new backup when testing the missing-backup notice. Ground-view panel with Geury's 4 NASA lander photos (one per stage, labeled example terrain), `tests/groundViews.test.mjs`. Duplicate route notices shown once
- 2026-11-14 · Yasser: project deployed to Vercel at https://terps-to-mars.vercel.app (auto-deploys `main`, preview per PR; build command `npm run build -- --base=/` because Vercel serves from the root; GitHub Pages unchanged)
- 2026-11-14 · Yasser's agent (PR #11): real Mars color on the basemap from the Viking MDIM 2.1 color mosaic, blended over CTX detail with CSS `mix-blend-mode: color` in its own pane (data layers unaffected), with a layer toggle; MGS MOC color atlas rejected (fully gray at this site); basemap tile failures logged once per layer (`map/tiles.error`) with 4 tests
- 2026-11-14 · Nic: audit provenance fixes (branch `docs/audit-provenance-fixes`): CRISM claim qualified (3 of 8 scarps, none confirmed for our face); placeholder drone alert no longer says "confirmed"; placeholder `chosen_option` empty (pending); README no longer says confirmed/safe; MAP_TILES documents THEMIS Night IR, MCD weather and imagery-resolution caveats; edited Yasser's placeholder `mission.json` (wording/pending only). Night IR toggle and weather display not built
- 2026-11-14 · Nic: UI follow-up on merged #8 (branch `ui/pipeline-review-followup`): orbital stage hides post-discovery routes; drone/eva use only the post-discovery backup and report a missing one in words; drone perch label reflects its coverage record (no active-drone claim for an inspection-required marker); route review logging (`route.candidate`/`route.unavailable`, `crew_clearance: not_established`); 20 frontend tests, typecheck and build pass
- 2026-11-14 · Nic: PR #6 refreshed against merged UI #8; integrated validation passed 76 Docker Python tests, 14 frontend/workflow tests, typecheck/build; actual eight-file synthetic bundle loaded by the TypeScript loader with zero errors and four expected inspection warnings
- 2026-11-14 · Nic: discovery/export suite passed 76 Docker Python tests; thermal context no longer claims measured inertia; simulated decisions/versions have one correlated trace; real run requires confirmed endpoints and reviewed scarp inputs; atomic exports and candidate statistics are tested
- 2026-11-14 · Yasser's agent: Nic's PR #8 review addressed: intro/captions/labels/placeholder text say proposed, simulated and needs-inspection (no safe/confirmed/clearance claims); evidence card marks placeholder shapes as hypothetical even when they name a NASA dataset; placeholder soft-ground hazard no longer cites the THEMIS day-IR mosaic as thermal-inertia evidence; non-ok routes with geometry drawn amber dashed, empty routes reported in words
- 2026-11-14 · Yasser's agent: frontend logging per CLAUDE.md section 16: `src/lib/logger.ts` (structured events, shared run_id, UTC timestamps, DEBUG off in production, secret-field redaction, sink failures never break the app) and `src/lib/appLogger.ts`; data loading, validation errors/warnings, stage changes, unavailable routes and the simulated discovery request are logged; 10 logging tests in `tests/logging.test.mjs`
- 2026-11-14 · Yasser's agent: `package.json` `test` script now runs Node with `--experimental-strip-types` so tests can import the TypeScript sources (Nic's area; one-flag change, needed by the logging tests)
- 2026-11-14 · Yasser's agent: CLAUDE.md git policy updated: pull first; agents commit/push only when their person asks; code reaches `main` only by PR with green `full-suite` and a Logging section; stacked PRs merge in order; never merge another person's PR while they are still changing it
- 2026-11-14 · Yasser's agent: clarity pass on `ui/map`: mission-brief intro, guided Back/Next steps with a "what to look at" caption, bold outlined routes, on-map legend, Demo-data badge instead of banner, auto-fit view, loading message, coverage off by default, CTX z10 → z9 → THEMIS tile fallback; loader accepts an empty `chosen_option` (crew not yet decided) to match Nic's discovery export
- 2026-11-14 · Yasser's agent: map app on branch `ui/map`: Mars basemap (CTX with THEMIS fallback), 4 stages, routes/hazards/coverage per stage, rover-needs-input card, click-a-hazard evidence card, layer toggles, auto HiRISE/slope overlays once bounds files exist (alignment verified pixel-exact with a test image)
- 2026-11-14 · Yasser's agent: CLAUDE.md rules added: update docs when data lands; Python checks in Docker; write pipeline outputs via temp file + rename (Vite EBUSY on Windows)
- 2026-11-14 · Nic: PR #5 corrected suite passed 57 Docker Python tests and npm ci/typecheck/test (4)/build; both crew and rover block unresolved scarp cells; observation work and actual backup-return budgets are tested; PR converted to draft for explicit merge hold
- 2026-11-14 · Nic: Yasser UI/scientific-wording handoff posted at https://github.com/YasserMoufrad/Terps-To-Mars/pull/8#issuecomment-6883539861; loader logging/pending-option support already exists there; no UI/placeholder files changed
- 2026-11-14 · Nic: PR #4 merged after 30 Docker Python tests, full frontend validation and latest frontend/pipeline/full-suite checks; PR #5 reopened against main after parent deletion closed it; cleanup guard added for stacked PR bases
- 2026-11-14 · Nic: PR #4 corrections passed 30 Python tests in Docker and npm ci/typecheck/test/build; added AGENTS.md and a PR template mirroring Section 16's mandatory logging/checklist/walkthrough requirements; Yasser loader/placeholder findings documented without modifying his code
- 2026-11-14 · Nic: PR #4 review corrections add nearest-odd roughness windows, uncertainty warnings, one-height provisional rockfall buffer and explicit unresolved scarp-risk exclusions; uv project/lock replaces requirements files; all implemented terrain/acquisition/export/validation stages have correlated structured logs
- 2026-11-14 · Nic: downloaded official DTM to ignored raw storage (380,863,440 bytes; SHA-256 `6543d410aabcdfed6d8c67117235c1dcaf0f67716dcf72c0ba13c6dd8d85c8f1`); verified Mars equirectangular CRS, declared no-data, 1 m pixels, and 128×128 center diagnostic crop; scarp/alignment validation still pending
- 2026-11-14 · Yasser's agent: `src/data/types.ts` (contract types) and `src/data/loadMissionData.ts` (loads all data files, reports issues instead of crashing); strict typecheck passes; tested against the placeholders and deliberately broken data
- 2026-11-14 · Yasser's agent: sensor coverage model v1 added to IMPLEMENTATION.md section 6 (for Nic's `coverage.geojson`)
- 2026-11-14 · Yasser: GitHub Pages enabled with GitHub Actions as the source
- 2026-11-14 · Nic: added merged-PR branch cleanup workflow; repository-level automatic deletion setting denied (admin required); workflow preserves default/base/fork branches and branches with newer commits
- 2026-11-14 · Nic: added minimal Vite/React/TypeScript bootstrap, Pages path, Python contract tests, CI and Pages workflows; preserved Yasser's placeholder data
- 2026-11-14 · Nic: local typecheck, frontend test (1), production build, contract validator, and Python contract tests (5) passed; PR https://github.com/YasserMoufrad/Terps-To-Mars/pull/3 opened; initial CI run passed
- 2026-11-14 · Yasser's agent: placeholder `routes`, `hazards`, `coverage` GeoJSON and `mission.json` at the site (contract check passes, 18 features); `public/data/SCHEMA.md`
- 2026-11-14 · Yasser's agent: basemap tile URLs tested at the site (CTX z≤10, THEMIS z≤9, MOLA z≤7), see `docs/MAP_TILES.md`
- 2026-11-14 · Yasser: repo created; README and `docs/IMPLEMENTATION.md` published
- 2026-11-14 · Geury: site locked (Scarps in Milankovic Crater, DTM `DTEEC_071085_2345_071006_2345_A01`)
- 2026-11-14 · Yasser's agent: hazard rules v1 with sources

## Blocked / waiting on

- Nic: real-data landmark alignment, scarp QC and edge/foot masks remain manual validation steps
- Yasser: protect `main` (Pages is now enabled) (Settings → Branches → Add rule for `main`: require PR, require `full-suite`, require branches up to date, and do not allow bypass); Nic's connected account has push but no admin permission
- Nic's routes → Geury's endpoints
- Brianna's instrument rack → team confirmation of "observation only"

## Handoffs

| From | To | What | Status |
| --- | --- | --- | --- |
| Geury | Nic | Site files (links) | Done |
| Yasser's agent | Nic | Hazard rules v1 | Done (in IMPLEMENTATION.md) |
| Geury | Nic | Endpoint coordinates | First pass received (in IMPLEMENTATION section 2); DTM QC and habitat distance pending |
| Brianna | Samar | Rover mass properties | Pending |
| Nic | Yasser | Real slope, hazards, routes | Pending (Saturday evening) |

## Decision log

- 2026-11-14 · Nic + Yasser: drive-then-walk EVA adopted. Contract bumped to schema 1.1 with optional route `legs` and `walkback_min`; 1.0 files (no legs) stay valid as walk-only. Two budget checks: (1) drive + walk round trip + site work ≤ 168 min; (2) drive out + site walk + site work + walk home along the drive legs ≤ 240 min. Drive speed 5 km/h, cautious and configurable (`hazard_rules.json`). Drive-leg routes stay `inspection_required` until a crew-rover traversability model exists
- 2026-11-14 · Nic + Yasser: the 5 km round-trip limit applies to walking distance only; the 10 km hard cap is measured from the habitat (walkback). (Proposed by Nic; logged by Yasser's agent at Yasser's request)
- 2026-11-14 · Nic: team second-pass request adopts provisional one-height rockfall buffer, nearest odd roughness window with uncertainty disclosure, and uv dependency management; schema remains 1.0
- 2026-11-14 · Site: Scarps in Milankovic Crater (only northern-hemisphere site of Dundas et al. 2018)
- 2026-11-14 · Stack: Vite + React + TypeScript + react-leaflet on GitHub Pages; Python pipeline
- 2026-11-14 · Demo format: 30-second video; depth on the project page and README
- 2026-11-14 · Hazards carry evidence labels; unscouted and no-data terrain are never safe
- 2026-11-14 · Rover autonomy follows the published AutoNav approach (not its code); LLM only for crew briefings, stretch goal
- 2026-11-14 · Go/no-go at feature freeze: Yasser (app), Nic (pipeline outputs)

## Open questions

- Yasser + Nic: agree optional `relief.png`/`relief.bounds.json` and `mission.json` `labels` (proposed in IMPLEMENTATION section 4; not implemented; decide whether `schema_version` bumps). Nic: fine to add as optional.
- Nic's answer to Yasser's agent: the HiRISE overlay export does not need Geury's endpoints, only an agreed crop box. The ~1 m ORTHO we downloaded gives ~1 m pixels; a sharper overlay needs the 0.25 m HiRISE RED image (separate download, size to confirm) and its own PR. Real hazards/routes still need from Geury: habitat, scarp foot, primary and backup observation points, drone perch; plus measured scarp height/apron and manual scarp/landmark QC. PR #6 is merged. No ETA for real routes until those arrive. 3D still: not started.
- ~~Yasser / PR #8: proposed/candidate wording, placeholder labels, inspection-required vs failed routes~~ Resolved in PR #8 (see Done).
- ~~Yasser: placeholder `rt-orbital-guess-v1` 24° with `status: ok`~~ Resolved in PR #8: status is now `inspection_required`, drawn amber dashed and stated in words.
- ~~Yasser: Section 16 browser logging~~ Resolved in PR #8: `src/lib/logger.ts` + `appLogger.ts`, loader/stage/safety events, 10 logging tests.
- Brianna / Samar: supply actual rover CAD clearances/traversability and sensor model; current 24°/35 cm/20 cm figures remain provisional references, not team hardware limits; no orbital wheel-slip/clearance measurement is generated.
- Confirm mission objective: observation only, no sampling or drilling (proposed)
- Final project name (placeholder: IceScout)
- Nic registered at the same Local Event as the team?
- ~~Placeholder endpoints are approximate~~ Geury's first-pass endpoints now in the placeholder data (`ui/real-site`).
- ~~Nic: agree `legs`/`walkback_min` and drive speed~~ Agreed (see Decision log); Nic adds drive-leg routing in a pipeline PR on top of #13.
- Nic: re-run `data/site/feasibility_audit*.json` and the full pipeline with `scarp_lines.geojson` + `scarp_measurements.json` (edge/foot/height/apron) and the DTM-checked points; these are Yasser's agent's measurements, please review before treating them as reviewed scarp inputs.
- Team: the crew views the scarp's east end (23–35 m face) because the tall middle (60–72 m) is not reachable within the EVA budget; the drone images the tall face. Confirm this is the story we tell.
- ~~Geury: pick the crew-rover parking point~~ Done from the DTM (see Done). Geury: please sanity-check the new points and the ice-band labels. Old item: pick the crew-rover parking point (flat ground east of the main band, outside the edge setback; placeholder 54.1590°N, −147.8925) and sanity-check a drive corridor from the habitat in HiRISE (avoid the southern scarp and the no-data patch). There is no driving route from Geury yet; the placeholder drive line is hand-drawn and the real one will come from Nic's rover cost grid.
- CTX tiles come from the Esri OnMars server: check visually that they line up with MOLA and the HiRISE overlay

## Sync points

1. Scaffold merged → Yasser starts the app
2. Saturday evening → real slope, hazards and routes replace placeholders
3. Sunday ~11 AM → final data, end-to-end test
4. Sunday lunch → feature freeze
