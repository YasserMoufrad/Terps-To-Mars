// Data and software credits. The map's on-screen credit bar is hidden (PR #29), so the "About this mission" box lists
// every source the map draws. The map layers read their attribution strings from here too, so the two never drift.
// Ground photos and lander weather data are credited on their own cards (groundViews.ts, conditions.ts).

export const CTX_ATTRIBUTION = 'CTX: NASA/JPL/MSSS, Caltech Murray Lab, Esri';
export const THEMIS_ATTRIBUTION = 'THEMIS: NASA/JPL/ASU via Mars Trek';
export const THEMIS_NIGHT_ATTRIBUTION = 'THEMIS Night IR: NASA/JPL/ASU via Mars Trek';
export const VIKING_COLOR_ATTRIBUTION = 'Color: Viking MDIM 2.1 color mosaic, NASA/USGS via Mars Trek';
export const HIRISE_CREDIT = 'HiRISE ESP_071006_2345: NASA/JPL-Caltech/UArizona';

export interface Credit {
  what: string; // what the app uses it for
  credit: string; // who to credit, as the source asks
  url: string; // where it comes from
}

export const MAP_CREDITS: Credit[] = [
  { what: 'Terrain image and elevation model (routes, slopes, hazards, cliff tracing)',
    credit: 'HiRISE ESP_071006_2345 and DTEEC_071085_2345_071006_2345_A01: NASA/JPL-Caltech/University of Arizona',
    url: 'https://www.uahirise.org/ESP_071006_2345' },
  { what: 'Base map', credit: 'CTX global mosaic: NASA/JPL/MSSS, Caltech Murray Lab, Esri', url: 'https://murray-lab.caltech.edu/CTX/' },
  { what: 'Base map under the CTX tiles', credit: 'THEMIS Day IR controlled mosaic: NASA/JPL/ASU, via NASA Mars Trek', url: 'https://trek.nasa.gov/mars/' },
  { what: 'Night infrared layer', credit: 'THEMIS Night IR controlled mosaic: NASA/JPL/ASU, via NASA Mars Trek', url: 'https://trek.nasa.gov/mars/' },
  { what: 'Mars color', credit: 'Viking MDIM 2.1 color mosaic: NASA/USGS, via NASA Mars Trek', url: 'https://trek.nasa.gov/mars/' },
  { what: 'Ice science', credit: 'Dundas, C. M. et al. (2018), Science 359, 199–201', url: 'https://doi.org/10.1126/science.aao1619' },
  { what: 'Map library', credit: 'Leaflet (BSD-2-Clause license)', url: 'https://leafletjs.com' },
];

export const OTHER_CREDITS_NOTE = 'Ground photos and lander weather data are credited on their own cards.';
