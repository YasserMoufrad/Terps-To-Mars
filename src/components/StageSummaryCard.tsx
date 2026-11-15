// "What this step shows": the data-driven summary for the current stage (stageSummary.ts).

import type { StageSummary } from '../map/stageSummary';

const TAG = { stop: 'Stop', caution: 'Caution', info: 'Info' } as const;

export function StageSummaryCard({ summary }: { summary: StageSummary }) {
  // Purpose: render one stage summary; each row's tone colors it (never green: no clearance).
  return (
    <section className="card stage-summary" aria-label={summary.title}>
      <h3>{summary.title}</h3>
      <ul>
        {summary.rows.map((row) => (
          <li key={row.label} className={`summary-row alert-${row.tone}`}>
            <span className="summary-label">{row.label}</span>
            <span className="summary-value">
              <span className="alert-tag">{TAG[row.tone]}</span> {row.value}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
