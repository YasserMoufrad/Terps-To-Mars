// Step 2: "Before and after scouting", a side-by-side table of the orbit-only route and the route after the rover.
// The numbers come from src/map/beforeAfter.ts; the card only lays them out.

import type { BeforeAfter } from '../map/beforeAfter';

export function BeforeAfterCard({ comparison }: { comparison: BeforeAfter | null }) {
  // Purpose: render `comparison`; hidden when either route is missing (beforeAfter returns null).
  if (!comparison) return null;
  return (
    <section className="card before-after" aria-label="Before and after scouting">
      <h3>Before and after scouting</h3>
      <p className="ba-headline">{comparison.headline}</p>
      <table className="ba-table">
        <thead>
          <tr><th scope="col"></th><th scope="col">Orbit only</th><th scope="col">After the rover</th></tr>
        </thead>
        <tbody>
          {comparison.rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              <td className={r.better === 'before' ? 'ba-better' : undefined}>{r.before}</td>
              <td className={r.better === 'after' ? 'ba-better' : undefined}>{r.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted ba-note">
        Green marks the better value. The rover and its find are simulated; distances, times and slopes come from the
        HiRISE elevation model. Use Replay under the map to show each route alone.
      </p>
    </section>
  );
}
