// Wording and zoom limits for the native-resolution HiRISE overlay (Nic's pipeline.publish_imagery).
// Kept free of React/Leaflet so the Node test runner can check it.

import type { HiriseMeta } from '../data/types.ts';

// Zoom 18 is ~0.18 m per screen pixel at Milankovič (54 N) in Leaflet's EPSG:4326 grid,
// just finer than the image's ~0.23-0.25 m sampling, so every source pixel can be seen.
// The CTX basemap's real detail stops at zoom 10; deeper zooms only enlarge it.
export const MAP_MAX_ZOOM = 18;

const ALIGNMENT_TEXT: Record<string, string> = {
  not_verified: 'alignment to the terrain model not yet checked',
  measured_within_tolerance: 'alignment to the terrain model measured within 1 m',
  measured_exceeds_tolerance: 'alignment to the terrain model measured, about 1 m off',
  insufficient_landmarks: 'alignment could not be measured (too few landmarks)',
};

export function imageryAttribution(meta: HiriseMeta | null): string {
  // Purpose: short credit line for the map corner; the full caption lives on the zoom button.
  const credit = 'HiRISE ESP_071006_2345: NASA/JPL-Caltech/UArizona';
  if (!meta) return credit;
  const [ew, ns] = meta.ground_sampling_m_ew_ns;
  return `${credit} (${Math.min(ew, ns).toFixed(2)}–${Math.max(ew, ns).toFixed(2)} m sampling)`;
}

export function imageryCaption(meta: HiriseMeta | null): string {
  // Purpose: one honest sentence about the HD image for the map caption and tooltip.
  // meta: hirise.meta.json, or null when it is missing (then only the source is named).
  if (!meta) return 'HiRISE image (ESP_071006_2345); resolution details unavailable.';
  const [ew, ns] = meta.ground_sampling_m_ew_ns;
  const [w, h] = meta.output_pixels;
  const sampling = `${Math.min(ew, ns).toFixed(2)}–${Math.max(ew, ns).toFixed(2)} m per pixel`;
  const alignment = ALIGNMENT_TEXT[meta.landmark_alignment] ?? `alignment: ${meta.landmark_alignment}`;
  const rms = meta.registration_rms_m !== undefined ? ` (RMS ${meta.registration_rms_m.toFixed(2)} m)` : '';
  // Sampling is not optical resolution: HiRISE resolves objects of roughly 1 m.
  return `HiRISE ${w}×${h} native pixels, ${sampling} sampling (not optical resolution); ${alignment}${rms}.`;
}
