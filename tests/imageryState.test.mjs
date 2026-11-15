// HiRISE load states, disclosures and the "Inspect scarp" target (pure logic behind MarsMap/ImageryControls).

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  EMPTY_LOAD, applyLoadEvent, combinedState, decodedSizeMatches, inspectTarget, registrationNote, SAMPLING_DISCLOSURE,
} from '../src/map/imageryState.ts';

const meta = JSON.parse(readFileSync(new URL('../public/data/hirise.meta.json', import.meta.url), 'utf8'));
const run = (...kinds) => kinds.reduce(applyLoadEvent, EMPTY_LOAD);

test('state is never "loaded" when the image failed (404 or corrupt asset)', () => {
  assert.equal(combinedState([run('loading', 'error', 'load')], true, true), 'failed');
  assert.equal(combinedState([run('loading', 'tileload', 'error', 'load')], true, true), 'partial');
  assert.equal(combinedState([run('loading', 'tileload', 'load')], true, true), 'loaded');
  assert.equal(combinedState([run('loading')], true, true), 'loading');
});

test('off, unpublished and not-yet-requested are distinct states', () => {
  assert.equal(combinedState([run('loading', 'error', 'load')], true, false), 'disabled');
  assert.equal(combinedState([], false, true), 'unavailable');
  assert.equal(combinedState([], true, true), 'ready'); // tiles outside the view are never requested
});

test('retry starts from fresh counters', () => {
  const failed = [run('loading', 'error', 'load')];
  assert.equal(combinedState(failed, true, true), 'failed');
  assert.equal(combinedState([run('loading', 'tileload', 'load')], true, true), 'loaded');
});

test('decoded image size must match the published metadata', () => {
  assert.ok(decodedSizeMatches(meta.output_pixels, meta));
  assert.ok(!decodedSizeMatches([2048, 2044], meta));
  assert.ok(decodedSizeMatches([1, 1], null));
});

test('disclosures state sampling vs optical resolution and the measured ~1 m registration', () => {
  assert.match(SAMPLING_DISCLOSURE, /not equivalent to 0\.25 m optical resolution/);
  const note = registrationNote(meta);
  assert.match(note, /RMS 0\.86 m/);
  assert.match(note, /exceeds 1 m tolerance/);
  assert.match(note, /not independent ground truth/);
  assert.doesNotMatch(note, /verified|cleared|safe/i);
});

test('Inspect scarp never targets a point outside the native image', () => {
  const b = { south: 54.15, west: -147.92, north: 54.17, east: -147.89 };
  assert.deepEqual(inspectTarget(b, [{ lat: 54.16291, lon: -147.90546 }]), { lat: 54.16291, lon: -147.90546 });
  const centre = inspectTarget(b, [{ lat: 54.141, lon: -147.894 }]); // main's observation point is south of the crop
  assert.ok(Math.abs(centre.lat - 54.16) < 1e-9 && Math.abs(centre.lon + 147.905) < 1e-9);
});
