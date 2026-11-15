// Science panel text: honest wording (consistent with ice, never "confirmed ice"), cited sources, and numbers that
// agree with the published mission data.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { ICE_EVIDENCE, SCIENCE_LEAD, SCIENCE_SECTIONS, SCIENCE_SOURCES } from '../src/content/science.ts';

const all = [SCIENCE_LEAD, ICE_EVIDENCE, ...SCIENCE_SECTIONS.map((s) => s.text)].join(' ');

test('ice is "consistent with", never claimed as confirmed', () => {
  assert.match(all, /consistent with/i);
  assert.doesNotMatch(all, /\b(ice is confirmed|confirmed ice|proves? (that )?ice)\b/i);
  assert.match(ICE_EVIDENCE, /not confirmed/);
});

test('every source is a DOI or the HiRISE page, and Dundas 2018 is cited', () => {
  for (const s of SCIENCE_SOURCES) assert.match(s.url, /^https:\/\/(doi\.org|www\.uahirise\.org)\//, s.label);
  assert.ok(SCIENCE_SOURCES.some((s) => s.url.endsWith('10.1126/science.aao1619')));
});

test('the stated viewpoint distance matches the published data (about 230 m from the second cliff foot)', () => {
  const read = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
  const v = read('mission.json').endpoints.observation_primary;
  const foot = read('scarp_lines.geojson').features.find((f) => f.properties.id === 'upper-scarp-foot').geometry.coordinates;
  const R = 3389500, r = Math.PI / 180;
  const d = Math.min(...foot.map(([lon, lat]) => 2 * R * Math.asin(Math.sqrt(Math.sin((lat - v.lat) * r / 2) ** 2
    + Math.cos(v.lat * r) * Math.cos(lat * r) * Math.sin((lon - v.lon) * r / 2) ** 2))));
  assert.ok(d > 200 && d < 260, `${d.toFixed(0)} m`);
  assert.match(SCIENCE_SECTIONS[0].text, /about 230 m back/);
});
