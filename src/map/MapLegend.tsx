// Compact legend that sits on the map itself, so the side panel stays short.

import { HAZARD_COLORS } from './layerStyles';

export function MapLegend() {
  // Purpose: static key for route lines, hazard colors and evidence outline patterns.
  return (
    <div className="map-legend" aria-label="Map legend">
      <div className="legend-row">
        <span className="line" style={{borderColor:'#ff5365'}} /> Rejected by audit
        <span className="line line-unverified" /> Candidate / unaudited
        <span className="line" style={{borderColor:'#b4b9c2'}} /> Replaced
      </div>
      <div className="legend-row">
        <span className="swatch" style={{ background: HAZARD_COLORS.U }} /> Under feet
        <span className="swatch" style={{ background: HAZARD_COLORS.O }} /> Overhead
        <span className="swatch" style={{ background: HAZARD_COLORS.S }} /> Shadow
      </div>
      <div className="legend-row muted">Outline: solid = NASA data · dashed = inferred · dotted = simulated</div>
    </div>
  );
}
