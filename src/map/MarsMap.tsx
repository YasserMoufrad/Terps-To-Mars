// The map itself: Mars basemap tiles plus our data layers for the current stage.

import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { GeoJsonObject } from 'geojson';
import { createPortal } from 'react-dom';
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Marker, Polygon, Tooltip, ImageOverlay, Pane, useMapEvents } from 'react-leaflet';
import { vehicleIcon } from './vehicleIcons';
import { appLogger } from '../lib/appLogger';
import { createTileErrorReporter, type TileCoords } from './tileErrors';
import type {
  StageId, Mission, HazardCollection, RouteCollection, CoverageCollection,
  HazardProperties, RouteProperties, CoverageProperties, LatLon, OverlayBounds, HiriseMeta, HiriseTiles,
  SlopeMeta, ScarpLines, RouteAudit,
} from '../data/types';
import { MAP_MAX_ZOOM, imageryAttribution } from './imagery';
import { ImageryControls } from './ImageryControls';
import {
  EMPTY_LOAD, applyLoadEvent, combinedState, decodedSizeMatches, registrationNote,
  type ImageryLoadState, type LayerLoad,
} from './imageryState';
import { hazardsFor, routesFor, coverageFor, highlightCoverageFor, hasLine } from './stageFilters';
import { hazardStyle, routeStyle, routeCasingStyle, coverageStyle } from './layerStyles';
import { splitRouteLegs, legSummary, crewRoverParking, type DrawnRouteProperties } from './routeLegs';
import { NIGHT_IR_RAMP, NIGHT_IR_STRETCH, nightIrStretch, type LayerVisibility } from './layers';
import { routeLabel } from './routeLabel';
import { FitToMission } from './FitToMission';
import { MapLegend, type LegendKeys, type LineKey } from './MapLegend';
import { CoordinateReadout } from './CoordinateReadout';
import { MarsScaleBar } from './MarsScaleBar';
import { MeasureButton, MeasureLayer } from './MeasureTool';
import { dronePerchLabel } from './reviewPresentation';
import { crewFaceTarget } from './scarpTarget';
import {
  DEFAULT_SCIENCE_TARGETS, activeScienceTarget, pointInspection, resolveScienceTarget, type InspectionTarget, type ScienceTargets,
} from './scienceTargets';
import { slopeAvailable, slopeDecodedState, type SlopeLoadState } from './slopeLayer';
import { SlopeLegend } from './SlopeLegend';
import { auditFor, routeRejectedForStyle } from './routeAudit';
import { readinessFor, type RouteReadiness } from './routeReadiness';
import { detectedBy } from './detectedBy';
import { RouteInspector } from '../components/RouteInspector';
import { currentEntry, nearestCell, type AuditCell, type Inspection } from './routeInspection';
import type { AnalysisResults } from '../data/analysis';

// CTX global mosaic: real tiles exist up to zoom 10 here (see docs/MAP_TILES.md).
// Its server sometimes fails a tile, so THEMIS (from Mars Trek) sits underneath:
// a missing CTX tile then shows coarser real terrain instead of a black hole.
// Both use the same grid (origin -180/90, level 0 = 2 x 1 tiles), so they line up.
const CTX_URL = 'https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer/tile/{z}/{y}/{x}';
const CTX_ATTRIBUTION = 'CTX: NASA/JPL/MSSS, Caltech Murray Lab, Esri';
const THEMIS_URL =
  'https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018/1.0.0/default/default028mm/{z}/{y}/{x}.png';
const THEMIS_ATTRIBUTION = 'THEMIS: NASA/JPL/ASU via Mars Trek';

// Real Mars color from the Viking MDIM 2.1 global color mosaic (232 m/px, via Mars Trek).
// It is coarse (tiles stop at zoom 7 here), so it is blended with CSS `mix-blend-mode:
// color`: hue and saturation come from this real color data, brightness and detail
// from the CTX tiles underneath. No invented tint. (The MGS MOC color atlas was tried
// first but is fully gray at this site.)
const VIKING_COLOR_URL =
  'https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg';
const VIKING_COLOR_ATTRIBUTION = 'Color: Viking MDIM 2.1 color mosaic, NASA/USGS via Mars Trek';

// THEMIS night-time infrared controlled mosaic (100 m/px; tiles stop at zoom 9 here, checked 2026-11-16).
// Night brightness is a relative proxy for how well the ground holds heat (firm vs loose), not a temperature.
const THEMIS_NIGHT_URL =
  'https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018/1.0.0/default/default028mm/{z}/{y}/{x}.png';
const THEMIS_NIGHT_ATTRIBUTION = 'THEMIS Night IR: NASA/JPL/ASU via Mars Trek';

const EVIDENCE_LABEL = { nasa_derived: 'NASA-derived', inferred: 'Inferred', simulated: 'Simulated' } as const;

interface MarsMapProps {
  scienceTargets?: ScienceTargets; // named scarps to inspect; the active one may be unresolved (PR #20)
  analysis?: AnalysisResults; // offline analysis reports with freshness (terrain samples, point uncertainty)
  stage: StageId;
  mission: Mission;
  hazards: HazardCollection;
  routes: RouteCollection;
  coverage: CoverageCollection;
  hiriseBounds: OverlayBounds | null;
  hiriseMeta: HiriseMeta | null;
  hiriseTiles: HiriseTiles[];
  slopeBounds: OverlayBounds | null;
  slopeMeta?: SlopeMeta | null; // legend, thresholds and grid size for slope.png
  scarpLines?: ScarpLines | null; // traced scarp edge/foot: the "Inspect scarp" target
  routeAudit?: RouteAudit | null; // measured diagnostics shown when a route is clicked
  layers: LayerVisibility;
  onSelectHazard: (hazard: HazardProperties) => void;
  onImageryState?: (state: ImageryLoadState) => void; // reports the HiRISE load state to the layer toggles
}

