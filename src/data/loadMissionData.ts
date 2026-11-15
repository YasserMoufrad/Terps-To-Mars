// Loads every file in public/data/, checks it against the contract, and
// collects problems as "issues" instead of crashing. The app shows the issues
// on screen, so a missing or broken file is never silently treated as "no hazards".

// Imports use the .ts extension so the Node test runner can load this file directly.
import {
  SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS,
  HAZARD_TYPES, HAZARD_CATEGORIES, SEVERITIES, EVIDENCE, HAZARD_AGENTS, STAGE_IDS,
  ROUTE_KINDS, ROUTE_AGENTS, ROUTE_VERSIONS, ROUTE_STATUSES, LEG_MODES,
  COVERAGE_STATES, SENSORS, type RouteLeg,
  type HazardCollection, type RouteCollection, type CoverageCollection,
  type Mission, type OverlayBounds, type HiriseMeta, type HiriseTiles,
  type SlopeMeta, type ScarpLines, type RouteAudit,
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
  hiriseMeta: HiriseMeta | null;
  hiriseTiles: HiriseTiles[]; // wide, then context, then core (draw order); empty when not published
  slopeBounds: OverlayBounds | null; // null unless slope.meta.json is valid and describes the same grid
  slopeMeta: SlopeMeta | null;
  scarpLines: ScarpLines | null; // traced scarp edge + foot; drives "Inspect scarp"
  routeAudit: RouteAudit | null; // measured diagnostics per route line (pipeline.route_audit)
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
  // Purpose: record an error when a file's schema_version is not one the app supports
  // (SUPPORTED_SCHEMA_VERSIONS: 1.0 and 1.1; the current version is SCHEMA_VERSION).
  if (!(SUPPORTED_SCHEMA_VERSIONS as readonly unknown[]).includes(data.schema_version)) {
    issues.push({
      file,
      severity: 'error',
      message: `schema_version is "${String(data.schema_version)}" but the app expects one of ${SUPPORTED_SCHEMA_VERSIONS.join(', ')}.`,
    });
  }
}

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

function coordinatesOk(c: unknown): boolean {
  // Purpose: true when `c` is a GeoJSON position ([lon, lat] in signed degrees) or a non-empty
  // nested array of positions. Rejects NaN/Infinity and longitudes outside -180..180 (e.g. 0..360 east).
  if (!Array.isArray(c) || c.length === 0) return false;
  if (c.every((v) => typeof v === 'number')) {
    const [lon, lat] = c as number[];
    return c.length >= 2 && c.every(Number.isFinite) && lon >= -180 && lon <= 180 && lat >= -90 && lat <= 90;
  }
  return c.every(coordinatesOk);
}

export function checkFeatureCollection(raw: unknown, file: string, issues: LoadIssue[]): unknown | null {
  // Purpose: structural check before a GeoJSON file is cast to its contract type. A file that is not a
  // FeatureCollection of features with object `properties`, a string `id` and valid geometry is an
  // error and returns null, so later code never dereferences a missing field and crashes the page.
  if (raw === null) return null;
  if (!isObject(raw) || raw.type !== 'FeatureCollection' || !Array.isArray(raw.features)) {
    issues.push({ file, severity: 'error', message: 'Not a GeoJSON FeatureCollection; file ignored.' });
    return null;
  }
  const bad = raw.features.findIndex((f: unknown) => !isObject(f) || !isObject(f.properties)
    || typeof f.properties.id !== 'string' || !isObject(f.geometry) || typeof f.geometry.type !== 'string'
    || !coordinatesOk(f.geometry.coordinates));
  if (bad >= 0) {
    issues.push({ file, severity: 'error', message: `Feature ${bad} has no id, properties or valid [lon, lat] geometry; file ignored.` });
    return null;
  }
  return raw;
}

export function checkMissionShape(raw: unknown, issues: LoadIssue[]): unknown | null {
  // Purpose: structural check of mission.json (site, stages, discovery with options, drone) before it
  // is cast; a malformed file is an error and returns null instead of crashing the panel.
  if (raw === null) return null;
  const ok = isObject(raw) && isObject(raw.site) && typeof raw.site.name === 'string' && Array.isArray(raw.stages)
    && raw.stages.every((st: unknown) => isObject(st) && typeof st.id === 'string')
    && isObject(raw.discovery) && Array.isArray(raw.discovery.options) && isObject(raw.drone);
  if (!ok) {
    issues.push({ file: 'mission.json', severity: 'error', message: 'mission.json is missing site, stages, discovery or drone; file ignored.' });
    return null;
  }
  return raw;
}

