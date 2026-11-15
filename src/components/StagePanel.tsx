// Side panel: the clicked hazard's evidence, the stage's numbers and alerts,
// the rover's request, honest route failures, and the layer switches.
// The stage description lives in the step bar; the legend lives on the map.

import type { ReactNode } from 'react';
import type { Mission, StageId, HazardProperties } from '../data/types';
import { DiscoveryCard } from './DiscoveryCard';
import { EvidenceCard } from './EvidenceCard';
import { GroundViewCard } from './GroundViewCard';
import { alertSeverity } from './alertSeverity';

interface StagePanelProps {
  stage: StageId;
  mission: Mission;
  selectedHazard: HazardProperties | null;
  hazardsArePlaceholder: boolean;
  onCloseHazard: () => void;
  routeNotices: string[];
  toggles: ReactNode; // the layer checkboxes, built by App
}

export function StagePanel({
  stage, mission, selectedHazard, hazardsArePlaceholder, onCloseHazard, routeNotices, toggles,
}: StagePanelProps) {
  // Purpose: side panel for `stage`: evidence card (if `selectedHazard`), stage stats,
  // honest route failures (`routeNotices`), alerts, the rover card, and layer toggles.
  const current = mission.stages.find((s) => s.id === stage);
  const alerts = mission.alerts[stage] ?? [];
  // Several routes can share one notice (e.g. main and backup both need inspection):
  // show each distinct sentence once. This also keeps React's list keys unique.
  const notices = [...new Set(routeNotices)];
  if (!current) return null;

  return (
    <aside className="panel">
      {selectedHazard && (
        <EvidenceCard hazard={selectedHazard} isPlaceholder={hazardsArePlaceholder} onClose={onCloseHazard} />
      )}

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

      {notices.length > 0 && (
        <section className="card notices">
          {notices.map((n) => (
            <div key={n}>{n}</div>
          ))}
        </section>
      )}

      {alerts.length > 0 && (
        <section className="card alerts" aria-label="Alerts">
          {alerts.map((a) => {
            const severity = alertSeverity(a);
            return (
              <div key={a} className={`alert alert-${severity}`}>
                <span className="alert-tag">{severity === 'stop' ? 'Stop' : severity === 'caution' ? 'Caution' : 'Info'}</span> {a}
              </div>
            );
          })}
        </section>
      )}

      {stage === 'rover' && <DiscoveryCard discovery={mission.discovery} />}

      <GroundViewCard stage={stage} />

      {toggles}
    </aside>
  );
}
