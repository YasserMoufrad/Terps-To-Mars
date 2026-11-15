// Splits a crew route with drive/walk `legs` into one line per leg, so the map can
// draw the crew-rover drive differently from the walk. Routes without legs pass
// through unchanged (drawn as one walking line, as before).

import type { LegMode, RouteCollection, RouteFeature, RouteProperties } from '../data/types.ts';

// A drawn piece of a route: the route's own properties plus which leg it is.
export type DrawnRouteProperties = RouteProperties & { leg_mode?: LegMode };

export function splitRouteLegs(routes: RouteCollection): RouteCollection {
  // Purpose: return a copy of `routes` where every route with valid `legs` becomes one
  // feature per leg (coordinates from leg.from to leg.to, inclusive, so pieces touch).
  // Invalid legs (bad indexes) fall back to the whole route; the loader already warned.
  const features: RouteFeature[] = routes.features.flatMap((f) => {
    const legs = f.properties.legs;
    const coords = f.geometry.coordinates;
    const valid = Array.isArray(legs) && legs.length > 0 &&
      legs.every((l) => Number.isInteger(l.from) && Number.isInteger(l.to) && l.from >= 0 && l.to > l.from && l.to < coords.length);
    if (!valid) return [f];
    return legs.map((leg) => ({
      ...f,
      properties: { ...f.properties, leg_mode: leg.mode } as DrawnRouteProperties,
      geometry: { ...f.geometry, coordinates: coords.slice(leg.from, leg.to + 1) },
    }));
  });
  return { ...routes, features };
}

export function crewRoverParking(routes: RouteCollection): [number, number] | null {
  // Purpose: where the crew rover is left while the crew walks: the end of the last
  // drive leg of the current main crew route, as a Leaflet [lat, lon]; null if none.
  const main = routes.features.find((f) => f.properties.agent === 'crew' && f.properties.kind === 'main' && f.properties.legs?.length);
  const drive = main?.properties.legs?.filter((l) => l.mode === 'drive').at(-1);
  const point = drive ? main!.geometry.coordinates[drive.to] : undefined;
  return point ? [point[1], point[0]] : null;
}

export function legSummary(p: RouteProperties): string | null {
  // Purpose: one-line "drive X km + walk Y m" text for tooltips; null without legs.
  if (!p.legs?.length) return null;
  const sum = (mode: LegMode) => p.legs!.filter((l) => l.mode === mode).reduce((s, l) => s + l.length_m, 0);
  const drive = sum('drive'), walk = sum('walk');
  const parts = [];
  if (drive > 0) parts.push(`drive ${(drive / 1000).toFixed(2)} km`);
  if (walk > 0) parts.push(`walk ${Math.round(walk)} m`);
  return `${parts.join(' + ')} each way`;
}
