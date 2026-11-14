// Tests for basemap tile-failure logging (CLAUDE.md section 16).

import assert from 'node:assert/strict';
import test from 'node:test';
import { createLogger } from '../src/lib/logger.ts';
import { createTileErrorReporter } from '../src/map/tileErrors.ts';

function capture() {
  // Purpose: a logger with a fixed run_id whose events land in `events`.
  const events = [];
  return { events, logger: createLogger({ runId: 'tile-test', sink: (e) => events.push(e) }) };
}

test('first tile failure is logged with layer and tile address', () => {
  const { events, logger } = capture();
  const reporter = createTileErrorReporter(logger, 'ctx_z10');
  reporter.report({ z: 10, x: 182, y: 203 });
  assert.equal(events.length, 1);
  assert.equal(events[0].level, 'warn');
  assert.equal(events[0].stage, 'map');
  assert.equal(events[0].event, 'tiles.error');
  assert.equal(events[0].layer, 'ctx_z10');
  assert.equal(events[0].tile, '10/203/182');
  assert.equal(events[0].run_id, 'tile-test');
});

test('repeat failures are counted, not logged (no high-volume logging)', () => {
  const { events, logger } = capture();
  const reporter = createTileErrorReporter(logger, 'ctx_z10');
  for (let i = 0; i < 25; i++) reporter.report({ z: 10, x: 182 + i, y: 203 });
  assert.equal(events.length, 1);
  assert.equal(reporter.count(), 25);
});

test('each layer reports its own first failure', () => {
  const { events, logger } = capture();
  createTileErrorReporter(logger, 'ctx_z10').report({ z: 10, x: 1, y: 1 });
  createTileErrorReporter(logger, 'viking_color').report({ z: 7, x: 1, y: 1 });
  assert.deepEqual(events.map((e) => e.layer), ['ctx_z10', 'viking_color']);
});

test('a broken log sink does not stop failures from being counted', () => {
  const logger = createLogger({ sink: () => { throw new Error('sink down'); } });
  const reporter = createTileErrorReporter(logger, 'themis_day_ir');
  assert.doesNotThrow(() => reporter.report({ z: 9, x: 91, y: 101 }));
  assert.equal(reporter.count(), 1);
});
