// The "Rover needs input" card: what the rover found, how sure it is, and the options.

import type { Discovery } from '../data/types';

export function DiscoveryCard({ discovery }: { discovery: Discovery }) {
  const decided = discovery.chosen_option !== '';
  return (
    <section className="card discovery">
      <h3>Rover needs input</h3>
      <p className="muted">
        The rover stopped and asked the habitat crew to decide. Uncertainty: {discovery.uncertainty} ·{' '}
        <span className="tag-simulated">Simulated</span>
      </p>
      <ul className="evidence">
        {Object.entries(discovery.sensor_evidence).map(([key, value]) => (
          <li key={key}>
            <span className="muted">{key.replace(/_/g, ' ')}:</span> {String(value)}
          </li>
        ))}
      </ul>
      <ol className="options">
        {discovery.options.map((o) => (
          <li key={o.id} className={o.id === discovery.chosen_option ? 'chosen' : undefined}>
            <strong>{o.label}</strong> <span className="muted">({o.consequence})</span>
            {o.id === discovery.chosen_option && <span className="chosen-tag">Crew chose this</span>}
          </li>
        ))}
      </ol>
      {!decided && <p className="muted">Awaiting the crew's decision.</p>}
    </section>
  );
}
