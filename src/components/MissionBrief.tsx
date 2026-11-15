// The first thing a judge sees: what this map is, why it matters, and how to use it.
// Reopened any time from the "About this mission" button in the header.

import { useEffect, useRef } from 'react';
import { MAP_CREDITS, OTHER_CREDITS_NOTE } from '../content/credits';

interface MissionBriefProps {
  siteName: string;
  isDemoData: boolean;
  onStart: () => void;
}

export function MissionBrief({ siteName, isDemoData, onStart }: MissionBriefProps) {
  // Purpose: intro dialog explaining the mission and how to use the map.
  // `isDemoData` adds the placeholder-data note; `onStart` closes it and begins step 1.
  // `briefRef` is the scrollable dialog body, `startRef` the Start button (focused on open).
  const briefRef = useRef<HTMLDivElement>(null);
  const startRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    // Focus Start for keyboard users without letting the browser scroll the dialog down to it,
    // then make sure the dialog opens at its top.
    startRef.current?.focus({ preventScroll: true });
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

        <ol className="brief-steps">
          <li><strong>Orbital planning:</strong> a first candidate route from NASA orbital data, needing inspection.</li>
          <li><strong>Rover reconnaissance:</strong> a simulated rover drives ahead and reports a hidden hazard.</li>
          <li><strong>Drone inspection concept:</strong> review planned coverage and inspection limits.</li>
          <li><strong>Astronaut mission review:</strong> review the proposed route, the reconnaissance evidence and the backup options.</li>
        </ol>
        <p className="muted">Nothing on this map is crew clearance; it shows what the evidence supports and what still needs inspection.</p>

        <div className="brief-howto">
          <span>Step through with <strong>Next</strong></span>
          <span>Click any hazard to see its evidence</span>
          <span>Toggle layers in the side panel</span>
        </div>

        {isDemoData && (
          <p className="brief-note">
            Demo data: routes and hazards are placeholders positioned near the real site while our pipeline
            processes the NASA HiRISE terrain. Robot observations are always simulated.
          </p>
        )}

        {/* The map's credit bar is hidden, so every source it draws is credited here. */}
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

        <button className="primary" onClick={onStart} ref={startRef}>
          Start the walkthrough
        </button>
      </div>
    </div>
  );
}
