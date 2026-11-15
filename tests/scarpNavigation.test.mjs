// "Inspect scarp" goes to the traced scarp face; "Inspect observation point" to the waypoint; no midpoint fallback.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  INTERIM_SCARP_FOCUS, insideAny, normalizeLon, observationTarget, resolveScarpTarget, scarpFocus,
} from '../src/map/scarpTarget.ts';
import { checkScarpLines } from '../src/data/loadMissionData.ts';

const dataDir = new URL('../public/data/', import.meta.url);
const read = (file) => JSON.parse(readFileSync(new URL(file, dataDir), 'utf8'));
const scarp = read('scarp_lines.geojson');
const hirise = read('hirise.bounds.json');
const core = read('hirise-tiles/core/tiles.json').bounds;
const mission = read('mission.json');
const coverage = [hirise, core];

test('published scarp lines are valid and drive the target', () => {
  const issues = [];
  assert.ok(checkScarpLines(scarp, 'scarp_lines.geojson', issues));
  assert.deepEqual(issues, []);
  const result = resolveScarpTarget(scarp, coverage);
  assert.equal(result.source, 'scarp_lines');
  assert.equal(result.evidence, 'inferred');
  assert.match(result.note, /inferred, not ground truth/);
});

test('scarp target lies between the traced edge and foot, inside native HiRISE coverage', () => {
  const { target } = resolveScarpTarget(scarp, coverage);
  // Traced edge 54.1635-54.1637 N, foot 54.1642-54.1651 N (scarp_lines meta).
  assert.ok(target.lat > 54.1634 && target.lat < 54.1652, `lat ${target.lat}`);
  assert.ok(target.lon > -147.9176 && target.lon < -147.8939, `lon ${target.lon}`);
  assert.ok(insideAny(target, [hirise]), 'inside the 4K native crop');
  // Close to the documented interim profile midpoint (54.164258, -147.905720).
  assert.ok(Math.abs(target.lat - INTERIM_SCARP_FOCUS.lat) < 0.0005 && Math.abs(target.lon - INTERIM_SCARP_FOCUS.lon) < 0.002);
});

test('latitude/longitude order: target is {lat ~54, lon ~-147.9}, not swapped', () => {
  const { target } = resolveScarpTarget(scarp, coverage);
  assert.ok(target.lat > 50 && target.lat < 60 && target.lon < -140 && target.lon > -150);
});

test('212.1 E and -147.9 longitudes give the same target', () => {
  const east = structuredClone(scarp);
  for (const f of east.features) f.geometry.coordinates = f.geometry.coordinates.map(([lon, lat]) => [lon + 360, lat]);
  const a = scarpFocus(scarp);
  const b = scarpFocus(east);
  assert.ok(Math.abs(a.lat - b.lat) < 1e-12 && Math.abs(a.lon - b.lon) < 1e-9);
  assert.ok(Math.abs(normalizeLon(212.106) - -147.894) < 1e-9);
});

test('observation button uses the observation coordinates, never the scarp', () => {
  const obs = observationTarget(mission.endpoints.observation_primary);
  assert.deepEqual(obs, mission.endpoints.observation_primary);
  const { target } = resolveScarpTarget(scarp, coverage);
  assert.notDeepEqual(obs, target);
  assert.equal(observationTarget({ lat: Number.NaN, lon: 1 }), null);
});

test('changing mission endpoints cannot move the scarp target', () => {
  const before = resolveScarpTarget(scarp, coverage).target;
  const moved = structuredClone(mission);
  moved.endpoints.observation_primary = { lat: 54.1, lon: -147.8 };
  moved.site = { ...moved.site, lat: 54.0, lon: -147.7 };
  assert.deepEqual(resolveScarpTarget(scarp, coverage).target, before);
});

test('missing scarp geometry uses the documented interim reference, labelled as such', () => {
  const result = resolveScarpTarget(null, coverage);
  assert.equal(result.source, 'interim_reference');
  assert.deepEqual(result.target, INTERIM_SCARP_FOCUS);
  assert.match(result.note, /Interim/);
});

test('no arbitrary relocation: target outside coverage, or no coverage, disables the button', () => {
  const south = [{ south: 54.12, west: -147.92, north: 54.14, east: -147.88 }];
  const outside = resolveScarpTarget(scarp, south);
  assert.equal(outside.target, null);
  assert.match(outside.reason, /outside/);
  const none = resolveScarpTarget(scarp, []);
  assert.equal(none.target, null);
  assert.match(none.reason, /No high-resolution/);
});

test('broken scarp files are ignored with a warning, not used', () => {
  const issues = [];
  const broken = structuredClone(scarp);
  broken.features = broken.features.filter((f) => f.properties.id !== 'scarp-foot');
  assert.equal(checkScarpLines(broken, 'scarp_lines.geojson', issues), null);
  assert.equal(issues[0].severity, 'warning');
});
