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

test('placeholder: replanned main route fits the budget and its walkback fits the EVA', () => {
  const routes = JSON.parse(readFileSync(new URL('../public/data/routes.geojson', import.meta.url), 'utf8')).features;
  const main = routes.find((r) => r.properties.id === 'rt-crew-main-v2').properties;
  assert.equal(main.status, 'ok');
  assert.ok(main.stats.est_time_min <= 168);
  const driveOneWay = main.legs.filter((l) => l.mode === 'drive').reduce((s, l) => s + l.est_time_min, 0);
  // Drive out, walk to the site and back, rover fails, walk home: must fit a 240 min EVA.
  assert.ok(main.stats.est_time_min - driveOneWay + main.walkback_min <= 240);
});
