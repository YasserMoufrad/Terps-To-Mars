// "Conditions at the site": season, nearby-lander temperatures and light, shown on Step 4 beside the time budget.
// The lead is always visible; the sections and sources open on click (same layout as the science card).

import { CONDITIONS_LEAD, CONDITIONS_SECTIONS, CONDITIONS_SOURCES, CONDITIONS_TITLE } from '../content/conditions';
import { appLogger } from '../lib/appLogger';

export function ConditionsCard() {
  // Purpose: render src/content/conditions.ts; opening a section is logged once per open (a reading event).
  return (
    <section className="card science-card" aria-label={CONDITIONS_TITLE}>
      <h3>{CONDITIONS_TITLE}</h3>
      <p>{CONDITIONS_LEAD}</p>
      {CONDITIONS_SECTIONS.map((s) => (
        <details key={s.heading} onToggle={(e) => {
          if ((e.target as HTMLDetailsElement).open) appLogger.info('content', 'conditions.section_open', { section: s.heading });
        }}>
          <summary>{s.heading}</summary>
          <p>{s.text}</p>
        </details>
      ))}
      <details>
        <summary>Sources</summary>
        <ul className="science-sources">
          {CONDITIONS_SOURCES.map((src) => (
            <li key={src.url}><a href={src.url} target="_blank" rel="noreferrer">{src.label}</a></li>
          ))}
        </ul>
      </details>
    </section>
  );
}
