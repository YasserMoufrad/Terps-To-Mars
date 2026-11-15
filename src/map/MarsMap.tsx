// The map itself: Mars basemap tiles plus our data layers for the current stage.

import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { GeoJsonObject } from 'geojson';
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip, ImageOverlay, Pane } from 'react-leaflet';
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
import { hazardsFor, routesFor, coverageFor, hasLine } from './stageFilters';
import { hazardStyle, routeStyle, routeCasingStyle, coverageStyle } from './layerStyles';
import type { LayerVisibility } from './layers';
import { FitToMission } from './FitToMission';
import { MapLegend } from './MapLegend';
import { dronePerchLabel } from './reviewPresentation';
import { DEFAULT_SCIENCE_TARGETS, activeScienceTarget, resolveScienceTarget, pointInspection, type InspectionTarget } from './scienceTargets';
import { slopeAvailable, slopeDecodedState, type SlopeLoadState } from './slopeLayer';
import { SlopeLegend } from './SlopeLegend';
import { auditFor, diagnosticHtml } from './routeAudit';

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

const EVIDENCE_LABEL = { nasa_derived: 'NASA-derived', inferred: 'Inferred', simulated: 'Simulated' } as const;

interface MarsMapProps {
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
  onImageryState, slopeMeta = null, scarpLines = null, routeAudit = null,
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

  // "Inspect scarp" goes to the traced scarp face, and only if native HiRISE covers it.
  const nativeCoverage = [
    ...(hiriseBounds ? [hiriseBounds] : []),
    ...hiriseTiles.filter((t) => t.role === 'core').map((t) => t.bounds),
  ];
  const targets = useMemo(() => {
    // Catalog entries reference published geometry only; unresolved science selection stays visible.
    const scarps = DEFAULT_SCIENCE_TARGETS.targets.map(t => resolveScienceTarget(t, scarpLines, nativeCoverage));
    return [activeScienceTarget(DEFAULT_SCIENCE_TARGETS, scarps), ...scarps,
      pointInspection('observation', 'Observation point (candidate)', mission.endpoints.observation_primary, 'mission.json', 'inferred'),
      pointInspection('discovery', 'Rover incident (simulated)', mission.discovery.location, 'mission.json', 'simulated')];
  }, [scarpLines, hiriseBounds, hiriseTiles, mission]);
  const [inspectedTarget, setInspectedTarget] = useState<InspectionTarget | null>(null);
  const [slopeOpacity, setSlopeOpacity] = useState(0.45);

  // Slope overlay: drawn only with valid bounds + metadata; the decoded PNG must have one pixel per DTM cell.
  const slopePublished = slopeAvailable(slopeBounds, slopeMeta);
  const [slopeState, setSlopeState] = useState<SlopeLoadState>(slopePublished ? 'loading' : 'unavailable');
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
  const drawnRoutes = { ...stageRoutes, features: stageRoutes.features.filter((f) => hasLine(f.geometry.coordinates)) };
  // During the rover stage the old crew route is shown faded next to the new one.
  const supersededId = stage === 'rover' ? mission.discovery.before_route_id : null;

