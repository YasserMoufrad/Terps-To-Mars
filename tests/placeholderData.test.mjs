// Checks on the placeholder data in public/data: the replanned crew routes must stay
// out of every "exclude" hazard, and route stats must not hide an over-budget walk.
// When Nic's real pipeline outputs replace these files, the same checks still apply.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

const load = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
const routes = load('routes.geojson').features;
const hazards = load('hazards.geojson').features.filter((h) => h.properties.severity === 'exclude');

function pointInRing([x, y], ring) {
  // Purpose: ray-casting test; `ring` is a closed [lon, lat] polygon ring.
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function hazardsCrossed(coords) {
  // Purpose: ids of exclude hazards that any sampled point of the `coords` polyline falls inside.
  const hit = new Set();
  for (let i = 1; i < coords.length; i++) {
    for (let t = 0; t <= 1; t += 0.01) {
      const p = [coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * t, coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * t];
      for (const h of hazards) if (pointInRing(p, h.geometry.coordinates[0])) hit.add(h.properties.id);
    }
  }
  return [...hit];
}

test('replanned crew routes avoid every exclude hazard', () => {
  const after = routes.filter((r) => r.properties.agent === 'crew' && r.properties.version === 'after');
  assert.ok(after.length >= 2, 'expected a replanned main and a backup');
  for (const r of after) assert.deepEqual(hazardsCrossed(r.geometry.coordinates), [], r.properties.id);
});

test('the orbital guess really does cross a hazard (that is the point of the demo)', () => {
  const guess = routes.find((r) => r.properties.kind === 'orbital_guess');
  assert.ok(hazardsCrossed(guess.geometry.coordinates).length > 0);
  assert.notEqual(guess.properties.status, 'ok');
});

test('a crew route over the 168 min EVA travel budget is never marked ok', () => {
  for (const r of routes.filter((x) => x.properties.agent === 'crew')) {
    if (r.properties.stats.est_time_min > 168) assert.notEqual(r.properties.status, 'ok', r.properties.id);
  }
});
