// Native-resolution HiRISE overlay: bounds/metadata checks, honest caption, zoom limit, loader logging.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { checkOverlayBounds, checkHiriseMeta, loadMissionData } from '../src/data/loadMissionData.ts';
import { imageryAttribution, imageryCaption, MAP_MAX_ZOOM } from '../src/map/imagery.ts';
import { createLogger } from '../src/lib/logger.ts';

const dataDir = new URL('../public/data/', import.meta.url);
const read = (file) => JSON.parse(readFileSync(new URL(file, dataDir), 'utf8'));

function stubFetch(overrides = {}) {
  // Purpose: serve public/data from disk; `overrides` maps a file to JSON or null (404).
  globalThis.fetch = async (url) => {
    const file = String(url).split('/data/')[1];
    if (file in overrides) {
      const body = overrides[file];
      return body === null ? { ok: false, status: 404, json: async () => null }
        : { ok: true, status: 200, json: async () => structuredClone(body) };
    }
    try {
      const text = readFileSync(new URL(file, dataDir), 'utf8');
      return { ok: true, status: 200, json: async () => JSON.parse(text) };
    } catch {
      return { ok: false, status: 404, json: async () => null };
    }
  };
}

test('published HiRISE files are native-resolution and placed in signed lat/lon', () => {
  const bounds = read('hirise.bounds.json');
  const meta = read('hirise.meta.json');
  const issues = [];
  assert.ok(checkOverlayBounds(bounds, 'hirise.bounds.json', issues));
  assert.ok(checkHiriseMeta(meta, 'hirise.meta.json', issues));
  assert.deepEqual(issues, []);
  assert.equal(meta.resampling, 'none_native');
  assert.ok(Math.max(...meta.output_pixels) <= 4096 && Math.min(...meta.output_pixels) >= 3000);
  // The crop must cover Geury's work site and main observation point (-147.905, 54.162-54.163).
  assert.ok(bounds.west < -147.905 && bounds.east > -147.905 && bounds.south < 54.162 && bounds.north > 54.163);
});

test('bad bounds are an error and never drawn', () => {
  const issues = [];
  assert.equal(checkOverlayBounds({ schema_version: '1.0', south: 54.17, north: 54.15, west: 212.1, east: 212.2 }, 'x', issues), null);
  assert.equal(issues[0].severity, 'error');
  assert.equal(checkOverlayBounds({ south: 'a' }, 'x', []), null);
  assert.equal(checkOverlayBounds(null, 'x', []), null);
});

test('incomplete or non-native metadata only warns', () => {
  const issues = [];
  assert.equal(checkHiriseMeta({ output_pixels: [1] }, 'm', issues), null);
  const meta = { ...read('hirise.meta.json'), resampling: 'bilinear' };
  assert.ok(checkHiriseMeta(meta, 'm', issues));
  assert.ok(issues.every((i) => i.severity === 'warning') && issues.length === 2);
});

test('caption states sampling, not optical resolution, and the measured alignment', () => {
  const caption = imageryCaption(read('hirise.meta.json'));
  assert.match(caption, /native pixels/);
  assert.match(caption, /not optical resolution/);
  assert.match(caption, /RMS \d\.\d\d m/);
  assert.doesNotMatch(caption, /verified|safe|cleared/i);
  assert.match(imageryCaption(null), /unavailable/);
  assert.equal(MAP_MAX_ZOOM, 18);
  assert.ok(imageryAttribution(read('hirise.meta.json')).length < 90); // short enough for a phone-width map
});

test('loader returns HD metadata and logs pixels and alignment', async () => {
  stubFetch();
  const events = [];
  const logger = createLogger({ runId: 'test-run', sink: (e) => events.push(e) });
  const data = await loadMissionData('/', logger);
  assert.ok(data.hiriseBounds && data.hiriseMeta);
  const complete = events.find((e) => e.event === 'load.complete');
  assert.deepEqual(complete.hirise_pixels, data.hiriseMeta.output_pixels);
  assert.equal(complete.hirise_alignment, data.hiriseMeta.landmark_alignment);
});

test('missing HD metadata warns but keeps the image', async () => {
  stubFetch({ 'hirise.meta.json': null });
  const data = await loadMissionData('/');
  assert.ok(data.hiriseBounds);
  assert.equal(data.hiriseMeta, null);
  assert.ok(data.issues.some((i) => i.file === 'hirise.meta.json' && i.severity === 'warning'));
});

test('no HD image published: no metadata request, no extra warning', async () => {
  const requested = [];
  stubFetch({ 'hirise.bounds.json': null });
  const inner = globalThis.fetch;
  globalThis.fetch = async (url) => { requested.push(String(url)); return inner(url); };
  const data = await loadMissionData('/');
  assert.equal(data.hiriseBounds, null);
  assert.ok(!requested.some((u) => u.endsWith('hirise.meta.json')));
});
