// Cursor coordinate readout: text format, longitude wrapping and the copy format.
import assert from 'node:assert/strict';
import test from 'node:test';
import { copyText, formatLatLon, marsDistanceM, niceScale, wrapLon } from '../src/map/coordinates.ts';

test('scale bar uses Mars distances and round lengths', () => {
  // One degree of latitude on Mars is ~59.2 km (Earth: ~111 km).
  assert.equal(Math.round(marsDistanceM({ lat: 54, lon: -147.9 }, { lat: 55, lon: -147.9 }) / 100) * 100, 59200);
  // 3 m per pixel, 110 px max -> 330 m fits -> 200 m bar, 67 px wide.
  assert.deepEqual(niceScale(3, 110), { metres: 200, px: 67, label: '200 m' });
  assert.equal(niceScale(40, 110).label, '2 km');
  assert.ok(niceScale(0.25, 110).px <= 110);
  // At 54°N one degree of longitude is cos(54°) of a degree of latitude: why the map needs two bars.
  const ew = marsDistanceM({ lat: 54.16, lon: -147.9 }, { lat: 54.16, lon: -147.89 });
  const ns = marsDistanceM({ lat: 54.155, lon: -147.9 }, { lat: 54.165, lon: -147.9 });
  assert.ok(Math.abs(ns / ew - 1 / Math.cos(54.16 * Math.PI / 180)) < 0.01, `${(ns / ew).toFixed(3)}`);
});

test('shows signed and 0..360 east longitude', () => {
  assert.equal(formatLatLon({ lat: 54.15, lon: -147.907 }), '54.15000°N, −147.90700° (212.09300°E)');
  assert.equal(formatLatLon({ lat: -4.5, lon: 137.4 }, 2), '4.50°S, 137.40° (137.40°E)');
});

test('wraps longitudes Leaflet reports past ±180', () => {
  assert.equal(wrapLon(212.093).toFixed(3), '-147.907');
  assert.equal(wrapLon(-147.907), -147.907);
  assert.equal(copyText({ lat: 54.15, lon: 212.093 }), '54.15000, -147.90700');
});
