// EVA time budget as a timeline, from the route's own legs (pipeline.mission_geography timings): the planned trip
// (drive out, walk out, science, walk back, drive back) against the planning limit (EVA minus reserve), and the
// contingency where the crew vehicle fails at parking and the crew walks home along the drive. Pure, so the Node tests
// can check it; the same numbers as the pipeline's budget check (240 min EVA, 30% reserve, 20 min at the site).

import type { RouteFeature } from '../data/types.ts';

export const EVA_MINUTES = 240; // full spacewalk (planning assumption, IMPLEMENTATION section 5)
export const RESERVE_FRACTION = 0.3; // kept unused for contingencies (hazard_rules.json eva_reserve_fraction)
export const SITE_MINUTES = 20; // observation time at the viewpoint (pipeline SITE_MINUTES)

export type SegmentKind = 'drive' | 'walk' | 'science' | 'walk-home';
export interface Segment { label: string; kind: SegmentKind; minutes: number }
export interface Timeline { segments: Segment[]; total: number; limit: number; fits: boolean }

export function evaTimeline(route: RouteFeature): { planned: Timeline; vehicleFails: Timeline } | null {
  // Purpose: both timelines for a crew route with drive/walk legs; null when the route has no legs (no timing data).
  // planned.limit = EVA x (1 - reserve) = 168 min; vehicleFails.limit = the whole EVA, 240 min.
  const legs = route.properties.legs ?? [];
  if (legs.length === 0) return null;
  const sum = (mode: 'drive' | 'walk') => legs.filter((l) => l.mode === mode).reduce((s, l) => s + l.est_time_min, 0);
  const drive = sum('drive');
  const walk = sum('walk');
  const walkHome = route.properties.walkback_min ?? 0;
  const out: Segment[] = [
    ...(drive > 0 ? [{ label: 'Drive out', kind: 'drive' as const, minutes: drive }] : []),
    { label: 'Walk to viewpoint', kind: 'walk', minutes: walk },
    { label: 'Science at the cliff', kind: 'science', minutes: SITE_MINUTES },
    { label: 'Walk back', kind: 'walk', minutes: walk },
  ];
  const planned = [...out, ...(drive > 0 ? [{ label: 'Drive back', kind: 'drive' as const, minutes: drive }] : [])];
  const failed = [...out, ...(walkHome > 0 ? [{ label: 'Walk home (vehicle fails)', kind: 'walk-home' as const, minutes: walkHome }] : [])];
  const make = (segments: Segment[], limit: number): Timeline => {
    const total = segments.reduce((s, x) => s + x.minutes, 0);
    return { segments, total, limit, fits: total <= limit };
  };
  return { planned: make(planned, EVA_MINUTES * (1 - RESERVE_FRACTION)), vehicleFails: make(failed, EVA_MINUTES) };
}
