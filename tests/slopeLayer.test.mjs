// Slope overlay: published grid/bounds agree, legend classes, availability, missing/corrupt handling.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { checkOverlayBounds, checkSlopeMeta, loadMissionData } from '../src/data/loadMissionData.ts';
import { SLOPE_SOURCE_TEXT, slopeAvailable, slopeDecodedState, slopeStatusText } from '../src/map/slopeLayer.ts';

const dataDir = new URL('../public/data/', import.meta.url);
const read = (file) => JSON.parse(readFileSync(new URL(file, dataDir), 'utf8'));
const bounds = read('slope.bounds.json');
const meta = read('slope.meta.json');

function stubFetch(overrides = {}) {
  // Purpose: serve public/data from disk; `overrides` maps a file to JSON or null (404).
  globalThis.fetch = async (url) => {
    const file = String(url).split('/data/')[1];
    if (file in overrides) {
      const body = overrides[file];
      return body === null ? { ok: false, status: 404, json: async () => null } : { ok: true, status: 200, json: async () => structuredClone(body) };
    }
    try {
      const text = readFileSync(new URL(file, dataDir), 'utf8');
      return { ok: true, status: 200, json: async () => JSON.parse(text) };
    } catch {
      return { ok: false, status: 404, json: async () => null };
    }
  };
}

function pngSize(file) {
  // Purpose: width/height from a PNG's IHDR chunk (bytes 16-23), without decoding the image.
  const b = readFileSync(new URL(file, dataDir));
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
}

test('published slope PNG, bounds and metadata describe one grid', () => {
  const issues = [];
  const b = checkOverlayBounds(bounds, 'slope.bounds.json', issues);
  assert.ok(b && checkSlopeMeta(meta, b, 'slope.meta.json', issues));
  assert.deepEqual(issues, []);
  assert.deepEqual(pngSize('slope.png'), meta.grid.pixels);
  for (const k of ['south', 'west', 'north', 'east']) assert.ok(Math.abs(bounds[k] - meta.bounds[k]) < 1e-9);
  assert.ok(bounds.north > bounds.south && bounds.east > bounds.west && bounds.west >= -180 && bounds.east <= 180);
  assert.equal(meta.evidence, 'nasa_derived');
});

test('slope grid covers the traced scarp, about one pixel per metre north-south', () => {
  const scarp = read('scarp_lines.geojson');
  for (const f of scarp.features) {
    for (const [lon, lat] of f.geometry.coordinates) {
      assert.ok(lat > bounds.south && lat < bounds.north && lon > bounds.west && lon < bounds.east);
    }
  }
  const metresNS = (bounds.north - bounds.south) * Math.PI / 180 * 3384416.5;
  assert.ok(Math.abs(metresNS / meta.grid.pixels[1] - 1) < 0.01);
});

test('legend labels state degrees for 15/20/24 and an unknown class', () => {
  const labels = meta.legend.map((e) => e.label).join(' | ');
  assert.match(labels, /Below 15°/);
  assert.match(labels, /15° to <20° \(crew caution\)/);
  assert.match(labels, /20° to <24° \(crew excluded under model\)/);
  assert.match(labels, /24° and above \(crew and rover excluded under model\)/);
  assert.match(labels, /Unknown/);
  assert.deepEqual(meta.thresholds_deg, { crew_caution: 15, crew_exclude: 20, rover_exclude: 24 });
  assert.match(SLOPE_SOURCE_TEXT, /NASA HiRISE DTM-derived slope/);
  assert.match(meta.limitations, /sub-metre rocks/);
});

test('availability needs both bounds and metadata; imagery or routes play no part', () => {
  assert.equal(slopeAvailable(bounds, meta), true);
  assert.equal(slopeAvailable(bounds, null), false);
  assert.equal(slopeAvailable(null, meta), false);
});

test('decoded size must equal the DTM grid; wrong size is reported as failed', () => {
  assert.equal(slopeDecodedState(meta.grid.pixels, meta), 'loaded');
  assert.equal(slopeDecodedState([meta.grid.pixels[0] - 1, meta.grid.pixels[1]], meta), 'failed');
  assert.match(slopeStatusText('failed'), /failed to load/);
  assert.match(slopeStatusText('unavailable'), /not published/);
});

test('metadata that disagrees with the bounds, or is synthetic, withdraws the slope map', () => {
  const bad = [
    { ...meta, evidence: 'simulated' },
    { ...meta, bounds: { ...meta.bounds, north: meta.bounds.north + 0.001 } },
    { ...meta, legend: meta.legend.filter((e) => e.class !== 'unknown') },
    { ...meta, thresholds_deg: { crew_caution: 25, crew_exclude: 20, rover_exclude: 24 } },
  ];
  for (const m of bad) {
    const issues = [];
    assert.equal(checkSlopeMeta(m, bounds, 'slope.meta.json', issues), null);
    assert.equal(issues[0].severity, 'error');
  }
});

test('loader: missing slope metadata hides the toggle; everything else still loads', async () => {
  stubFetch({ 'slope.meta.json': null });
  const data = await loadMissionData('/');
  assert.equal(data.slopeBounds, null);
  assert.ok(data.routes && data.mission, 'mission data unaffected');
  assert.ok(data.issues.some((i) => i.file === 'slope.meta.json'));
});

test('loader: published slope, scarp lines and route audit all load cleanly', async () => {
  stubFetch();
  const data = await loadMissionData('/');
  assert.ok(data.slopeBounds && data.slopeMeta && data.scarpLines && data.routeAudit);
  assert.deepEqual(data.issues.filter((i) => /slope|scarp|route_audit/.test(i.file)), []);
});
