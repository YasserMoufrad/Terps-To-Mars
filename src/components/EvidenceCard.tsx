// Shown when a hazard is clicked: where the claim comes from and how sure we are.
// This is what lets a judge check our map instead of trusting it.

import type { HazardProperties, Mission } from '../data/types';
import { HAZARD_COLORS, SOFT_GROUND_OUTLINE } from '../map/layerStyles';
import { detectedBy } from '../map/detectedBy';
import { ICE_EVIDENCE } from '../content/science';

const TYPE_LABEL = { U: 'Under their feet', O: 'Over their heads', S: 'In shadow' } as const;
const EVIDENCE_TEXT = {
  nasa_derived: 'NASA-derived: measured directly from NASA data.',
  inferred: 'Inferred: our reading of NASA data; not directly measured.',
  simulated: 'Simulated: a modeled robot observation, not real data.',
} as const;

interface EvidenceCardProps {
  hazard: HazardProperties;
  isPlaceholder: boolean; // true while hazards.geojson is placeholder data
  mission: Mission | null; // supplies the rover's sensor readings for the simulated discovery
  onClose: () => void;
}

export function EvidenceCard({ hazard, isPlaceholder, mission, onClose }: EvidenceCardProps) {
  // Purpose: explain one clicked `hazard`: type, severity, who it affects, evidence
  // class in plain words, source and note. `isPlaceholder` adds a warning that the
  // shape is hypothetical even when it names a NASA dataset. `onClose` hides the card.
  return (
    <section className="card evidence-card" style={{ borderColor: hazard.category === 'soft_ground' ? SOFT_GROUND_OUTLINE : HAZARD_COLORS[hazard.type] }}>
      <div className="card-head">
        <h3>
          {hazard.type} · {hazard.category.replace('_', ' ')}
        </h3>
        <button className="close" onClick={onClose} aria-label="Close evidence">
          ×
        </button>
      </div>
      <dl className="stats">
        <div><dt>Hazard type</dt><dd>{TYPE_LABEL[hazard.type]}</dd></div>
        <div><dt>Severity</dt><dd>{hazard.severity === 'exclude' ? 'Exclude from routes' : 'Caution'}</dd></div>
        <div><dt>Applies to</dt><dd>{hazard.agent}</dd></div>
        <div><dt>First seen at</dt><dd>{hazard.stage} stage</dd></div>
      </dl>
      {isPlaceholder && (
        <p className="placeholder-warning">
          Placeholder: this shape is hypothetical, drawn for the demo. It is not derived from the dataset named
          below and is not crew clearance.
        </p>
      )}
      <p className="evidence-kind">
        {isPlaceholder ? 'Intended evidence class: ' : ''}
        {EVIDENCE_TEXT[hazard.evidence]}
      </p>
      <p><span className="muted">Detected by:</span> {detectedBy(hazard, mission)}</p>
      {/* The traced cliff faces carry Geury's ice evidence: consistent with ice, not confirmed. */}
      {hazard.id.includes('scarp-face') && <p className="evidence-kind">{ICE_EVIDENCE}</p>}
      <p><span className="muted">Source:</span> {hazard.source}</p>
      <p>{hazard.note}</p>
    </section>
  );
}
