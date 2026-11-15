// Tests for the per-stage summary card and stage-specific coverage: each stage tells a
// different part of the story, its words follow the data, and nothing reads as clearance.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { stageSummary } from '../src/map/stageSummary.ts';
import { highlightCoverageFor } from '../src/map/stageFilters.ts';

const read = (f) => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), 'utf8'));
const data = { mission: read('mission.json'), hazards: read('hazards.geojson'), routes: read('routes.geojson'), coverage: read('coverage.geojson') };
const STAGES = ['orbital', 'rover', 'drone', 'eva'];
const text = (s) => s.rows.map((r) => `${r.label}: ${r.value}`).join(' | ');

test('every stage has its own summary and no row is ever "ok"/green', () => {
  const titles = STAGES.map((s) => stageSummary(s, data).title);
  assert.equal(new Set(titles).size, 4);
  for (const s of STAGES) {
    for (const row of stageSummary(s, data).rows) assert.ok(['info', 'caution', 'stop'].includes(row.tone), `${s}: ${row.label}`);
  }
});

test('orbital: the orbit-only plan avoids mapped hazards but stays unverified', () => {
  const row = stageSummary('orbital', data).rows.find((r) => r.label === 'Orbit-only plan');
  assert.equal(row.tone, 'caution');
  assert.match(row.value, /Drive \d\.\d\d km, walk \d+ m; routed around every mapped/);
  assert.ok(!stageSummary('orbital', data).rows.some((r) => r.label === 'First guess'));
});

test('orbital: without the plan, the straight-line guess is reported as crossing no-go zones', () => {
  const beforeId = data.mission.discovery.before_route_id;
  const noPlan = { ...data, routes: { ...data.routes, features: data.routes.features.filter((r) => r.properties.id !== beforeId) } };
  const row = stageSummary('orbital', noPlan).rows.find((r) => r.label === 'First guess');
  assert.equal(row.tone, 'stop');
  assert.match(row.value, /crosses \d+ no-go zone/);
});

test('rover: old route runs through the simulated soft ground; decision follows chosen_option', () => {
  const s = stageSummary('rover', data);
  assert.match(text(s), /Old route: .*soft ground/);
  assert.match(text(s), /Crew decision: Pending/);
  const decided = { ...data, mission: { ...data.mission, discovery: { ...data.mission.discovery, chosen_option: 'opt-reroute' } } };
  assert.match(text(stageSummary('rover', decided)), /Crew decision: Chosen: Reroute/);
});

test('eva: main route status and backup limits come from the route data', () => {
  const s = stageSummary('eva', data);
  assert.match(text(s), /Main route: Needs inspection: the crew-rover drive is not yet modeled/);
  assert.match(text(s), /Backup: A \d+ m walk between the backup viewpoint and the crew rover; it shares/);
  const noBackup = { ...data, routes: { ...data.routes, features: data.routes.features.filter((r) => r.properties.kind !== 'backup') } };
  const row = stageSummary('eva', noBackup).rows.find((r) => r.label === 'Backup');
  assert.equal(row.tone, 'stop');
});

test('drone: never claims a flight happened', () => {
  assert.match(text(stageSummary('drone', data)), /No flight has occurred/);
});

test('each stage highlights its own coverage on the map', () => {
  const ids = (stage) => highlightCoverageFor(stage, data.coverage, data.mission).features.map((f) => f.properties.state);
  assert.ok(ids('orbital').length > 0 && ids('orbital').every((s) => s === 'unscouted'));
  assert.ok(ids('rover').length > 0 && ids('rover').every((s) => s === 'rover_checked'));
  const drone = highlightCoverageFor('drone', data.coverage, data.mission).features.map((f) => f.properties.id);
  assert.ok(drone.includes(data.mission.drone.view_cone_id));
  assert.equal(ids('eva').length, 0);
});
