// Tiny map icons for the three machines in the story, drawn as inline SVG (no image files, no outside assets):
// the uncrewed scout rover (six wheels, camera mast), the crew vehicle (open two-seat rover the astronauts drive),
// and the quadcopter drone. Each sits on a dark disc so it reads on bright or dark terrain.

import L from 'leaflet';

export type Vehicle = 'scout' | 'crew' | 'drone';

const SVG: Record<Vehicle, string> = {
  // Scout rover: body, six wheels, mast with a camera head.
  scout: `<rect x="7" y="13" width="18" height="6" rx="1.5" fill="#e8eef5"/>
    <rect x="15" y="6" width="2" height="7" fill="#e8eef5"/><rect x="12.5" y="4" width="7" height="3.5" rx="1" fill="#e8eef5"/>
    <circle cx="9" cy="22" r="2.6" fill="#e8eef5"/><circle cx="16" cy="22" r="2.6" fill="#e8eef5"/><circle cx="23" cy="22" r="2.6" fill="#e8eef5"/>`,
  // Crew vehicle: low open chassis, two seats, two large wheels.
  crew: `<rect x="5" y="14" width="22" height="4" rx="1.5" fill="#7cc4ff"/>
    <rect x="10" y="9" width="3" height="5" rx="1" fill="#7cc4ff"/><rect x="17" y="9" width="3" height="5" rx="1" fill="#7cc4ff"/>
    <circle cx="9" cy="21" r="3.4" fill="#7cc4ff"/><circle cx="23" cy="21" r="3.4" fill="#7cc4ff"/>`,
  // Drone: four rotors on crossed arms around a body.
  drone: `<path d="M8 8 L24 24 M24 8 L8 24" stroke="#4da3ff" stroke-width="2.2"/>
    <circle cx="8" cy="8" r="4" fill="none" stroke="#4da3ff" stroke-width="2"/><circle cx="24" cy="8" r="4" fill="none" stroke="#4da3ff" stroke-width="2"/>
    <circle cx="8" cy="24" r="4" fill="none" stroke="#4da3ff" stroke-width="2"/><circle cx="24" cy="24" r="4" fill="none" stroke="#4da3ff" stroke-width="2"/>
    <rect x="13" y="13" width="6" height="6" rx="1.5" fill="#4da3ff"/>`,
};

const cache: Partial<Record<string, L.DivIcon>> = {};

export function vehicleIcon(kind: Vehicle, ring = '#0b0d10'): L.DivIcon {
  // Purpose: a 34 px Leaflet icon for `kind`; `ring` colors the disc border (e.g. red for the stopped rover).
  const key = `${kind}:${ring}`;
  cache[key] ??= L.divIcon({
    className: 'vehicle-icon',
    html: `<svg width="34" height="34" viewBox="-2 -2 36 36" aria-hidden="true">`
      + `<circle cx="16" cy="16" r="17" fill="#0b0d10" fill-opacity="0.85" stroke="${ring}" stroke-width="2.5"/>${SVG[kind]}</svg>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    tooltipAnchor: [0, -14],
  });
  return cache[key]!;
}
