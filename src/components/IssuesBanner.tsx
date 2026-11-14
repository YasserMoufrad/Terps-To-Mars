// Data problems. Errors get a full-width banner (something is genuinely broken);
// placeholders and warnings collapse into a small header badge so they don't
// dominate the screen, but are still one click away.

import type { LoadIssue } from '../data/loadMissionData';

export function ErrorBanner({ issues }: { issues: LoadIssue[] }) {
  const errors = issues.filter((i) => i.severity === 'error');
  if (errors.length === 0) return null;
  return (
    <div className="issues">
      {errors.map((i, n) => (
        <div key={n} className="issue issue-error">{i.file}: {i.message}</div>
      ))}
    </div>
  );
}

export function DataBadge({ issues, placeholderFiles }: { issues: LoadIssue[]; placeholderFiles: string[] }) {
  const warnings = issues.filter((i) => i.severity === 'warning');
  if (warnings.length === 0 && placeholderFiles.length === 0) return null;
  return (
    <details className="data-badge">
      <summary>{placeholderFiles.length > 0 ? 'Demo data' : `${warnings.length} data note${warnings.length > 1 ? 's' : ''}`}</summary>
      <div className="data-badge-body">
        {placeholderFiles.length > 0 && (
          <p>Placeholder files, not yet from the pipeline: {placeholderFiles.join(', ')}.</p>
        )}
        {warnings.map((i, n) => (
          <p key={n} className="muted">{i.file}: {i.message}</p>
        ))}
      </div>
    </details>
  );
}
