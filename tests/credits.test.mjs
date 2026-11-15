// The map's credit bar is hidden, so the About box must credit every source the map draws.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { MAP_CREDITS } from '../src/content/credits.ts';

const all = MAP_CREDITS.map((c) => `${c.what} ${c.credit}`).join('\n');

test('every map layer source is credited in the About box', () => {
  for (const needle of ['HiRISE', 'DTEEC_071085_2345_071006_2345_A01', 'CTX', 'MSSS', 'Esri', 'THEMIS Day IR', 'THEMIS Night IR', 'Viking MDIM 2.1', 'Mars Trek', 'Leaflet']) {
    assert.ok(all.includes(needle), `missing credit: ${needle}`);
  }
});

test('every credit links to its source over https', () => {
  for (const c of MAP_CREDITS) assert.match(c.url, /^https:\/\//, c.what);
});

test('the map reads its attribution strings from credits.ts instead of defining its own', () => {
  const map = readFileSync(new URL('../src/map/MarsMap.tsx', import.meta.url), 'utf8');
  assert.match(map, /from '\.\.\/content\/credits'/);
  assert.doesNotMatch(map, /const \w*ATTRIBUTION = '/);
});
