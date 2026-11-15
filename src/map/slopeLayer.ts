// Slope overlay availability and load state. Pure functions so the Node tests can check them.

import type { OverlayBounds, SlopeMeta } from '../data/types.ts';

export const SLOPE_SOURCE_TEXT = 'NASA HiRISE DTM-derived slope — approximately 1 m terrain grid.';

// unavailable: not published (or withdrawn by the loader); loading; loaded; failed: 404, corrupt or wrong size.
export type SlopeLoadState = 'unavailable' | 'loading' | 'loaded' | 'failed';

export function slopeAvailable(bounds: OverlayBounds | null, meta: SlopeMeta | null): boolean {
  // Purpose: the toggle is offered only when both valid bounds and matching metadata were loaded.
  // Imagery visibility and route status play no part.
  return bounds !== null && meta !== null;
}

export function slopeDecodedState(natural: [number, number], meta: SlopeMeta): SlopeLoadState {
  // Purpose: after the PNG decodes, confirm it has one pixel per DTM cell (meta.grid.pixels = [width, height]).
  return natural[0] === meta.grid.pixels[0] && natural[1] === meta.grid.pixels[1] ? 'loaded' : 'failed';
}

export function slopeStatusText(state: SlopeLoadState): string {
  // Purpose: visible status line under the legend (nothing is shown once loaded).
  switch (state) {
    case 'unavailable': return 'Slope map not published.';
    case 'loading': return 'Slope map loading…';
    case 'failed': return 'Slope map failed to load (missing, corrupt or wrong size); not shown.';
    case 'loaded': return '';
  }
}
