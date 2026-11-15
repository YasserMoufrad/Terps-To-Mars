// "Inspect scarp" vs "Inspect crew's ice face": the main face (drone target) and the second-scarp face
// the crew actually observes are different places, and each button goes to the right one.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { crewFaceTarget, resolveScarpTarget } from '../src/map/scarpTarget.ts';

const read = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
const lines = read('scarp_lines.geojson');
const viewpoint = read('mission.json').endpoints.observation_primary;
const coverage = [read('hirise-tiles/core/tiles.json').bounds, read('hirise.bounds.json')];
const R = 3389500, rad = Math.PI / 180;
const dist = (a, b) => 2 * R * Math.asin(Math.sqrt(Math.sin((b.lat - a.lat) * rad / 2) ** 2
  + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin((b.lon - a.lon) * rad / 2) ** 2));

test("the crew's ice face is on the second scarp, in front of the viewpoint", () => {
  const face = crewFaceTarget(lines, viewpoint, coverage);
  assert.ok(face.target, face.reason);
  const edge = lines.features.find((f) => f.properties.id === 'upper-scarp-edge').geometry.coordinates;
  const foot = lines.features.find((f) => f.properties.id === 'upper-scarp-foot').geometry.coordinates;
  const lats = [...edge, ...foot].map((p) => p[1]);
  assert.ok(face.target.lat >= Math.min(...lats) && face.target.lat <= Math.max(...lats), 'between the second scarp lines');
  assert.ok(face.target.lat < viewpoint.lat, 'the north-facing face is south of the viewpoint');
  assert.ok(dist(face.target, viewpoint) < 400, `${dist(face.target, viewpoint).toFixed(0)} m from the viewpoint`);
});

test('"Inspect scarp" still goes to the main face, a different place', () => {
  const main = resolveScarpTarget(lines, coverage).target;
  const face = crewFaceTarget(lines, viewpoint, coverage).target;
  assert.ok(dist(main, face) > 300, `${dist(main, face).toFixed(0)} m apart`);
  assert.ok(dist(main, viewpoint) > dist(face, viewpoint));
});

test('disabled with a reason when the second scarp is not traced or not covered', () => {
  const mainOnly = { ...lines, features: lines.features.filter((f) => !f.properties.id.startsWith('upper-')) };
  assert.match(crewFaceTarget(mainOnly, viewpoint, coverage).reason, /not traced/);
  assert.match(crewFaceTarget(lines, viewpoint, []).reason, /outside the published HiRISE coverage/);
  assert.match(crewFaceTarget(lines, { lat: 54.13, lon: -147.95 }, coverage).reason, /not in front/);
});
