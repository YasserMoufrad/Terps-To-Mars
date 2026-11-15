import type { CoverageCollection, Mission, RouteCollection, RouteFeature, StageId } from '../data/types.ts';
import type { Logger } from '../lib/logger.ts';
import { hasLine, routesFor } from './stageFilters.ts';

export function routeReviewNotice(route: RouteFeature): string | null {
  // Explain route status without equating calculated geometry with crew clearance.
  // route carries both planning status and possibly a drawable candidate line.
  const { status, kind, status_reason: reason } = route.properties;
  const drawn = hasLine(route.geometry.coordinates);
  if (status === 'no_viable_route') {
    return reason
      ? `No viable route under the mission rules: ${reason}.${drawn ? ' The drawn line is the rejected candidate.' : ''}`
      : 'No viable route was found in the modeled terrain.';
  }
  if (status === 'backup_unavailable') {
    return reason ? `No usable backup: ${reason}.${drawn ? ' The drawn line is the rejected candidate.' : ''}`
      : 'No independent, budgeted backup route was found.';
  }
  if (status === 'inspection_required') {
    return hasLine(route.geometry.coordinates)
      ? 'Calculated candidate requires inspection; it is not crew clearance.'
      : 'Route requires inspection; no candidate geometry is available.';
  }
  return kind === 'orbital_guess' ? 'Orbital candidate is unverified; review the evidence before use.' : null;
}

export function missingBackupAssessment(stage: StageId, routes: RouteCollection): boolean {
  // stage determines whether the discovery already happened; only an after-version backup is current.
  return (stage === 'drone' || stage === 'eva') && !routes.features.some(
    f => f.properties.kind === 'backup' && f.properties.agent === 'crew' && f.properties.version === 'after',
  );
}

export function reviewNotices(stage: StageId, routes: RouteCollection, mission: Mission): string[] {
  // Build notices for this mission stage and explicitly report a missing post-discovery assessment.
  const notices = routesFor(stage, routes, mission).features.flatMap(route => {
    const notice = routeReviewNotice(route);
    return notice ? [notice] : [];
  });
  if (missingBackupAssessment(stage, routes)) notices.push('No post-discovery backup assessment was supplied.');
  return notices;
}

export function logRouteReview(logger: Logger, route: RouteFeature, stage: StageId): void {
  // logger supplies the page correlation ID; route/status distinguish a candidate from failure.
  const p = route.properties;
  const hasGeometry = hasLine(route.geometry.coordinates);
  const candidate = hasGeometry && (p.status === 'inspection_required' || p.kind === 'orbital_guess');
  const fields = { mission_stage: stage, route_id: p.id, status: p.status, version: p.version,
    has_geometry: hasGeometry, geometric_feasibility: hasGeometry && (p.status === 'ok' || p.status === 'inspection_required'),
    crew_clearance: 'not_established' };
  if (candidate) logger.warn('safety', 'route.candidate', fields);
  else if (p.status !== 'ok') logger.warn('safety', 'route.unavailable', fields);
  else logger.info('safety', 'route.geometric_result', fields);
}

export function dronePerchLabel(coverage: CoverageCollection, mission: Mission): string {
  // The referenced coverage record distinguishes a proposed inspection marker from simulated coverage.
  const zone = coverage.features.find(f => f.properties.id === mission.drone.view_cone_id)?.properties;
  if (!zone) return 'Proposed drone perch: coverage pending';
  if (zone.state === 'inspection_required' || zone.sensor === 'none') return 'Proposed drone perch: inspection required';
  return zone.simulated ? 'Drone view concept (simulated)' : 'Drone observation area: review evidence';
}