function toLatLng(p: LatLon): [number, number] {
  // Purpose: convert our {lat, lon} object into the [lat, lon] pair react-leaflet wants.
  return [p.lat, p.lon];
}

function toCorners(b: OverlayBounds): [[number, number], [number, number]] {
  // Purpose: image overlay corners from a bounds file, as [[south, west], [north, east]].
  return [[b.south, b.west], [b.north, b.east]];
}

function asGeoJson(data: unknown): GeoJsonObject {
  // Purpose: our collections already have GeoJSON's shape; this tells TypeScript so.
  return data as GeoJsonObject;
}

function dataUrl(file: string): string {
  // Purpose: URL of a file in public/data/; BASE_URL is "/Terps-To-Mars/" on GitHub Pages.
  return `${import.meta.env.BASE_URL}data/${file}`;
}

export function MarsMap({
  stage, mission, hazards, routes, coverage, hiriseBounds, hiriseMeta, hiriseTiles, slopeBounds, layers, onSelectHazard,
  onImageryState, slopeMeta = null, scarpLines = null, routeAudit = null, scienceTargets = DEFAULT_SCIENCE_TARGETS, analysis,
}: MarsMapProps) {
  // `hiriseTiles`: published HiRISE tile sets (context ring first, native corridor last).
  // Purpose: draw the basemap and every data layer for the current `stage`.
  // `layers` holds the user's toggles; `onSelectHazard` opens a hazard's evidence card.
  // `hiriseMeta` describes the native-resolution HiRISE image (pixel size, measured alignment).
  // `imageryLoaded` hides the loading message once the first CTX tiles arrive.
  const [imageryLoaded, setImageryLoaded] = useState(false);
  // HiRISE load tracking: per-layer counters (key = tile role or "overlay"), the retry `attempt`
  // (bumping it remounts the layers), and a decoded-size mismatch that withdraws the 4K overlay.
  const [sizeMismatch, setSizeMismatch] = useState(false);
  const showOverlay = hiriseBounds !== null && !sizeMismatch && !hiriseTiles.some((t) => t.role === 'core');
  // The single 4K overlay starts requesting its image as soon as it mounts, so it begins "pending".
  const initialLoads = (): Record<string, LayerLoad> => (showOverlay ? { overlay: { ...EMPTY_LOAD, pending: true } } : {});
  const [hdLoads, setHdLoads] = useState<Record<string, LayerLoad>>(initialLoads);
  const [attempt, setAttempt] = useState(0);
  const loggedRef = useRef('');
  const hdPublished = hiriseTiles.length > 0 || showOverlay;
  const hdState = combinedState(Object.values(hdLoads), hdPublished, layers.hirise);
  const hdEvent = (key: string, kind: 'loading' | 'load' | 'tileload' | 'error') =>
    setHdLoads((prev) => ({ ...prev, [key]: applyLoadEvent(prev[key] ?? EMPTY_LOAD, kind) }));

  // Inspection targets resolve only from published geometry, and only where native HiRISE covers them.
  const nativeCoverage = [
    ...(hiriseBounds ? [hiriseBounds] : []),
    ...hiriseTiles.filter((t) => t.role === 'core').map((t) => t.bounds),
  ];
  const targets = useMemo((): InspectionTarget[] => {
    // Catalog scarps (science_targets.json), the crew's ice face in front of the viewpoint (#17), the observation
    // point and the simulated rover incident. An unresolved active target stays visibly unresolved.
    const scarps = scienceTargets.targets.map((t) => resolveScienceTarget(t, scarpLines, nativeCoverage));
    const face = crewFaceTarget(scarpLines, mission.endpoints.observation_primary, nativeCoverage);
    const crewFace: InspectionTarget = face.target
      ? { ...pointInspection('crew-face', "Crew's ice face (second scarp)", face.target, 'scarp_lines.geojson (DTM trace)', 'inferred'), note: face.note }
      : { id: 'crew-face', name: "Crew's ice face (second scarp)", target: null, bounds: null, source: 'scarp_lines.geojson', evidence: 'inferred', note: face.note, reason: face.reason };
    return [activeScienceTarget(scienceTargets, scarps), ...scarps, crewFace,
      pointInspection('observation', 'Observation point (candidate)', mission.endpoints.observation_primary, 'mission.json', 'inferred'),
      pointInspection('discovery', 'Rover incident (simulated)', mission.discovery.location, 'mission.json', 'simulated')];
  }, [scarpLines, hiriseBounds, hiriseTiles, mission, scienceTargets]);
  useEffect(() => {
    // Log once per data load which targets resolved and why the others are disabled.
    appLogger.info('map', 'inspection_targets.resolved', {
      targets: targets.map((t) => ({ id: t.id, resolved: t.target !== null, reason: t.reason ?? null, evidence: t.evidence })),
    });
  }, [targets]);
  const [inspectedTarget, setInspectedTarget] = useState<InspectionTarget | null>(null);
  const [selection, setSelection] = useState<Inspection | null>(null);
  const [replay, setReplay] = useState('context'); // rover stage: show both routes, or only before / after
  const [measuring, setMeasuring] = useState(false); // measuring tool on: map clicks place points A and B
  const selectRoute = (id: string, point: LatLon | null = null) => {
    // Open the inspector for route `id`; `point` (a click) picks the nearest crossed native DTM cell. Only a current
    // audit whose feature snapshot matches the drawn route supplies measurements.
    const route = routes.features.find((f) => f.properties.id === id);
    if (!route) return;
    const entry = currentEntry(routeAudit, route);
    const cell = point ? nearestCell(entry?.cells ?? [], point) : null;
    setSelection({ route, cell, point, name: id, source: 'route_audit.json / routes.geojson', evidence: 'inferred; terrain NASA-derived' });
    appLogger.info('analysis', 'route.inspect', { route_id: id, audit_status: entry?.audit_status ?? 'not_current',
      segment: cell?.segment_index, coordinates: cell?.coordinates, crew_clearance: 'not_established' });
  };
  const inspectPoint = (name: string, point: LatLon, evidence = 'inferred', source = 'mission.json', purpose = name) => {
    // Open the inspector for a published point; its modeled position uncertainty comes from a current feasibility report.
    const report = analysis?.reportStates?.['feasibility_report.json'] === 'current'
      ? analysis.reports['feasibility_report.json'] as { points?: Record<string, { lonlat: number[]; uncertainty: unknown }> } : null;
    const assessed = Object.entries(report?.points ?? {}).find(([, p]) => Math.abs(p.lonlat[0] - point.lon) < 0.00003 && Math.abs(p.lonlat[1] - point.lat) < 0.00003);
    setSelection({ route: null, cell: null, point, name, source, evidence, details: { purpose,
      quality: source !== 'mission.json' ? 'Image-traced feature; ground truth not reviewed' : mission.placeholder ? 'Placeholder mission coordinate' : 'Published candidate; review status unresolved',
      uncertainty: assessed?.[1].uncertainty ?? 'Not measured', clearance: 'not_established' } });
    appLogger.info('analysis', 'node.inspect', { name, point, evidence, crew_clearance: 'not_established' });
  };
  useEffect(() => {
    // Stage navigation clears the inspection; geographic navigation never changes the stage.
    setSelection(null);
    setInspectedTarget(null);
    setReplay('context');
  }, [stage]);

  // Slope overlay: drawn only with valid bounds + metadata; the decoded PNG must have one pixel per DTM cell.
  const slopePublished = slopeAvailable(slopeBounds, slopeMeta);
  const [slopeState, setSlopeState] = useState<SlopeLoadState>(slopePublished ? 'loading' : 'unavailable');
  const [slopeOpacity, setSlopeOpacity] = useState(0.75);
  const [slopeAttempt, setSlopeAttempt] = useState(0);
  const retrySlope = () => {
    // Purpose: drop a failed slope load and request the image again (new URL, remounted overlay).
    appLogger.info('map', 'slope.retry', { attempt: slopeAttempt + 1 });
    setSlopeState('loading');
    setSlopeAttempt((a) => a + 1);
  };
  useEffect(() => {
    // Switching the layer back on after a failure retries instead of staying silently failed.
    if (layers.slope && slopeState === 'failed') retrySlope();
  }, [layers.slope]);
  const setSlope = (next: SlopeLoadState, fields: Record<string, unknown> = {}) => {
    setSlopeState(next);
    if (next === 'failed') appLogger.error('map', 'slope.load_state', { slope_state: next, ...fields });
    else appLogger.info('map', 'slope.load_state', { slope_state: next, ...fields });
  };

  // Report and log the HiRISE state once per attempt and state (pans that reload tiles do not re-log).
  useEffect(() => {
    onImageryState?.(hdState);
    const key = `${attempt}:${hdState}`;
    if (hdState === 'loading' || hdState === 'ready' || loggedRef.current === key) return;
    loggedRef.current = key;
    const fields = { imagery_state: hdState, attempt, tiles: hiriseTiles.map((t) => t.role), overlay: showOverlay };
    if (hdState === 'failed' || hdState === 'partial') appLogger.warn('map', 'imagery.load_state', fields);
    else appLogger.info('map', 'imagery.load_state', fields);
  }, [hdState, attempt]);

  const retryImagery = () => {
    // Purpose: drop the failed attempt's counters and remount the HiRISE layers.
    appLogger.info('map', 'imagery.retry', { attempt: attempt + 1 });
    setSizeMismatch(false);
    setHdLoads(hiriseBounds && !hiriseTiles.some((t) => t.role === 'core') ? { overlay: { ...EMPTY_LOAD, pending: true } } : {});
    setAttempt((a) => a + 1);
  };

  // One tile-error reporter per basemap layer, created once for the life of the map.
  const tileErrors = useMemo(
    () => ({
      themis: createTileErrorReporter(appLogger, 'themis_day_ir'),
      ctx9: createTileErrorReporter(appLogger, 'ctx_z9'),
      ctx10: createTileErrorReporter(appLogger, 'ctx_z10'),
      color: createTileErrorReporter(appLogger, 'viking_color'),
      nightIr: createTileErrorReporter(appLogger, 'themis_night_ir'),
    }),
    [],
  );
  const onTileError = (reporter: { report: (c: TileCoords) => void }) => ({
    // Leaflet's tileerror event carries the failed tile's z/x/y in `coords`.
    tileerror: (e: L.TileErrorEvent) => reporter.report(e.coords),
  });

  const visibleHazards = hazardsFor(stage, hazards);
  const visibleCoverage = coverageFor(stage, coverage, mission);
  const stageRoutes = routesFor(stage, routes, mission);
  // Routes with no line (failed searches) are reported in the side panel instead.
  // A non-"ok" route that still has a line (e.g. the unverified orbital guess) is drawn,
  // styled amber so it never looks like a cleared route.
  // Crew routes with drive/walk legs are split so the drive leg can be drawn differently.
  // Readiness per route at this stage: "go" (green) once the robots have scouted it end to end (routeReadiness).
  const readiness = useMemo((): Record<string, RouteReadiness> => readinessFor(stage, routes, routeAudit, coverage, hazards),
    [routes, stage, routeAudit, coverage, hazards]);
  useEffect(() => {
    // One safety-decision event per stage: which crew routes read as go, and why the others do not.
    appLogger.info('safety', 'route.readiness', { mission_stage: stage, evidence: 'simulated scouting', crew_clearance: 'planning_go_only',
      routes: Object.fromEntries(Object.entries(readiness).map(([id, r]) => [id, { state: r.state, reasons: r.reasons }])) });
  }, [readiness]);
  // Rover-stage replay (a static preview, no command): "before" or "after" shows only that crew route.
  const replayId = replay === 'before' ? mission.discovery.before_route_id : replay === 'after' ? mission.discovery.after_route_id : null;
  const drawnRoutes = splitRouteLegs({ ...stageRoutes, features: stageRoutes.features
    .filter((f) => stage !== 'rover' || replayId === null || f.properties.id === replayId || f.properties.kind === 'rover_path')
    .filter((f) => hasLine(f.geometry.coordinates)) });
  // During the rover stage the old crew route is shown faded next to the new one.
  const supersededId = stage === 'rover' ? mission.discovery.before_route_id : null;
  const parking = stage === 'eva' ? crewRoverParking(stageRoutes) : null;
  // Legend entries for exactly what this stage draws (same decisions as routeStyle below).
  const shownCoverage = layers.coverage ? visibleCoverage : highlightCoverageFor(stage, coverage, mission);
  const legendKeys: LegendKeys = { lines: new Set<LineKey>(), hazards: new Set(), coverage: new Set() };
  for (const f of drawnRoutes.features) {
    const p = f.properties as DrawnRouteProperties;
    const go = readiness[p.id]?.state === 'go';
    if (p.id === supersededId) legendKeys.lines.add('replaced');
    else if (routeRejectedForStyle(p, auditFor(routeAudit, p.id))) legendKeys.lines.add('rejected');
    else if (p.kind === 'orbital_guess') legendKeys.lines.add('to-scout');
    else if (p.kind === 'rover_path') legendKeys.lines.add('rover');
    else if (!go) legendKeys.lines.add(p.leg_mode === 'drive' ? 'candidate-drive' : 'candidate');
    else legendKeys.lines.add(p.leg_mode === 'drive' ? 'drive' : p.kind === 'backup' ? 'backup' : 'walk');
  }
  if (layers.hazards) for (const h of visibleHazards.features) legendKeys.hazards.add(h.properties.category === 'soft_ground' ? 'soft' : h.properties.type);
  for (const c of shownCoverage.features) if (c.properties.state !== 'orbit_only') legendKeys.coverage.add(c.properties.state);

  return (
    <div className="map-wrap">
      <MapContainer
        className="map"
        crs={L.CRS.EPSG4326} // plain lat/lon, matching the Mars tiles
        center={toLatLng(mission.site)}
        zoom={12}
        minZoom={4}
        maxZoom={MAP_MAX_ZOOM}
        attributionControl={false} // hides the bottom-right credit bar (Leaflet + tile source credits)
      >
        <FitToMission
          // Routes and endpoints only: hazard and coverage polygons (DTM-wide slope clusters) would widen the view.
          geometries={routes.features.map((f) => f.geometry.coordinates)}
          points={[mission.endpoints.habitat, mission.endpoints.observation_primary, mission.endpoints.observation_backup]}
        />
        <CoordinateReadout />
        <MarsScaleBar />
        {/* While measuring, clicks place measure points instead of opening the terrain inspector. */}
        {!measuring && <TerrainClick analysis={analysis} onSelect={setSelection} />}
        <MeasureLayer active={measuring} />

        <TileLayer
          url={THEMIS_URL}
          attribution={THEMIS_ATTRIBUTION}
          maxNativeZoom={9}
          maxZoom={MAP_MAX_ZOOM}
          eventHandlers={onTileError(tileErrors.themis)}
        />
        {/* Three layers, best on top. The CTX server sometimes fails a zoom-10 tile
            (HTTP 500); when that happens the zoom-9 CTX copy underneath shows through,
            and THEMIS is the last resort. A failed tile never leaves a black hole. */}
        <TileLayer url={CTX_URL} maxNativeZoom={9} maxZoom={MAP_MAX_ZOOM} eventHandlers={onTileError(tileErrors.ctx9)} />
        <TileLayer
          url={CTX_URL}
          attribution={CTX_ATTRIBUTION}
          maxNativeZoom={10}
          maxZoom={MAP_MAX_ZOOM}
          eventHandlers={{ load: () => setImageryLoaded(true), ...onTileError(tileErrors.ctx10) }}
        />

        {/* Real Mars color, in its own pane just above the tiles (tilePane is z-index 200,
            overlays start at 400) so it colors the basemap but never the data layers. */}
        {layers.color && (
          <Pane name="mars-color" style={{ zIndex: 250, mixBlendMode: 'color' }}>
            <TileLayer
              url={VIKING_COLOR_URL}
              attribution={VIKING_COLOR_ATTRIBUTION}
              maxNativeZoom={7}
              maxZoom={MAP_MAX_ZOOM}
              eventHandlers={onTileError(tileErrors.color)}
            />
          </Pane>
        )}

        {/* Native-resolution HiRISE (grayscale RED band), drawn only once Nic's bounds file exists.
            Its pane sits between the basemap tiles (200) and the color pane (250), so the real
            Viking color tints it exactly as it tints CTX: hue from color data, every detail from HiRISE. */}
        {/* Tiles: the ~1 m context ring (zoom 12-15) underneath, native ~0.25 m corridor (zoom 16+)
            on top; Leaflet fetches only the tiles on screen. The single 4K overlay is the fallback
            when no native core tiles are published. */}
        {layers.hirise && hdPublished && (
          <Pane name="hirise-detail" style={{ zIndex: 220 }}>
            {hiriseTiles.map((t, i) => (
              <TileLayer
                key={`${t.role}-${attempt}`}
                url={dataUrl(t.url_template)}
                bounds={[[t.bounds.south, t.bounds.west], [t.bounds.north, t.bounds.east]]}
                minZoom={t.min_zoom}
                maxNativeZoom={t.max_native_zoom}
                maxZoom={MAP_MAX_ZOOM}
                attribution={i === 0 ? imageryAttribution(hiriseMeta) : undefined}
                eventHandlers={{
                  loading: () => hdEvent(t.role, 'loading'),
                  tileload: () => hdEvent(t.role, 'tileload'),
                  tileerror: () => hdEvent(t.role, 'error'),
                  load: () => hdEvent(t.role, 'load'),
                }}
              />
            ))}
            {showOverlay && hiriseBounds && (
              <ImageOverlay
                key={`overlay-${attempt}`}
                url={dataUrl('hirise.jpg')}
                bounds={toCorners(hiriseBounds)}
                attribution={hiriseTiles.length === 0 ? imageryAttribution(hiriseMeta) : undefined}
                eventHandlers={{
                  load: (e) => {
                    // A decoded size that disagrees with hirise.meta.json means image and metadata come from
                    // different exports: withdraw the image instead of showing it with a wrong caption.
                    const img = (e.target as L.ImageOverlay).getElement();
                    const natural: [number, number] = [img?.naturalWidth ?? 0, img?.naturalHeight ?? 0];
                    if (!decodedSizeMatches(natural, hiriseMeta)) {
                      appLogger.error('map', 'imagery.size_mismatch', { decoded: natural, expected: hiriseMeta?.output_pixels });
                      setSizeMismatch(true);
                      hdEvent('overlay', 'error');
                    } else {
                      hdEvent('overlay', 'tileload');
                    }
                    hdEvent('overlay', 'load');
                  },
                  error: () => { hdEvent('overlay', 'error'); hdEvent('overlay', 'load'); },
                }}
              />
            )}
          </Pane>
        )}
        {/* Night infrared, above the HiRISE detail (220) and the color (250) but under the slope map (380) and every
            data layer, so routes and hazards stay readable on top of it. */}
        {layers.nightIr && (
          // `filter` stretches the site's brightness range and false-colors it (NightIrFilter below): display only,
          // the NASA tiles themselves are unchanged.
          <Pane name="night-ir" style={{ zIndex: 300, filter: 'url(#night-ir-ramp)' }}>
            <TileLayer
              url={THEMIS_NIGHT_URL}
              attribution={THEMIS_NIGHT_ATTRIBUTION}
              maxNativeZoom={9}
              maxZoom={MAP_MAX_ZOOM}
              opacity={0.9}
              eventHandlers={onTileError(tileErrors.nightIr)}
            />
          </Pane>
        )}
        <ImageryControls
          overview={{
            geometries: stageRoutes.features.map((f) => f.geometry.coordinates),
            points: [mission.endpoints.habitat, mission.endpoints.observation_primary],
          }}
          hiriseBounds={hiriseBounds}
          targets={targets}
          stage={stage}
          onInspect={(target) => {
            setInspectedTarget(target);
            if (target?.target) inspectPoint(target.name, target.target, target.evidence, target.source, target.note);
            else setSelection(null);
          }}
          state={sizeMismatch && hiriseTiles.length === 0 ? 'failed' : hdState}
          registration={registrationNote(hiriseMeta)}
          onRetry={retryImagery}
        />
        {/* Slope raster in its own pane under the vector overlays (overlayPane is 400), so route lines,
            hazard outlines and markers always stay on top. Toggling it never moves the map. */}
        {slopePublished && slopeBounds && slopeMeta && layers.slope && slopeState !== 'failed' && (
          <Pane name="slope" style={{ zIndex: 380 }}>
            <ImageOverlay
              key={`slope-${slopeAttempt}`}
              url={slopeAttempt ? `${dataUrl('slope.png')}?retry=${slopeAttempt}` : dataUrl('slope.png')}
              bounds={toCorners(slopeBounds)}
              opacity={slopeOpacity}
              eventHandlers={{
                load: (e) => {
                  const img = (e.target as L.ImageOverlay).getElement();
                  const natural: [number, number] = [img?.naturalWidth ?? 0, img?.naturalHeight ?? 0];
                  const next = slopeDecodedState(natural, slopeMeta);
                  setSlope(next, { decoded: natural, expected: slopeMeta.grid.pixels });
                },
                error: () => setSlope('failed', { reason: 'image_error' }),
              }}
            />
          </Pane>
        )}

        {/* `key` makes React rebuild a layer when the stage changes; Leaflet's GeoJSON
            layer does not redraw by itself when its data prop changes. */}
        {/* Coverage: everything when the toggle is on; otherwise just this stage's key zones. */}
        <GeoJSON
          key={`coverage-${stage}-${layers.coverage}`}
          data={asGeoJson(layers.coverage ? visibleCoverage : highlightCoverageFor(stage, coverage, mission))}
          style={(f) => {
            // The drone's field of view is drawn stronger than ordinary coverage so the cone reads clearly.
            const p = f?.properties as CoverageProperties;
            return p.id === mission.drone.view_cone_id ? { ...coverageStyle(p), weight: 2, fillOpacity: 0.25 } : coverageStyle(p);
          }}
          onEachFeature={(f, layer) => {
            const p = f.properties as CoverageProperties;
            const what = p.id === mission.drone.view_cone_id ? 'Drone field of view' : `Coverage: ${p.state.replace('_', ' ')}`;
            layer.bindTooltip(`${what}${p.simulated ? ' (simulated)' : ''}`);
          }}
        />

        {layers.hazards && (
          <GeoJSON
            key={`hazards-${stage}-${measuring}`}
            data={asGeoJson(visibleHazards)}
            interactive={!measuring} // while measuring, a click on a hazard places a point instead
            style={(f) => hazardStyle(f?.properties as HazardProperties)}
            onEachFeature={(f, layer) => {
              const p = f.properties as HazardProperties;
              layer.bindTooltip(
                `<strong>${p.type} · ${p.category.replace('_', ' ')}</strong> (${p.severity})<br/>` +
                  `${EVIDENCE_LABEL[p.evidence]} · detected by: ${detectedBy(p, mission)} · click for evidence`,
              );
              // Clicking a hazard opens its evidence card in the side panel (not a terrain-sample inspection).
              layer.on('click', (e: L.LeafletMouseEvent) => { L.DomEvent.stopPropagation(e.originalEvent); onSelectHazard(p); });
            }}
          />
        )}

        {/* Routes are drawn twice: a dark outline first, then the colored line on top. */}
        <GeoJSON
          key={`route-casing-${stage}-${replay}`}
          data={asGeoJson(drawnRoutes)}
          style={(f) => { const p = f?.properties as RouteProperties; return routeCasingStyle(p, supersededId, routeRejectedForStyle(p, auditFor(routeAudit, p.id)), readiness[p.id]?.state === 'go'); }}
          interactive={false}
        />
        <GeoJSON
          key={`routes-${stage}-${replay}-${measuring}`}
          data={asGeoJson(drawnRoutes)}
          interactive={!measuring} // while measuring, a click on a route places a point instead
          style={(f) => { const p = f?.properties as RouteProperties; return routeStyle(p, supersededId, routeRejectedForStyle(p, auditFor(routeAudit, p.id)), readiness[p.id]?.state === 'go'); }}
          onEachFeature={(f, layer) => {
            const p = f.properties as DrawnRouteProperties;
            const entry = auditFor(routeAudit, p.id);
            const rejected = routeRejectedForStyle(p, entry);
            const go = readiness[p.id]?.state === 'go';
            const label =
              p.id === supersededId
                ? 'Old route (replaced)'
                : p.kind === 'rover_path'
                  ? 'Scout rover path (simulated, uncrewed)'
                  : `${rejected ? 'REJECTED ' : ''}${p.agent} ${p.kind.replace('_', ' ')}${p.leg_mode ? ` (${p.leg_mode} leg)` : ''}` +
                    (go ? ' (conditional planning go after simulated scouting; crew clearance not established)'
                      : `${p.status !== 'ok' ? ` (${p.status.replace(/_/g, ' ')}${p.status_reason ? `: ${p.status_reason}` : ''})` : ''}`);
            const legs = legSummary(p);
            // Prefer measured numbers from the route audit (#18) over the file's claimed stats; otherwise show the
            // drive/walk legs and walkback from the route data. The popup explains the audit verdict.
            layer.bindTooltip(entry && entry.length_m !== undefined
              ? `${label}: measured ${(entry.length_m / 1000).toFixed(2)} km one way, steepest crossed ${entry.max_slope_deg ?? '?'}° · click for diagnostics`
              : `${label}: ${legs ?? `${(p.stats.round_trip_m / 1000).toFixed(2)} km round trip`}, ${p.stats.est_time_min} min round trip (claimed, not audited)` +
                (p.walkback_min ? `<br/>Walkback if the crew rover fails: ${p.walkback_min} min on foot` : ''));
            // Clicking opens the inspector in the side panel; the clicked native DTM cell supplies local values
            // (not the route-wide maximum).
            layer.on('click', (e: L.LeafletMouseEvent) => {
              L.DomEvent.stopPropagation(e.originalEvent);
              selectRoute(p.id, { lat: e.latlng.lat, lon: e.latlng.lng });
            });
          }}
        />

        {/* Where each drawn route first enters excluded terrain (from the audit). */}
        {/* One marker per route id (drawnRoutes splits a route into drive/walk legs). */}
        {drawnRoutes.features.filter((f, i, all) => all.findIndex((g) => g.properties.id === f.properties.id) === i).map((f) => {
          const first = auditFor(routeAudit, f.properties.id)?.first_exclusion;
          return first ? (
            <CircleMarker key={`excl-${f.properties.id}`} center={[first.lat, first.lon]} radius={6}
              pathOptions={{ color: '#0b0d10', fillColor: '#e5484d', fillOpacity: 1, weight: 2 }}>
              <Tooltip direction="top">{`First excluded crossing: ${first.kind.replace(/_/g, ' ')}, ${Math.round(first.distance_m)} m along ${routeLabel(f.properties.id)}`}</Tooltip>
            </CircleMarker>
          ) : null;
        })}

        <CircleMarker bubblingMouseEvents={false} eventHandlers={{ click: () => inspectPoint('Habitat (landing site)', mission.endpoints.habitat) }}
          center={toLatLng(mission.endpoints.habitat)} radius={8} pathOptions={{ color: '#0b0d10', fillColor: '#ffffff', fillOpacity: 1, weight: 2 }}>
          <Tooltip permanent direction="left" className="map-label">Habitat (landing site)</Tooltip>
        </CircleMarker>
        <CircleMarker bubblingMouseEvents={false} eventHandlers={{ click: () => inspectPoint('Observation primary', mission.endpoints.observation_primary) }}
          center={toLatLng(mission.endpoints.observation_primary)} radius={8} pathOptions={{ color: '#0b0d10', fillColor: '#f5a524', fillOpacity: 1, weight: 2 }}>
          {/* Amber, not green: the point is an unconfirmed candidate, not a cleared site. */}
          <Tooltip permanent direction="right" className="map-label">Observation point (candidate)</Tooltip>
        </CircleMarker>
        {mission.endpoints.observation_backup && (
          <CircleMarker bubblingMouseEvents={false} eventHandlers={{ click: () => inspectPoint('Observation backup', mission.endpoints.observation_backup!) }}
            center={toLatLng(mission.endpoints.observation_backup)} radius={6} pathOptions={{ color: '#0b0d10', fillColor: '#f5a524', fillOpacity: 0.6, weight: 2 }}>
            <Tooltip direction="right">Backup viewpoint (candidate)</Tooltip>
          </CircleMarker>
        )}

        {/* Small vehicle icons (vehicleIcons.ts): the scout rover where it stopped (red ring: hazard found), the crew
            vehicle where the astronauts park it, the drone on its perch. */}
        {stage === 'rover' && (
          <Marker icon={vehicleIcon('scout', '#e5484d')} position={toLatLng(mission.discovery.location)}
            eventHandlers={{ click: (e) => { L.DomEvent.stopPropagation(e.originalEvent); inspectPoint('Rover incident', mission.discovery.location, 'simulated'); } }}>
            <Tooltip permanent direction="left" offset={[-16, 0]} className="map-label">Scout rover stopped (simulated): soft ground</Tooltip>
          </Marker>
        )}

        {parking && (
          <Marker icon={vehicleIcon('crew')} position={parking}>
            <Tooltip permanent direction="right" offset={[16, 0]} className="map-label">Crew vehicle parks here; walk the rest</Tooltip>
          </Marker>
        )}

        {(stage === 'drone' || stage === 'eva') && (
          <Marker icon={vehicleIcon('drone')} position={toLatLng(mission.drone.perch)}
            eventHandlers={{ click: (e) => { L.DomEvent.stopPropagation(e.originalEvent); inspectPoint('Drone perch', mission.drone.perch, 'simulated'); } }}>
            {/* "top": the perch is only ~50 m from the observation point, whose label sits to the right. */}
            <Tooltip permanent direction="top" offset={[0, -16]} className="map-label">{dronePerchLabel(coverage, mission)}</Tooltip>
          </Marker>
        )}

        {/* Modeled 15 m position uncertainty of each assessed point (current feasibility report only). */}
        {analysis?.reportStates?.['feasibility_report.json'] === 'current'
          && Object.entries((analysis.reports['feasibility_report.json'] as { points?: Record<string, { lonlat: [number, number]; uncertainty: { radius_m: number } }> })?.points ?? {})
            .map(([id, p]) => (
              <Polygon bubblingMouseEvents={false} key={`uncertainty-${id}`} positions={uncertaintyRing(p.lonlat, p.uncertainty.radius_m)}
                pathOptions={{ color: '#d6b5ff', weight: 1, dashArray: '3 3', fillOpacity: 0.08 }}
                eventHandlers={{ click: () => inspectPoint(id, { lon: p.lonlat[0], lat: p.lonlat[1] }) }}>
                <Tooltip>{id}: {p.uncertainty.radius_m} m modeled position uncertainty</Tooltip>
              </Polygon>
            ))}
        {/* The inspected target's own geometry and a ring at its focus; the selected route and clicked cell. */}
        {inspectedTarget?.geometry && <GeoJSON key={`target-${inspectedTarget.id}`} data={asGeoJson(inspectedTarget.geometry)}
          style={{ color: '#62ddff', weight: 5, opacity: 0.95 }} interactive={false} />}
        {inspectedTarget?.target && (
          <CircleMarker bubblingMouseEvents={false} center={toLatLng(inspectedTarget.target)} radius={14} pathOptions={{ color: '#62ddff', weight: 3, fillOpacity: 0 }}>
            <Tooltip permanent>{inspectedTarget.name}</Tooltip>
          </CircleMarker>
        )}
        {selection?.route && <GeoJSON key={`selected-${selection.route.properties.id}`} data={asGeoJson(selection.route)}
          style={{ color: '#ffffff', weight: 7, opacity: 0.6 }} interactive={false} />}
        {selection?.cell && <CircleMarker bubblingMouseEvents={false} center={[selection.cell.coordinates[1], selection.cell.coordinates[0]]} radius={7}
          pathOptions={{ color: '#ffffff', fillColor: '#ff642f', fillOpacity: 1 }} />}
      </MapContainer>

      {/* Route picker (works without hitting a thin line) and, in the rover stage, the static before/after replay. */}
      <div className="route-selector">
        <label>Inspect route{' '}
          <select aria-label="Inspect route" value={selection?.route?.properties.id ?? ''}
            onChange={(e) => (e.target.value ? selectRoute(e.target.value) : setSelection(null))}>
            <option value="">Select a route</option>
            {routes.features.map((f) => <option key={f.properties.id} value={f.properties.id}>{routeLabel(f.properties.id)}</option>)}
          </select>
        </label>
        {stage === 'rover' && (
          <label>Replay{' '}
            <select aria-label="Static replay" value={replay} onChange={(e) => {
              setReplay(e.target.value);
              appLogger.info('simulation', 'replay.view', { view: e.target.value, evidence: 'simulated', human_approval: 'not_granted', live_control: false });
            }}>
              <option value="context">Before and after</option>
              <option value="before">Before the incident</option>
              <option value="after">After the reroute</option>
            </select>
            <span>Preview only · no command or crew approval</span>
          </label>
        )}
      </div>
      {selection && typeof document !== 'undefined' && document.getElementById('analysis-inspector-slot')
        && createPortal(<RouteInspector selection={selection} audit={routeAudit} onClose={() => setSelection(null)} />, document.getElementById('analysis-inspector-slot')!)}

      <NightIrFilter />
      <MeasureButton active={measuring} onToggle={() => {
        appLogger.info('ui', 'measure.toggle', { on: !measuring });
        setMeasuring((m) => !m);
      }} />
      <MapLegend keys={legendKeys} />
      {layers.slope && slopeMeta && slopePublished && <SlopeLegend meta={slopeMeta} state={slopeState} opacity={slopeOpacity} onOpacity={setSlopeOpacity} onRetry={retrySlope} />}
      {!imageryLoaded && <div className="map-loading">Loading Mars imagery…</div>}
    </div>
  );
}

