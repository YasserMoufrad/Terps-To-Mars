# Science Target and Analytical Inspection Implementation Plan

> For agentic workers: implement sequentially with superpowers:executing-plans. Intermediate commits are checkpoints; the user explicitly requested full testing at completion.

**Goal:** Make scarp navigation and every meaningful analytical selection understandable, geographically correct and traceable without a live Python service.

**Architecture:** Existing React/Leaflet consumers plus versioned optional static result artifacts. Python exports the measurements it already computes, fingerprints all dependencies, and keeps unresolved or infeasible outcomes explicit.

**Tech stack:** Existing Vite/React/TypeScript/Leaflet, Python uv/Rasterio/NumPy, Docker Desktop, Node tests and browser verification.

**Spec:** User-provided geographic/capability integration and route/segment/waypoint addenda; summarized in docs/SCIENCE_RESULTS_AUDIT.md.

## Global constraints

- No automatic merge; publish a new draft PR early and checkpoint code as it progresses.
- Do not alter the shared checkout's local data/real-mission-geography changes.
- Core schema 1.0 compatibility; no silent use of pending 1.1 contracts.
- Strict total excursion <5000 m, 30% EVA reserve, Mars radius 3389500 m.
- No invented target choice, route, scientific measurements, terrain safety or live rover control.
- Standard structured logging, one execution run ID, signal-variable descriptions and privacy.
- Local Python runs only in isolated Terps Docker containers; never alter Capstone Triage.

## Review focus

1. Missing/infeasible bundles must still display valid independent analysis.
2. Endpoint/hazard/rules/scarp/terrain changes must invalidate diagnostics even if IDs match.
3. Zero and absent numbers must be visibly different; no claimed statistic substitutes for measurement.
4. Unresolved target choice or geometry outside HiRISE disables navigation without hidden fallback.
5. Mobile panels/controls must not obscure the selected feature; stage and viewport remain distinct.

## Tasks

- [ ] Add optional results contracts, raw-file dependency fingerprints and build/CI stale-result validation (pipeline publication/validators; src/data consumers).
- [ ] Extend route_audit with exact first-exclusion cell and compact local records; explicit objective semantics; bind all relevant inputs.
- [ ] Extend slope_mvp with artifact-mask input/QC disclosure and numeric terrain samples; preserve unsmoothed reference and thresholds.
- [ ] Add target-aware geometry resolution and bounds navigation with padding, marker, highlighted outline, source/evidence and unresolved active selection.
- [ ] Add complete route/segment/waypoint inspector, numeric formatting, local selection and profile highlighting; use authoritative audit in styling/notices/logging.
- [ ] Expose optional feasibility, mixed itinerary, uncertainty/backup/walkback and coverage/registration summaries; labeled replay only for existing scenario outcomes.
- [ ] Add focused tests for all requested regressions and update the traceability matrix/contract/source/status docs.
- [ ] Final full Docker Python + frontend/build + exact-head CI, actual desktop/mobile browser interaction and screenshots. Update PR description with before/after capability table and walkthrough; leave unmerged.

## Checkpoint workflow

Commit the initial audit/plan and open a draft PR now. Push coherent implementation increments without per-commit test runs, as requested. Mark progress honestly. Run the complete verification at the end and correct failures rather than weakening tests.
