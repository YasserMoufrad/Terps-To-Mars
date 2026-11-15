// EVA time budget: the timeline adds up to the route's own timing and the mission's published "Time" stat,
// and the walk-home contingency uses the route's walkback.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { evaTimeline, SITE_MINUTES } from '../src/map/evaTimeline.ts';

const read = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
const mission = read('mission.json');
const main = read('routes.geojson').features.find((f) => f.properties.id === mission.discovery.after_route_id);

test('planned trip = route round trip + site time, against 168 min, matching the published stat', () => {
  const t = evaTimeline(main);
  assert.ok(t);
  assert.equal(t.planned.limit, 168);
  assert.ok(Math.abs(t.planned.total - (main.properties.stats.est_time_min + SITE_MINUTES)) < 0.5);
  const published = Number(/(\d+) of 168/.exec(mission.stages.find((s) => s.id === 'eva').stats.Time)[1]);
  assert.equal(Math.round(t.planned.total), published);
  assert.equal(t.planned.fits, true);
  assert.deepEqual(t.planned.segments.map((s) => s.kind), ['drive', 'walk', 'science', 'walk', 'drive']);
});

test('vehicle-fails contingency walks home instead of driving, against the full 240 min', () => {
  const t = evaTimeline(main);
  assert.equal(t.vehicleFails.limit, 240);
  assert.equal(t.vehicleFails.segments.at(-1).kind, 'walk-home');
  assert.equal(t.vehicleFails.segments.at(-1).minutes, main.properties.walkback_min);
  assert.equal(t.vehicleFails.fits, true);
});

test('a route without legs has no timeline; an overlong one does not fit', () => {
  assert.equal(evaTimeline({ ...main, properties: { ...main.properties, legs: [] } }), null);
  const long = { ...main, properties: { ...main.properties, legs: main.properties.legs.map((l) => ({ ...l, est_time_min: l.est_time_min * 3 })) } };
  assert.equal(evaTimeline(long).planned.fits, false);
});
