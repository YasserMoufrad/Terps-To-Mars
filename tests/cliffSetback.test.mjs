// No crew point may sit near a traced cliff edge: the 20 m setback rule (hazard_rules.json)
// plus the 15 m position uncertainty. Written after the east-end viewpoint turned out to be
// 20 m from an untraced second scarp. Every scarp in data/site/scarp_lines.geojson counts.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (path) => JSON.parse(readFileSync(new URL(`../${path}`, import.meta.url), 'utf8'));
const mission = read('public/data/mission.json');
const lines = read('data/site/scarp_lines.geojson').features;
const site = Object.fromEntries(read('data/site/site_points_dtm.geojson').features.map((f) => [f.properties.id, f.geometry.coordinates]));
const MARS_R = 3389500;
const SETBACK_M = 20;
const UNCERTAINTY_M = 15;

function toXY([lon, lat], lat0) {
  // Purpose: local metres (east, north) around latitude lat0 on the Mars sphere.
  const r = Math.PI / 180;
  return [lon * r * MARS_R * Math.cos(lat0 * r), lat * r * MARS_R];
}

function distanceToLine(point, coords) {
  // Purpose: shortest distance in metres from a [lon, lat] point to a [lon, lat] polyline.
  const [px, py] = toXY(point, point[1]);
  let best = Infinity;
  for (let i = 1; i < coords.length; i++) {
    const [ax, ay] = toXY(coords[i - 1], point[1]);
    const [bx, by] = toXY(coords[i], point[1]);
    const dx = bx - ax, dy = by - ay;
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1)));
    best = Math.min(best, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)));
  }
  return best;
}

const edges = lines.filter((f) => f.properties.id.endsWith('scarp-edge'));
const ll = (p) => [p.lon, p.lat];

test('both scarps are traced', () => {
  assert.ok(edges.length >= 2, 'expected the main scarp and the second (upper) scarp');
});

test('no crew point is within the cliff setback plus position uncertainty of any scarp edge', () => {
  const points = { habitat: ll(mission.endpoints.habitat), observation_primary: ll(mission.endpoints.observation_primary),
    observation_backup: ll(mission.endpoints.observation_backup), parking: site.parking };
  for (const [name, p] of Object.entries(points)) {
    for (const e of edges) {
      const d = distanceToLine(p, e.geometry.coordinates);
      assert.ok(d >= SETBACK_M + UNCERTAINTY_M, `${name} is ${d.toFixed(1)} m from ${e.properties.id}`);
    }
  }
});

test('the old east-end viewpoint would fail this check (guards the regression)', () => {
  const old = [-147.894135, 54.166626];
  const nearest = Math.min(...edges.map((e) => distanceToLine(old, e.geometry.coordinates)));
  assert.ok(nearest < SETBACK_M + UNCERTAINTY_M, `old viewpoint is ${nearest.toFixed(1)} m from an edge`);
});

test('primary and backup viewpoints are independent (about 100 m apart, never under 90 m)', () => {
  // The points were chosen 100 m apart on the DTM grid (local radius); on the mean sphere that is ~99.8 m.
  const [a, b] = [ll(mission.endpoints.observation_primary), ll(mission.endpoints.observation_backup)];
  const [ax, ay] = toXY(a, a[1]);
  const [bx, by] = toXY(b, a[1]);
  assert.ok(Math.hypot(ax - bx, ay - by) >= 90);
});
