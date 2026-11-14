# Status

Live log shared by the team and both agents. Update it whenever you start or finish meaningful work, and before ending a session. One line per item, newest first, with a name.

## Current focus

| Person | Working on | Next |
| --- | --- | --- |
| Nic | Project scaffold: Vite + React + TypeScript + react-leaflet, GitHub Pages deploy | Download and validate the Milankovic DTM + RED_C image; crop to the scarp |
| Yasser | Map app PR from `ui/map` (frontend logging included) | Merge Nic's PRs #4 → #5 → #6 once Nic finishes logging instrumentation and CI is green; branch protection for `main` |
| Geury | Exact endpoints: scarp foot, habitat, primary and backup observation points (inside the color strip) | Ice evidence specific to this scarp; evidence panel text |
| Samar / Yasser's agent | Hazard rules v1 done (in IMPLEMENTATION.md section 5) | Sensor ranges for coverage; decision states; discovery scenario |
| Brianna | Rover CAD on the JPL Open Source Rover base: dock, mast | Specs to Samar; hold the drill until "observation only" is confirmed |

## In progress

- 2026-11-14 · Nic: repository-wide logging policy proposed in `docs/mandatory-logging-pr-policy`; open pipeline PRs being audited and instrumented before merge; frontend logging gaps handed to Yasser
- Nic: scaffold and CI in PR #3 (`pipeline/nic-scaffold-ci-v2`); merge protection requires repository admin

## Done

- 2026-11-14 · Yasser's agent: frontend logging per CLAUDE.md section 16: `src/lib/logger.ts` (structured events, shared run_id, UTC timestamps, DEBUG off in production, secret-field redaction, sink failures never break the app) and `src/lib/appLogger.ts`; data loading, validation errors/warnings, stage changes, unavailable routes and the simulated discovery request are logged; 9 logging tests in `tests/logging.test.mjs`
- 2026-11-14 · Yasser's agent: `package.json` `test` script now runs Node with `--experimental-strip-types` so tests can import the TypeScript sources (Nic's area; one-flag change, needed by the logging tests)
- 2026-11-14 · Yasser's agent: CLAUDE.md git policy updated: pull first; agents commit/push only when their person asks; code reaches `main` only by PR with green `full-suite` and a Logging section; stacked PRs merge in order; never merge another person's PR while they are still changing it
- 2026-11-14 · Yasser's agent: clarity pass on `ui/map`: mission-brief intro, guided Back/Next steps with a "what to look at" caption, bold outlined routes, on-map legend, Demo-data badge instead of banner, auto-fit view, loading message, coverage off by default, CTX z10 → z9 → THEMIS tile fallback; loader accepts an empty `chosen_option` (crew not yet decided) to match Nic's discovery export
- 2026-11-14 · Yasser's agent: map app on branch `ui/map`: Mars basemap (CTX with THEMIS fallback), 4 stages, routes/hazards/coverage per stage, rover-needs-input card, click-a-hazard evidence card, layer toggles, auto HiRISE/slope overlays once bounds files exist (alignment verified pixel-exact with a test image)
- 2026-11-14 · Yasser's agent: CLAUDE.md rules added: update docs when data lands; Python checks in Docker; write pipeline outputs via temp file + rename (Vite EBUSY on Windows)
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

- Yasser: protect `main` (Pages is now enabled) (Settings → Branches → Add rule for `main`: require PR, require `full-suite`, require branches up to date, and do not allow bypass); Nic's connected account has push but no admin permission
- Yasser's app work → Nic's scaffold
- Nic's routes → Geury's endpoints
- Brianna's instrument rack → team confirmation of "observation only"

## Handoffs

| From | To | What | Status |
| --- | --- | --- | --- |
| Geury | Nic | Site files (links) | Done |
| Yasser's agent | Nic | Hazard rules v1 | Done (in IMPLEMENTATION.md) |
| Geury | Nic | Endpoint coordinates | Pending |
| Brianna | Samar | Rover mass properties | Pending |
| Nic | Yasser | Real slope, hazards, routes | Pending (Saturday evening) |

## Decision log

- 2026-11-14 · Site: Scarps in Milankovic Crater (only northern-hemisphere site of Dundas et al. 2018)
- 2026-11-14 · Stack: Vite + React + TypeScript + react-leaflet on GitHub Pages; Python pipeline
- 2026-11-14 · Demo format: 30-second video; depth on the project page and README
- 2026-11-14 · Hazards carry evidence labels; unscouted and no-data terrain are never safe
- 2026-11-14 · Rover autonomy follows the published AutoNav approach (not its code); LLM only for crew briefings, stretch goal
- 2026-11-14 · Go/no-go at feature freeze: Yasser (app), Nic (pipeline outputs)

## Open questions

- Confirm mission objective: observation only, no sampling or drilling (proposed)
- Final project name (placeholder: IceScout)
- Nic registered at the same Local Event as the team?
- Placeholder endpoints (habitat, observation points) are approximate; Geury to replace with real coordinates
- CTX tiles come from the Esri OnMars server: check visually that they line up with MOLA and the HiRISE overlay

## Sync points

1. Scaffold merged → Yasser starts the app
2. Saturday evening → real slope, hazards and routes replace placeholders
3. Sunday ~11 AM → final data, end-to-end test
4. Sunday lunch → feature freeze
