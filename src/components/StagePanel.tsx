// Side panel: the clicked hazard's evidence, the stage's numbers and alerts,
// the rover's request, honest route failures, and the layer switches.
// The stage description lives in the step bar; the legend lives on the map.

import type { ReactNode } from 'react';
import type { Mission, StageId, HazardProperties, RouteFeature } from '../data/types';
import { TimeBudgetCard } from './TimeBudgetCard';
import { ConditionsCard } from './ConditionsCard';
import { BeforeAfterCard } from './BeforeAfterCard';
import type { BeforeAfter } from '../map/beforeAfter';
import { DiscoveryCard } from './DiscoveryCard';
import { EvidenceCard } from './EvidenceCard';
import { alertSeverity } from './alertSeverity';
import { GroundViewCard } from './GroundViewCard';
import { ScienceCard } from './ScienceCard';
import { StageSummaryCard } from './StageSummaryCard';
import type { StageSummary } from '../map/stageSummary';

interface StagePanelProps {
  stage: StageId;
  mission: Mission;
  selectedHazard: HazardProperties | null;
  hazardsArePlaceholder: boolean;
  onCloseHazard: () => void;
  routeNotices: string[];
  summary: StageSummary; // "what this step shows", computed from the data by App
  toggles: ReactNode; // the layer checkboxes, built by App
  mainRoute?: RouteFeature; // the post-scouting crew route (discovery.after_route_id), for the Step 4 time budget
  comparison?: BeforeAfter | null; // orbit-only route vs route after scouting, for the Step 2 card
}

export function StagePanel({
  stage, mission, selectedHazard, hazardsArePlaceholder, onCloseHazard, routeNotices, summary, toggles, mainRoute, comparison = null,
}: StagePanelProps) {
  // Purpose: side panel for `stage`: the layer `toggles` first, then the evidence card (if
  // `selectedHazard`), stage stats, the stage `summary`, honest route failures (`routeNotices`),
  // alerts and the rover card.
  const current = mission.stages.find((s) => s.id === stage);
  const alerts = mission.alerts[stage] ?? [];
  // Several routes can share one notice (e.g. main and backup both need inspection):
  // show each distinct sentence once. This also keeps React's list keys unique.
  const notices = [...new Set(routeNotices)];
  if (!current) return null;

  return (
    <aside className="panel">
      {/* Layer toggles come first so they are visible as soon as the page opens. */}
      {toggles}

      {selectedHazard && (
        <EvidenceCard hazard={selectedHazard} isPlaceholder={hazardsArePlaceholder} mission={mission} onClose={onCloseHazard} />
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

      <StageSummaryCard summary={summary} />

      {/* Step 2: what the robots changed, orbit-only route next to the scouted one. */}
      {stage === 'rover' && <BeforeAfterCard comparison={comparison} />}

      {/* Step 4: the main (post-scouting) route's time budget as a picture. */}
      {stage === 'eva' && <TimeBudgetCard route={mainRoute} />}

      {/* Step 4: season, nearby-lander temperatures and light at the cliff (cited; no site forecast). */}
      {stage === 'eva' && <ConditionsCard />}

      {/* Why the walk exists (Step 1) and what the crew does at the cliff (Step 4). */}
      {(stage === 'orbital' || stage === 'eva') && <ScienceCard />}

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

    </aside>
  );
}
