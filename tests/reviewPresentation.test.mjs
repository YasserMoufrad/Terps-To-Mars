// Tests for review wording, stage route filtering and safety logging (CLAUDE.md section 16).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createLogger } from '../src/lib/logger.ts';
import { conservativeFeasibilityNotice, dronePerchLabel, logConservativeFeasibility, logRouteReview, missingBackupAssessment, reviewNotices, routeReviewNotice } from '../src/map/reviewPresentation.ts';
import { routesFor } from '../src/map/stageFilters.ts';

const read = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
const routes = read('routes.geojson');
const coverage = read('coverage.geojson');
const mission = read('mission.json');

function route(props, coordinates = [[0, 0], [1, 1]]) {
  // Purpose: minimal route feature; `props` override kind/status/version.
  return { type: 'Feature', geometry: { type: 'LineString', coordinates },
    properties: { id: 'r', kind: 'main', agent: 'crew', version: 'after', status: 'ok', ...props } };
}

function capture() {
  const events = [];
  return { events, logger: createLogger({ runId: 'test-run', sink: (e) => events.push(e) }) };
}

test('orbital stage hides post-discovery routes', () => {
  const ids = routesFor('orbital', routes, mission).features.map((f) => f.properties.id);
  assert.deepEqual(ids, ['rt-orbital-guess-v1']);
});

test('drone/eva stages exclude the preliminary (before) backup', () => {
  for (const stage of ['drone', 'eva']) {
    const kinds = routesFor(stage, routes, mission).features.map((f) => f.properties.id);
    assert.ok(!kinds.includes('rt-crew-backup-v1'));
    assert.ok(kinds.includes('rt-crew-main-v2'));
  }
});

test('missing post-discovery backup is reported, not hidden', () => {
  // The placeholder data now ships a post-discovery backup, so strip it to test the missing case.
  const noBackup = { ...routes, features: routes.features.filter((f) => !(f.properties.kind === 'backup' && f.properties.version === 'after')) };
  assert.equal(missingBackupAssessment('eva', noBackup), true);
  assert.equal(missingBackupAssessment('orbital', noBackup), false);
  assert.ok(reviewNotices('eva', noBackup, mission).some((n) => /post-discovery backup/.test(n)));
  assert.equal(missingBackupAssessment('eva', routes), false);
  const withBackup = { ...noBackup, features: [...noBackup.features, route({ id: 'b2', kind: 'backup' })] };
  assert.equal(missingBackupAssessment('eva', withBackup), false);
});

test('route notices never claim clearance', () => {
  assert.match(routeReviewNotice(route({ status: 'inspection_required' })), /not crew clearance/);
  assert.match(routeReviewNotice(route({ status: 'inspection_required' }, [])), /no candidate geometry/);
  assert.match(routeReviewNotice(route({ status: 'no_viable_route' }, [])), /No viable route/);
  assert.match(routeReviewNotice(route({ status: 'backup_unavailable' }, [])), /No independent/);
  assert.match(routeReviewNotice(route({ kind: 'orbital_guess' })), /unverified/);
  const rejected = routeReviewNotice(route({ status: 'no_viable_route', status_reason: 'over the 5 km round-trip rule' }));
  assert.match(rejected, /over the 5 km round-trip rule/);
  assert.match(rejected, /rejected candidate/);
  assert.equal(routeReviewNotice(route({})), null);
});

test('current conservative no-route verdict is separate from provisional route assessments', () => {
  const report = read('feasibility_report.json');
  const notice = conservativeFeasibilityNotice(report, true);
  assert.match(notice, /all-unscouted assessment: no route found/);
  assert.match(notice, /provisional planning candidates/);
  assert.match(notice, /neither assessment grants crew clearance/);
  assert.equal(conservativeFeasibilityNotice(report, false), null);
  assert.equal(conservativeFeasibilityNotice({ verdict: 'feasible' }, true), null);
  assert.equal(conservativeFeasibilityNotice(null, true), null);
  const { logger, events } = capture();
  logConservativeFeasibility(logger, 'eva', report, true);
  logConservativeFeasibility(logger, 'eva', report, false);
  assert.equal(events.length, 1);
  assert.equal(events[0].event, 'feasibility.conservative_no_route');
  assert.equal(events[0].run_id, 'test-run');
  assert.equal(events[0].assessment, 'all_unscouted');
  assert.equal(events[0].crew_clearance, 'not_established');
  const broken = createLogger({ runId: 'x', sink: () => { throw new Error('sink down'); } });
  assert.doesNotThrow(() => logConservativeFeasibility(broken, 'eva', report, true));
});

test('drone perch label separates a proposed marker from simulated coverage', () => {
  assert.equal(dronePerchLabel({ features: [] }, mission), 'Proposed drone perch: coverage pending');
  const zone = (props) => ({ features: [{ properties: { id: mission.drone.view_cone_id, ...props } }] });
  assert.match(dronePerchLabel(zone({ state: 'inspection_required', sensor: 'none', simulated: false }), mission), /inspection required/);
  assert.match(dronePerchLabel(zone({ state: 'drone_checked', sensor: 'drone_cam', simulated: true }), mission), /simulated/);
  assert.match(dronePerchLabel(coverage, mission), /simulated/);
});

test('route review logging keeps crew clearance not established and never raises on logging failure', () => {
  const { logger, events } = capture();
  logRouteReview(logger, route({ status: 'inspection_required' }), 'orbital');
  logRouteReview(logger, route({ status: 'no_viable_route' }, []), 'eva');
  logRouteReview(logger, route({}), 'eva');
  assert.deepEqual(events.map((e) => e.event), ['route.candidate', 'route.unavailable', 'route.geometric_result']);
  for (const e of events) assert.equal(e.crew_clearance ?? e.fields?.crew_clearance, 'not_established');
  const broken = createLogger({ runId: 'x', sink: () => { throw new Error('sink down'); } });
  assert.doesNotThrow(() => logRouteReview(broken, route({}), 'eva'));
});
