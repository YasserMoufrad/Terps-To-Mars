// Native-resolution HiRISE overlay: bounds/metadata checks, honest caption, zoom limit, loader logging.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { checkOverlayBounds, checkHiriseMeta, checkHiriseTiles, loadMissionData } from '../src/data/loadMissionData.ts';
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

test('incomplete, non-native or non-finite metadata is rejected as an error', () => {
  const good = read('hirise.meta.json');
  const bad = [
    { output_pixels: [1] },
    { ...good, resampling: 'bilinear' },
    { ...good, ground_sampling_m_ew_ns: [Number.NaN, 0.25] },
    { ...good, output_pixels: [4093.5, 4088] },
    { ...good, registration_rms_m: Number.POSITIVE_INFINITY },
    { ...good, landmark_alignment: 'looks_fine' },
  ];
  for (const meta of bad) {
    const issues = [];
    assert.equal(checkHiriseMeta(meta, 'm', issues), null, JSON.stringify(meta).slice(0, 60));
    assert.equal(issues[0].severity, 'error');
  }
});

test('invalid HD metadata withdraws the image; schema-mismatched bounds are never drawn', async () => {
  stubFetch({ 'hirise.meta.json': { ...read('hirise.meta.json'), resampling: 'bilinear' } });
  let data = await loadMissionData('/');
  assert.equal(data.hiriseBounds, null);
  assert.ok(data.mission && data.routes); // an optional overlay failure never erases mission data
  stubFetch({ 'hirise.bounds.json': { ...read('hirise.bounds.json'), schema_version: '2.0' } });
  data = await loadMissionData('/');
  assert.equal(data.hiriseBounds, null);
  assert.ok(data.issues.some((i) => i.file === 'hirise.bounds.json' && i.severity === 'error'));
});

test('structurally broken core files are errors, not crashes', async () => {
  const routes = JSON.parse(readFileSync(new URL('routes.geojson', dataDir), 'utf8'));
  const swapped = structuredClone(routes);
  swapped.features[0].geometry.coordinates = [[212.1, 54.16], [212.11, 54.17]]; // 0..360 longitude
  const cases = [
    ['routes.geojson', { type: 'FeatureCollection' }],
    ['routes.geojson', swapped],
    ['hazards.geojson', { type: 'FeatureCollection', features: [{ properties: {} }] }],
    ['mission.json', { schema_version: '1.0', stages: 'orbital' }],
  ];
  for (const [file, body] of cases) {
    stubFetch({ [file]: body });
    const data = await loadMissionData('/');
    assert.equal(data[file === 'mission.json' ? 'mission' : file.split('.')[0]], null, file);
    assert.ok(data.issues.some((i) => i.file === file && i.severity === 'error'));
  }
});

test('duplicate ids across data files are an error', async () => {
  const hazards = JSON.parse(readFileSync(new URL('hazards.geojson', dataDir), 'utf8'));
  hazards.features.push(structuredClone(hazards.features[0]));
  stubFetch({ 'hazards.geojson': hazards });
  const data = await loadMissionData('/');
  assert.ok(data.issues.some((i) => i.severity === 'error' && /more than once/.test(i.message)));
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

const tileSet = (role, extra = {}) => ({
  schema_version: '1.0', role, url_template: `hirise-tiles/${role}/{z}/{x}/{y}.webp`,
  bounds: { south: 54.12, west: -147.93, north: 54.18, east: -147.88 },
  min_zoom: role === 'core' ? 16 : 12, max_native_zoom: role === 'core' ? 17 : 15, read_factor: role === 'core' ? 1 : 4,
  landmark_alignment: 'measured_exceeds_tolerance', ...extra,
});

test('tile sets are validated before Leaflet requests them', () => {
  const issues = [];
  assert.ok(checkHiriseTiles(tileSet('core'), 'core', issues));
  assert.equal(checkHiriseTiles(tileSet('core', { url_template: '../../etc/{z}/{x}/{y}' }), 'a', issues), null);
  assert.equal(checkHiriseTiles(tileSet('core', { min_zoom: 18, max_native_zoom: 17 }), 'b', issues), null);
  assert.equal(checkHiriseTiles(tileSet('core', { bounds: { south: 1, north: 0, west: 0, east: 1 } }), 'c', issues), null);
  assert.equal(checkHiriseTiles(tileSet('overview'), 'd', issues), null); // unknown role
  assert.ok(checkHiriseTiles(tileSet('wide'), 'wide', issues));
  assert.equal(issues.length, 4);
  assert.ok(issues.every((i) => i.severity === 'warning'));
});

test('loader orders wide under context under core and missing tile sets raise no issue', async () => {
  stubFetch({ 'hirise-tiles/core/tiles.json': tileSet('core'), 'hirise-tiles/context/tiles.json': tileSet('context'),
    'hirise-tiles/wide/tiles.json': tileSet('wide') });
  const all = await loadMissionData('/');
  assert.deepEqual(all.hiriseTiles.map((t) => t.role), ['wide', 'context', 'core']);
  stubFetch({ 'hirise-tiles/core/tiles.json': null, 'hirise-tiles/context/tiles.json': null, 'hirise-tiles/wide/tiles.json': null });
  const none = await loadMissionData('/');
  assert.deepEqual(none.hiriseTiles, []);
  assert.ok(!none.issues.some((i) => i.file.startsWith('hirise-tiles')));
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
