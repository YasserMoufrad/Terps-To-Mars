// Shown when a hazard is clicked: where the claim comes from and how sure we are.
// This is what lets a judge check our map instead of trusting it.

import type { HazardProperties } from '../data/types';
import { HAZARD_COLORS } from '../map/layerStyles';

const TYPE_LABEL = { U: 'Under their feet', O: 'Over their heads', S: 'In shadow' } as const;
const EVIDENCE_TEXT = {
  nasa_derived: 'NASA-derived: measured directly from NASA data.',
  inferred: 'Inferred: our reading of NASA data; not directly measured.',
  simulated: 'Simulated: a modeled robot observation, not real data.',
} as const;

interface EvidenceCardProps {
  hazard: HazardProperties;
  onClose: () => void;
}

export function EvidenceCard({ hazard, onClose }: EvidenceCardProps) {
  return (
    <section className="card evidence-card" style={{ borderColor: HAZARD_COLORS[hazard.type] }}>
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
      <p className="evidence-kind">{EVIDENCE_TEXT[hazard.evidence]}</p>
      <p><span className="muted">Source:</span> {hazard.source}</p>
      <p>{hazard.note}</p>
    </section>
  );
}
