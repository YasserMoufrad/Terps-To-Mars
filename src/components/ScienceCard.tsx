// "The science: why this cliff": the reason for the walk, shown in the side panel on Step 1 (why we go) and Step 4
// (what the crew does there). The lead paragraph is always visible; the detail sections open on click.

import { SCIENCE_CREDIT, SCIENCE_LEAD, SCIENCE_SECTIONS, SCIENCE_SOURCES, SCIENCE_TITLE } from '../content/science';
import { appLogger } from '../lib/appLogger';

export function ScienceCard() {
  // Purpose: render the science text from src/content/science.ts; opening a section is logged once per open
  // (a reading event, not a safety decision).
  return (
    <section className="card science-card" aria-label={SCIENCE_TITLE}>
      <h3>{SCIENCE_TITLE}</h3>
      <p>{SCIENCE_LEAD}</p>
      {SCIENCE_SECTIONS.map((s) => (
        <details key={s.heading} onToggle={(e) => {
          if ((e.target as HTMLDetailsElement).open) appLogger.info('content', 'science.section_open', { section: s.heading });
        }}>
          <summary>{s.heading}</summary>
          <p>{s.text}</p>
        </details>
      ))}
      <details>
        <summary>Sources</summary>
        <ul className="science-sources">
          {SCIENCE_SOURCES.map((src) => (
            <li key={src.url}><a href={src.url} target="_blank" rel="noreferrer">{src.label}</a></li>
          ))}
        </ul>
      </details>
      <p className="muted science-credit">{SCIENCE_CREDIT}</p>
    </section>
  );
}
