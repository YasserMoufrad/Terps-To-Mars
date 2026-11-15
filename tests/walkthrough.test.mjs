import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { STAGE_IDS } from '../src/data/types.ts';
import { createLogger } from '../src/lib/logger.ts';
import { stageSummary } from '../src/map/stageSummary.ts';
import { WALKTHROUGH_GUIDANCE, recapRoutes, logWalkthroughTransition } from '../src/components/walkthrough.ts';

const read = (name) => JSON.parse(readFileSync(new URL(`../public/data/${name}`, import.meta.url), 'utf8'));

test('every stage offers one concrete action with the right evidence limits', () => {
  assert.deepEqual(Object.keys(WALKTHROUGH_GUIDANCE), STAGE_IDS);
  for (const stage of STAGE_IDS) {
    assert.ok(WALKTHROUGH_GUIDANCE[stage].action.length > 8);
    assert.ok(WALKTHROUGH_GUIDANCE[stage].instruction.length > 30);
  }
  assert.match(WALKTHROUGH_GUIDANCE.orbital.instruction, /Slope map/);
  assert.match(WALKTHROUGH_GUIDANCE.rover.instruction, /simulated rover incident/);
  assert.match(WALKTHROUGH_GUIDANCE.rover.instruction, /Replay/);
  assert.match(WALKTHROUGH_GUIDANCE.drone.instruction, /no drone flight/);
  assert.match(WALKTHROUGH_GUIDANCE.eva.instruction, /backup/);
});

test('recap reflects published route and backup assessments without inventing clearance', () => {
  const data = { mission: read('mission.json'), hazards: read('hazards.geojson'), routes: read('routes.geojson'), coverage: read('coverage.geojson') };
  const summary = stageSummary('eva', data);
  const recap = recapRoutes(summary);
  assert.equal(recap.main, summary.rows.find((row) => row.label === 'Main route').value);
  assert.equal(recap.backup, summary.rows.find((row) => row.label === 'Backup').value);
  assert.match(recap.main, /Needs inspection/);
  assert.equal(recapRoutes({ title: '', rows: [] }).backup, 'No backup assessment supplied');
});

test('finish and restart are correlated, preserve no-clearance, and tolerate a failed log sink', () => {
  const events = [];
  const logger = createLogger({ runId: 'walkthrough-test', sink: (event) => events.push(event) });
  logWalkthroughTransition(logger, 'finish', 'eva');
  logWalkthroughTransition(logger, 'restart', 'eva');
  assert.deepEqual(events.map((event) => event.event), ['walkthrough.finish', 'walkthrough.restart']);
  for (const event of events) {
    assert.equal(event.run_id, 'walkthrough-test');
    assert.equal(event.crew_clearance, 'not_established');
    assert.equal(event.mission_stage, 'eva');
  }
  const broken = createLogger({ runId: 'broken', sink: () => { throw new Error('sink unavailable'); } });
  assert.doesNotThrow(() => logWalkthroughTransition(broken, 'finish', 'eva'));
});