function TerrainClick({ analysis, onSelect }: { analysis: AnalysisResults | undefined; onSelect: (selection: Inspection) => void }) {
  // Purpose: a click on open terrain opens the nearest sparse native-cell sample from a current terrain_samples.json,
  // with its actual position and offset; values are never interpolated. Outside coverage says so.
  useMapEvents({ click: (e) => {
    const point = { lat: e.latlng.lat, lon: e.latlng.lng };
    type Sample = [number, number, number | null, number | null, number | null, string, number, number];
    const report = analysis?.reportStates?.['terrain_samples.json'] === 'current'
      ? analysis.reports['terrain_samples.json'] as { samples?: Sample[]; stride_cells: number; bounds: { west: number; east: number; south: number; north: number } } : null;
    const b = report?.bounds;
    const inside = Boolean(b && point.lon >= b.west && point.lon <= b.east && point.lat >= b.south && point.lat <= b.north);
    const limit = (analysis?.reports['analysis_rules.json'] as { rules?: { crew_exclude_deg?: { value: number } } } | undefined)?.rules?.crew_exclude_deg?.value ?? 20;
    const cells: AuditCell[] = inside ? (report?.samples ?? []).map(([lon, lat, elevation, slope, roughness_m, quality, col, row]) => ({
      coordinates: [lon, lat], elevation, slope, roughness_m, known: quality === 'valid_unreviewed', inside: true, col, row,
      segment_index: -1, distance_m: 0, limit, mode: 'walk',
    })) : [];
    onSelect({ point, route: null, cell: nearestCell(cells, point), name: 'Terrain sample',
      source: inside ? `terrain_samples.json (sparse; every ${report?.stride_cells} native cells)` : 'Outside published numeric coverage',
      evidence: 'nasa_derived; artifact review unavailable' });
    appLogger.info('analysis', 'terrain.inspect', { point, inside, state: analysis?.state });
  } });
  return null;
}

