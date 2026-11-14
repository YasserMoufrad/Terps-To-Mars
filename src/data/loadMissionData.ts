// Loads every file in public/data/, checks it against the contract, and
// collects problems as "issues" instead of crashing. The app shows the issues
// on screen, so a missing or broken file is never silently treated as "no hazards".

import {
  SCHEMA_VERSION,
  HAZARD_TYPES, HAZARD_CATEGORIES, SEVERITIES, EVIDENCE, HAZARD_AGENTS, STAGE_IDS,
  ROUTE_KINDS, ROUTE_AGENTS, ROUTE_VERSIONS, ROUTE_STATUSES,
  COVERAGE_STATES, SENSORS,
  type HazardCollection, type RouteCollection, type CoverageCollection,
  type Mission, type OverlayBounds,
} from './types';

export interface LoadIssue {
  file: string;
  severity: 'error' | 'warning';
  message: string;
}

export interface MissionData {
  hazards: HazardCollection | null;
  routes: RouteCollection | null;
  coverage: CoverageCollection | null;
  mission: Mission | null;
  hiriseBounds: OverlayBounds | null;
  slopeBounds: OverlayBounds | null;
  issues: LoadIssue[];
  placeholderFiles: string[];
}

// ---------- small helpers ----------

// Fetch one JSON file. Returns null (and records an issue) instead of throwing.
async function fetchJson(
  baseUrl: string,
  file: string,
  issues: LoadIssue[],
  missingSeverity: LoadIssue['severity'],
): Promise<unknown | null> {
  try {
    const response = await fetch(`${baseUrl}data/${file}`);
    if (!response.ok) {
      issues.push({ file, severity: missingSeverity, message: `Could not load (HTTP ${response.status}).` });
      return null;
    }
    return await response.json();
  } catch (err) {
    issues.push({ file, severity: missingSeverity, message: `Could not load or parse: ${String(err)}` });
    return null;
  }
}

// Check that a value is one of the allowed strings, recording an issue if not.
function checkAllowed(
  value: unknown,
  allowed: readonly string[],
  label: string,
  file: string,
  issues: LoadIssue[],
): void {
  if (typeof value !== 'string' || !allowed.includes(value)) {
    issues.push({ file, severity: 'error', message: `${label} is "${String(value)}"; expected one of ${allowed.join(', ')}.` });
  }
}

function checkSchemaVersion(data: { schema_version?: unknown }, file: string, issues: LoadIssue[]): void {
  if (data.schema_version !== SCHEMA_VERSION) {
    issues.push({
      file,
      severity: 'error',
      message: `schema_version is "${String(data.schema_version)}" but the app expects "${SCHEMA_VERSION}".`,
    });
  }
}

// ---------- per-file checks ----------

function checkHazards(data: HazardCollection, issues: LoadIssue[], ids: Set<string>): void {
  const file = 'hazards.geojson';
  checkSchemaVersion(data, file, issues);
  for (const f of data.features) {
    const p = f.properties;
    const label = `hazard ${p.id}`;
    ids.add(p.id);
    checkAllowed(p.type, HAZARD_TYPES, `${label} type`, file, issues);
    checkAllowed(p.category, HAZARD_CATEGORIES, `${label} category`, file, issues);
    checkAllowed(p.severity, SEVERITIES, `${label} severity`, file, issues);
    checkAllowed(p.evidence, EVIDENCE, `${label} evidence`, file, issues);
    checkAllowed(p.agent, HAZARD_AGENTS, `${label} agent`, file, issues);
    checkAllowed(p.stage, STAGE_IDS, `${label} stage`, file, issues);
  }
}

function checkRoutes(data: RouteCollection, issues: LoadIssue[], ids: Set<string>): void {
  const file = 'routes.geojson';
  checkSchemaVersion(data, file, issues);
  for (const f of data.features) {
    const p = f.properties;
    const label = `route ${p.id}`;
    ids.add(p.id);
    checkAllowed(p.kind, ROUTE_KINDS, `${label} kind`, file, issues);
    checkAllowed(p.agent, ROUTE_AGENTS, `${label} agent`, file, issues);
    checkAllowed(p.version, ROUTE_VERSIONS, `${label} version`, file, issues);
    checkAllowed(p.status, ROUTE_STATUSES, `${label} status`, file, issues);
    // A route that failed (e.g. no_viable_route) is not an error: it is an honest
    // result the app must show. We flag it as a warning so it is never missed.
    if (p.status !== 'ok') {
      issues.push({ file, severity: 'warning', message: `${label} status is ${p.status}.` });
    }
  }
}

