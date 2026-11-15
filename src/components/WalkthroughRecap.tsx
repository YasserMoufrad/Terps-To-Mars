import { useEffect, useRef } from 'react';
import type { StageSummary } from '../map/stageSummary';
import { recapRoutes } from './walkthrough';

interface WalkthroughRecapProps {
  summary: StageSummary;
  onExplore: () => void;
  onRestart: () => void;
}

export function WalkthroughRecap({ summary, onExplore, onRestart }: WalkthroughRecapProps) {
  // Summarize the published EVA route and backup assessments; closing the tour does not approve an EVA.
  const { main, backup } = recapRoutes(summary);
  const recapRef = useRef<HTMLElement>(null);
  const exploreRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    // Keep the recap's heading visible while focusing its primary action.
    exploreRef.current?.focus({ preventScroll: true });
    if (recapRef.current) recapRef.current.scrollTop = 0;
  }, []);
  return <div className="brief-backdrop" role="dialog" aria-modal="true" aria-labelledby="recap-title">
    <section className="brief recap" aria-label="Walkthrough recap" ref={recapRef}>
      <p className="brief-kicker">Four-step mission review complete</p>
      <h1 id="recap-title">What the map established</h1>
      <ul>
        <li><strong>Orbit:</strong> NASA terrain supports a preliminary route and mapped hazards; ground conditions remain unresolved.</li>
        <li><strong>Rover:</strong> a simulated scout reports suspected soft ground and a proposed reroute.</li>
        <li><strong>Drone:</strong> the proposed perch and field of view show what a future inspection could cover. No flight occurred.</li>
        <li><strong>Main route:</strong> {main}.</li>
        <li><strong>Backup:</strong> {backup}.</li>
      </ul>
      <p className="brief-note">The science target and some terrain measurements still need review. Finishing this tour is not crew clearance or EVA authorization.</p>
      <div className="brief-actions">
        <button className="primary" onClick={onExplore} ref={exploreRef}>Explore freely</button>
        <button className="link-btn" onClick={onRestart}>Restart walkthrough</button>
      </div>
    </section>
  </div>;
}
