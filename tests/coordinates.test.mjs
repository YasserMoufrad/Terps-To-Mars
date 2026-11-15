// Cursor coordinate readout: text format, longitude wrapping and the copy format.
import assert from 'node:assert/strict';
import test from 'node:test';
import { copyText, formatLatLon, wrapLon } from '../src/map/coordinates.ts';

test('shows signed and 0..360 east longitude', () => {
  assert.equal(formatLatLon({ lat: 54.15, lon: -147.907 }), '54.15000°N, −147.90700° (212.09300°E)');
  assert.equal(formatLatLon({ lat: -4.5, lon: 137.4 }, 2), '4.50°S, 137.40° (137.40°E)');
});

test('wraps longitudes Leaflet reports past ±180', () => {
  assert.equal(wrapLon(212.093).toFixed(3), '-147.907');
  assert.equal(wrapLon(-147.907), -147.907);
  assert.equal(copyText({ lat: 54.15, lon: 212.093 }), '54.15000, -147.90700');
});
