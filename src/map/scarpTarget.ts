// Where "Inspect scarp" and "Inspect observation point" go. Pure functions (no React/Leaflet) so the
// Node test runner can check them. The scarp target comes only from scarp geometry; it never falls back to
// an observation point, the mission centre or the middle of an image.

import type { LatLon, OverlayBounds, ScarpLines } from '../data/types.ts';

export type TargetSource = 'scarp_lines' | 'interim_reference';

export interface ScarpTarget {
  target: LatLon | null; // null: the button is disabled and `reason` says why
  source: TargetSource | null;
  evidence: 'inferred';
  note: string; // shown next to the button / in its title
  reason?: string;
}

// Documented interim focus: midpoint between a traced scarp-edge and scarp-foot position on the
// central profile (Yasser's agent's HiRISE trace, PR #15). Used only when scarp_lines.geojson is
// missing. Inferred from imagery, not verified ground truth.
export const INTERIM_SCARP_FOCUS: LatLon = { lat: 54.164258, lon: -147.90572 };

export function normalizeLon(lon: number): number {
  // Purpose: signed longitude in -180..180 (HiRISE labels use 0..360 east: 212.1 E -> -147.9).
  // Values already in range are returned unchanged (no floating-point drift).
  if (lon >= -180 && lon <= 180) return lon;
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

export function scarpFocus(lines: ScarpLines | null): LatLon | null {
  // Purpose: centre of the scarp face from the traced lines: on the profile nearest the middle of the
  // traced longitude range, the midpoint between the edge vertex and the foot vertex (the trace samples
  // both lines on the same profiles). Null when either line is missing.
  const line = (id: string) => lines?.features.find((f) => f.properties.id === id)?.geometry.coordinates;
  const edge = line('scarp-edge');
  const foot = line('scarp-foot');
  if (!edge || !foot || edge.length < 2 || foot.length < 2) return null;
  const lons = edge.map((p) => normalizeLon(p[0]));
  const mid = (Math.min(...lons) + Math.max(...lons)) / 2;
  let index = 0;
  lons.forEach((lon, i) => { if (Math.abs(lon - mid) < Math.abs(lons[index] - mid)) index = i; });
  const footPoint = foot.reduce((best, p) => (Math.abs(normalizeLon(p[0]) - lons[index]) < Math.abs(normalizeLon(best[0]) - lons[index]) ? p : best));
  return { lat: (edge[index][1] + footPoint[1]) / 2, lon: (lons[index] + normalizeLon(footPoint[0])) / 2 };
}

export function insideAny(point: LatLon, boxes: OverlayBounds[] | { south: number; west: number; north: number; east: number }[]): boolean {
  // Purpose: true when `point` lies inside at least one high-resolution coverage box.
  const lon = normalizeLon(point.lon);
  return boxes.some((b) => point.lat >= b.south && point.lat <= b.north && lon >= b.west && lon <= b.east);
}

export function resolveScarpTarget(
  lines: ScarpLines | null,
  coverage: { south: number; west: number; north: number; east: number }[],
): ScarpTarget {
  // Purpose: the verified "Inspect scarp" destination. `lines`: traced scarp (preferred source);
  // `coverage`: native HiRISE boxes (4K overlay and/or core tiles). Outside coverage -> disabled.
  const traced = scarpFocus(lines);
  const target = traced ?? INTERIM_SCARP_FOCUS;
  const source: TargetSource = traced ? 'scarp_lines' : 'interim_reference';
  const note = traced
    ? 'Centre of the traced scarp face (HiRISE image trace; inferred, not ground truth).'
    : 'Interim scarp reference (traced profile midpoint; inferred, not ground truth): scarp lines not published.';
  if (coverage.length === 0) {
    return { target: null, source: null, evidence: 'inferred', note, reason: 'No high-resolution HiRISE coverage is published.' };
  }
  if (!insideAny(target, coverage)) {
    return { target: null, source: null, evidence: 'inferred', note, reason: 'The scarp target lies outside the published HiRISE coverage.' };
  }
  return { target: { lat: target.lat, lon: normalizeLon(target.lon) }, source, evidence: 'inferred', note };
}

export function crewFaceTarget(
  lines: ScarpLines | null,
  viewpoint: LatLon | null | undefined,
  coverage: { south: number; west: number; north: number; east: number }[],
): ScarpTarget {
  // Purpose: "Inspect crew's ice face": the face the crew actually looks at, i.e. the second (upper) scarp's
  // traced face at the viewpoint's longitude (midpoint of the nearest edge and foot vertices). "Inspect
  // scarp" stays on the main face (the drone's target). Disabled, with a reason, when the upper scarp is not
  // traced, the viewpoint is not in front of it, or native HiRISE does not cover the face.
  const note = "Second-scarp face in front of the crew's viewpoint (DTM trace; inferred, not ground truth).";
  const line = (id: string) => lines?.features.find((f) => f.properties.id === id)?.geometry.coordinates;
  const edge = line('upper-scarp-edge');
  const foot = line('upper-scarp-foot');
  if (!edge || !foot || edge.length < 2 || foot.length < 2 || !viewpoint) {
    return { target: null, source: null, evidence: 'inferred', note, reason: 'The face in front of the crew viewpoint is not traced.' };
  }
  const vlon = normalizeLon(viewpoint.lon);
  const lons = edge.map((p) => normalizeLon(p[0]));
  if (vlon < Math.min(...lons) - 0.0005 || vlon > Math.max(...lons) + 0.0005) {
    return { target: null, source: null, evidence: 'inferred', note, reason: 'The crew viewpoint is not in front of the traced second scarp.' };
  }
  const nearest = (pts: number[][]) => pts.reduce((best, p) => (Math.abs(normalizeLon(p[0]) - vlon) < Math.abs(normalizeLon(best[0]) - vlon) ? p : best));
  const e = nearest(edge);
  const f = nearest(foot);
  const target = { lat: (e[1] + f[1]) / 2, lon: (normalizeLon(e[0]) + normalizeLon(f[0])) / 2 };
  if (coverage.length === 0 || !insideAny(target, coverage)) {
    return { target: null, source: null, evidence: 'inferred', note, reason: "The crew's ice face lies outside the published HiRISE coverage." };
  }
  return { target, source: 'scarp_lines', evidence: 'inferred', note };
}

export function observationTarget(point: LatLon | null | undefined): LatLon | null {
  // Purpose: "Inspect observation point" destination: the selected observation waypoint itself, if valid.
  if (!point || !Number.isFinite(point.lat) || !Number.isFinite(point.lon)) return null;
  return { lat: point.lat, lon: normalizeLon(point.lon) };
}
