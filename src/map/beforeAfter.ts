// Step 2 "Before and after scouting": the orbit-only crew route (discovery.before_route_id) next to the route after the
// simulated rover scouting (discovery.after_route_id), measured from the same data the map draws.
// Pure (no React/Leaflet) so the Node test runner can check it.

import type { CoverageCollection, HazardCollection, Mission, RouteAudit, RouteCollection, RouteFeature } from '../data/types.ts';
import { insideAreas, polygons, readinessFor, samplePoints } from './routeReadiness.ts';

const STEP_M = 5; // sampling step along each line, metres (same as routeReadiness)

export type Better = 'after' | 'before' | 'same';
export interface CompareRow { label: string; before: string; after: string; better: Better }
export interface BeforeAfter { headline: string; rows: CompareRow[] }

function scoutedShare(route: RouteFeature, coverage: CoverageCollection): number {
  // Purpose: fraction (0..1) of the route's 5 m sample points inside the simulated rover-checked coverage.
  const areas = coverage.features.filter((f) => f.properties.state === 'rover_checked').flatMap((f) => polygons(f.geometry));
  const pts = samplePoints(route.geometry.coordinates, STEP_M);
  return pts.length ? pts.filter(([lon, lat]) => insideAreas(lon, lat, areas)).length / pts.length : 0;
}

function metresInside(route: RouteFeature, geometry: { type: string; coordinates: unknown } | undefined): number {
  // Purpose: approximate length (m) of the route inside one hazard polygon, counted in 5 m steps.
  if (!geometry) return 0;
  const areas = polygons(geometry);
  return samplePoints(route.geometry.coordinates, STEP_M).filter(([lon, lat]) => insideAreas(lon, lat, areas)).length * STEP_M;
}

const better = (b: number, a: number, lowerIsBetter: boolean, tolerance = 0): Better =>
  Math.abs(a - b) <= tolerance ? 'same' : (a < b) === lowerIsBetter ? 'after' : 'before';

export function beforeAfter(mission: Mission, routes: RouteCollection, coverage: CoverageCollection,
  hazards: HazardCollection, audit: RouteAudit | null): BeforeAfter | null {
  // Purpose: the comparison rows, or null when either route is missing or has no line (nothing honest to compare).
  // `hazards`: the discovery's simulated hazard (discovery.hazard_id) is the soft ground both routes are checked against.
  const d = mission.discovery;
  const before = routes.features.find((r) => r.properties.id === d.before_route_id);
  const after = routes.features.find((r) => r.properties.id === d.after_route_id);
  if (!before || !after || before.geometry.coordinates.length < 2 || after.geometry.coordinates.length < 2) return null;

  const soft = hazards.features.find((h) => h.properties.id === d.hazard_id)?.geometry;
  const softB = metresInside(before, soft);
  const softA = metresInside(after, soft);
  const scoutB = scoutedShare(before, coverage);
  const scoutA = scoutedShare(after, coverage);
  const pb = before.properties.stats;
  const pa = after.properties.stats;
  // Readiness as it stands once scouting is finished (Step 3): the same rule that turns the map line green.
  const ready = readinessFor('drone', routes, audit, coverage, hazards);
  const goA = ready[after.properties.id]?.state === 'go';
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  const delta = pa.length_m - pb.length_m;

  const rows: CompareRow[] = [
    { label: 'Through the soft ground (simulated find)', before: softB > 0 ? `About ${softB} m` : 'None', after: softA > 0 ? `About ${softA} m` : 'None',
      better: better(softB, softA, true) },
    { label: 'Line checked by the scout rover', before: pct(scoutB), after: pct(scoutA), better: better(scoutB, scoutA, false, 0.005) },
    { label: 'Distance, one way', before: `${(pb.length_m / 1000).toFixed(2)} km`, after: `${(pa.length_m / 1000).toFixed(2)} km (${delta >= 0 ? '+' : ''}${Math.round(delta)} m)`,
      better: better(pb.length_m, pa.length_m, true, 20) },
    { label: 'Travel time, round trip', before: `${Math.round(pb.est_time_min)} min`, after: `${Math.round(pa.est_time_min)} min`,
      better: better(pb.est_time_min, pa.est_time_min, true, 1) },
    { label: 'Steepest slope crossed', before: `${pb.max_slope_deg.toFixed(1)}°`, after: `${pa.max_slope_deg.toFixed(1)}°`,
      better: better(pb.max_slope_deg, pa.max_slope_deg, true, 0.05) },
    { label: 'Ready for the crew', before: 'No: seen from orbit only', after: goA ? 'Go from Step 3 (simulated scouting)' : 'Still needs inspection',
      better: goA ? 'after' : 'same' },
  ];
  const cost = Math.abs(delta) < 20 ? 'almost no extra distance' : `${delta >= 0 ? '+' : ''}${Math.round(delta)} m`;
  const headline = softB > 0 && softA === 0
    ? `The orbit-only route ran through about ${softB} m of ground that looked firm from orbit; the scout rover found it soft (simulated). The new route goes around it for ${cost}.`
    : `Scouting checked ${pct(scoutA)} of the new route on the ground, against ${pct(scoutB)} of the orbit-only route.`;
  return { headline, rows };
}
