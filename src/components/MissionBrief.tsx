// The first thing a judge sees: what this map is, why it matters, and how to use it.
// Reopened any time from the "About this mission" button in the header.

import { useEffect, useRef } from 'react';

interface MissionBriefProps {
  siteName: string;
  isDemoData: boolean;
  hasStarted: boolean;
  onContinue: () => void;
  onRestart: () => void;
}

export function MissionBrief({ siteName, isDemoData, hasStarted, onContinue, onRestart }: MissionBriefProps) {
  // Purpose: compact first-use help. `hasStarted` changes Continue to Resume without resetting the current stage.
  const briefRef = useRef<HTMLDivElement>(null);
  const continueRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    // Keep the help dialog at its top while focusing the primary action for keyboard users.
    continueRef.current?.focus({ preventScroll: true });
    if (briefRef.current) briefRef.current.scrollTop = 0;
  }, []);
  return (
    <div className="brief-backdrop" role="dialog" aria-modal="true" aria-labelledby="brief-title">
      <div className="brief" ref={briefRef}>
        <p className="brief-kicker">NASA Space Apps 2026 · Interplanetary Survival Guide: Martian Map</p>
        <h1 id="brief-title">Plan and evaluate a Marswalk to an ice-scarp candidate</h1>
        <p>
          In 2018, scientists using NASA's Mars Reconnaissance Orbiter reported cliffs on Mars that expose thick
          sheets of buried ice (Dundas et al., <em>Science</em>). No rover or human has ever visited one. This map plans a spacewalk to the <strong>{siteName}</strong> and shows how
          (simulated) robot scouting adds evidence about hazards astronauts can't see before the crew walks out.
        </p>

        <div className="brief-howto">
          <span><strong>Explore:</strong> zoom and pan the map; click locations for terrain details.</span>
          <span><strong>Inspect routes:</strong> select a line or use Inspect route for distance, slope and hazards.</span>
          <span><strong>Switch layers:</strong> compare HiRISE, slope and scouting coverage in the side panel.</span>
          <span><strong>Follow four steps:</strong> use Next and each “Try this on the map” action.</span>
        </div>
        <p className="brief-key"><strong>Map key:</strong> gray = preliminary or rejected; amber = candidate needing inspection; green = conditional planning route after simulated scouting. Dotted marks simulated evidence, dashed marks inferred evidence, and solid marks NASA-derived evidence.</p>
        <p className="muted">NASA observations are real; rover and drone reconnaissance are simulated. Green never means certified astronaut safety or crew clearance.</p>

        {isDemoData && (
          <p className="brief-note">
            Demo data: routes and hazards are placeholders positioned near the real site while our pipeline
            processes the NASA HiRISE terrain. Robot observations are always simulated.
          </p>
        )}

        <div className="brief-actions">
          <button className="primary" onClick={onContinue} ref={continueRef}>{hasStarted ? 'Resume walkthrough' : 'Start walkthrough'}</button>
          {hasStarted && <button className="link-btn" onClick={onRestart}>Restart from Step 1</button>}
        </div>
      </div>
    </div>
  );
}