  return (
    <div className="map-wrap">
      <MapContainer
        className="map"
        crs={L.CRS.EPSG4326} // plain lat/lon, matching the Mars tiles
        center={toLatLng(mission.site)}
        zoom={12}
        minZoom={4}
        maxZoom={MAP_MAX_ZOOM}
      >
        <FitToMission
          geometries={[...routes.features, ...hazards.features].map((f) => f.geometry.coordinates)}
          points={[mission.endpoints.habitat, mission.endpoints.observation_primary]}
        />

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
        <ImageryControls
          overview={{
            geometries: [...stageRoutes.features, ...visibleHazards.features].map((f) => f.geometry.coordinates),
            points: [mission.endpoints.habitat, mission.endpoints.observation_primary],
          }}
          hiriseBounds={hiriseBounds}
          targets={targets}
          stage={stage}
          onInspect={setInspectedTarget}
          slopeOpacity={slopeOpacity}
          onOpacity={setSlopeOpacity}
          state={sizeMismatch && hiriseTiles.length === 0 ? 'failed' : hdState}
          registration={registrationNote(hiriseMeta)}
          onRetry={retryImagery}
        />
        {/* Slope raster in its own pane under the vector overlays (overlayPane is 400), so route lines,
            hazard outlines and markers always stay on top. Toggling it never moves the map. */}
        {slopePublished && slopeBounds && slopeMeta && layers.slope && slopeState !== 'failed' && (
          <Pane name="slope" style={{ zIndex: 380 }}>
            <ImageOverlay
              url={dataUrl('slope.png')}
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
        {layers.coverage && (
          <GeoJSON
            key={`coverage-${stage}`}
            data={asGeoJson(visibleCoverage)}
            style={(f) => coverageStyle(f?.properties as CoverageProperties)}
            onEachFeature={(f, layer) => {
              const p = f.properties as CoverageProperties;
              layer.bindTooltip(`Coverage: ${p.state.replace('_', ' ')}${p.simulated ? ' (simulated)' : ''}`);
            }}
          />
        )}

        {layers.hazards && (
          <GeoJSON
            key={`hazards-${stage}`}
            data={asGeoJson(visibleHazards)}
            style={(f) => hazardStyle(f?.properties as HazardProperties)}
            onEachFeature={(f, layer) => {
              const p = f.properties as HazardProperties;
              layer.bindTooltip(
                `<strong>${p.type} · ${p.category.replace('_', ' ')}</strong> (${p.severity})<br/>` +
                  `${EVIDENCE_LABEL[p.evidence]} · click for evidence`,
              );
              // Clicking a hazard opens its evidence card in the side panel.
              layer.on('click', () => onSelectHazard(p));
            }}
          />
        )}

        {/* Routes are drawn twice: a dark outline first, then the colored line on top. */}
        <GeoJSON
          key={`route-casing-${stage}`}
          data={asGeoJson(drawnRoutes)}
          style={(f) => routeCasingStyle(f?.properties as RouteProperties, supersededId)}
          interactive={false}
        />
        <GeoJSON
          key={`routes-${stage}`}
          data={asGeoJson(drawnRoutes)}
          style={(f) => routeStyle(f?.properties as RouteProperties, supersededId)}
          onEachFeature={(f, layer) => {
            const p = f.properties as RouteProperties;
            const label =
              p.id === supersededId
                ? 'Old route (replaced)'
                : `${p.agent} ${p.kind.replace('_', ' ')}${p.status !== 'ok' ? ` (${p.status.replace(/_/g, ' ')})` : ''}`;
            const entry = auditFor(routeAudit, p.id);
            // Prefer measured numbers over the file's claimed stats; the popup explains the verdict.
            layer.bindTooltip(entry && entry.length_m !== undefined
              ? `${label}: measured ${(entry.length_m / 1000).toFixed(2)} km one way, steepest crossed ${entry.max_slope_deg ?? '?'}° · click for diagnostics`
              : `${label}: ${(p.stats.round_trip_m / 1000).toFixed(2)} km round trip (claimed, not audited)`);
            layer.bindPopup(diagnosticHtml(p, entry, routeAudit), { maxWidth: 320 });
          }}
        />

        <CircleMarker center={toLatLng(mission.endpoints.habitat)} radius={8} pathOptions={{ color: '#0b0d10', fillColor: '#ffffff', fillOpacity: 1, weight: 2 }}>
          <Tooltip permanent direction="left" className="map-label">Habitat</Tooltip>
        </CircleMarker>
        <CircleMarker center={toLatLng(mission.endpoints.observation_primary)} radius={8} pathOptions={{ color: '#0b0d10', fillColor: '#f5a524', fillOpacity: 1, weight: 2 }}>
          {/* Amber, not green: the point is an unconfirmed candidate, not a cleared site. */}
          <Tooltip permanent direction="right" className="map-label">Observation point (candidate)</Tooltip>
        </CircleMarker>

        {stage === 'rover' && (
          <CircleMarker center={toLatLng(mission.discovery.location)} radius={9} pathOptions={{ color: '#0b0d10', fillColor: '#e5484d', fillOpacity: 1, weight: 2 }}>
            <Tooltip permanent direction="left" className="map-label">Rover stopped (simulated): soft ground?</Tooltip>
          </CircleMarker>
        )}

        {stage === 'eva' && (
          <CircleMarker center={toLatLng(mission.drone.perch)} radius={7} pathOptions={{ color: '#0b0d10', fillColor: '#4da3ff', fillOpacity: 1, weight: 2 }}>
            <Tooltip permanent direction="right" className="map-label">{dronePerchLabel(coverage, mission)}</Tooltip>
          </CircleMarker>
        )}
        {inspectedTarget?.geometry && <GeoJSON key={inspectedTarget.id} data={asGeoJson(inspectedTarget.geometry)}
          style={{color:'#62ddff',weight:5,opacity:0.95}} interactive={false}/>}
        {inspectedTarget?.target && <CircleMarker center={toLatLng(inspectedTarget.target)} radius={14}
          pathOptions={{color:'#62ddff',weight:3,fillOpacity:0}}><Tooltip permanent>{inspectedTarget.name}</Tooltip></CircleMarker>}
      </MapContainer>

      <MapLegend />
      {layers.slope && slopeMeta && slopePublished && <SlopeLegend meta={slopeMeta} state={slopeState} />}
      {!imageryLoaded && <div className="map-loading">Loading Mars imagery…</div>}
    </div>
  );
}
