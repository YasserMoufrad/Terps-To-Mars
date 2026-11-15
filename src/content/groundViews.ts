// Real NASA surface photos that show what each hazard looks like from the ground.
// None of them was taken at Milankovič crater: they are labeled "example Mars terrain"
// everywhere they appear. Picked by Geury; images are NASA public domain, served from
// NASA's own image CDN (science.nasa.gov Photojournal renditions).

import type { StageId } from '../data/types';

export interface GroundView {
  id: string; // NASA Photojournal id, e.g. "PIA10682"
  title: string; // NASA's own title
  mission: string; // which lander took it, and where
  shows: string; // what a judge should notice, tied to our hazard types
  imageUrl: string;
  pageUrl: string; // the NASA catalog page (source and full credit)
  credit: string;
  stages: StageId[]; // stages whose side panel shows this photo
}

const RENDITION = (path: string) =>
  `https://assets.science.nasa.gov/content/dam/science/psd/photojournal/pia/${path}.jpg/jcr:content/renditions/cq5dam.web.1280.1280.jpeg`;

export const EXAMPLE_LABEL = 'Example Mars terrain, not this site';

export const GROUND_VIEWS: GroundView[] = [
  {
    id: 'PIA10682',
    title: 'Icy, Patterned Ground on Mars',
    mission: 'Phoenix lander, northern plains (68°N)',
    shows: 'Ice-rich mid-to-high-latitude plains break into polygons. From orbit this looks smooth; on foot it is cracked, uneven ground.',
    imageUrl: RENDITION('pia10/pia10682/PIA10682'),
    pageUrl: 'https://photojournal.jpl.nasa.gov/catalog/PIA10682',
    credit: 'NASA/JPL-Caltech/University of Arizona',
    stages: ['orbital'],
  },
  {
    id: 'PIA11383',
    title: 'Phoenix Deepens Trenches on Mars',
    mission: 'Phoenix lander, northern plains (68°N)',
    shows: 'Loose soil over buried ice. This is the "under their feet" (U) hazard an orbiter cannot measure and the rover has to feel with its wheels.',
    imageUrl: RENDITION('pia11/pia11383/PIA11383'),
    pageUrl: 'https://photojournal.jpl.nasa.gov/catalog/PIA11383',
    credit: 'NASA/JPL-Caltech/University of Arizona/Texas A&M University',
    stages: ['rover'],
  },
  {
    id: 'PIA10903',
    title: '"Dodo-Goldilocks" Trench Dug by Phoenix',
    mission: 'Phoenix lander, northern plains (68°N)',
    shows: 'Bright water ice a few centimetres down. Our scarp exposes ice like this on a cliff face; the drone images it from a distance.',
    imageUrl: RENDITION('pia10/pia10903/PIA10903'),
    pageUrl: 'https://photojournal.jpl.nasa.gov/catalog/PIA10903',
    credit: 'NASA/JPL-Caltech/University of Arizona/Texas A&M University',
    stages: ['drone'],
  },
  {
    id: 'PIA00571',
    title: 'Ice on Mars Utopia Planitia Again',
    mission: 'Viking 2 lander, Utopia Planitia (48°N)',
    shows: 'Frost on the ground at a northern landing site. Cold, shadowed ground like the foot of our pole-facing scarp is the "in shadow" (S) hazard.',
    imageUrl: RENDITION('pia00/pia00571/PIA00571'),
    pageUrl: 'https://photojournal.jpl.nasa.gov/catalog/PIA00571',
    credit: 'NASA/JPL',
    stages: ['eva'],
  },
];

export function groundViewsFor(stage: StageId): GroundView[] {
  // Purpose: the example photos to show in the side panel for `stage` (may be empty).
  return GROUND_VIEWS.filter((v) => v.stages.includes(stage));
}
