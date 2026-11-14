# Terps To Mars: shared agent protocol

This file is read by every AI agent working in this repo (Yasser's and Nic's). Follow it exactly so both agents work from the same facts, plan and rules. Personal preferences (explanations, quizzes) live in each person's user-level `~/.claude/CLAUDE.md`, not here.

## Project in one paragraph

NASA Space Apps Challenge 2026, challenge *Interplanetary Survival Guide: Martian Map*. We build an astronaut-facing map for one Marswalk to the exposed water-ice scarp in Milankovič crater (54.144°N, 212.106°E = −147.894). Robots (a rover and a drone) scout first; the map shows how their reconnaissance changes the crew's route. The map, NASA data layers, terrain analysis, hazards and routes are real. The robots and their observations are concepts and are always labeled `simulated`. Deadline: submit Sunday November 15, 2026 by about 10 PM local (hard limit 11:59 PM). Feature freeze: Sunday lunch.

## Shared memory: read first, update always

| File | What it is | When to read | When to update |
| --- | --- | --- | --- |
| `docs/IMPLEMENTATION.md` | The plan: site, architecture, **data contract**, hazard rules, robot logic, pipeline steps, acceptance criteria | Start of every session | When the plan or contract changes (and log the decision in STATUS) |
| `docs/STATUS.md` | Live log: who is doing what, done, blocked, decisions, handoffs | Start of every session, and before starting a new task | After finishing or starting any meaningful chunk of work, and before ending a session |

Rules:

1. **At session start:** `git pull`, then read `CLAUDE.md`, `docs/STATUS.md`, `docs/IMPLEMENTATION.md`.
2. **Before ending a session or handing off:** update `docs/STATUS.md` (move your items, add decisions, note blockers), commit it with your work, push.
3. **Every decision that changes the plan** gets a dated line in the Decision log in `STATUS.md`, and the matching section of `IMPLEMENTATION.md` is edited in the same commit.
4. Keep entries short: one line each, with the person's name, not "the agent".
5. If `STATUS.md` and `IMPLEMENTATION.md` disagree, `IMPLEMENTATION.md` wins for the contract; raise the conflict in Open questions.

## Ownership (do not edit the other side's area without logging it)

| Area | Owner | Agent may change |
| --- | --- | --- |
| `src/`, app styling, UI behavior | Yasser | Yasser's agent |
| `public/data/` placeholder files | Yasser (until real data lands) | Yasser's agent |
| `public/data/` real outputs, `pipeline/`, `pipeline/hazard_rules.json` | Nic | Nic's agent |
| Build config, GitHub Actions, Pages deploy | Nic | Nic's agent |
| `docs/`, `CLAUDE.md`, `README.md` | Shared | Both, through pull requests or small direct commits |

The data contract (section 4 of `IMPLEMENTATION.md`) belongs to both. Change it only after both owners agree; bump `schema_version` when a field is added, renamed or removed.

## Git workflow

- Branches: `ui/<topic>` (Yasser), `pipeline/<topic>` and `data/<topic>` (Nic), `docs/<topic>` (shared). Small doc and status updates may go straight to `main`.
- `git pull --rebase` before starting work and before pushing.
- Merge feature branches through pull requests at the sync points listed in `STATUS.md`.
- Never commit raw NASA files. `pipeline/raw/` is git-ignored; GitHub rejects files over 100 MB. Commit only processed, web-sized outputs.
- On Windows, set `git config core.longpaths true` in this repo.
- Commit messages: imperative summary line, short body saying why.

## Non-negotiable technical rules

- **Coordinates:** GeoJSON is `[longitude, latitude]`. Other JSON uses `{"lat", "lon"}`. Longitudes are always −180..180 (HiRISE gives 0..360 east: subtract 360).
- **Map:** Mars Trek global tiles are plain lat/lon: react-leaflet uses `crs={L.CRS.EPSG4326}`.
- **Distances:** computed in the pipeline with Mars radius 3,389.5 km; never with Leaflet's Earth-based tools.
- **IDs:** every hazard, route and coverage zone has a stable `id`; every data file has `schema_version`.
- **Determinism:** the pipeline reads thresholds from `pipeline/hazard_rules.json` and produces identical outputs for identical inputs.

## Scientific honesty rules (these protect the Validity score)

- Every hazard carries `evidence`: `nasa_derived`, `inferred` or `simulated`. Rover and drone observations are always `simulated`.
- Missing, no-data or suspect DTM cells are never safe: mark them `inspection_required`.
- Unscouted terrain is never shown as safe.
- No invented precision: no "95% safe", no oxygen or physiology modeling.
- Safe failure is a feature: emit `no_viable_route` or `backup_unavailable` instead of forcing an unsafe route.
- Ice evidence is cited from Dundas et al. (2018) and CRISM results, not from image color alone.
- Every dataset, library and outside asset used is added to the Sources section of `IMPLEMENTATION.md`.
- AI-generated content (code, crew briefings, images) is disclosed; AI images and video need a visible watermark and no NASA logos.

## Scope control

Use the priority tiers and cut lines in `IMPLEMENTATION.md` (sections 10 and 11). Do not add ROS, Gazebo, trained vision models, live LLM features or 3D terrain unless every acceptance criterion is already met and `STATUS.md` records the team's go-ahead.

## Commands

App (once scaffolded):

```bash
npm install
npm run dev
npm run build
```

Pipeline: see `pipeline/README.md` once it exists (Nic keeps it current).