function addId(id: string, label: string, file: string, ids: Set<string>, issues: LoadIssue[]): void {
  // Purpose: register a stable id; a duplicate makes mission.json references ambiguous, so it is an error.
  if (ids.has(id)) issues.push({ file, severity: 'error', message: `${label} id "${id}" is used more than once.` });
  ids.add(id);
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
    addId(p.id, 'hazard', file, ids, issues);
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
    addId(p.id, 'route', file, ids, issues);
    checkAllowed(p.kind, ROUTE_KINDS, `${label} kind`, file, issues);
    checkAllowed(p.agent, ROUTE_AGENTS, `${label} agent`, file, issues);
    checkAllowed(p.version, ROUTE_VERSIONS, `${label} version`, file, issues);
    checkAllowed(p.status, ROUTE_STATUSES, `${label} status`, file, issues);
    // A route that failed (e.g. no_viable_route) is not an error: it is an honest
    // result the app must show. We flag it as a warning so it is never missed.
    if (p.status !== 'ok') {
      issues.push({ file, severity: 'warning', message: `${label} status is ${p.status}.` });
    }
    if (p.legs !== undefined && data.schema_version === '1.0') {
      issues.push({ file, severity: 'warning', message: `${label} has legs, which need schema_version 1.1.` });
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
    addId(p.id, 'coverage', file, ids, issues);
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

export function checkOverlayBounds(raw: unknown, file: string, issues: LoadIssue[]): OverlayBounds | null {
  // Purpose: accept an overlay bounds file only if it can place the image correctly.
  // A misplaced image is worse than none, so bad bounds are an error and return null (not drawn).
  if (raw === null) return null;
  const b = raw as Partial<OverlayBounds>;
  const nums = [b.south, b.west, b.north, b.east];
  if (!nums.every((v) => typeof v === 'number' && Number.isFinite(v))) {
    issues.push({ file, severity: 'error', message: 'south, west, north and east must be numbers.' });
    return null;
  }
  const [south, west, north, east] = nums as number[];
  if (!(-90 <= south && south < north && north <= 90 && -180 <= west && west < east && east <= 180)) {
    issues.push({ file, severity: 'error', message: 'Bounds must be signed degrees with south < north and west < east (longitude -180..180).' });
    return null;
  }
  if (!(SUPPORTED_SCHEMA_VERSIONS as readonly unknown[]).includes(b.schema_version)) {
    // An unknown contract version may mean different corner semantics: never draw it.
    // 1.1 changed only route legs, so overlay bounds written as "1.0" stay valid.
    checkSchemaVersion(b, file, issues);
    return null;
  }
  if (!b.source || !b.processing) {
    issues.push({ file, severity: 'warning', message: 'Overlay has no source/processing provenance.' });
  }
  return b as OverlayBounds;
}

export const ALIGNMENT_STATES = [
  'not_verified', 'measured_within_tolerance', 'measured_exceeds_tolerance', 'insufficient_landmarks',
] as const;

export function checkHiriseMeta(raw: unknown, file: string, issues: LoadIssue[]): HiriseMeta | null {
  // Purpose: check the HD image metadata the map states to viewers (pixel size, sampling, alignment).
  // Returns null with an error when it is malformed or not native resolution; the loader then refuses
  // to draw the image, because an image with wrong provenance must not look authoritative.
  if (raw === null) return null;
  const m = raw as Partial<HiriseMeta>;
  const pair = (p: unknown, lo: number, hi: number) => Array.isArray(p) && p.length === 2
    && p.every((v) => finite(v) && v >= lo && v <= hi);
  const reasons: string[] = [];
  if (!pair(m.output_pixels, 1, 16384) || !(m.output_pixels as number[]).every(Number.isInteger)) {
    reasons.push('output_pixels must be two integers in 1..16384');
  }
  if (!pair(m.ground_sampling_m_ew_ns, 0.05, 2)) reasons.push('ground_sampling_m_ew_ns must be two values in 0.05..2 m');
  if (!(ALIGNMENT_STATES as readonly unknown[]).includes(m.landmark_alignment)) {
    reasons.push(`landmark_alignment "${String(m.landmark_alignment)}" is not a known state`);
  }
  if (m.resampling !== 'none_native' && m.resampling !== 'average_nodata_aware') {
    reasons.push(`resampling "${String(m.resampling)}" is not native resolution`);
  }
  for (const key of ['registration_rms_m', 'registration_max_m'] as const) {
    const v = m[key];
    if (v !== undefined && !(finite(v) && v >= 0 && v < 100)) reasons.push(`${key} must be a finite non-negative distance`);
  }
  if (reasons.length > 0) {
    issues.push({ file, severity: 'error', message: `HiRISE metadata rejected: ${reasons.join('; ')}.` });
    return null;
  }
  return m as HiriseMeta;
}

export function checkHiriseTiles(raw: unknown, file: string, issues: LoadIssue[]): HiriseTiles | null {
  // Purpose: accept a tile set only if Leaflet can place and request it correctly.
  // A malformed set is skipped with a warning; the single 4K overlay and CTX still show.
  if (raw === null) return null;
  const t = raw as Partial<HiriseTiles>;
  const b = t.bounds;
  const boundsOk = !!b && [b.south, b.west, b.north, b.east].every((v) => typeof v === 'number' && Number.isFinite(v))
    && -90 <= b.south && b.south < b.north && b.north <= 90 && -180 <= b.west && b.west < b.east && b.east <= 180;
  const zoomOk = Number.isInteger(t.min_zoom) && Number.isInteger(t.max_native_zoom)
    && (t.min_zoom as number) <= (t.max_native_zoom as number) && (t.max_native_zoom as number) <= 19;
  const urlOk = typeof t.url_template === 'string' && /\{z\}.*\{x\}.*\{y\}/.test(t.url_template) && !t.url_template.includes('..');
  if (!boundsOk || !zoomOk || !urlOk || !['wide', 'context', 'core'].includes(t.role as string)) {
    issues.push({ file, severity: 'warning', message: 'HiRISE tile set is malformed and was skipped.' });
    return null;
  }
  checkSchemaVersion(t, file, issues);
  return t as HiriseTiles;
}

export function checkSlopeMeta(raw: unknown, bounds: OverlayBounds | null, file: string, issues: LoadIssue[]): SlopeMeta | null {
  // Purpose: accept slope.meta.json only when it is NASA-derived, has a legend and describes exactly the
  // grid in slope.bounds.json. A mismatch means PNG and bounds come from different runs: never draw it.
  if (raw === null) return null;
  const m = raw as Partial<SlopeMeta>;
  const reasons: string[] = [];
  // 1.1 changed only route legs, so slope metadata written as "1.0" stays valid.
  if (!(SUPPORTED_SCHEMA_VERSIONS as readonly unknown[]).includes(m.schema_version)) {
    reasons.push(`schema_version ${String(m.schema_version)} is not one of ${SUPPORTED_SCHEMA_VERSIONS.join(', ')}`);
  }
  if (m.evidence !== 'nasa_derived') reasons.push('evidence must be nasa_derived (no synthetic slope maps)');
  const px = m.grid?.pixels;
  if (!Array.isArray(px) || px.length !== 2 || !px.every((v) => Number.isInteger(v) && v > 0 && v <= 16384)) {
    reasons.push('grid.pixels must be two positive integers');
  }
  const t = m.thresholds_deg;
  if (!t || !finite(t.crew_caution) || !finite(t.crew_exclude) || !finite(t.rover_exclude)
    || !(t.crew_caution < t.crew_exclude && t.crew_exclude <= t.rover_exclude)) {
    reasons.push('thresholds_deg must be increasing finite degrees');
  }
  if (!Array.isArray(m.legend) || m.legend.length < 5 || !m.legend.some((e) => e.class === 'unknown')) {
    reasons.push('legend must list every class including unknown');
  }
  const b = m.bounds;
  if (bounds && b && (['south', 'west', 'north', 'east'] as const).some((k) => !finite(b[k]) || Math.abs(b[k] - bounds[k]) > 1e-7)) {
    reasons.push('bounds differ from slope.bounds.json');
  }
  if (reasons.length > 0) {
    issues.push({ file, severity: 'error', message: `Slope map withdrawn: ${reasons.join('; ')}.` });
    return null;
  }
  return m as SlopeMeta;
}

export function checkScarpLines(raw: unknown, file: string, issues: LoadIssue[]): ScarpLines | null {
  // Purpose: accept the traced scarp only with both an edge and a foot line of finite signed coordinates.
  if (raw === null) return null;
  const fc = raw as Partial<ScarpLines>;
  const lines = Array.isArray(fc.features) ? fc.features : [];
  const ok = (id: string) => lines.some((f) => f?.properties?.id === id && f.geometry?.type === 'LineString'
    && Array.isArray(f.geometry.coordinates) && f.geometry.coordinates.length >= 2 && coordinatesOk(f.geometry.coordinates));
  if (!ok('scarp-edge') || !ok('scarp-foot')) {
    issues.push({ file, severity: 'warning', message: 'Scarp lines need a valid scarp-edge and scarp-foot LineString; ignored.' });
    return null;
  }
  checkSchemaVersion(fc, file, issues);
  return fc as ScarpLines;
}

export function checkRouteAudit(raw: unknown, file: string, issues: LoadIssue[]): RouteAudit | null {
  // Purpose: accept route_audit.json when it lists route entries with an audit status; never an "ok" status.
  if (raw === null) return null;
  const a = raw as Partial<RouteAudit>;
  if (!Array.isArray(a.routes) || a.routes.some((r) => typeof r?.id !== 'string' || typeof r?.audit_status !== 'string'
    || (r.audit_status as string) === 'ok' || !Array.isArray(r.reasons))) {
    issues.push({ file, severity: 'warning', message: 'Route audit is malformed and was ignored.' });
    return null;
  }
  checkSchemaVersion(a, file, issues);
  return a as RouteAudit;
}

async function fetchOptional(baseUrl: string, file: string, issues: LoadIssue[]): Promise<unknown | null> {
  // Purpose: fetch a file that may legitimately be absent (no issue for 404); parse errors still warn.
  const local: LoadIssue[] = [];
  const result = await fetchJson(baseUrl, file, local, 'warning');
  issues.push(...local.filter((i) => !/HTTP 404|File not found/.test(i.message)));
  return result;
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

  // Shape first: only structurally valid files are cast to their contract types.
  const hazards = checkFeatureCollection(hazardsRaw, 'hazards.geojson', issues) as HazardCollection | null;
  const routes = checkFeatureCollection(routesRaw, 'routes.geojson', issues) as RouteCollection | null;
  const coverage = checkFeatureCollection(coverageRaw, 'coverage.geojson', issues) as CoverageCollection | null;
  const mission = checkMissionShape(missionRaw, issues) as Mission | null;

  // GeoJSON files first, so their IDs are known before mission.json is checked.
  if (hazards) checkHazards(hazards, issues, ids);
  if (routes) checkRoutes(routes, issues, ids);
  if (coverage) checkCoverage(coverage, issues, ids);
  if (mission) checkMission(mission, issues, ids);

  // The HD image's metadata is only fetched when the image itself is published.
  // Missing metadata (an older publish) keeps the image without a caption; metadata that is present
  // but invalid withdraws the image, so a malformed HD asset never draws just because bounds exist.
  let hiriseBounds = checkOverlayBounds(hiriseRaw, 'hirise.bounds.json', issues);
  let slopeBounds = checkOverlayBounds(slopeRaw, 'slope.bounds.json', issues);
  // The slope map is drawn only with metadata describing the same grid (legend, thresholds, provenance).
  const slopeMetaRaw = slopeBounds ? await fetchJson(baseUrl, 'slope.meta.json', issues, 'error') : null;
  const slopeMeta = checkSlopeMeta(slopeMetaRaw, slopeBounds, 'slope.meta.json', issues);
  if (slopeMeta === null) slopeBounds = null;
  const [scarpRaw, auditRaw] = await Promise.all([
    fetchOptional(baseUrl, 'scarp_lines.geojson', issues),
    fetchOptional(baseUrl, 'route_audit.json', issues),
  ]);
  const scarpLines = checkScarpLines(scarpRaw, 'scarp_lines.geojson', issues);
  const routeAudit = checkRouteAudit(auditRaw, 'route_audit.json', issues);
  if (routeAudit && routes) {
    const audited = new Set(routeAudit.routes.map((r) => r.id));
    const missing = routes.features.map((f) => f.properties.id).filter((id) => !audited.has(id));
    if (missing.length > 0) {
      issues.push({ file: 'route_audit.json', severity: 'warning', message: `No terrain audit for ${missing.join(', ')}; re-run pipeline.route_audit.` });
    }
  }
  const hiriseMetaRaw = hiriseBounds ? await fetchJson(baseUrl, 'hirise.meta.json', issues, 'warning') : null;
  const hiriseMeta = checkHiriseMeta(hiriseMetaRaw, 'hirise.meta.json', issues);
  if (hiriseMetaRaw !== null && hiriseMeta === null) hiriseBounds = null;
  // Tile pyramids are optional: whole strip (low zoom) first, ~1 m context ring, native core on top.
  const hiriseTiles = (await Promise.all(['wide', 'context', 'core'].map(async (role) => {
    const file = `hirise-tiles/${role}/tiles.json`;
    return checkHiriseTiles(await fetchOptional(baseUrl, file, issues), file, issues);
  }))).filter((t): t is HiriseTiles => t !== null);

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
    overlays: { hirise: hiriseBounds !== null, slope: slopeBounds !== null },
    scarp_lines: scarpLines !== null,
    route_audit: routeAudit ? Object.fromEntries(routeAudit.routes.map((r) => [r.id, r.audit_status])) : null,
    hirise_pixels: hiriseMeta?.output_pixels ?? null,
    hirise_alignment: hiriseMeta?.landmark_alignment ?? null,
    hirise_tiles: hiriseTiles.map((t) => `${t.role}:z${t.min_zoom}-${t.max_native_zoom}`),
  });

  return {
    hazards,
    routes,
    coverage,
    mission,
    hiriseBounds,
    hiriseMeta,
    hiriseTiles,
    slopeBounds,
    slopeMeta,
    scarpLines,
    routeAudit,
    issues,
    placeholderFiles,
  };
}
