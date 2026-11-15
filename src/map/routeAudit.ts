// Route diagnostic summary shown when a route line is clicked: measured length vs claimed, steepest
// crossed slope, excluded/unknown cells, endpoint alignment, the audit verdict and its reasons, and a
// small distance-vs-elevation profile. Pure functions returning strings so the Node tests can check them.

import type { RouteAudit, RouteAuditEntry, RouteProperties } from '../data/types.ts';

export const AUDIT_STATUS_TEXT: Record<string, string> = {
  geometry_invalid: 'Route geometry invalid',
  outside_assessed_terrain: 'Leaves the assessed terrain',
  excluded_terrain: 'Crosses excluded terrain (rejected under the model)',
  unassessed_terrain: 'Crosses unassessed terrain',
  endpoint_mismatch: 'Does not reach its intended points',
  candidate_requires_inspection: 'Candidate: requires inspection (model-feasible, not crew-cleared)',
};

// Audit verdicts that mean the line crosses ground the model excludes, or never reaches its points.
export const REJECTING_AUDIT = new Set(['geometry_invalid', 'outside_assessed_terrain', 'excluded_terrain', 'unassessed_terrain', 'endpoint_mismatch']);

export function isRejected(p: RouteProperties, entry: RouteAuditEntry | null): boolean {
  // Purpose: true when a drawn route must read as rejected (red, broken): the file says no route,
  // or the terrain audit rejects the line. Never true merely because a route is unverified.
  return p.status === 'no_viable_route' || p.status === 'backup_unavailable' || (entry !== null && REJECTING_AUDIT.has(entry.audit_status));
}

export function terrainRejected(entry: RouteAuditEntry | null): boolean {
  // Purpose: true only when the terrain audit itself rejects the line (not a budget or status verdict).
  return entry !== null && REJECTING_AUDIT.has(entry.audit_status);
}

export function routeRejectedForStyle(p: RouteProperties, entry: RouteAuditEntry | null): boolean {
  // Purpose: the orbital candidate is a scouting line (drawn grey) unless the terrain audit rejects it;
  // other routes read as rejected for any no-route status too.
  return p.kind === 'orbital_guess' ? terrainRejected(entry) : isRejected(p, entry);
}

export function escapeHtml(text: string): string {
  // Purpose: make pipeline text safe to place inside a Leaflet popup's HTML.
  return text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
}

export function auditFor(audit: RouteAudit | null, id: string): RouteAuditEntry | null {
  // Purpose: the audit entry for route `id`, or null when the route has not been audited or the analysis
  // manifest marks the audit stale/missing/invalid (audit.freshness, PR #20).
  if (audit?.freshness && audit.freshness !== 'current') return null;
  return audit?.routes.find((r) => r.id === id) ?? null;
}

function measuredText(value: unknown, unit = ''): string {
  // Purpose: a finite number with its unit (zero included), otherwise "Not measured": never blank, never "0" for missing.
  return typeof value === 'number' && Number.isFinite(value) ? `${value}${unit}` : 'Not measured';
}

export function diagnosticRows(entry: RouteAuditEntry): [string, string][] {
  // Purpose: label/value rows for the popup and inspector. Every count is shown, zero included, and measured
  // and claimed lengths are separate rows (PR #20); scarp-zone, first-exclusion and objective rows come from #19.
  const rows: [string, string][] = [
    ['Status', AUDIT_STATUS_TEXT[entry.audit_status] ?? entry.audit_status],
    ['Measured length', measuredText(entry.length_m, ' m')],
    ['Claimed length', measuredText(entry.claimed_length_m, ' m')],
    ['Length discrepancy', measuredText(entry.length_mismatch_m, ' m')],
    ['Steepest crossed cell', measuredText(entry.max_slope_deg, '°')],
    ['Cells crossed', measuredText(entry.cells_crossed)],
    ['Caution cells crossed', measuredText(entry.cells_caution)],
    ['Excluded cells crossed', measuredText(entry.cells_excluded)],
    ['Unknown cells', measuredText(entry.cells_unknown)],
    ['Outside assessed terrain', measuredText(entry.cells_outside)],
    ['Scarp face cells', measuredText(entry.cells_on_scarp_face)],
    ['Start / end offset', `${measuredText(entry.start_offset_m, ' m')} / ${measuredText(entry.end_offset_m, ' m')} from the intended points`],
  ];
  if (entry.first_exclusion) {
    rows.push(['First excluded crossing', `${entry.first_exclusion.kind.replace(/_/g, ' ')} at ${Math.round(entry.first_exclusion.distance_m)} m along (marked on the map)`]);
  }
  if ((entry.cells_in_rockfall_zone ?? 0) > 0 || (entry.cells_in_edge_setback ?? 0) > 0) {
    rows.push(['Scarp zones crossed', `${entry.cells_in_rockfall_zone ?? 0} rockfall, ${entry.cells_in_edge_setback ?? 0} edge-setback cells`]);
  }
  if (entry.objective) rows.push(['Joins', entry.objective.replace('->', ' ↔ ').replace(/_/g, ' ')]);
  if (entry.end_to_scarp_foot_m !== undefined) rows.push(['Objective end to scarp foot', `${Math.round(entry.end_to_scarp_foot_m)} m`]);
  rows.push(['File status', entry.status_consistent === false
    ? `"${entry.claimed_status}" overclaims: terrain evidence supports at most inspection` : entry.claimed_status]);
  return rows;
}

