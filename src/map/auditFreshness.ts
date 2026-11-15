// Audit freshness: recompute the fingerprints pipeline.route_audit stored and reject a stale audit.
// The text formats must match pipeline/route_audit.py (route_fingerprint, endpoints_fingerprint,
// scarp_fingerprint) exactly; published values are pre-rounded, so toFixed matches Python's format.
// No imports from React or Leaflet, so the Node test runner can load it.

import type { Mission, RouteAudit, RouteFeature, ScarpLines, SlopeMeta } from '../data/types';

export const AUDIT_ALGORITHM_VERSION = 'route_audit/2';

async function sha256Hex(text: string): Promise<string> {
  // Purpose: hex SHA-256 of a UTF-8 string (Web Crypto, available in browsers and Node 20+).
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

export function routeFingerprintText(feature: RouteFeature): string {
  // Purpose: id|kind|agent|version|status|length .1f|legs mode:from:to;...|coords lon,lat .7f;...
  const p = feature.properties as unknown as Record<string, unknown> & RouteFeature['properties'];
  const head = ['id', 'kind', 'agent', 'version', 'status'].map((k) => String(p[k] ?? '')).join('|');
  const legs = (p.legs ?? []).map((l) => `${l.mode}:${l.from}:${l.to}`).join(';');
  const length = p.stats?.length_m;
  const coords = (feature.geometry.coordinates ?? []).map(([lon, lat]) => `${lon.toFixed(7)},${lat.toFixed(7)}`).join(';');
  return `${head}|${length === undefined || length === null ? '' : length.toFixed(1)}|${legs}|${coords}`;
}

export function endpointsFingerprintText(mission: Mission): string {
  // Purpose: sorted endpoint names with lat,lon .7f, as pipeline endpoints_fingerprint.
  const endpoints = mission.endpoints as unknown as Record<string, { lat: number; lon: number }>;
  return Object.keys(endpoints).sort().map((k) => `${k}:${endpoints[k].lat.toFixed(7)},${endpoints[k].lon.toFixed(7)}`).join(';');
}

export function scarpFingerprintText(scarp: ScarpLines): string {
  // Purpose: scarp features sorted by id, "lon lat" pairs .7f, as pipeline scarp_fingerprint.
  return [...scarp.features]
    .sort((a, b) => (String(a.properties.id) < String(b.properties.id) ? -1 : String(a.properties.id) > String(b.properties.id) ? 1 : 0))
    .map((f) => `${f.properties.id}:${f.geometry.coordinates.map(([lon, lat]) => `${lon.toFixed(7)} ${lat.toFixed(7)}`).join(',')}`)
    .join(';');
}

export interface AuditFreshness {
  fresh: boolean;
  problems: string[]; // human-readable reasons the audit no longer describes what is drawn
  staleRoutes: string[];
}

export async function checkAuditFreshness(
  audit: RouteAudit, routes: RouteFeature[], mission: Mission | null, scarp: ScarpLines | null, slopeMeta: SlopeMeta | null,
): Promise<AuditFreshness> {
  // Purpose: compare what the audit was computed from with the files the app is about to draw.
  // Any difference (route line or claims, endpoints, scarp, DTM id, thresholds, algorithm) makes it stale.
  const problems: string[] = [];
  const staleRoutes: string[] = [];
  const fp = audit.fingerprint;
  if (!fp) return { fresh: false, problems: ['audit has no fingerprint (made before freshness checks)'], staleRoutes: routes.map((r) => r.properties.id) };
  if (fp.algorithm_version !== AUDIT_ALGORITHM_VERSION) problems.push(`audit algorithm ${fp.algorithm_version}, app expects ${AUDIT_ALGORITHM_VERSION}`);
  if (mission && fp.dtm_id !== mission.site.dtm_id) problems.push(`audit DTM ${fp.dtm_id} is not the mission DTM ${mission.site.dtm_id}`);
  if (mission && fp.endpoints !== await sha256Hex(endpointsFingerprintText(mission))) problems.push('mission endpoints changed since the audit');
  if (scarp && fp.scarp && fp.scarp !== await sha256Hex(scarpFingerprintText(scarp))) problems.push('scarp lines changed since the audit');
  if (slopeMeta) {
    const t = audit.thresholds_deg;
    const s = slopeMeta.thresholds_deg;
    if (t.crew_caution !== s.crew_caution || t.crew_exclude !== s.crew_exclude || t.rover_exclude !== s.rover_exclude) {
      problems.push('audit thresholds differ from the slope map thresholds');
    }
  }
  for (const route of routes) {
    const id = route.properties.id;
    const expected = fp.routes[id];
    if (!expected || expected !== await sha256Hex(routeFingerprintText(route))) staleRoutes.push(id);
  }
  if (staleRoutes.length) problems.push(`route lines or claims changed since the audit: ${staleRoutes.join(', ')}`);
  return { fresh: problems.length === 0, problems, staleRoutes };
}
