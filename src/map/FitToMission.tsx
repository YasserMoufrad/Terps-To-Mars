// Zooms the map so the whole mission area fills the screen, once, when it loads.
// It must sit inside <MapContainer> because useMap() only works there.

import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import type { LatLon } from '../data/types';

// Every [lon, lat] position in the data, however deeply nested in the geometry.
function collectPositions(value: unknown, out: [number, number][]): void {
  if (Array.isArray(value) && value.length === 2 && typeof value[0] === 'number' && typeof value[1] === 'number') {
    out.push([value[1], value[0]]); // GeoJSON [lon, lat] -> Leaflet [lat, lon]
  } else if (Array.isArray(value)) {
    for (const child of value) collectPositions(child, out);
  }
}

interface FitToMissionProps {
  geometries: unknown[]; // geometry.coordinates from routes and hazards
  points: LatLon[]; // habitat, observation points
}

export function FitToMission({ geometries, points }: FitToMissionProps) {
  const map = useMap();

  useEffect(() => {
    const positions: [number, number][] = points.map((p) => [p.lat, p.lon]);
    for (const g of geometries) collectPositions(g, positions);
    if (positions.length > 1) map.fitBounds(positions, { padding: [40, 40] });
    // Depends only on `map`, so it runs once on load: re-fitting on every
    // stage change would make the view jump while the viewer is reading.
  }, [map]);

  return null;
}
