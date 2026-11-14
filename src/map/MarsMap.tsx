// The map itself: Mars basemap tiles plus our data layers for the current stage.

import { useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { GeoJsonObject } from 'geojson';
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip, ImageOverlay } from 'react-leaflet';
import type {
  StageId, Mission, HazardCollection, RouteCollection, CoverageCollection,
  HazardProperties, RouteProperties, CoverageProperties, LatLon, OverlayBounds,
} from '../data/types';
import { hazardsFor, routesFor, coverageFor } from './stageFilters';
import { hazardStyle, routeStyle, routeCasingStyle, coverageStyle } from './layerStyles';
import type { LayerVisibility } from './layers';
import { FitToMission } from './FitToMission';
import { MapLegend } from './MapLegend';

// CTX global mosaic: real tiles exist up to zoom 10 here (see docs/MAP_TILES.md).
// Its server sometimes fails a tile, so THEMIS (from Mars Trek) sits underneath:
// a missing CTX tile then shows coarser real terrain instead of a black hole.
// Both use the same grid (origin -180/90, level 0 = 2 x 1 tiles), so they line up.
const CTX_URL = 'https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer/tile/{z}/{y}/{x}';
const CTX_ATTRIBUTION = 'CTX: NASA/JPL/MSSS, Caltech Murray Lab, Esri';
const THEMIS_URL =
  'https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018/1.0.0/default/default028mm/{z}/{y}/{x}.png';
const THEMIS_ATTRIBUTION = 'THEMIS: NASA/JPL/ASU via Mars Trek';

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

// react-leaflet wants positions as [lat, lon].
const toLatLng = (p: LatLon): [number, number] => [p.lat, p.lon];

// Image overlays are placed by their south-west and north-east corners.
const toCorners = (b: OverlayBounds): [[number, number], [number, number]] => [[b.south, b.west], [b.north, b.east]];

// Our collections have the right shape for GeoJSON; this tells TypeScript so.
const asGeoJson = (data: unknown) => data as GeoJsonObject;

// Overlay images live next to the JSON files; BASE_URL is "/Terps-To-Mars/" on GitHub Pages.
const dataUrl = (file: string) => `${import.meta.env.BASE_URL}data/${file}`;

export function MarsMap({
  stage, mission, hazards, routes, coverage, hiriseBounds, slopeBounds, layers, onSelectHazard,
}: MarsMapProps) {
  const [imageryLoaded, setImageryLoaded] = useState(false);

  const visibleHazards = hazardsFor(stage, hazards);
  const visibleCoverage = coverageFor(stage, coverage, mission);
  const stageRoutes = routesFor(stage, routes, mission);
  // Failed routes (no_viable_route, backup_unavailable...) have no line to draw;
  // the side panel reports them instead.
  const drawnRoutes = { ...stageRoutes, features: stageRoutes.features.filter((f) => f.properties.status === 'ok') };
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
        maxZoom={15}
      >
        <FitToMission
          geometries={[...routes.features, ...hazards.features].map((f) => f.geometry.coordinates)}
          points={[mission.endpoints.habitat, mission.endpoints.observation_primary]}
        />

        <TileLayer url={THEMIS_URL} attribution={THEMIS_ATTRIBUTION} maxNativeZoom={9} maxZoom={15} />
        {/* Three layers, best on top. The CTX server sometimes fails a zoom-10 tile
            (HTTP 500); when that happens the zoom-9 CTX copy underneath shows through,
            and THEMIS is the last resort. A failed tile never leaves a black hole. */}
        <TileLayer url={CTX_URL} maxNativeZoom={9} maxZoom={15} />
        <TileLayer
          url={CTX_URL}
          attribution={CTX_ATTRIBUTION}
          maxNativeZoom={10}
          maxZoom={15}
          eventHandlers={{ load: () => setImageryLoaded(true) }}
        />

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
            const p = f.properties as RouteProperties;
            const label = p.id === supersededId ? 'Old route (replaced)' : `${p.agent} ${p.kind.replace('_', ' ')}`;
            layer.bindTooltip(`${label}: ${(p.stats.round_trip_m / 1000).toFixed(2)} km round trip, steepest ${p.stats.max_slope_deg}°`);
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
            <Tooltip permanent direction="left" className="map-label">Rover stopped: soft ground</Tooltip>
          </CircleMarker>
        )}

        {stage === 'eva' && (
          <CircleMarker center={toLatLng(mission.drone.perch)} radius={7} pathOptions={{ color: '#0b0d10', fillColor: '#4da3ff', fillOpacity: 1, weight: 2 }}>
            <Tooltip permanent direction="right" className="map-label">Drone watching the cliff</Tooltip>
          </CircleMarker>
        )}
      </MapContainer>

      <MapLegend />
      {!imageryLoaded && <div className="map-loading">Loading Mars imagery…</div>}
    </div>
  );
}
