// Audit freshness: the published audit matches the published lines; any edit makes it stale and the loader rejects it.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { AUDIT_ALGORITHM_VERSION, checkAuditFreshness, routeFingerprintText } from '../src/map/auditFreshness.ts';
import { loadMissionData } from '../src/data/loadMissionData.ts';

const dataDir = new URL('../public/data/', import.meta.url);
const read = (file) => JSON.parse(readFileSync(new URL(file, dataDir), 'utf8'));
const audit = read('route_audit.json');
const routes = read('routes.geojson');
const mission = read('mission.json');
const scarp = read('scarp_lines.geojson');
const slopeMeta = read('slope.meta.json');

function stubFetch(overrides = {}) {
  // Purpose: serve public/data from disk; `overrides` maps a file to replacement JSON.
  globalThis.fetch = async (url) => {
    const file = String(url).split('/data/')[1];
    if (file in overrides) return { ok: true, status: 200, json: async () => structuredClone(overrides[file]) };
    try {
      const text = readFileSync(new URL(file, dataDir), 'utf8');
      return { ok: true, status: 200, json: async () => JSON.parse(text) };
    } catch {
      return { ok: false, status: 404, json: async () => null };
    }
  };
}

test('published audit is fresh for the published routes, endpoints, scarp and thresholds', async () => {
  assert.equal(audit.fingerprint.algorithm_version, AUDIT_ALGORITHM_VERSION);
  const result = await checkAuditFreshness(audit, routes.features, mission, scarp, slopeMeta);
  assert.deepEqual(result.problems, []);
  assert.ok(result.fresh);
});

test('moving one vertex by ~1 m makes that route stale', async () => {
  const moved = structuredClone(routes.features);
  moved[0].geometry.coordinates[1][1] += 0.00002;
  const result = await checkAuditFreshness(audit, moved, mission, scarp, slopeMeta);
  assert.equal(result.fresh, false);
  assert.deepEqual(result.staleRoutes, [moved[0].properties.id]);
});

test('changed claims, endpoints, DTM, algorithm or a missing fingerprint make the audit stale', async () => {
  const claims = structuredClone(routes.features);
  claims[1].properties.status = 'ok';
  assert.equal((await checkAuditFreshness(audit, claims, mission, scarp, slopeMeta)).fresh, false);
  const m = structuredClone(mission);
  m.endpoints.observation_primary.lat += 0.001;
  assert.match((await checkAuditFreshness(audit, routes.features, m, scarp, slopeMeta)).problems.join(), /endpoints/);
  const d = structuredClone(mission);
  d.site.dtm_id = 'OTHER';
  assert.match((await checkAuditFreshness(audit, routes.features, d, scarp, slopeMeta)).problems.join(), /DTM/);
  const old = { ...audit, fingerprint: { ...audit.fingerprint, algorithm_version: 'route_audit/1' } };
  assert.match((await checkAuditFreshness(old, routes.features, mission, scarp, slopeMeta)).problems.join(), /algorithm/);
  const none = { ...audit, fingerprint: undefined };
  assert.equal((await checkAuditFreshness(none, routes.features, mission, scarp, slopeMeta)).fresh, false);
});

test('fingerprint text uses fixed decimals in GeoJSON [lon, lat] order', () => {
  const text = routeFingerprintText({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[-147.9, 54.1], [-147.8, 54.2]] },
    properties: { id: 'r', kind: 'main', agent: 'crew', version: 'after', status: 'inspection_required', stats: { length_m: 10 } } });
  assert.equal(text, 'r|main|crew|after|inspection_required|10.0||-147.9000000,54.1000000;-147.8000000,54.2000000');
});

test('loader withholds a stale audit and reports it as an error', async () => {
  const stale = structuredClone(routes);
  stale.features[0].geometry.coordinates[0][0] += 0.0001;
  stubFetch({ 'routes.geojson': stale });
  const data = await loadMissionData('/');
  assert.equal(data.routeAudit, null);
  assert.ok(data.issues.some((i) => i.file === 'route_audit.json' && i.severity === 'error' && /stale/.test(i.message)));
  stubFetch();
  const fresh = await loadMissionData('/');
  assert.ok(fresh.routeAudit);
});
