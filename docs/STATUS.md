# Status

Live log shared by the team and both agents. Update it whenever you start or finish meaningful work, and before ending a session. One line per item, newest first, with a name.

## Current focus

| Person | Working on | Next |
| --- | --- | --- |
| Nic | Project scaffold: Vite + React + TypeScript + react-leaflet, GitHub Pages deploy | Download and validate the Milankovic DTM + RED_C image; crop to the scarp |
| Yasser | Managing; placeholder data and tile URLs done (branch `ui/placeholder-data`) | Mars map centered on Milankovic once the scaffold lands |
| Geury | Exact endpoints: scarp foot, habitat, primary and backup observation points (inside the color strip) | Ice evidence specific to this scarp; evidence panel text |
| Samar / Yasser's agent | Hazard rules v1 done (in IMPLEMENTATION.md section 5) | Sensor ranges for coverage; decision states; discovery scenario |
| Brianna | Rover CAD on the JPL Open Source Rover base: dock, mast | Specs to Samar; hold the drill until "observation only" is confirmed |

## In progress

- Nic: terrain/hazard processing on `pipeline/terrain-hazards`; scaffold PR #3 merged with CI passing; merge protection requires repository admin
- 2026-11-14 · Nic: logging policy PR #7 merged with all checks passing; open pipeline PRs being corrected and instrumented before merge; frontend logging gaps handed to Yasser

## Done

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
| Geury | Nic | Endpoint coordinates | Pending |
| Brianna | Samar | Rover mass properties | Pending |
| Nic | Yasser | Real slope, hazards, routes | Pending (Saturday evening) |

## Decision log

- 2026-11-14 · Nic: team second-pass request adopts provisional one-height rockfall buffer, nearest odd roughness window with uncertainty disclosure, and uv dependency management; schema remains 1.0
- 2026-11-14 · Site: Scarps in Milankovic Crater (only northern-hemisphere site of Dundas et al. 2018)
- 2026-11-14 · Stack: Vite + React + TypeScript + react-leaflet on GitHub Pages; Python pipeline
- 2026-11-14 · Demo format: 30-second video; depth on the project page and README
- 2026-11-14 · Hazards carry evidence labels; unscouted and no-data terrain are never safe
- 2026-11-14 · Rover autonomy follows the published AutoNav approach (not its code); LLM only for crew briefings, stretch goal
- 2026-11-14 · Go/no-go at feature freeze: Yasser (app), Nic (pipeline outputs)

## Open questions

- Yasser: placeholder `rt-orbital-guess-v1` has 24° max slope with `status: ok`; hypothetical geometry/stats are not crew clearance. Loader correctly returns `placeholderFiles` for `placeholder: true`. Present it explicitly as unverified/simulated and review its status; Nic left placeholder data/UI unchanged.
- Yasser: new Section 16 requires browser logging for loader failures/schema mismatches and meaningful mission-stage changes; current loader returns issues but has no shared operational logger. Ownership handoff only; no UI edits made.
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
