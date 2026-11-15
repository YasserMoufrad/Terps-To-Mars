// Compact legend that sits on the map itself, so the side panel stays short. It lists only what the current
// stage actually draws (legendKeys), so every entry can be found on the map.

import type { HazardType, CoverageState } from '../data/types';
import { HAZARD_COLORS, COVERAGE_COLORS } from './layerStyles';

export type LineKey = 'drive' | 'walk' | 'backup' | 'rover' | 'candidate' | 'candidate-drive' | 'to-scout' | 'replaced' | 'rejected';

export interface LegendKeys {
  lines: Set<LineKey>; // route line styles currently drawn
  hazards: Set<HazardType>; // hazard types currently drawn (U/O/S)
  coverage: Set<CoverageState>; // coverage states currently drawn
}

const LINES: [LineKey, string, string][] = [
  ['drive', 'line-drive', 'Crew vehicle drive (scouted, go)'],
  ['walk', 'line-main', 'Crew walk (scouted, go)'],
  ['backup', 'line-backup', 'Backup (scouted, go)'],
  ['candidate', 'line-unverified', 'Candidate: needs scouting'],
  ['candidate-drive', 'line-unverified-drive', 'Candidate drive'],
  ['to-scout', 'line-candidate', 'Orbit-only plan (to scout)'],
  ['replaced', 'line-candidate', 'Old route (replaced)'],
  ['rover', 'line-rover', 'Scout rover path (simulated)'],
  ['rejected', 'line-rejected', 'Rejected'],
];
const HAZARDS: [HazardType, string][] = [['U', 'Under feet'], ['O', 'Overhead'], ['S', 'Shadow']];
const COVERAGE: [CoverageState, string][] = [
  ['unscouted', 'Unscouted'], ['rover_checked', 'Rover scouted (simulated)'], ['drone_checked', 'Drone view (simulated)'],
  ['inspection_required', 'Inspection required'],
];

export function MapLegend({ keys }: { keys: LegendKeys }) {
  // Purpose: key for the route lines, hazard colors and coverage shown at this stage, plus the evidence patterns.
  const lines = LINES.filter(([k]) => keys.lines.has(k));
  const hazards = HAZARDS.filter(([k]) => keys.hazards.has(k));
  const coverage = COVERAGE.filter(([k]) => keys.coverage.has(k));
  return (
    <div className="map-legend" aria-label="Map legend">
      {lines.length > 0 && (
        <div className="legend-row">
          {lines.map(([k, cls, text]) => <span key={k}><span className={`line ${cls}`} /> {text}</span>)}
        </div>
      )}
      {(hazards.length > 0 || coverage.length > 0) && (
        <div className="legend-row">
          {hazards.map(([k, text]) => <span key={k}><span className="swatch" style={{ background: HAZARD_COLORS[k] }} /> {text}</span>)}
          {coverage.map(([k, text]) => <span key={k}><span className="swatch" style={{ background: COVERAGE_COLORS[k] }} /> {text}</span>)}
        </div>
      )}
      <div className="legend-row muted">Outline: solid = NASA data · dashed = inferred · dotted = simulated</div>
    </div>
  );
}
