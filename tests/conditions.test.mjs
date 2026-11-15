// Conditions card: no invented precision. Every temperature names the lander that measured it, the text says the site
// itself was never measured, and every claim has an https source.
import assert from 'node:assert/strict';
import test from 'node:test';
import { CONDITIONS_LEAD, CONDITIONS_SECTIONS, CONDITIONS_SOURCES } from '../src/content/conditions.ts';

const texts = [CONDITIONS_LEAD, ...CONDITIONS_SECTIONS.map((s) => s.text)];

test('every °C figure sits in a sentence that names Viking 2 or Phoenix', () => {
  for (const t of texts) {
    for (const sentence of t.split(/(?<=\.)\s+/)) {
      if (/°C/.test(sentence)) assert.match(sentence, /Viking 2|Phoenix/, `unattributed temperature: ${sentence}`);
    }
  }
});

test('the card says the site itself has no measurements', () => {
  assert.match(CONDITIONS_LEAD, /No instrument has measured this crater/);
  assert.ok(texts.some((t) => /not from this site/.test(t)));
});

test('sources are https and include the NASA lander records', () => {
  assert.ok(CONDITIONS_SOURCES.length >= 3);
  for (const s of CONDITIONS_SOURCES) assert.match(s.url, /^https:\/\//);
  assert.ok(CONDITIONS_SOURCES.some((s) => /PIA11003/.test(s.url)));
});
