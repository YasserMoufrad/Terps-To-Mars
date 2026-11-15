// Coordinate text for the map's cursor readout. Pure functions so the Node test runner can check them.

export interface LatLonPoint { lat: number; lon: number }

export function wrapLon(lon: number): number {
  // Purpose: Leaflet reports longitudes past ±180 after panning across the date line; return −180..180.
  // In-range values are returned unchanged (the modulo arithmetic would add floating-point drift).
  if (lon >= -180 && lon <= 180) return lon;
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

export function formatLatLon(p: LatLonPoint, digits = 5): string {
  // Purpose: "54.15000°N, −147.90700° (212.09300°E)": signed −180..180 longitude as the repo uses it, plus the
  // 0..360 east form HiRISE labels use. `digits` = decimal places (5 ≈ 0.6 m of latitude on Mars).
  const lon = wrapLon(p.lon);
  const ns = p.lat >= 0 ? 'N' : 'S';
  const east = (lon + 360) % 360;
  const signed = `${lon < 0 ? '−' : ''}${Math.abs(lon).toFixed(digits)}°`;
  return `${Math.abs(p.lat).toFixed(digits)}°${ns}, ${signed} (${east.toFixed(digits)}°E)`;
}

export const MARS_RADIUS_M = 3389500; // mean radius; never Leaflet's Earth radius

export function marsDistanceM(a: LatLonPoint, b: LatLonPoint): number {
  // Purpose: great-circle metres between two points on the Mars sphere (haversine).
  const r = Math.PI / 180;
  const h = Math.sin(((b.lat - a.lat) * r) / 2) ** 2
    + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
  return 2 * MARS_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export const WALK_M_PER_MIN = 20; // the EVA planning walking pace (same as the time budget)

export function measureText(a: LatLonPoint, b: LatLonPoint): { metres: number; distance: string; walk: string } {
  // Purpose: the measuring tool's label for points `a` → `b`: Mars great-circle distance ("412 m" / "1.23 km") and
  // the straight-line walking time at the planning pace. Straight line over the sphere: not a route, ignores slope.
  const metres = marsDistanceM(a, b);
  const distance = metres >= 1000 ? `${(metres / 1000).toFixed(2)} km` : `${Math.round(metres)} m`;
  const minutes = metres / WALK_M_PER_MIN;
  const walk = minutes < 1 ? 'under 1 min walk' : `about ${Math.round(minutes)} min walk`;
  return { metres, distance, walk };
}

export function niceScale(metresPerPixel: number, maxPx = 110): { metres: number; px: number; label: string } {
  // Purpose: the largest "round" length (1, 2 or 5 x 10^n m) that fits in `maxPx` pixels at `metresPerPixel`,
  // with its bar width in pixels and a label in m or km.
  const maxM = metresPerPixel * maxPx;
  const pow = 10 ** Math.floor(Math.log10(maxM));
  const metres = [5, 2, 1].map((k) => k * pow).find((m) => m <= maxM) ?? pow;
  return { metres, px: Math.round(metres / metresPerPixel), label: metres >= 1000 ? `${metres / 1000} km` : `${metres} m` };
}

export function copyText(p: LatLonPoint, digits = 5): string {
  // Purpose: plain "lat, lon" (signed, −180..180) for pasting into chat, configs or the {"lat","lon"} JSON.
  return `${p.lat.toFixed(digits)}, ${wrapLon(p.lon).toFixed(digits)}`;
}
