// Tests for the example ground photos: every stage has one, and every photo is
// credited, sourced from NASA, and never presented as our site.

import assert from 'node:assert/strict';
import test from 'node:test';
import { GROUND_VIEWS, EXAMPLE_LABEL, groundViewsFor } from '../src/content/groundViews.ts';

test('each mission stage shows at least one example photo', () => {
  for (const stage of ['orbital', 'rover', 'drone', 'eva']) {
    assert.ok(groundViewsFor(stage).length > 0, `no photo for ${stage}`);
  }
});

test('every photo is credited and served from NASA', () => {
  for (const v of GROUND_VIEWS) {
    assert.match(v.id, /^PIA\d{5}$/);
    assert.ok(v.credit.startsWith('NASA'), `${v.id} credit`);
    assert.ok(new URL(v.imageUrl).hostname.endsWith('nasa.gov'), `${v.id} image host`);
    assert.ok(v.pageUrl.includes(v.id), `${v.id} source page`);
  }
});

test('photos are labeled as example terrain, not this site', () => {
  assert.match(EXAMPLE_LABEL, /not this site/i);
  for (const v of GROUND_VIEWS) assert.doesNotMatch(v.mission, /Milankovi/i, `${v.id} claims to be our site`);
});
