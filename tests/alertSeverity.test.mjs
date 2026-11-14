// Alert severity: cautions and stops are never shown as good news; every committed alert is classified.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { alertSeverity } from '../src/components/alertSeverity.ts';

test('cautions and stops are recognised', () => {
  assert.equal(alertSeverity('Plan unverified: small hazards are below orbital resolution'), 'caution');
  assert.equal(alertSeverity('Simulated drone concept: rockfall zone suspected, not verified'), 'caution');
  assert.equal(alertSeverity('Rover stopped: wheel slip 38 percent, requesting input'), 'stop');
  assert.equal(alertSeverity('Backup route unavailable'), 'stop');
  assert.equal(alertSeverity('Backup route available for review'), 'info');
});

test('every committed mission alert gets a severity and none is "ok"', () => {
  const mission = JSON.parse(readFileSync(new URL('../public/data/mission.json', import.meta.url), 'utf8'));
  for (const lines of Object.values(mission.alerts)) {
    for (const line of lines) assert.ok(['stop', 'caution', 'info'].includes(alertSeverity(line)), line);
  }
});
