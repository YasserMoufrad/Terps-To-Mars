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

export function escapeHtml(text: string): string {
  // Purpose: make pipeline text safe to place inside a Leaflet popup's HTML.
  return text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
}

export function auditFor(audit: RouteAudit | null, id: string): RouteAuditEntry | null {
  // Purpose: the audit entry for route `id`, or null when the route has not been audited.
  if (audit?.freshness && audit.freshness !== 'current') return null;
  return audit?.routes.find((r) => r.id === id) ?? null;
}

export function diagnosticRows(entry: RouteAuditEntry): [string, string][] {
  // Keep zero and missing values distinct; measured and claimed lengths remain separate.
  const number=(v:unknown,unit='')=>typeof v==='number'&&Number.isFinite(v)?String(v)+unit:'Not measured';
  return [
    ['Status', AUDIT_STATUS_TEXT[entry.audit_status] ?? entry.audit_status],
    ['Measured length',number(entry.length_m,' m')],['Claimed length',number(entry.claimed_length_m,' m')],
    ['Length discrepancy',number(entry.length_mismatch_m,' m')],['Steepest crossed cell',number(entry.max_slope_deg,'°')],
    ['Cells crossed',number(entry.cells_crossed)],['Caution cells crossed',number(entry.cells_caution)],
    ['Excluded cells crossed',number(entry.cells_excluded)],['Unknown cells',number(entry.cells_unknown)],
    ['Outside assessed terrain',number(entry.cells_outside)],['Scarp face cells',number(entry.cells_on_scarp_face)],
    ['Start / end offset',number(entry.start_offset_m,' m')+' / '+number(entry.end_offset_m,' m')+' from the intended points'],
    ['Objective end to scarp foot',number(entry.end_to_scarp_foot_m,' m')],
    ['File status',entry.status_consistent===false?'"'+entry.claimed_status+'" overclaims: terrain evidence supports at most inspection':entry.claimed_status],
  ];
}

export function profileSvg(profile: RouteAuditEntry['profile'], caution: number, exclude: number, width = 240, height = 70): string {
  // Purpose: inline SVG of elevation (line) against distance, with cells at/above `caution` (amber) and
  // `exclude` (red) degrees marked along the bottom. Gaps are left where elevation is unknown.
  const points = (profile ?? []).filter((p) => Number.isFinite(p[0]));
  const known = points.filter((p) => p[1] !== null) as [number, number, number | null][];
  if (known.length < 2) return '';
  const maxD = Math.max(...points.map((p) => p[0])) || 1;
  const zs = known.map((p) => p[1]);
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
  const ticks = points.filter((p) => p[2] !== null && (p[2] as number) >= caution)
    .map((p) => `<rect x="${x(p[0])}" y="${height - 8}" width="2" height="6" fill="${(p[2] as number) >= exclude ? '#e5484d' : '#f5a524'}"/>`)
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
