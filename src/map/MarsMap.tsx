// The map itself: Mars basemap tiles plus our data layers for the current stage.

import { useMemo, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { GeoJsonObject } from 'geojson';
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip, ImageOverlay, Pane } from 'react-leaflet';
import { appLogger } from '../lib/appLogger';
import { createTileErrorReporter, type TileCoords } from './tileErrors';
import type {
  StageId, Mission, HazardCollection, RouteCollection, CoverageCollection,
  HazardProperties, RouteProperties, CoverageProperties, LatLon, OverlayBounds,
} from '../data/types';
import { hazardsFor, routesFor, coverageFor, hasLine } from './stageFilters';
import { hazardStyle, routeStyle, routeCasingStyle, coverageStyle, DRIVE_COLOR } from './layerStyles';
import { splitRouteLegs, legSummary, crewRoverParking, type DrawnRouteProperties } from './routeLegs';
import type { LayerVisibility } from './layers';
import { FitToMission } from './FitToMission';
import { MapLegend } from './MapLegend';
import { dronePerchLabel } from './reviewPresentation';

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
  slopeBounds: OverlayBounds | null;
  layers: LayerVisibility;
  onSelectHazard: (hazard: HazardProperties) => void;
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
  stage, mission, hazards, routes, coverage, hiriseBounds, slopeBounds, layers, onSelectHazard,
}: MarsMapProps) {
  // Purpose: draw the basemap and every data layer for the current `stage`.
  // `layers` holds the user's toggles; `onSelectHazard` opens a hazard's evidence card.
  // `imageryLoaded` hides the loading message once the first CTX tiles arrive.
  const [imageryLoaded, setImageryLoaded] = useState(false);

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
  // Crew routes with drive/walk legs are split so the drive leg can be drawn differently.
  const drawnRoutes = splitRouteLegs({ ...stageRoutes, features: stageRoutes.features.filter((f) => hasLine(f.geometry.coordinates)) });
  // During the rover stage the old crew route is shown faded next to the new one.
  const supersededId = stage === 'rover' ? mission.discovery.before_route_id : null;
  const parking = stage === 'eva' ? crewRoverParking(stageRoutes) : null;

  return (
    <div className="map-wrap">
      <MapContainer
        className="map"
        crs={L.CRS.EPSG4326} // plain lat/lon, matching the Mars tiles
        center={toLatLng(mission.site)}
        zoom={12}
        minZoom={4}
        maxZoom={15}
      >
        <FitToMission
          geometries={[...routes.features, ...hazards.features].map((f) => f.geometry.coordinates)}
          points={[mission.endpoints.habitat, mission.endpoints.observation_primary]}
        />

        <TileLayer
          url={THEMIS_URL}
          attribution={THEMIS_ATTRIBUTION}
          maxNativeZoom={9}
          maxZoom={15}
          eventHandlers={onTileError(tileErrors.themis)}
        />
        {/* Three layers, best on top. The CTX server sometimes fails a zoom-10 tile
            (HTTP 500); when that happens the zoom-9 CTX copy underneath shows through,
            and THEMIS is the last resort. A failed tile never leaves a black hole. */}
        <TileLayer url={CTX_URL} maxNativeZoom={9} maxZoom={15} eventHandlers={onTileError(tileErrors.ctx9)} />
        <TileLayer
          url={CTX_URL}
          attribution={CTX_ATTRIBUTION}
          maxNativeZoom={10}
          maxZoom={15}
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
              maxZoom={15}
              eventHandlers={onTileError(tileErrors.color)}
            />
          </Pane>
        )}

        {/* Pipeline images: drawn only once Nic's bounds files exist and the toggle is on. */}
        {hiriseBounds && layers.hirise && (
          <ImageOverlay url={dataUrl('hirise.jpg')} bounds={toCorners(hiriseBounds)} attribution="HiRISE: NASA/JPL-Caltech/UArizona" />
        )}
        {slopeBounds && layers.slope && (
          <ImageOverlay url={dataUrl('slope.png')} bounds={toCorners(slopeBounds)} opacity={0.6} />
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
            const p = f.properties as DrawnRouteProperties;
            const label =
              p.id === supersededId
                ? 'Old route (replaced)'
                : `${p.agent} ${p.kind.replace('_', ' ')}${p.leg_mode ? ` (${p.leg_mode} leg)` : ''}${p.status !== 'ok' ? ` (${p.status.replace(/_/g, ' ')})` : ''}`;
            const legs = legSummary(p);
            layer.bindTooltip(
              `${label}: ${legs ?? `${(p.stats.round_trip_m / 1000).toFixed(2)} km round trip`}, ` +
                `${p.stats.est_time_min} min round trip, steepest ${p.stats.max_slope_deg}°` +
                (p.walkback_min ? `<br/>Walkback if the crew rover fails: ${p.walkback_min} min on foot` : ''),
            );
          }}
        />

        <CircleMarker center={toLatLng(mission.endpoints.habitat)} radius={8} pathOptions={{ color: '#0b0d10', fillColor: '#ffffff', fillOpacity: 1, weight: 2 }}>
          <Tooltip permanent direction="left" className="map-label">Habitat</Tooltip>
        </CircleMarker>
        <CircleMarker center={toLatLng(mission.endpoints.observation_primary)} radius={8} pathOptions={{ color: '#0b0d10', fillColor: '#3ddc97', fillOpacity: 1, weight: 2 }}>
          <Tooltip permanent direction="right" className="map-label">Observation point</Tooltip>
        </CircleMarker>

        {stage === 'rover' && (
          <CircleMarker center={toLatLng(mission.discovery.location)} radius={9} pathOptions={{ color: '#0b0d10', fillColor: '#e5484d', fillOpacity: 1, weight: 2 }}>
            <Tooltip permanent direction="left" className="map-label">Rover stopped (simulated): soft ground?</Tooltip>
          </CircleMarker>
        )}

        {parking && (
          <CircleMarker center={parking} radius={7} pathOptions={{ color: '#0b0d10', fillColor: DRIVE_COLOR, fillOpacity: 1, weight: 2 }}>
            <Tooltip permanent direction="right" className="map-label">Crew rover parks (proposed)</Tooltip>
          </CircleMarker>
        )}

        {stage === 'eva' && (
          <CircleMarker center={toLatLng(mission.drone.perch)} radius={7} pathOptions={{ color: '#0b0d10', fillColor: '#4da3ff', fillOpacity: 1, weight: 2 }}>
            {/* "top": the perch is only ~50 m from the observation point, whose label sits to the right. */}
            <Tooltip permanent direction="top" offset={[0, -8]} className="map-label">{dronePerchLabel(coverage, mission)}</Tooltip>
          </CircleMarker>
        )}
      </MapContainer>

      <MapLegend />
      {!imageryLoaded && <div className="map-loading">Loading Mars imagery…</div>}
    </div>
  );
}
