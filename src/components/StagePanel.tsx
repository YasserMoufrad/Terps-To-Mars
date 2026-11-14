// Side panel: the clicked hazard's evidence, the stage's numbers and alerts,
// the rover's request, honest route failures, and the layer switches.
// The stage description lives in the step bar; the legend lives on the map.

import type { ReactNode } from 'react';
import type { Mission, StageId, HazardProperties } from '../data/types';
import { DiscoveryCard } from './DiscoveryCard';
import { EvidenceCard } from './EvidenceCard';

interface StagePanelProps {
  stage: StageId;
  mission: Mission;
  selectedHazard: HazardProperties | null;
  onCloseHazard: () => void;
  routeNotices: string[];
  toggles: ReactNode; // the layer checkboxes, built by App
}

export function StagePanel({ stage, mission, selectedHazard, onCloseHazard, routeNotices, toggles }: StagePanelProps) {
  const current = mission.stages.find((s) => s.id === stage);
  const alerts = mission.alerts[stage] ?? [];
  if (!current) return null;

  return (
    <aside className="panel">
      {selectedHazard && <EvidenceCard hazard={selectedHazard} onClose={onCloseHazard} />}

      <section className="card">
        <h2>{current.title}</h2>
        <p>{current.text}</p>
        <dl className="stats">
          {Object.entries(current.stats).map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {routeNotices.length > 0 && (
        <section className="card notices">
          {routeNotices.map((n) => (
            <div key={n}>{n}</div>
          ))}
        </section>
      )}

      {alerts.length > 0 && (
        <section className="card alerts">
          {alerts.map((a) => (
            <div key={a}>{a}</div>
          ))}
        </section>
      )}

      {stage === 'rover' && <DiscoveryCard discovery={mission.discovery} />}

      {toggles}
    </aside>
  );
}
