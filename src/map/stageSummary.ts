// "What this step shows": a short, data-driven summary per mission stage, so each stage
// tells a different part of the story and its words can never contradict the data.
// Pure (no React, no Leaflet) so the Node test runner can check it.

import type {
  StageId, Mission, HazardCollection, RouteCollection, CoverageCollection, RouteFeature, HazardFeature,
} from '../data/types.ts';
import { hazardsFor } from './stageFilters.ts';

// No "ok" tone on purpose: nothing in this demo is crew clearance, so nothing is drawn green.
export type SummaryTone = 'info' | 'caution' | 'stop';

export interface SummaryRow {
  label: string;
  value: string;
  tone: SummaryTone;
}

export interface StageSummary {
  title: string;
  rows: SummaryRow[];
}

interface SummaryData {
  mission: Mission;
  hazards: HazardCollection;
  routes: RouteCollection;
  coverage: CoverageCollection;
}

type Ring = number[][];

function pointInRing([x, y]: number[], ring: Ring): boolean {
  // Purpose: ray-casting test; `ring` is a closed [lon, lat] polygon ring.
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function hazardsCrossed(route: RouteFeature, hazards: HazardFeature[]): HazardFeature[] {
  // Purpose: exclude-severity polygon hazards that the route's line passes through
  // (each segment sampled every 1% of its length).
  const coords = route.geometry.coordinates;
  const polys = hazards.filter((h) => h.properties.severity === 'exclude' && h.geometry.type === 'Polygon');
  const hit = new Set<HazardFeature>();
  for (let i = 1; i < coords.length; i++) {
    for (let t = 0; t <= 1; t += 0.01) {
      const p = [coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * t, coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * t];
      for (const h of polys) if (pointInRing(p, (h.geometry.coordinates as Ring[])[0])) hit.add(h);
    }
  }
  return [...hit];
}

const km = (m: number) => `${(m / 1000).toFixed(2)} km`;
const legLength = (r: RouteFeature, mode: 'drive' | 'walk') =>
  (r.properties.legs ?? []).filter((l) => l.mode === mode).reduce((s, l) => s + l.length_m, 0);
const statusWords = (status: string) =>
  status === 'ok' ? 'Geometric result only (not clearance)' : status === 'inspection_required' ? 'Needs inspection' : status.replace(/_/g, ' ');
const statusTone = (status: string): SummaryTone =>
  status === 'no_viable_route' || status === 'backup_unavailable' ? 'stop' : status === 'ok' ? 'info' : 'caution';

function orbital({ hazards, routes, coverage }: SummaryData): StageSummary {
  // Purpose: what orbital data shows and what it cannot show yet.
  const seen = hazardsFor('orbital', hazards).features;
  const nasa = seen.filter((h) => h.properties.evidence === 'nasa_derived').length;
  const inferred = seen.filter((h) => h.properties.evidence === 'inferred').length;
  const guess = routes.features.find((r) => r.properties.kind === 'orbital_guess');
  const unscouted = coverage.features.filter((c) => c.properties.state === 'unscouted').length;
  const rows: SummaryRow[] = [
    { label: 'From orbit', value: `${nasa} NASA-derived and ${inferred} inferred hazard zones`, tone: 'info' },
  ];
  if (guess) {
    // The orbital candidate is the DTM least-cost drive + walk (pipeline.mission_geography), not a straight line.
    const crossed = hazardsCrossed(guess, seen);
    const legs = guess.properties.legs?.length
      ? `Drive ${km(legLength(guess, 'drive'))}, walk ${Math.round(legLength(guess, 'walk'))} m; `
      : '';
    rows.push({
      label: 'Orbit-only plan',
      value: crossed.length > 0
        ? `${legs}crosses ${crossed.length} mapped no-go zone${crossed.length > 1 ? 's' : ''} (${crossed.map((h) => h.properties.category.replace('_', ' ')).join(', ')})`
        : `${legs}routed around every mapped no-go zone. ${statusWords(guess.properties.status)}`,
      tone: crossed.length > 0 ? 'stop' : statusTone(guess.properties.status),
    });
  }
  rows.push({ label: 'Not visible yet', value: 'Rocks under about 1 m, soft ground, and anything no robot has scouted', tone: 'caution' });
  if (unscouted > 0) rows.push({ label: 'Unscouted', value: `${unscouted} area${unscouted > 1 ? 's' : ''} shown in gray`, tone: 'caution' });
  return { title: 'What orbit can and cannot tell us', rows };
}

function rover({ mission, routes, hazards }: SummaryData): StageSummary {
  // Purpose: what the simulated rover found and how the route changed.
  const d = mission.discovery;
  const before = routes.features.find((r) => r.properties.id === d.before_route_id);
  const after = routes.features.find((r) => r.properties.id === d.after_route_id);
  const sim = hazards.features.find((h) => h.properties.id === d.hazard_id);
  const rows: SummaryRow[] = [
    { label: 'Found', value: `Suspected soft ground (simulated, uncertainty ${d.uncertainty})`, tone: 'stop' },
  ];
  if (before) {
    const hitsSim = sim ? hazardsCrossed(before, [sim]).length > 0 : false;
    rows.push({ label: 'Old route', value: `${km(before.properties.stats.length_m)} each way${hitsSim ? ', runs through the soft ground' : ''} (gray)`, tone: hitsSim ? 'stop' : 'caution' });
  }
  if (before && after) {
    const delta = after.properties.stats.length_m - before.properties.stats.length_m;
    rows.push({ label: 'Proposed reroute', value: `${km(after.properties.stats.length_m)} each way (${delta >= 0 ? '+' : ''}${delta.toFixed(0)} m), ${statusWords(after.properties.status).toLowerCase()}`, tone: statusTone(after.properties.status) });
  }
  rows.push({ label: 'Crew decision', value: d.chosen_option === '' ? 'Pending: the crew has not chosen an option' : `Chosen: ${d.options.find((o) => o.id === d.chosen_option)?.label ?? d.chosen_option}`, tone: d.chosen_option === '' ? 'caution' : 'info' });
  return { title: 'What the rover changed', rows };
}

function drone({ mission, coverage }: SummaryData): StageSummary {
  // Purpose: what the drone concept adds over the rover, and what stays unresolved.
  const cone = coverage.features.find((c) => c.properties.id === mission.drone.view_cone_id);
  const droneZones = coverage.features.filter((c) => c.properties.state === 'drone_checked').length;
  const unscouted = coverage.features.filter((c) => c.properties.state === 'unscouted').length;
  return {
    title: 'What the drone adds',
    rows: [
      { label: 'Why a drone', value: 'It can image the tall middle of the ice face and the rockfall zone, which the rover and crew cannot reach', tone: 'info' },
      { label: 'Field of view', value: cone ? `Blue cone from the perch${cone.properties.simulated ? ' (simulated)' : ''}` : 'Not supplied', tone: cone ? 'caution' : 'stop' },
      { label: 'Coverage', value: `${droneZones} planned inspection footprint${droneZones === 1 ? '' : 's'} (simulated)`, tone: 'caution' },
      { label: 'Flight', value: 'No flight has occurred; this is the planned inspection', tone: 'caution' },
      ...(unscouted > 0 ? [{ label: 'Still unresolved', value: `${unscouted} unscouted area${unscouted > 1 ? 's' : ''} (gray)`, tone: 'caution' as SummaryTone }] : []),
    ],
  };
}

function eva({ mission, routes, hazards }: SummaryData): StageSummary {
  // Purpose: the crew's review: route feasibility, backup limits, open hazards, decision needed.
  const main = routes.features.find((r) => r.properties.id === mission.discovery.after_route_id);
  const backup = routes.features.find((r) => r.properties.kind === 'backup' && r.properties.agent === 'crew' && r.properties.version === 'after');
  const open = hazards.features.filter((h) => h.properties.evidence !== 'nasa_derived');
  const rows: SummaryRow[] = [];
  if (main) {
    const drive = legLength(main, 'drive');
    const reason = drive > 0 && main.properties.status === 'inspection_required' ? ': the crew-rover drive is not yet modeled' : '';
    rows.push({ label: 'Main route', value: `${statusWords(main.properties.status)}${reason}`, tone: statusTone(main.properties.status) });
  } else {
    rows.push({ label: 'Main route', value: 'No post-discovery route supplied', tone: 'stop' });
  }
  if (backup) {
    const walk = legLength(backup, 'walk');
    const shared = backup.properties.stats.shared_with_main_m;
    const sharesDrive = shared > 0.5 * backup.properties.stats.length_m;
    rows.push({
      label: 'Backup',
      value: `${walk > 0 ? `A ${walk.toFixed(0)} m walk between the backup viewpoint and the crew rover` : 'Alternative way to the backup viewpoint'}` +
        (sharesDrive ? `; it shares ${km(shared)} of driving with the main route, so if the drive is blocked the fallback is walking home (walkback)` : ''),
      tone: sharesDrive ? 'caution' : statusTone(backup.properties.status),
    });
  } else {
    rows.push({ label: 'Backup', value: 'No post-discovery backup assessment supplied', tone: 'stop' });
  }
  rows.push({ label: 'Open hazards', value: `${open.length} zone${open.length === 1 ? '' : 's'} inferred or simulated, to confirm on site`, tone: 'caution' });
  rows.push({ label: 'Crew decision', value: 'Accept the route after rover scouting and inspection, or hold the EVA', tone: 'caution' });
  return { title: 'Crew review', rows };
}

export function stageSummary(stage: StageId, data: SummaryData): StageSummary {
  // Purpose: the summary card for `stage`, computed from the loaded mission data.
  switch (stage) {
    case 'orbital': return orbital(data);
    case 'rover': return rover(data);
    case 'drone': return drone(data);
    case 'eva': return eva(data);
  }
}
