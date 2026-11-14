// Load state, disclosure text and navigation targets for the HiRISE imagery layer.
// Pure functions (no React/Leaflet) so the Node test runner can check them.

import type { HiriseMeta, LatLon, OverlayBounds } from '../data/types.ts';

// unavailable: nothing published; disabled: layer switched off; ready: published but nothing on screen yet;
// loading / loaded / partial (some tiles failed) / failed (nothing could be shown).
export type ImageryLoadState = 'unavailable' | 'disabled' | 'ready' | 'loading' | 'loaded' | 'partial' | 'failed';

export const IMAGERY_STATUS_TEXT: Record<ImageryLoadState, string> = {
  unavailable: 'not published',
  disabled: 'switched off',
  ready: 'available; zoom in to load',
  loading: 'loading…',
  loaded: 'shown',
  partial: 'shown, but some tiles failed to load',
  failed: 'failed to load',
};

// Shown next to the imagery controls, not only in a tooltip.
export const SAMPLING_DISCLOSURE = 'Approximately 0.25 m map sampling; not equivalent to 0.25 m optical resolution.';

// Zoom used by "Inspect scarp": ~0.36 m (E-W) per screen pixel at 54 N, close to native sampling.
export const INSPECT_ZOOM = 17;

export interface LayerLoad {
  pending: boolean; // a loading cycle is in progress
  loaded: number; // tiles/images that arrived in the current attempt
  failed: number; // tiles/images that failed in the current attempt
}

export const EMPTY_LOAD: LayerLoad = { pending: false, loaded: 0, failed: 0 };

export function applyLoadEvent(layer: LayerLoad, kind: 'loading' | 'load' | 'tileload' | 'error'): LayerLoad {
  // Purpose: update one layer's counters for a Leaflet event. `kind`: "loading" starts a cycle,
  // "tileload"/"error" count one tile or image, "load" ends the cycle (all visible tiles settled).
  switch (kind) {
    case 'loading': return { ...layer, pending: true };
    case 'tileload': return { ...layer, loaded: layer.loaded + 1 };
    case 'error': return { ...layer, failed: layer.failed + 1 };
    case 'load': return { ...layer, pending: false };
  }
}

export function combinedState(layers: LayerLoad[], published: boolean, enabled: boolean): ImageryLoadState {
  // Purpose: one honest state for the HiRISE checkbox and status line from every HiRISE layer's counters.
  // A layer that only failed is "failed"; any success plus a failure is "partial"; never "loaded" on errors.
  if (!published) return 'unavailable';
  if (!enabled) return 'disabled';
  if (layers.some((l) => l.pending)) return 'loading';
  const loaded = layers.reduce((n, l) => n + l.loaded, 0);
  const failed = layers.reduce((n, l) => n + l.failed, 0);
  if (failed > 0) return loaded > 0 ? 'partial' : 'failed';
  return loaded > 0 ? 'loaded' : 'ready';
}

export function decodedSizeMatches(natural: [number, number], meta: HiriseMeta | null): boolean {
  // Purpose: true when the decoded image's [width, height] matches hirise.meta.json's output_pixels
  // (or no metadata exists to compare). A mismatch means the image and metadata come from different exports.
  if (!meta) return true;
  return natural[0] === meta.output_pixels[0] && natural[1] === meta.output_pixels[1];
}

export function registrationNote(meta: HiriseMeta | null): string {
  // Purpose: visible one-line statement of the measured image alignment, including its limitation.
  if (!meta) return 'Image alignment not stated (metadata missing).';
  if (meta.registration_rms_m === undefined || meta.registration_max_m === undefined) {
    return meta.landmark_alignment === 'not_verified' ? 'Image alignment not yet measured.' : `Alignment: ${meta.landmark_alignment.replace(/_/g, ' ')}.`;
  }
  const verdict = meta.landmark_alignment === 'measured_within_tolerance' ? 'within' : 'exceeds';
  return `Measured offset vs the 1 m companion orthoimage: RMS ${meta.registration_rms_m.toFixed(2)} m, `
    + `max ${meta.registration_max_m.toFixed(2)} m (${verdict} 1 m tolerance); not independent ground truth.`;
}

export function inside(point: LatLon, b: OverlayBounds): boolean {
  // Purpose: true when `point` lies within the south/west/north/east box `b`.
  return point.lat >= b.south && point.lat <= b.north && point.lon >= b.west && point.lon <= b.east;
}

export function inspectTarget(bounds: OverlayBounds, candidates: LatLon[]): LatLon {
  // Purpose: where "Inspect scarp" centres the map: the first candidate point (e.g. the primary observation
  // point) that lies inside the native image, otherwise the image centre. Never a point outside the image.
  return candidates.find((p) => inside(p, bounds))
    ?? { lat: (bounds.south + bounds.north) / 2, lon: (bounds.west + bounds.east) / 2 };
}
