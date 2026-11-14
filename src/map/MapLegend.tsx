// Compact legend that sits on the map itself, so the side panel stays short.

import { HAZARD_COLORS } from './layerStyles';

export function MapLegend() {
  return (
    <div className="map-legend" aria-label="Map legend">
      <div className="legend-row">
        <span className="line line-main" /> Crew route
        <span className="line line-backup" /> Backup
        <span className="line line-rover" /> Rover
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
