// First-time mission walkthrough and a way back to mission context and data credits.
// Keeps the PR #31 walkthrough and the newer main-branch credits/focus behavior.

import { useEffect, useRef } from 'react';
import { MAP_CREDITS, OTHER_CREDITS_NOTE } from '../content/credits';

interface MissionBriefProps {
  siteName: string;
  isDemoData: boolean;
  hasStarted: boolean;
  onContinue: () => void;
  onRestart: () => void;
}

export function MissionBrief({
  siteName,
  isDemoData,
  hasStarted,
  onContinue,
  onRestart,
}: MissionBriefProps) {
  const briefRef = useRef<HTMLDivElement>(null);
  const continueRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // Focus the primary action without scrolling the dialog down to its end.
    continueRef.current?.focus({ preventScroll: true });
    if (briefRef.current) briefRef.current.scrollTop = 0;
  }, []);

  return (
    <div className="brief-backdrop" role="dialog" aria-modal="true" aria-labelledby="brief-title">
      <div className="brief" ref={briefRef}>
        <p className="brief-kicker">NASA Space Apps 2026 · Interplanetary Survival Guide: Martian Map</p>
        <h1 id="brief-title">Plan and evaluate a Marswalk to an ice-scarp candidate</h1>
        <p>
          In 2018, scientists using NASA&apos;s Mars Reconnaissance Orbiter reported cliffs on Mars that expose
          thick sheets of buried ice (Dundas et al., <em>Science</em>). No rover or human has ever visited
          one. This map plans a spacewalk to the <strong>{siteName}</strong> and shows how simulated robotic
          scouting adds evidence about hazards astronauts cannot see from orbit.
        </p>

        <ol className="brief-steps">
          <li><strong>Orbital planning:</strong> inspect a candidate route and modeled hazards.</li>
          <li><strong>Rover reconnaissance:</strong> examine a simulated discovery and proposed reroute.</li>
          <li><strong>Drone inspection concept:</strong> review proposed coverage and its limits.</li>
          <li><strong>Astronaut mission review:</strong> compare routes, backup options, and uncertainties.</li>
        </ol>

        <div className="brief-howto">
          <span><strong>Explore:</strong> zoom and pan the map; click locations for terrain details.</span>
          <span><strong>Inspect routes:</strong> select a line or use Inspect route for distance, slope, and hazards.</span>
          <span><strong>Switch layers:</strong> compare HiRISE, slope, and scouting coverage in the side panel.</span>
          <span><strong>Follow four steps:</strong> use Next and each “Try this on the map” action.</span>
        </div>
        <p className="brief-key">
          <strong>Map key:</strong> gray = preliminary or rejected; amber = candidate needing inspection;
          green = a conditional planning route after simulated scouting. Dotted lines indicate simulated
          evidence, dashed lines indicate inferred evidence, and solid lines indicate NASA-derived evidence.
          Consult the stage-specific legend for the exact route type.
        </p>
        <p className="muted">
          NASA observations are real; rover and drone reconnaissance are simulated. Green never means
          certified astronaut safety or crew clearance.
        </p>

        {isDemoData && (
          <p className="brief-note">
            Demo data: routes and hazards are placeholders positioned near the real site while the pipeline
            processes NASA HiRISE terrain. Robot observations are always simulated.
          </p>
        )}

        {/* The on-map attribution bar is hidden; keep source attribution discoverable here. */}
        <details className="brief-credits">
          <summary>Data credits</summary>
          <ul>
            {MAP_CREDITS.map((c) => (
              <li key={c.what}>
                <span className="muted">{c.what}:</span>{' '}
                <a href={c.url} target="_blank" rel="noreferrer">{c.credit}</a>
              </li>
            ))}
          </ul>
          <p className="muted">{OTHER_CREDITS_NOTE}</p>
        </details>

        <div className="brief-actions">
          <button type="button" className="primary" onClick={onContinue} ref={continueRef}>
            {hasStarted ? 'Resume walkthrough' : 'Start walkthrough'}
          </button>
          {hasStarted && (
            <button type="button" className="link-btn" onClick={onRestart}>
              Restart from Step 1
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