function NightIrFilter() {
  // Purpose: the SVG filter the night-IR pane uses: first a linear stretch so the site's 2nd-98th percentile brightness
  // (NIGHT_IR_STRETCH) fills 0..1, then a lookup table that maps that gray to the blue (loose) → orange (firm) ramp.
  const { slope, intercept } = nightIrStretch(NIGHT_IR_STRETCH.low, NIGHT_IR_STRETCH.high);
  const table = (i: 0 | 1 | 2) => NIGHT_IR_RAMP.map((c) => c[i]).join(' ');
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      <filter id="night-ir-ramp" colorInterpolationFilters="sRGB">
        <feComponentTransfer>
          <feFuncR type="linear" slope={slope} intercept={intercept} />
          <feFuncG type="linear" slope={slope} intercept={intercept} />
          <feFuncB type="linear" slope={slope} intercept={intercept} />
        </feComponentTransfer>
        <feComponentTransfer>
          <feFuncR type="table" tableValues={table(0)} />
          <feFuncG type="table" tableValues={table(1)} />
          <feFuncB type="table" tableValues={table(2)} />
        </feComponentTransfer>
      </filter>
    </svg>
  );
}

function uncertaintyRing(point: [number, number], radius: number): [number, number][] {
  // Purpose: polygon ring [lat, lon] of `radius` Mars ground metres around [lon, lat] (not Leaflet's Earth-metre circle).
  const dy = (radius / 3389500) * (180 / Math.PI);
  const dx = dy / Math.cos((point[1] * Math.PI) / 180);
  return Array.from({ length: 48 }, (_, i) => [point[1] + dy * Math.sin((i * Math.PI) / 24), point[0] + dx * Math.cos((i * Math.PI) / 24)]);
}
