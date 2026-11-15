// Route readiness for the crew, by mission stage. Step 1 (orbit) and Step 2 (scouting) are amber candidates; from
// Step 3 a crew route is "go" (drawn green) only when the robots have finished with it:
//   - the terrain audit finds no excluded, unknown or outside cell (candidate_requires_inspection),
//   - the file status is not a budget rejection (no_viable_route / backup_unavailable),
//   - every 5 m along the line lies inside the simulated rover-checked coverage,
//   - no exclusion hazard known at this stage (including the rover's discovery) touches the line.
// "Go" means go under this planning model with simulated scouting, never a real-world certification.
// Pure functions (no React/Leaflet) so the Node test runner can check them.

import type { CoverageCollection, HazardCollection, RouteAudit, RouteAuditEntry, RouteCollection, RouteFeature, StageId } from '../data/types.ts';
import { STAGE_INDEX, hazardsFor } from './stageFilters.ts';
import { auditFor } from './routeAudit.ts';

export type Readiness = 'go' | 'candidate' | 'rejected';
export interface RouteReadiness { state: Readiness; reasons: string[] } // reasons: why it is not "go"

type Ring = number[][];

function inRing(lon: number, lat: number, ring: Ring): boolean {
  // Purpose: even-odd ray casting for one [lon, lat] ring.
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function polygons(geometry: { type: string; coordinates: unknown }): Ring[][] {
  // Purpose: Polygon or MultiPolygon as a list of polygons (outer ring first, then holes).
  if (geometry.type === 'Polygon') return [geometry.coordinates as Ring[]];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates as Ring[][];
  return [];
}

export function insideAreas(lon: number, lat: number, areas: Ring[][]): boolean {
  // Purpose: true when the point is inside any polygon (inside its outer ring, outside its holes).
  return areas.some((poly) => poly.length > 0 && inRing(lon, lat, poly[0]) && !poly.slice(1).some((hole) => inRing(lon, lat, hole)));
}

export function samplePoints(coords: number[][], stepM = 5): number[][] {
  // Purpose: points every ~`stepM` metres along a [lon, lat] polyline (local metres; Mars radius 3,389.5 km).
  const out: number[][] = [];
  const mPerDeg = (3389500 * Math.PI) / 180;
  for (let i = 0; i + 1 < coords.length; i++) {
    const [x0, y0] = coords[i];
    const [x1, y1] = coords[i + 1];
    const d = Math.hypot((x1 - x0) * Math.cos((y0 * Math.PI) / 180), y1 - y0) * mPerDeg;
    const n = Math.max(1, Math.ceil(d / stepM));
    for (let k = 0; k < n; k++) out.push([x0 + ((x1 - x0) * k) / n, y0 + ((y1 - y0) * k) / n]);
  }
  if (coords.length) out.push(coords[coords.length - 1]);
  return out;
}

export function routeReadiness(route: RouteFeature, stage: StageId, entry: RouteAuditEntry | null,
  coverage: CoverageCollection, hazards: HazardCollection): RouteReadiness {
  // Purpose: readiness of one route at `stage`. `entry` is its current terrain audit (null = no current audit);
  // `coverage` supplies the rover_checked areas; `hazards` the exclusion zones known so far.
  const p = route.properties;
  if (p.status === 'no_viable_route' || p.status === 'backup_unavailable') return { state: 'rejected', reasons: [p.status_reason ?? p.status] };
  if (entry && entry.audit_status !== 'candidate_requires_inspection') return { state: 'rejected', reasons: [entry.audit_status] };
  const reasons: string[] = [];
  if (STAGE_INDEX[stage] < STAGE_INDEX.drone) reasons.push('robot scouting not finished at this step');
  if (p.agent !== 'crew' || (p.kind !== 'main' && p.kind !== 'backup') || p.version !== 'after') reasons.push('not a post-scouting crew route');
  if (!entry) reasons.push('no current terrain audit');
  const scouted = coverage.features.filter((f) => f.properties.state === 'rover_checked').flatMap((f) => polygons(f.geometry));
  const points = samplePoints(route.geometry.coordinates);
  const unscouted = points.filter(([lon, lat]) => !insideAreas(lon, lat, scouted)).length;
  if (unscouted > 0) reasons.push(`${unscouted} of ${points.length} sampled points outside rover-scouted ground`);
  const blocking = hazardsFor(stage, hazards).features
    .filter((h) => h.properties.severity === 'exclude')
    .filter((h) => { const areas = polygons(h.geometry); return points.some(([lon, lat]) => insideAreas(lon, lat, areas)); });
  if (blocking.length) reasons.push(`crosses ${blocking.map((h) => h.properties.id).join(', ')}`);
  return { state: reasons.length ? 'candidate' : 'go', reasons };
}

export function readinessFor(stage: StageId, routes: RouteCollection, audit: RouteAudit | null,
  coverage: CoverageCollection, hazards: HazardCollection): Record<string, RouteReadiness> {
  // Purpose: routeReadiness for every route at `stage`, keyed by route id (one source for map, summary and notices).
  return Object.fromEntries(routes.features.map((r) => [r.properties.id, routeReadiness(r, stage, auditFor(audit, r.properties.id), coverage, hazards)]));
}