function checkCoverage(data: CoverageCollection, issues: LoadIssue[], ids: Set<string>): void {
  const file = 'coverage.geojson';
  checkSchemaVersion(data, file, issues);
  for (const f of data.features) {
    const p = f.properties;
    const label = `coverage ${p.id}`;
    ids.add(p.id);
    checkAllowed(p.state, COVERAGE_STATES, `${label} state`, file, issues);
    checkAllowed(p.sensor, SENSORS, `${label} sensor`, file, issues);
    // Honesty rule: robot coverage in this demo is always simulated.
    if ((p.state === 'rover_checked' || p.state === 'drone_checked') && p.simulated !== true) {
      issues.push({ file, severity: 'error', message: `${label} is robot coverage but not marked simulated.` });
    }
  }
}

function checkMission(data: Mission, issues: LoadIssue[], ids: Set<string>): void {
  const file = 'mission.json';
  checkSchemaVersion(data, file, issues);

  const stageOrder = data.stages.map((s) => s.id).join(',');
  if (stageOrder !== STAGE_IDS.join(',')) {
    issues.push({ file, severity: 'error', message: `stages are "${stageOrder}"; expected "${STAGE_IDS.join(',')}".` });
  }

  // Every ID that mission.json points at must exist in one of the GeoJSON files.
  const references = [
    ['discovery.hazard_id', data.discovery.hazard_id],
    ['discovery.before_route_id', data.discovery.before_route_id],
    ['discovery.after_route_id', data.discovery.after_route_id],
    ['drone.view_cone_id', data.drone.view_cone_id],
  ] as const;
  for (const [field, id] of references) {
    if (!ids.has(id)) {
      issues.push({ file, severity: 'error', message: `${field} points at "${id}", which is not in any data file.` });
    }
  }

  const optionIds = data.discovery.options.map((o) => o.id);
  if (!optionIds.includes(data.discovery.chosen_option)) {
    issues.push({ file, severity: 'error', message: `discovery.chosen_option "${data.discovery.chosen_option}" is not one of the options.` });
  }
}

// ---------- main entry point ----------

// baseUrl: where the site is served from. In the app, pass import.meta.env.BASE_URL
// (Vite sets it, e.g. "/Terps-To-Mars/" on GitHub Pages). It must end with "/".
export async function loadMissionData(baseUrl: string): Promise<MissionData> {
  const issues: LoadIssue[] = [];
  const ids = new Set<string>();

  // Fetch all files at the same time instead of one after another.
  const [hazardsRaw, routesRaw, coverageRaw, missionRaw, hiriseRaw, slopeRaw] = await Promise.all([
    fetchJson(baseUrl, 'hazards.geojson', issues, 'error'),
    fetchJson(baseUrl, 'routes.geojson', issues, 'error'),
    fetchJson(baseUrl, 'coverage.geojson', issues, 'error'),
    fetchJson(baseUrl, 'mission.json', issues, 'error'),
    // Overlays come from Nic's pipeline later, so missing ones are only warnings for now.
    fetchJson(baseUrl, 'hirise.bounds.json', issues, 'warning'),
    fetchJson(baseUrl, 'slope.bounds.json', issues, 'warning'),
  ]);

  const hazards = hazardsRaw as HazardCollection | null;
  const routes = routesRaw as RouteCollection | null;
  const coverage = coverageRaw as CoverageCollection | null;
  const mission = missionRaw as Mission | null;

  // GeoJSON files first, so their IDs are known before mission.json is checked.
  if (hazards) checkHazards(hazards, issues, ids);
  if (routes) checkRoutes(routes, issues, ids);
  if (coverage) checkCoverage(coverage, issues, ids);
  if (mission) checkMission(mission, issues, ids);

  const placeholderFiles = [
    ['hazards.geojson', hazards],
    ['routes.geojson', routes],
    ['coverage.geojson', coverage],
    ['mission.json', mission],
  ]
    .filter(([, data]) => (data as { placeholder?: boolean } | null)?.placeholder === true)
    .map(([file]) => file as string);

  return {
    hazards,
    routes,
    coverage,
    mission,
    hiriseBounds: hiriseRaw as OverlayBounds | null,
    slopeBounds: slopeRaw as OverlayBounds | null,
    issues,
    placeholderFiles,
  };
}
