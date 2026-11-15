// Tests for the optional drive/walk legs on crew routes: splitting for the map,
// loader validation (bad legs warn, never hide the route), and the placeholder data.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { splitRouteLegs, legSummary, crewRoverParking } from '../src/map/routeLegs.ts';
import { checkLegs } from '../src/data/loadMissionData.ts';

const line = [[0, 0], [1, 0], [2, 0], [3, 0]];
function route(props) {
  // Purpose: a minimal crew route over `line`; `props` override any property.
  return { type: 'Feature', geometry: { type: 'LineString', coordinates: line },
    properties: { id: 'r', kind: 'main', agent: 'crew', version: 'after', status: 'ok',
      stats: { length_m: 3, round_trip_m: 6, est_time_min: 1, elevation_gain_m: 0, max_slope_deg: 0, shared_with_main_m: 0 }, ...props } };
}
const legs = [
  { mode: 'drive', from: 0, to: 2, length_m: 2000, est_time_min: 24 },
  { mode: 'walk', from: 2, to: 3, length_m: 400, est_time_min: 20 },
];

test('a route with legs is split into touching pieces, one per leg', () => {
  const out = splitRouteLegs({ type: 'FeatureCollection', schema_version: '1.0', features: [route({ legs })] });
  assert.deepEqual(out.features.map((f) => f.properties.leg_mode), ['drive', 'walk']);
  assert.deepEqual(out.features[0].geometry.coordinates, [[0, 0], [1, 0], [2, 0]]);
  assert.deepEqual(out.features[1].geometry.coordinates, [[2, 0], [3, 0]]);
});

test('routes without legs, or with broken legs, are drawn whole', () => {
  const broken = [{ mode: 'drive', from: 0, to: 9, length_m: 1, est_time_min: 1 }];
  const out = splitRouteLegs({ type: 'FeatureCollection', schema_version: '1.0', features: [route({}), route({ id: 'b', legs: broken })] });
  assert.equal(out.features.length, 2);
  assert.ok(out.features.every((f) => f.geometry.coordinates.length === 4));
});

test('leg summary and crew rover parking point', () => {
  assert.equal(legSummary(route({ legs }).properties), 'drive 2.00 km + walk 400 m each way');
  assert.equal(legSummary(route({}).properties), null);
  assert.deepEqual(crewRoverParking({ features: [route({ legs })] }), [0, 2]); // [lat, lon] of index 2
  assert.equal(crewRoverParking({ features: [route({})] }), null);
});

test('loader warns about bad legs and accepts good or missing ones', () => {
  const run = (l, n = 4) => { const issues = []; checkLegs(l, n, 'route r', issues); return issues; };
  assert.deepEqual(run(undefined), []);
  assert.deepEqual(run(legs), []);
  assert.match(run([{ ...legs[0], mode: 'fly' }])[0].message, /mode/);
  assert.match(run([legs[1]])[0].message, /indexes/);
  assert.match(run([legs[0]])[0].message, /whole line/);
  assert.ok(run('x').every((i) => i.severity === 'warning'));
});

test('loader accepts schema 1.0 and 1.1, rejects others, and flags legs in a 1.0 file', async () => {
  // Purpose: run loadMissionData against in-memory files served by a fake fetch.
  const { loadMissionData } = await import('../src/data/loadMissionData.ts');
  const read = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
  const load = async (routesVersion) => {
    const files = { 'hazards.geojson': read('hazards.geojson'), 'routes.geojson': { ...read('routes.geojson'), schema_version: routesVersion },
      'coverage.geojson': read('coverage.geojson'), 'mission.json': read('mission.json') };
    const realFetch = globalThis.fetch;
    globalThis.fetch = async (url) => {
      const name = String(url).split('/').pop();
      return name in files
        ? { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => files[name] }
        : { ok: false, status: 404, headers: { get: () => 'text/plain' }, json: async () => null };
    };
    try { return (await loadMissionData('/')).issues.filter((i) => i.file === 'routes.geojson'); } finally { globalThis.fetch = realFetch; }
  };
  assert.ok(!(await load('1.1')).some((i) => i.severity === 'error'));
  const v10 = await load('1.0');
  assert.ok(!v10.some((i) => i.severity === 'error'));
  assert.ok(v10.some((i) => /need schema_version 1.1/.test(i.message)));
  assert.ok((await load('2.0')).some((i) => i.severity === 'error' && /schema_version/.test(i.message)));
});

// Budget rules agreed with Nic (2026-11-14) for routes with legs.
const EVA = 240, TRAVEL_BUDGET = EVA * 0.7, SITE_WORK = 20;
const legSum = (p, mode, key) => p.legs.filter((l) => l.mode === mode).reduce((s, l) => s + l[key], 0);
const routesFile = JSON.parse(readFileSync(new URL('../public/data/routes.geojson', import.meta.url), 'utf8'));
const placeholder = (id) => routesFile.features.find((r) => r.properties.id === id).properties;

test('placeholder: 30% reserve check (drive + walk round trip + site work <= 168 min)', () => {
  const main = placeholder('rt-crew-main-v2');
  assert.ok(main.stats.est_time_min + SITE_WORK <= TRAVEL_BUDGET);
});

test('placeholder: walkback check (drive out + site walk + work + walk home <= 240 min)', () => {
  const main = placeholder('rt-crew-main-v2');
  const driveOut = legSum(main, 'drive', 'est_time_min');
  const siteWalk = 2 * legSum(main, 'walk', 'est_time_min');
  assert.ok(driveOut + siteWalk + SITE_WORK + main.walkback_min <= EVA);
});

test('placeholder: 5 km applies to walking only; 10 km hard cap from the habitat', () => {
  for (const id of ['rt-crew-main-v2', 'rt-crew-backup-v2']) {
    const p = placeholder(id);
    assert.ok(2 * legSum(p, 'walk', 'length_m') < 5000, `${id} walking distance`);
    assert.ok(p.stats.length_m <= 10000, `${id} distance from habitat`);
  }
});

test('placeholder: drive-leg routes stay inspection_required (no crew-rover terrain model yet)', () => {
  assert.equal(routesFile.schema_version, '1.1');
  for (const f of routesFile.features) {
    if (f.properties.legs?.some((l) => l.mode === 'drive')) assert.notEqual(f.properties.status, 'ok', f.properties.id);
  }
});
