// Types for the data files in public/data/.
// They mirror the data contract in docs/IMPLEMENTATION.md, section 4.
// If the contract changes, change it there first, then here, and bump SCHEMA_VERSION.
// This file has no imports, so the Node test runner can load it directly.

export const SCHEMA_VERSION = '1.0';

// ---------- Allowed values ----------
// Each list is the single source of truth for one property. The `as const`
// turns the array into a fixed set of literal strings, and the type below it
// is built from that set, so the type and the runtime check can never drift apart.

export const HAZARD_TYPES = ['U', 'O', 'S'] as const;
export type HazardType = (typeof HAZARD_TYPES)[number];

export const HAZARD_CATEGORIES = [
  'slope', 'roughness', 'rockfall', 'edge', 'soft_ground', 'void', 'shadow', 'no_data', 'artifact',
] as const;
export type HazardCategory = (typeof HAZARD_CATEGORIES)[number];

export const SEVERITIES = ['exclude', 'caution'] as const;
export type Severity = (typeof SEVERITIES)[number];

export const EVIDENCE = ['nasa_derived', 'inferred', 'simulated'] as const;
export type Evidence = (typeof EVIDENCE)[number];

export const HAZARD_AGENTS = ['crew', 'rover', 'both'] as const;
export type HazardAgent = (typeof HAZARD_AGENTS)[number];

export const STAGE_IDS = ['orbital', 'rover', 'drone', 'eva'] as const;
export type StageId = (typeof STAGE_IDS)[number];

export const ROUTE_KINDS = ['orbital_guess', 'main', 'backup', 'rover_path'] as const;
export type RouteKind = (typeof ROUTE_KINDS)[number];

export const ROUTE_AGENTS = ['crew', 'rover'] as const;
export type RouteAgent = (typeof ROUTE_AGENTS)[number];

export const ROUTE_VERSIONS = ['before', 'after'] as const;
export type RouteVersion = (typeof ROUTE_VERSIONS)[number];

export const ROUTE_STATUSES = ['ok', 'no_viable_route', 'backup_unavailable', 'inspection_required'] as const;
export type RouteStatus = (typeof ROUTE_STATUSES)[number];

export const COVERAGE_STATES = ['orbit_only', 'rover_checked', 'drone_checked', 'unscouted', 'inspection_required'] as const;
export type CoverageState = (typeof COVERAGE_STATES)[number];

export const SENSORS = ['stereo_cam', 'hazard_cam', 'thermal', 'drone_cam', 'none'] as const;
export type Sensor = (typeof SENSORS)[number];

// ---------- GeoJSON building blocks ----------
// GeoJSON positions are [longitude, latitude], in that order.

export type LonLat = [number, number];

export interface PointGeometry { type: 'Point'; coordinates: LonLat }
export interface LineStringGeometry { type: 'LineString'; coordinates: LonLat[] }
export interface PolygonGeometry { type: 'Polygon'; coordinates: LonLat[][] }

export interface Feature<G, P> {
  type: 'Feature';
  geometry: G;
  properties: P;
}

export interface FeatureCollection<F> {
  type: 'FeatureCollection';
  schema_version: string;
  placeholder?: boolean;
  features: F[];
}

// ---------- hazards.geojson ----------

export interface HazardProperties {
  id: string;
  type: HazardType;
  category: HazardCategory;
  severity: Severity;
  evidence: Evidence;
  agent: HazardAgent;
  stage: StageId;
  source: string;
  note: string;
}

export type HazardFeature = Feature<PolygonGeometry | PointGeometry, HazardProperties>;
export type HazardCollection = FeatureCollection<HazardFeature>;

// ---------- routes.geojson ----------

export interface RouteStats {
  length_m: number;
  round_trip_m: number;
  est_time_min: number;
  elevation_gain_m: number;
  max_slope_deg: number;
  shared_with_main_m: number;
}

export interface RouteProperties {
  id: string;
  kind: RouteKind;
  agent: RouteAgent;
  version: RouteVersion;
  status: RouteStatus;
  stats: RouteStats;
}

export type RouteFeature = Feature<LineStringGeometry, RouteProperties>;
export type RouteCollection = FeatureCollection<RouteFeature>;

// ---------- coverage.geojson ----------

export interface CoverageProperties {
  id: string;
  state: CoverageState;
  simulated: boolean;
  sensor: Sensor;
}

export type CoverageFeature = Feature<PolygonGeometry, CoverageProperties>;
export type CoverageCollection = FeatureCollection<CoverageFeature>;

// ---------- mission.json ----------
// Outside GeoJSON we use named fields, so there is no lat/lon order to get wrong.

export interface LatLon { lat: number; lon: number }

export interface Stage {
  id: StageId;
  title: string;
  text: string;
  stats: Record<string, string>;
}

export interface DiscoveryOption {
  id: string;
  label: string;
  consequence: string;
}

export interface Discovery {
  id: string;
  hazard_id: string;
  before_route_id: string;
  after_route_id: string;
  location: LatLon;
  sensor_evidence: Record<string, string | number>;
  evidence: Evidence;
  uncertainty: string;
  decision: 'continue' | 'reroute' | 'request_input' | 'stop';
  options: DiscoveryOption[];
  chosen_option: string; // '' = the crew has not decided yet
}

export interface Mission {
  schema_version: string;
  placeholder?: boolean;
  site: { name: string; lat: number; lon: number; dtm_id: string; image_id: string };
  sun: { ls_deg: number; local_time: string; elevation_deg: number; source: string };
  endpoints: { habitat: LatLon; observation_primary: LatLon; observation_backup: LatLon };
  stages: Stage[];
  alerts: Partial<Record<StageId, string[]>>;
  drone: { perch: LatLon; view_cone_id: string };
  discovery: Discovery;
}

// ---------- *.bounds.json (image overlays from the pipeline) ----------

export interface OverlayBounds {
  schema_version: string;
  south: number;
  west: number;
  north: number;
  east: number;
  source: string;
  processing: string;
}

// hirise.meta.json, written by Nic's pipeline.publish_imagery next to hirise.jpg.
// Only the fields the app shows or checks are listed; the file carries more provenance.
export interface HiriseMeta {
  schema_version: string;
  source: string;
  output_pixels: [number, number]; // image width, height in pixels
  ground_sampling_m_ew_ns: [number, number]; // ground metres per pixel, east-west and north-south
  resampling: string; // "none_native" = every pixel is a real source pixel
  landmark_alignment: string; // not_verified | measured_within_tolerance | measured_exceeds_tolerance | insufficient_landmarks
  registration_rms_m?: number; // measured offset vs the DTM-companion orthoimage, metres
  registration_max_m?: number;
}
