// Small persistent key shown whenever the slope layer is on: degree classes from slope.meta.json,
// the data source, its resolution limits and the layer's load state. Collapsible so it never hides the map.

import type { SlopeMeta } from '../data/types';
import { SLOPE_SOURCE_TEXT, slopeStatusText, type SlopeLoadState } from './slopeLayer';

export function SlopeLegend({ meta, state }: { meta: SlopeMeta; state: SlopeLoadState }) {
  // Purpose: `meta` supplies the class labels and colours; `state` reports whether the PNG really decoded.
  // The failure line stays visible even when the key is collapsed.
  const narrow = typeof window !== 'undefined' && window.matchMedia?.('(max-width: 900px)').matches;
  return (
    <div className="slope-legend" aria-label="Slope legend">
      {state !== 'loaded' && <div className={`legend-row slope-state slope-${state}`} role="status">{slopeStatusText(state)}</div>}
      <details open={!narrow}>
        <summary className="slope-legend-title">Slope (degrees)</summary>
        {meta.legend.map((entry) => (
          <div className="legend-row" key={entry.class}>
            <span
              className={`swatch${entry.class === 'unknown' ? ' swatch-unknown' : ''}`}
              style={{ background: `rgba(${entry.rgba[0]}, ${entry.rgba[1]}, ${entry.rgba[2]}, ${(entry.rgba[3] / 255).toFixed(2)})` }}
            />
            {entry.label}
          </div>
        ))}
        <div className="legend-row muted">{SLOPE_SOURCE_TEXT}</div>
        <div className="legend-row muted">Artifact QC: not reviewed. Unknown fraction: {(meta.unknown_fraction*100).toFixed(2)}%. Zero unknown cells does not mean artifact-free.</div>
        <div className="legend-row muted">Does not resolve sub-metre rocks, overhangs, loose soil or surface instability.</div>
      </details>
    </div>
  );
}
