// Decides which features are visible at each mission stage.
// Pure functions (no React, no Leaflet), so the rules are easy to read and test.

import type {
  StageId, HazardCollection, RouteCollection, CoverageCollection, Mission, FeatureCollection,
} from '../data/types';

// Stage order: a hazard found at the "rover" stage stays visible at "drone" and "eva".
export const STAGE_INDEX: Record<StageId, number> = { orbital: 0, rover: 1, drone: 2, eva: 3 };

function keep<F>(collection: FeatureCollection<F>, test: (feature: F) => boolean): FeatureCollection<F> {
  // Purpose: return a copy of `collection` holding only the features that pass `test`.
  return { ...collection, features: collection.features.filter(test) };
}

export function hazardsFor(stage: StageId, hazards: HazardCollection): HazardCollection {
  // Purpose: hazards first seen at or before `stage` (found hazards stay visible).
  return keep(hazards, (f) => STAGE_INDEX[f.properties.stage] <= STAGE_INDEX[stage]);
}

export function coverageFor(stage: StageId, coverage: CoverageCollection, mission: Mission): CoverageCollection {
  // Purpose: coverage zones shown at `stage`. Robot coverage appears once its robot
  // has scouted; the drone's view cone (mission.drone.view_cone_id) only during the EVA.
  return keep(coverage, (f) => {
    const p = f.properties;
    if (p.id === mission.drone.view_cone_id) return stage === 'eva';
    if (p.state === 'rover_checked') return STAGE_INDEX[stage] >= STAGE_INDEX.rover;
    if (p.state === 'drone_checked') return STAGE_INDEX[stage] >= STAGE_INDEX.drone;
    // "orbit_only" is the default for the whole map, so drawing it adds only clutter.
    if (p.state === 'orbit_only') return false;
    return true; // unscouted, inspection_required: always shown
  });
}

export function routesFor(stage: StageId, routes: RouteCollection, mission: Mission): RouteCollection {
  // Purpose: routes shown at `stage`. Uses the discovery's before/after route ids
  // from `mission` to show the reroute in the rover stage and the result afterwards.
  const { before_route_id: beforeId, after_route_id: afterId } = mission.discovery;
  return keep(routes, (f) => {
    const p = f.properties;
    switch (stage) {
      case 'orbital':
        return p.kind === 'orbital_guess' && p.version === 'before';
      case 'rover':
        // Show the discovery: the rover's path, the old crew route and the new one.
        return (p.kind === 'rover_path' && p.version === 'after') || p.id === beforeId || p.id === afterId;
      case 'drone':
      case 'eva':
        // Post-discovery candidates only; a preliminary backup is not a new assessment.
        return p.id === afterId || (p.kind === 'backup' && p.agent === 'crew' && p.version === 'after');
    }
  });
}

export function hasLine(coordinates: unknown[]): boolean {
  // Purpose: true when a route has a drawable line (at least two positions).
  // Failed routes may arrive with empty geometry and are reported in words instead.
  return Array.isArray(coordinates) && coordinates.length >= 2;
}