export function profileSvg(profile: RouteAuditEntry['profile'], caution: number, exclude: number, width = 240, height = 70): string {
  // Purpose: inline SVG of elevation (line) against distance, with cells at/above `caution` (amber) and the
  // exclusion limit (red) marked along the bottom. Each sample's own limit/mode (route_audit/3) is used when
  // present, so drive cells are judged against 24° and walk cells against 20°; `exclude` is the fallback.
  const points = (profile ?? []).filter((p) => Number.isFinite(p[0]));
  const known = points.filter((p) => p[1] !== null);
  if (known.length < 2) return '';
  const maxD = Math.max(...points.map((p) => p[0])) || 1;
  const zs = known.map((p) => p[1] as number);
  const lo = Math.min(...zs);
  const span = Math.max(Math.max(...zs) - lo, 1);
  const x = (d: number) => ((d / maxD) * (width - 2) + 1).toFixed(1);
  const y = (z: number) => ((1 - (z - lo) / span) * (height - 14) + 2).toFixed(1);
  let path = '';
  let pen = false;
  for (const p of points) {
    if (p[1] === null) { pen = false; continue; }
    path += `${pen ? 'L' : 'M'}${x(p[0])},${y(p[1])}`;
    pen = true;
  }
  const limit = (p: (typeof points)[number]) => p[3] ?? exclude;
  const ticks = points.filter((p) => p[2] !== null && ((p[4] !== 'drive' && (p[2] as number) >= caution) || (p[2] as number) >= limit(p)))
    .map((p) => `<rect x="${x(p[0])}" y="${height - 8}" width="2" height="6" fill="${(p[2] as number) >= limit(p) ? '#e5484d' : '#f5a524'}"/>`)
    .join('');
  return `<svg class="route-profile" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" `
    + `aria-label="Elevation profile, ${Math.round(span)} m relief over ${Math.round(maxD)} m">`
    + `<path d="${path}" fill="none" stroke="#e6e6e6" stroke-width="1.5"/>${ticks}</svg>`;
}

export function diagnosticHtml(props: RouteProperties, entry: RouteAuditEntry | null, audit: RouteAudit | null): string {
  // Purpose: complete popup HTML for one route; says plainly when no measured audit exists.
  const title = `<strong>${escapeHtml(props.id)}</strong> · ${escapeHtml(props.agent)} ${escapeHtml(props.kind.replace(/_/g, ' '))}`;
  if (!entry) {
    return `<div class="route-diag">${title}<p>No terrain audit for this route: its line has not been checked against the DTM.</p></div>`;
  }
  const rows = diagnosticRows(entry).map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(v)}</td></tr>`).join('');
  const reasons = entry.reasons.length
    ? `<ul>${entry.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join('')}</ul>` : '';
  const t = audit?.thresholds_deg;
  const exclude = entry.agent === 'rover' ? t?.rover_exclude ?? 24 : t?.crew_exclude ?? 20;
  const svg = profileSvg(entry.profile, t?.crew_caution ?? 15, exclude);
  const placeholder = audit?.mission_placeholder ? '<p class="muted">Mission endpoints are placeholders; offsets refer to them.</p>' : '';
  return `<div class="route-diag">${title}<table>${rows}</table>${reasons}${svg}${placeholder}`
    + '<p class="muted">Measured on the NASA HiRISE DTM (~1 m). Below-threshold slope is not crew clearance.</p></div>';
}
