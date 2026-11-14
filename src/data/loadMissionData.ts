// Loads every file in public/data/, checks it against the contract, and
// collects problems as "issues" instead of crashing. The app shows the issues
// on screen, so a missing or broken file is never silently treated as "no hazards".

// Imports use the .ts extension so the Node test runner can load this file directly.
import {
  SCHEMA_VERSION,
  HAZARD_TYPES, HAZARD_CATEGORIES, SEVERITIES, EVIDENCE, HAZARD_AGENTS, STAGE_IDS,
  ROUTE_KINDS, ROUTE_AGENTS, ROUTE_VERSIONS, ROUTE_STATUSES, LEG_MODES,
  COVERAGE_STATES, SENSORS, type RouteLeg,
  type HazardCollection, type RouteCollection, type CoverageCollection,
  type Mission, type OverlayBounds,
} from './types.ts';
import { silentLogger, type Logger } from '../lib/logger.ts';

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

async function fetchJson(
  baseUrl: string,
  file: string,
  issues: LoadIssue[],
  missingSeverity: LoadIssue['severity'],
): Promise<unknown | null> {
  // Purpose: fetch and parse one file from public/data/. Never throws: on failure it
  // records an issue in `issues` at `missingSeverity` ("error" for core files,
  // "warning" for optional pipeline overlays) and returns null.
  try {
    const response = await fetch(`${baseUrl}data/${file}`);
    if (!response.ok) {
      issues.push({ file, severity: missingSeverity, message: `Could not load (HTTP ${response.status}).` });
      return null;
    }
    // The dev server answers a missing file with its HTML page instead of a 404.
    if (response.headers?.get('content-type')?.includes('text/html')) {
      issues.push({ file, severity: missingSeverity, message: 'File not found.' });
      return null;
    }
    return await response.json();
  } catch (err) {
    issues.push({ file, severity: missingSeverity, message: `Could not load or parse: ${String(err)}` });
    return null;
  }
}

function checkAllowed(
  value: unknown,
  allowed: readonly string[],
  label: string,
  file: string,
  issues: LoadIssue[],
): void {
  // Purpose: record an error if `value` is not one of the `allowed` contract values.
  // `label` names the property in the message (e.g. "hazard hz-1 evidence").
  if (typeof value !== 'string' || !allowed.includes(value)) {
    issues.push({ file, severity: 'error', message: `${label} is "${String(value)}"; expected one of ${allowed.join(', ')}.` });
  }
}

function checkSchemaVersion(data: { schema_version?: unknown }, file: string, issues: LoadIssue[]): void {
  // Purpose: record an error when a file's schema_version differs from SCHEMA_VERSION.
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
  // Purpose: validate every hazard's enum properties; adds each hazard id to `ids`
  // so mission.json references can be checked afterwards.
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
  // Purpose: validate every route's enum properties, add its id to `ids`, and warn
  // about any route whose status is not "ok" so failures are never silent.
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
    checkLegs(p.legs, f.geometry.coordinates.length, label, issues);
  }
}

export function checkLegs(legs: unknown, pointCount: number, label: string, issues: LoadIssue[]): void {
  // Purpose: validate the optional drive/walk `legs` of one route. `pointCount` is the
  // number of coordinates in its line. Bad legs are a warning, not an error: the route
  // is still drawn as one walking line, so nothing is hidden.
  if (legs === undefined) return;
  const file = 'routes.geojson';
  const warn = (message: string): void => {
    issues.push({ file, severity: 'warning', message: `${label} legs: ${message}` });
  };
  if (!Array.isArray(legs)) return warn('expected a list.');
  let expectedFrom = 0;
  for (const leg of legs as RouteLeg[]) {
    if (!(LEG_MODES as readonly string[]).includes(String(leg?.mode))) return warn(`mode "${String(leg?.mode)}" is not drive or walk.`);
    if (!Number.isInteger(leg.from) || !Number.isInteger(leg.to) || leg.from !== expectedFrom || leg.to <= leg.from || leg.to >= pointCount) {
      return warn('indexes must run along the line without gaps or overlaps.');
    }
    expectedFrom = leg.to;
  }
  if (expectedFrom !== pointCount - 1) warn('do not cover the whole line.');
}

function checkCoverage(data: CoverageCollection, issues: LoadIssue[], ids: Set<string>): void {
  // Purpose: validate coverage zones and enforce the honesty rule that robot
  // coverage (rover_checked / drone_checked) is always marked simulated.
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
  // Purpose: check stage order, that every id mission.json references exists in `ids`
  // (filled by the GeoJSON checks), and that chosen_option is empty or a real option.
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

  // An empty chosen_option means the crew has not decided yet (Nic's pipeline leaves
  // it empty until a human approves an option). Anything else must be a real option.
  const optionIds = data.discovery.options.map((o) => o.id);
  if (data.discovery.chosen_option !== '' && !optionIds.includes(data.discovery.chosen_option)) {
    issues.push({ file, severity: 'error', message: `discovery.chosen_option "${data.discovery.chosen_option}" is not one of the options.` });
  }
}

// ---------- main entry point ----------

export async function loadMissionData(baseUrl: string, logger: Logger = silentLogger): Promise<MissionData> {
  // Purpose: load and check every data file, returning what loaded plus `issues`.
  // baseUrl: where the site is served from (import.meta.env.BASE_URL, ends with "/").
  // logger: receives load.start, one event per issue, and a load.complete summary.
  const started = performance.now();
  logger.info('data', 'load.start', { base_url: baseUrl, schema_version: SCHEMA_VERSION });
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

  // One event per problem (there are only a handful), then one summary event.
  for (const issue of issues) {
    const fields = { file: issue.file, reason: issue.message };
    if (issue.severity === 'error') logger.error('data', 'validation.error', fields);
    else logger.warn('data', 'validation.warning', fields);
  }
  const errorCount = issues.filter((i) => i.severity === 'error').length;
  logger.info('data', 'load.complete', {
    outcome: errorCount === 0 ? 'ok' : 'errors',
    duration_ms: Math.round(performance.now() - started),
    errors: errorCount,
    warnings: issues.length - errorCount,
    hazards: hazards?.features.length ?? 0,
    routes: routes?.features.length ?? 0,
    coverage_zones: coverage?.features.length ?? 0,
    placeholder_files: placeholderFiles,
    overlays: { hirise: hiriseRaw !== null, slope: slopeRaw !== null },
  });

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
