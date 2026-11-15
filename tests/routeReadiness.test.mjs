// Route readiness ("scouted: go", green) and "detected by": Step 1-2 routes are candidates; from Step 3 a crew route is
// go only when the scout covered every metre, the audit passes and no known exclusion zone touches it.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { readinessFor, routeReadiness } from '../src/map/routeReadiness.ts';
import { stageSummary } from '../src/map/stageSummary.ts';
import { detectedBy } from '../src/map/detectedBy.ts';

const read = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
const routes = read('routes.geojson'), coverage = read('coverage.geojson'), hazards = read('hazards.geojson');
const mission = read('mission.json'), audit = { ...read('route_audit.json'), freshness: 'current' };
const entry = (id) => audit.routes.find((r) => r.id === id);
const route = (id) => routes.features.find((f) => f.properties.id === id);

test('both crew routes are go from Step 3 on, and only candidates before', () => {
  for (const stage of ['drone', 'eva']) {
    const r = readinessFor(stage, routes, audit, coverage, hazards);
    assert.equal(r['rt-crew-main-v2'].state, 'go', JSON.stringify(r['rt-crew-main-v2']));
    assert.equal(r['rt-crew-backup-v2'].state, 'go', JSON.stringify(r['rt-crew-backup-v2']));
    assert.notEqual(r['rt-orbital-guess-v1'].state, 'go');
    assert.notEqual(r['rt-rover-v2'].state, 'go');
  }
  for (const stage of ['orbital', 'rover']) {
    for (const [id, x] of Object.entries(readinessFor(stage, routes, audit, coverage, hazards))) assert.notEqual(x.state, 'go', `${stage} ${id}`);
  }
});

test('unscouted ground, a budget rejection, a failed audit or no audit keeps a route from going green', () => {
  const main = route('rt-crew-main-v2');
  const shifted = { ...main, geometry: { ...main.geometry, coordinates: main.geometry.coordinates.map(([lon, lat]) => [lon + 0.01, lat]) } };
  assert.match(routeReadiness(shifted, 'eva', entry(main.properties.id), coverage, hazards).reasons.join(), /outside rover-scouted ground/);
  const rejected = { ...main, properties: { ...main.properties, status: 'backup_unavailable', status_reason: 'EVA time' } };
  assert.equal(routeReadiness(rejected, 'eva', entry(main.properties.id), coverage, hazards).state, 'rejected');
  assert.equal(routeReadiness(main, 'eva', { ...entry(main.properties.id), audit_status: 'excluded_terrain' }, coverage, hazards).state, 'rejected');
  assert.match(routeReadiness(main, 'eva', null, coverage, hazards).reasons.join(), /no current terrain audit/);
});

test('Step 4 summary shows Go only with readiness, and the old route still reaches the soft ground', () => {
  const data = { mission, hazards, routes, coverage };
  const withGo = stageSummary('eva', { ...data, readiness: readinessFor('eva', routes, audit, coverage, hazards) });
  assert.equal(withGo.rows.find((r) => r.label === 'Main route').tone, 'go');
  assert.equal(withGo.rows.find((r) => r.label === 'Backup').tone, 'go');
  assert.ok(stageSummary('eva', data).rows.every((r) => r.tone !== 'go'), 'no readiness supplied: nothing is go');
});

test('the rover discovery names the scout sensors; orbital hazards name their source', () => {
  const sim = hazards.features.find((h) => h.properties.id === mission.discovery.hazard_id).properties;
  assert.match(detectedBy(sim, mission), /^Scout rover \(simulated\): wheel-slip sensor \(\d+% slip\) \+ thermal camera/);
  const slope = hazards.features.find((h) => h.properties.category === 'slope').properties;
  assert.match(detectedBy(slope, mission), /HiRISE .*DTM.*NASA-derived/);
  assert.match(stageSummary('rover', { mission, hazards, routes, coverage }).rows.find((r) => r.label === 'Detected by').value, /wheel-slip/);
});
