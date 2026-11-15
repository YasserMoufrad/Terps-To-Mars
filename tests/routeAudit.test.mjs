// Route diagnostics: measured evidence shown on click; rejected routes explain why; nothing reads as cleared.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { checkRouteAudit } from '../src/data/loadMissionData.ts';
import { AUDIT_STATUS_TEXT, auditFor, diagnosticHtml, diagnosticRows, escapeHtml, isRejected, profileSvg, routeRejectedForStyle } from '../src/map/routeAudit.ts';
import { routeStyle } from '../src/map/layerStyles.ts';

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

test('generated routes pass their own terrain audit; budget-rejected ones still read as rejected', () => {
  for (const f of routes.features) {
    const entry = auditFor(audit, f.properties.id);
    assert.equal(entry.audit_status, 'candidate_requires_inspection', f.properties.id);
    assert.equal(entry.cells_excluded, 0);
    assert.equal(entry.cells_in_rockfall_zone, 0);
    assert.equal(entry.cells_on_scarp_face, 0);
    assert.ok(Math.abs(entry.length_m - f.properties.stats.length_m) < 1, 'claimed length equals the audited line');
    const rejected = isRejected(f.properties, entry);
    assert.equal(rejected, f.properties.status === 'no_viable_route' || f.properties.status === 'backup_unavailable');
  }
  const orbital = routes.features.find((f) => f.properties.kind === 'orbital_guess');
  // In orbital planning the candidate is a scouting line: grey unless the terrain audit rejects it.
  assert.equal(routeRejectedForStyle(orbital.properties, auditFor(audit, orbital.properties.id)), false);
  assert.equal(routeRejectedForStyle(orbital.properties, { audit_status: 'excluded_terrain' }), true);
  assert.equal(routeStyle(orbital.properties, null, false).color, '#b4b9c2');
  const main = routes.features.find((f) => f.properties.id === 'rt-crew-main-v2');
  assert.equal(routeStyle(main.properties, null, routeRejectedForStyle(main.properties, auditFor(audit, 'rt-crew-main-v2'))).color, '#b4b9c2');
  assert.equal(orbital.properties.status, 'no_viable_route');
  assert.match(orbital.properties.status_reason, /round-trip/);
});

test('a terrain-rejected line is rejected and its first excluded crossing is listed', () => {
  const entry = { id: 'x', agent: 'crew', kind: 'main', claimed_status: 'inspection_required', audit_status: 'excluded_terrain',
    reasons: ['excluded_terrain: 3 walk cells ≥ 20°'], cells_excluded: 3,
    first_exclusion: { distance_m: 412.4, lon: -147.9, lat: 54.16, kind: 'scarp_face' } };
  assert.ok(isRejected({ id: 'x', status: 'inspection_required' }, entry));
  const rows = Object.fromEntries(diagnosticRows(entry));
  assert.match(rows['First excluded crossing'], /scarp face at 412 m along/);
  assert.match(diagnosticHtml({ id: 'x', agent: 'crew', kind: 'main' }, entry, audit), /Crosses excluded terrain/);
  assert.ok(!isRejected({ id: 'y', status: 'inspection_required' }, { ...entry, audit_status: 'candidate_requires_inspection' }));
});

test('claimed vs measured length is shown only when they disagree', () => {
  const base = { id: 'x', agent: 'crew', kind: 'main', claimed_status: 'inspection_required', audit_status: 'candidate_requires_inspection',
    length_m: 1140, claimed_length_m: 940, length_mismatch_m: 200 };
  assert.match(Object.fromEntries(diagnosticRows({ ...base, reasons: ['stats_mismatch: claims 940 m, line measures 1140 m'] }))['Claimed length'], /differs by/);
  assert.equal(Object.fromEntries(diagnosticRows({ ...base, reasons: [] }))['Claimed length'], undefined);
});

test('a file status of ok is called an overclaim', () => {
  const entry = { id: 'x', agent: 'crew', kind: 'main', claimed_status: 'ok', audit_status: 'candidate_requires_inspection',
    status_consistent: false, reasons: [] };
  assert.match(Object.fromEntries(diagnosticRows(entry))['File status'], /overclaims/);
});

test('profile SVG draws elevation and marks steep cells; unaudited routes say so', () => {
  const svg = profileSvg(auditFor(audit, 'rt-orbital-guess-v1').profile, 15, 20);
  assert.match(svg, /^<svg/);
  assert.match(profileSvg([[0, 10, 5], [10, 12, 25], [20, 14, 5]], 15, 20), /#e5484d/); // excluded cells are marked red
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
  assert.equal(auditFor(empty, 'rt-crew-main-v2'), null);
});
