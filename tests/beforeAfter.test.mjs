// Step 2 before/after card and the night-infrared layer text: the comparison is measured from the same data the map
// draws, agrees with route readiness, and the night-IR explanation never claims a temperature or meter-scale detail.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { beforeAfter } from '../src/map/beforeAfter.ts';
import { readinessFor } from '../src/map/routeReadiness.ts';
import { DEFAULT_LAYERS, LAYER_EXPLANATIONS, LAYER_LABELS, NIGHT_IR_RAMP } from '../src/map/layers.ts';
import { EVIDENCE_DASH, HAZARD_COLORS, SOFT_GROUND_OUTLINE, hazardStyle } from '../src/map/layerStyles.ts';

const read = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
const routes = read('routes.geojson'), coverage = read('coverage.geojson'), hazards = read('hazards.geojson');
const mission = read('mission.json'), audit = { ...read('route_audit.json'), freshness: 'current' };
const row = (cmp, label) => cmp.rows.find((r) => r.label.startsWith(label));

test('the orbit-only route crosses the simulated soft ground and the scouted route does not', () => {
  const cmp = beforeAfter(mission, routes, coverage, hazards, audit);
  assert.ok(cmp);
  const soft = row(cmp, 'Through the soft ground');
  assert.match(soft.before, /^About \d+ m$/);
  assert.equal(soft.after, 'None');
  assert.equal(soft.better, 'after');
  assert.match(cmp.headline, /found it soft \(simulated\)/); // the find is always labelled simulated
});

test('the scouted route is fully rover-checked and its readiness matches the map rule', () => {
  const cmp = beforeAfter(mission, routes, coverage, hazards, audit);
  assert.equal(row(cmp, 'Line checked').after, '100%');
  const go = readinessFor('drone', routes, audit, coverage, hazards)[mission.discovery.after_route_id].state === 'go';
  assert.equal(row(cmp, 'Ready for the crew').after.startsWith('Go'), go);
});

test('distances and times are the route files\' own numbers', () => {
  const cmp = beforeAfter(mission, routes, coverage, hazards, audit);
  const find = (id) => routes.features.find((f) => f.properties.id === id).properties.stats;
  const b = find(mission.discovery.before_route_id), a = find(mission.discovery.after_route_id);
  assert.equal(row(cmp, 'Distance').before, `${(b.length_m / 1000).toFixed(2)} km`);
  assert.ok(row(cmp, 'Distance').after.startsWith(`${(a.length_m / 1000).toFixed(2)} km`));
  assert.equal(row(cmp, 'Travel time').after, `${Math.round(a.est_time_min)} min`);
});

test('no comparison when a route is missing', () => {
  const noAfter = { ...routes, features: routes.features.filter((f) => f.properties.id !== mission.discovery.after_route_id) };
  assert.equal(beforeAfter(mission, noAfter, coverage, hazards, audit), null);
});

test('soft ground is filled with the loose end of the night-IR ramp, outlined in a color no hazard type uses, and stays dotted', () => {
  const sim = hazards.features.find((h) => h.properties.id === mission.discovery.hazard_id).properties;
  const s = hazardStyle(sim);
  const [r, g, b] = NIGHT_IR_RAMP[0].map((v) => Math.round(v * 255));
  assert.equal(s.fillColor, `#${[r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')}`);
  assert.equal(s.color, SOFT_GROUND_OUTLINE);
  assert.ok(!Object.values(HAZARD_COLORS).includes(s.color));
  assert.equal(s.dashArray, EVIDENCE_DASH.simulated); // simulated evidence keeps its dotted outline
  const slope = hazards.features.find((h) => h.properties.category === 'slope').properties;
  assert.equal(hazardStyle(slope).fillColor, HAZARD_COLORS[slope.type]); // other hazards unchanged
});

test('night infrared is off by default and explained as relative, coarse context', () => {
  assert.equal(DEFAULT_LAYERS.nightIr, false);
  assert.match(LAYER_LABELS.nightIr, /THEMIS/);
  const text = LAYER_EXPLANATIONS.nightIr;
  assert.match(text, /not a temperature/);
  assert.match(text, /100 m/);
  assert.doesNotMatch(text, /°C|K\b/);
});
