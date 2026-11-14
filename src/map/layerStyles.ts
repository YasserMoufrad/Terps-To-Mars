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
  return {
    color: HAZARD_COLORS[p.type],
    weight: 2,
    dashArray: EVIDENCE_DASH[p.evidence],
    fillColor: HAZARD_COLORS[p.type],
    fillOpacity: p.severity === 'exclude' ? 0.35 : 0.18,
  };
}

export function coverageStyle(p: CoverageProperties): PathOptions {
  return {
    color: COVERAGE_COLORS[p.state],
    weight: 1,
    dashArray: p.simulated ? '2 6' : undefined,
    fillColor: COVERAGE_COLORS[p.state],
    fillOpacity: p.state === 'unscouted' || p.state === 'inspection_required' ? 0.18 : 0.06,
  };
}

// `supersededId` is the crew route replaced by the discovery; it is drawn faded.
export function routeStyle(p: RouteProperties, supersededId: string | null): PathOptions {
  if (p.id === supersededId) return { color: '#b4b9c2', weight: 4, dashArray: '8 8', opacity: 0.8 };
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

// A dark outline drawn under every route so it stands out on gray terrain.
export function routeCasingStyle(p: RouteProperties, supersededId: string | null): PathOptions {
  const width = routeStyle(p, supersededId).weight ?? 4;
  return { color: '#0b0d10', weight: width + 4, opacity: 0.75, lineCap: 'round' };
}
