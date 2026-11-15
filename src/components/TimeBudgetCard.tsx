// Step 4: "Does it fit?" Two bars on one 240-minute scale: the planned trip against the 168-minute planning limit
// (30% reserve kept), and the walk-home contingency against the full 240-minute spacewalk.

import type { RouteFeature } from '../data/types';
import { EVA_MINUTES, evaTimeline, type SegmentKind, type Timeline } from '../map/evaTimeline';

const COLORS: Record<SegmentKind, string> = { drive: '#7cc4ff', walk: '#3ddc97', science: '#b18cff', 'walk-home': '#f5a524' };

function Bar({ title, t }: { title: string; t: Timeline }) {
  // Purpose: one labelled stacked bar; widths are minutes / 240, with a tick at this timeline's limit.
  const pct = (m: number) => `${(m / EVA_MINUTES) * 100}%`;
  return (
    <div className="tb-row">
      <div className="tb-title">
        <span>{title}</span>
        <span className={t.fits ? 'tb-fit' : 'tb-over'}>{Math.round(t.total)} of {Math.round(t.limit)} min{t.fits ? '' : ' (over)'}</span>
      </div>
      <div className="tb-track" role="img" aria-label={`${title}: ${t.segments.map((s) => `${s.label} ${Math.round(s.minutes)} min`).join(', ')}; ${Math.round(t.total)} of ${Math.round(t.limit)} minutes`}>
        {t.segments.map((s, i) => (
          <div key={i} className="tb-seg" style={{ width: pct(s.minutes), background: COLORS[s.kind] }} title={`${s.label}: ${Math.round(s.minutes)} min`} />
        ))}
        <div className="tb-limit" style={{ left: pct(t.limit) }} />
      </div>
    </div>
  );
}

export function TimeBudgetCard({ route }: { route: RouteFeature | undefined }) {
  // Purpose: show the main route's time budget; hidden when the route has no drive/walk legs (no timing data).
  const timeline = route ? evaTimeline(route) : null;
  if (!timeline) return null;
  return (
    <section className="card time-budget" aria-label="Spacewalk time budget">
      <h3>Does the walk fit the spacewalk?</h3>
      <Bar title="Planned trip" t={timeline.planned} />
      <Bar title="If the crew vehicle fails at parking" t={timeline.vehicleFails} />
      <div className="tb-legend">
        {(['drive', 'walk', 'science', 'walk-home'] as SegmentKind[]).map((k) => (
          <span key={k}><i style={{ background: COLORS[k] }} />{k === 'walk-home' ? 'walk home' : k}</span>
        ))}
      </div>
      <p className="muted tb-note">
        Scale: one 240-minute spacewalk. The planned trip must finish by 168 minutes (30% kept in reserve); if the vehicle
        fails, walking home must still fit in 240. Times from the route's measured lengths at 20 m/min walking and 5 km/h
        driving; a planning model, not physiology.
      </p>
    </section>
  );
}
