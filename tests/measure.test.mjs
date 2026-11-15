// Measuring tool label: Mars-radius distance (never Earth's), m below 1 km and km above, and walking time at the
// EVA planning pace of 20 m/min.
import assert from 'node:assert/strict';
import test from 'node:test';
import { MARS_RADIUS_M, WALK_M_PER_MIN, measureText } from '../src/map/coordinates.ts';
import { LAYER_EXPLANATIONS, NIGHT_IR_RAMP, NIGHT_IR_STRETCH, nightIrStretch, rampGradient } from '../src/map/layers.ts';

const site = { lat: 54.15, lon: -147.9 };
const northBy = (m) => ({ lat: site.lat + (m / MARS_RADIUS_M) * (180 / Math.PI), lon: site.lon });

test('uses the Mars radius: 0.01° of latitude is about 592 m on Mars (it would be about 1112 m on Earth)', () => {
  const m = measureText(site, { lat: site.lat + 0.01, lon: site.lon });
  assert.ok(Math.abs(m.metres - 591.6) < 1, String(m.metres));
});

test('metres under 1 km, kilometres with two decimals above', () => {
  assert.equal(measureText(site, northBy(412)).distance, '412 m');
  assert.equal(measureText(site, northBy(1234)).distance, '1.23 km');
});

test('walking time at the planning pace; a tiny distance says under 1 min', () => {
  assert.equal(WALK_M_PER_MIN, 20);
  assert.equal(measureText(site, northBy(400)).walk, 'about 20 min walk');
  assert.equal(measureText(site, northBy(10)).walk, 'under 1 min walk');
});

test('the same point twice measures zero', () => {
  assert.equal(measureText(site, site).metres, 0);
});

test('night-IR stretch maps the site\'s 2nd percentile to 0 and 98th to 1, and the key uses the map ramp', () => {
  const { slope, intercept } = nightIrStretch(NIGHT_IR_STRETCH.low, NIGHT_IR_STRETCH.high);
  const f = (v) => slope * (v / 255) + intercept; // what the SVG filter does to a 0..255 tile value
  assert.ok(Math.abs(f(NIGHT_IR_STRETCH.low)) < 1e-9);
  assert.ok(Math.abs(f(NIGHT_IR_STRETCH.high) - 1) < 1e-9);
  assert.ok(NIGHT_IR_RAMP[0][2] > NIGHT_IR_RAMP[0][0], 'cold end is blue');
  assert.ok(NIGHT_IR_RAMP.at(-1)[0] > NIGHT_IR_RAMP.at(-1)[2], 'warm end is orange/red');
  assert.equal((rampGradient().match(/rgb\(/g) ?? []).length, NIGHT_IR_RAMP.length);
  assert.match(LAYER_EXPLANATIONS.nightIr, /false-colored/);
});
