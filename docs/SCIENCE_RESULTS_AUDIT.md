# Science results integration audit

Baseline: main 65c1514 (PR #18 merged). User requests scarp/target correction, complete offline analytical access, and route/segment/waypoint inspection. This document is updated as code lands; "planned" is not completion.

## Architecture and boundaries

Retain React/Leaflet and offline Python. Add small, versioned optional static artifacts and freshness verification; no live planner/control service. Core schema 1.0 remains compatible. Unmerged 1.1 drive/walk contracts are not silently accepted as 1.0. A science target is distinct from an original scarp and an observation waypoint. Because #17 is draft and its backup viewpoint is unresolved, active target selection stays explicitly unresolved until a reviewed stable target ID is supplied; users can inspect available geometry without that becoming mission approval.

## Backend to frontend traceability

| Backend capability | Actual implementation / artifact | Existing consumer | Before | Planned action / validation |
| --- | --- | --- | --- | --- |
| Raster acquisition / publication | acquire, publish_imagery, tiles_hd | imagery/status controls | Backend-only infrastructure | Keep operational controls out of crew UI |
| Terrain slope | terrain.analyze, slope_mvp / slope PNG+meta | slopeLayer, SlopeLegend | Partially integrated | Numeric measurements, opacity, artifact-QC disclosure; compare original DTM samples |
| Elevation / roughness / quality | terrain.analyze | None | Implemented but not exposed | Compact numeric terrain artifact; actual sample locations, effective windows, unknown quality |
| Hazard constraints | hazards.hazard_masks | hazards layer / evidence card | Partially integrated | Selected-location assessment, agent limits, unresolved inputs; no safety inference from absence |
| Route search / fallback / budgets | routing, feasibility | Static routes and review notices | Partially integrated | Show published verdicts/reasons and constraints; no fictitious Run Planner button |
| Route audit | route_audit / route_audit.json | routeAudit popup | Partially integrated | Complete fields, exact first exclusion, per-cell segment records, side inspector and highlight |
| Audit validity | routes_sha256 only | entry lookup by ID | Partially integrated | Bind mission/hazards/scarps/rules/terrain and actual route; stale reports withdrawn |
| Site feasibility | feasibility.audit_site / feasibility_report.json | None | Implemented but not exposed | Optional standalone report; infeasibility remains usable without complete mission bundle |
| Drive/walk / walkback | itinerary.evaluate_mixed, backup_independence | Unmerged #15/#17 UI | Missing published data contract | Optional evaluated reports + legs/parking inspection; strict 5000 m total and 30% reserve unchanged |
| Simulated rover decisions | scenario.rover_decision / discovery | static choices | Partially integrated | Labeled replay of supported/precomputed states; never a command to Mars |
| Coverage | scenario.coverage / coverage.geojson | toggle and tooltip | Partially integrated | Sensor/model/evidence/visibility limits in inspector |
| Registration | registration / hirise.meta.json | numeric disclosure | Partially integrated | Coordinate inspection alongside native imagery; companion registration is not ground truth |
| Scarp targeting | scarp_lines / scarpFocus | fixed original pair and flyTo | Partially integrated | Stable target registry, bounds framing/highlight/source, explicit unresolved active target |
| Selected waypoints | mission endpoints / feasibility discs | labels | Partially integrated | Coordinates, purpose, measured values or Not measured, uncertainty verdict |

## Route field mapping

Identity (id, agent, kind, evidence, terrain_evidence, orientation, modes, vertices), geometry (length_m, claimed_length_m, length_mismatch_m, start/end offsets), terrain (max_slope_deg, cells_caution/crossed/excluded/unknown/outside/on_scarp_face, first_exclusion_at_m, profile), and decision (audit_status, reasons, status_consistent) already exist in Python. Many are omitted or conditionally hidden in routeAudit.ts. Zero must remain zero; missing is Not measured; stale is Stale — requires regeneration. Add exact first-exclusion coordinates and compact crossed-cell records, not route-wide slopes presented as local measurements. Objective semantics must remain undeclared where mission data does not specify one.

## Related PRs

- #14 ui/real-site: real candidate endpoints/photos; open, not merged by this work.
- #15 ui/drive-walk: stacked on #14; implements proposed legs/UI but has budget/common-corridor questions. Reconcile interfaces without importing unrelated placeholder data.
- #17 ui/second-scarp: draft on #15; upper edge/foot and proposed new viewpoint; known backup coverage test failure. Do not choose/merge its mission target implicitly.

## Verification evidence

Initial frontend baseline: 67 tests passed; final typecheck and Docker Python baseline were started separately. Final verification, browser desktop/mobile, slope on/off screenshots and geographic inspection are pending. Intermediate commits are user-requested checkpoints; do full verification once the implementation is complete.

## Remaining scientific limits

No reviewed artifact mask is currently supplied to slope_mvp. Zero no-data fraction is not evidence of artifact-free reconstruction. No automatic landmark ground-truth or source-specification claims are added. Active mission target selection is a team decision, not inferred solely from blue image color.
