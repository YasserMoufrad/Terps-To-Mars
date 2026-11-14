// How each kind of feature is drawn. Color carries the hazard TYPE;
// line pattern carries the EVIDENCE, so "simulated" never looks like real data.

import type { PathOptions } from 'leaflet';
import type {
  HazardProperties, RouteProperties, CoverageProperties, HazardType, Evidence, CoverageState,
} from '../data/types';

export const HAZARD_COLORS: Record<HazardType, string> = {
  U: '#d98a3d', // under their feet
  O: '#e5484d', // over their heads
  S: '#8b6cd9', // in shadow
};

export const EVIDENCE_DASH: Record<Evidence, string | undefined> = {
  nasa_derived: undefined, // solid line
  inferred: '8 6', // dashed
  simulated: '2 6', // dotted
};

export const COVERAGE_COLORS: Record<CoverageState, string> = {
  orbit_only: '#9aa3ad',
  rover_checked: '#3ddc97',
  drone_checked: '#4da3ff',
  unscouted: '#6e7580',
  inspection_required: '#f5a524',
};

export function hazardStyle(p: HazardProperties): PathOptions {
  // Purpose: Leaflet style for one hazard. Color = p.type (U/O/S), outline pattern =
  // p.evidence, fill strength = p.severity (exclude is stronger than caution).
  return {
    color: HAZARD_COLORS[p.type],
    weight: 2,
    dashArray: EVIDENCE_DASH[p.evidence],
    fillColor: HAZARD_COLORS[p.type],
    fillOpacity: p.severity === 'exclude' ? 0.35 : 0.18,
  };
}

export function coverageStyle(p: CoverageProperties): PathOptions {
  // Purpose: Leaflet style for one coverage zone; dotted outline when p.simulated,
  // stronger fill for unscouted / inspection-required ground.
  return {
    color: COVERAGE_COLORS[p.state],
    weight: 1,
    dashArray: p.simulated ? '2 6' : undefined,
    fillColor: COVERAGE_COLORS[p.state],
    fillOpacity: p.state === 'unscouted' || p.state === 'inspection_required' ? 0.18 : 0.06,
  };
}

export const DRIVE_COLOR = '#7cc4ff';

export function routeStyle(p: RouteProperties & { leg_mode?: 'drive' | 'walk' }, supersededId: string | null): PathOptions {
  // Purpose: Leaflet style for one route by p.kind. `supersededId` is the crew route
  // replaced by the discovery (drawn faded gray); a route that is not "ok" but still
  // has a line (e.g. the unverified orbital guess) is drawn amber and dashed.
  // `p.leg_mode` is set on split routes: a crew-rover drive leg is drawn light blue.
  if (p.id === supersededId) return { color: '#b4b9c2', weight: 4, dashArray: '8 8', opacity: 0.8 };
  if (p.status !== 'ok') return { color: '#f5a524', weight: 5, dashArray: '12 8', opacity: 1 };
  if (p.leg_mode === 'drive' && p.agent === 'crew') {
    return { color: DRIVE_COLOR, weight: p.kind === 'backup' ? 4 : 6, dashArray: p.kind === 'backup' ? '12 8' : undefined, opacity: 1 };
  }
  switch (p.kind) {
    case 'main':
      return { color: '#3ddc97', weight: 6, opacity: 1 };
    case 'backup':
      return { color: '#3ddc97', weight: 4, dashArray: '12 8', opacity: 1 };
    case 'rover_path':
      return { color: '#ffffff', weight: 4, dashArray: '2 8', opacity: 1, lineCap: 'round' };
    case 'orbital_guess':
      return { color: '#ffffff', weight: 5, dashArray: '12 8', opacity: 1 };
  }
}

export function routeCasingStyle(p: RouteProperties, supersededId: string | null): PathOptions {
  // Purpose: dark outline drawn under a route, 4 px wider than the route itself,
  // so the line stands out on gray terrain.
  const width = routeStyle(p, supersededId).weight ?? 4;
  return { color: '#0b0d10', weight: width + 4, opacity: 0.75, lineCap: 'round' };
}
