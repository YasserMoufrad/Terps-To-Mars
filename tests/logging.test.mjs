// Logging tests required by CLAUDE.md section 16 for the frontend.
// Run with `npm test` (Node loads the .ts files with --experimental-strip-types).

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createLogger } from '../src/lib/logger.ts';
import { loadMissionData } from '../src/data/loadMissionData.ts';

const dataDir = new URL('../public/data/', import.meta.url);

function capturingLogger(options = {}) {
  // Purpose: a logger with fixed run_id "test-run" whose events land in `events`.
  const events = [];
  const logger = createLogger({ runId: 'test-run', sink: (e) => events.push(e), ...options });
  return { logger, events };
}

function stubFetch(overrides = {}) {
  // Purpose: replace global fetch with one that serves public/data from disk.
  // `overrides` maps a file name to replacement JSON, or null to answer 404.
  globalThis.fetch = async (url) => {
    const file = String(url).split('/data/')[1];
    if (file in overrides) {
      const body = overrides[file];
      return body === null
        ? { ok: false, status: 404, json: async () => null }
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

function readData(file) {
  // Purpose: parsed copy of one committed file in public/data/, for tests to modify.
  return JSON.parse(readFileSync(new URL(file, dataDir), 'utf8'));
}

test('events are structured and share one run_id', () => {
  const { logger, events } = capturingLogger();
  logger.info('ui', 'stage.change', { stage: 'rover' });
  logger.warn('safety', 'route.unavailable', { route_id: 'rt-1' });
  assert.equal(events.length, 2);
  for (const e of events) {
    assert.equal(e.run_id, 'test-run');
    assert.match(e.ts, /^\d{4}-\d{2}-\d{2}T.*Z$/); // UTC ISO timestamp
    assert.ok(e.stage && e.event && e.level);
  }
  assert.equal(events[0].stage, 'ui');
  assert.equal(events[1].route_id, 'rt-1');
});

test('caller fields cannot overwrite the standard fields', () => {
  const { logger, events } = capturingLogger();
  logger.info('ui', 'x', { run_id: 'forged', level: 'debug', stage: 'forged' });
  assert.equal(events[0].run_id, 'test-run');
  assert.equal(events[0].level, 'info');
  assert.equal(events[0].stage, 'ui');
});

test('the app logs the mission step as mission_stage, not stage', () => {
  // Guards the bug where { stage } was silently replaced by the logger's own field.
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(app, /'stage\.change', \{ mission_stage: stage \}/);
});

test('DEBUG is off by default and on when enabled', () => {
  const off = capturingLogger();
  off.logger.debug('ui', 'noise');
  assert.equal(off.events.length, 0);
  const on = capturingLogger({ debug: true });
  on.logger.debug('ui', 'detail');
  assert.equal(on.events.length, 1);
});

test('secret-looking fields are redacted', () => {
  const { logger, events } = capturingLogger();
  logger.info('data', 'x', { api_key: 'abc', token: 'xyz', file: 'routes.geojson' });
  assert.equal(events[0].api_key, '[redacted]');
  assert.equal(events[0].token, '[redacted]');
  assert.equal(events[0].file, 'routes.geojson');
});

test('a failing log sink never throws into the app', () => {
  const logger = createLogger({ sink: () => { throw new Error('sink down'); } });
  assert.doesNotThrow(() => logger.error('data', 'validation.error', { file: 'x' }));
});

test('loading the committed data logs start and an ok summary', async () => {
  stubFetch();
  const { logger, events } = capturingLogger();
  const data = await loadMissionData('/', logger);
  const summary = events.find((e) => e.event === 'load.complete');
  assert.ok(events.find((e) => e.event === 'load.start'));
  assert.equal(summary.outcome, 'ok');
  assert.equal(summary.errors, 0);
  assert.equal(summary.hazards, data.hazards.features.length);
  assert.ok(events.every((e) => e.run_id === 'test-run'));
});

test('a missing file and a schema mismatch are logged as errors, not hidden', async () => {
  const routes = readData('routes.geojson');
  routes.schema_version = '2.0';
  stubFetch({ 'hazards.geojson': null, 'routes.geojson': routes });
  const { logger, events } = capturingLogger();
  const data = await loadMissionData('/', logger);

  const errors = events.filter((e) => e.event === 'validation.error');
  assert.ok(errors.some((e) => e.file === 'hazards.geojson'));
  assert.ok(errors.some((e) => e.file === 'routes.geojson' && /schema_version/.test(e.reason)));
  assert.equal(events.find((e) => e.event === 'load.complete').outcome, 'errors');
  // Logging the failure must not turn it into success: the data is still missing.
  assert.equal(data.hazards, null);
});

test('robot coverage not marked simulated is an error even when logging fails', async () => {
  const coverage = readData('coverage.geojson');
  const robot = coverage.features.find((f) => f.properties.state === 'rover_checked');
  robot.properties.simulated = false;
  stubFetch({ 'coverage.geojson': coverage });
  const brokenLogger = createLogger({ sink: () => { throw new Error('sink down'); } });
  const data = await loadMissionData('/', brokenLogger);
  assert.ok(data.issues.some((i) => i.severity === 'error' && /not marked simulated/.test(i.message)));
});

test('an undecided discovery (empty chosen_option) is accepted, a bogus one is not', async () => {
  const mission = readData('mission.json');
  mission.discovery.chosen_option = '';
  stubFetch({ 'mission.json': mission });
  let data = await loadMissionData('/');
  assert.ok(!data.issues.some((i) => /chosen_option/.test(i.message)));

  mission.discovery.chosen_option = 'opt-does-not-exist';
  stubFetch({ 'mission.json': mission });
  data = await loadMissionData('/');
  assert.ok(data.issues.some((i) => i.severity === 'error' && /chosen_option/.test(i.message)));
});
