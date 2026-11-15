// Compact legend that sits on the map itself, so the side panel stays short.

import { HAZARD_COLORS, COVERAGE_COLORS } from './layerStyles';

export function MapLegend() {
  // Purpose: static key for route lines, hazard colors and evidence outline patterns.
  return (
    <div className="map-legend" aria-label="Map legend">
      <div className="legend-row">
        <span className="line line-drive" /> Crew rover drive
        <span className="line line-main" /> Crew walk
        <span className="line line-backup" /> Backup
        <span className="line line-rover" /> Rover
        <span className="line line-unverified" /> Needs inspection
        <span className="line line-unverified-drive" /> (drive)
      </div>
      <div className="legend-row">
        <span className="swatch" style={{ background: HAZARD_COLORS.U }} /> Under feet
        <span className="swatch" style={{ background: HAZARD_COLORS.O }} /> Overhead
        <span className="swatch" style={{ background: HAZARD_COLORS.S }} /> Shadow
      </div>
      <div className="legend-row">
        <span className="swatch" style={{ background: COVERAGE_COLORS.unscouted }} /> Unscouted
        <span className="swatch" style={{ background: COVERAGE_COLORS.rover_checked }} /> Rover scouted
        <span className="swatch" style={{ background: COVERAGE_COLORS.drone_checked }} /> Drone view (simulated)
      </div>
      <div className="legend-row muted">Outline: solid = NASA data · dashed = inferred · dotted = simulated</div>
    </div>
  );
}
