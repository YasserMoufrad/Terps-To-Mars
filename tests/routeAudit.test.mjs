// Route diagnostics: measured evidence shown on click; rejected routes explain why; nothing reads as cleared.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { checkRouteAudit } from '../src/data/loadMissionData.ts';
import { AUDIT_STATUS_TEXT, auditFor, diagnosticHtml, diagnosticRows, escapeHtml, profileSvg } from '../src/map/routeAudit.ts';

const dataDir = new URL('../public/data/', import.meta.url);
const read = (file) => JSON.parse(readFileSync(new URL(file, dataDir), 'utf8'));
const audit = read('route_audit.json');
const routes = read('routes.geojson');

test('every published route has an audit entry and none says ok', () => {
  const issues = [];
  assert.ok(checkRouteAudit(audit, 'route_audit.json', issues));
  assert.deepEqual(issues, []);
  for (const f of routes.features) {
    const entry = auditFor(audit, f.properties.id);
    assert.ok(entry, f.properties.id);
    assert.notEqual(entry.audit_status, 'ok');
    assert.ok(entry.audit_status in AUDIT_STATUS_TEXT);
  }
});

test('the preliminary orbital route is shown as rejected with its endpoint gap', () => {
  const entry = auditFor(audit, 'rt-orbital-guess-v1');
  assert.equal(entry.audit_status, 'excluded_terrain');
  assert.ok(entry.end_offset_m > 200, `end offset ${entry.end_offset_m}`);
  const html = diagnosticHtml(routes.features[0].properties, entry, audit);
  assert.match(html, /Crosses excluded terrain/);
  assert.match(html, /from the intended points/);
  assert.match(html, /not crew clearance/);
});

test('claimed and measured length are always shown separately', () => {
  const rows = (id) => Object.fromEntries(diagnosticRows(auditFor(audit, id)));
  assert.match(rows('rt-crew-main-v2')['Claimed length'], / m$/);
  assert.match(rows('rt-crew-main-v1')['Claimed length'], / m$/);
  assert.ok(rows('rt-crew-main-v2')['Length discrepancy']);
});

test('a file status of ok is called an overclaim', () => {
  const entry = auditFor(audit, 'rt-crew-main-v1');
  assert.equal(entry.claimed_status, 'ok');
  assert.match(Object.fromEntries(diagnosticRows(entry))['File status'], /overclaims/);
});

test('profile SVG draws elevation and marks steep cells; unaudited routes say so', () => {
  const svg = profileSvg(auditFor(audit, 'rt-orbital-guess-v1').profile, 15, 20);
  assert.match(svg, /^<svg/);
  assert.match(svg, /#e5484d/); // excluded cells are marked red
  assert.equal(profileSvg([], 15, 20), '');
  const html = diagnosticHtml({ id: 'rt-x', agent: 'crew', kind: 'main' }, null, audit);
  assert.match(html, /No terrain audit/);
});

test('popup text is escaped and a malformed or ok-claiming audit is rejected', () => {
  assert.equal(escapeHtml('<b>&"'), '&lt;b&gt;&amp;&quot;');
  const issues = [];
  assert.equal(checkRouteAudit({ routes: [{ id: 'a', audit_status: 'ok', reasons: [] }] }, 'route_audit.json', issues), null);
  assert.equal(checkRouteAudit({ routes: 'x' }, 'route_audit.json', issues), null);
});

test('no viable route: an audit with zero routes still loads and nothing is drawn as cleared', () => {
  const issues = [];
  const empty = { ...audit, routes: [] };
  assert.ok(checkRouteAudit(empty, 'route_audit.json', issues));
  assert.equal(auditFor(empty, 'rt-crew-main-v1'), null);
});
