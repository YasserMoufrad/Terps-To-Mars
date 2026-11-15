// Science panel text: why this cliff, what the crew observes, why it matters, how sure we are, and sources.
// Written by Geury (team science lead) from his HiRISE enhanced-color check (2026-11-14); numbers updated for the
// viewpoint that moved ~90 m west to face the bluest stretch of the second cliff (now ~226 m from its foot).
// Bluish tones are "consistent with" ice, never proof: that wording is deliberate (scientific honesty rules).

export interface ScienceSection {
  heading: string;
  text: string;
}

export interface Source {
  label: string;
  url: string;
}

export const SCIENCE_TITLE = 'The science: why this cliff';

// Always visible: the one-paragraph answer.
export const SCIENCE_LEAD =
  'Our site in Milankovič crater (54.2°N, 147.9°W) is a candidate for observing exposed subsurface ice. '
  + 'Dundas et al. (2018, Science) documented ice-rich scarps in this region; ice beginning 1–2 m below the surface '
  + 'was measured at studied scarps, not along our route. HiRISE enhanced color shows bluish tones on both traced cliffs, '
  + 'consistent with ice but not a spectral confirmation of either face. The planned drone and crew imaging would test the interpretation.';

export const SCIENCE_SECTIONS: ScienceSection[] = [
  {
    heading: 'What the crew observes',
    text: 'From a viewpoint about 230 m back, the crew would image the north-facing second cliff, tens of metres tall '
      + '(estimates differ: about 24 m from the color trace, up to about 44 m on the elevation model). In HiRISE enhanced color the '
      + 'stretch they face is bluish (29–43% of face pixels in the team\'s analysis, pending independent review), consistent with water ice. At studied scarps, Dundas et al. '
      + '(2018) describe banding and color changes that suggest layers laid down with changing amounts of ice and dust as the climate '
      + 'varied. At those scarps, ice lies beneath a thin cap of dust and ice-cemented soil, and debris collects at the foot. '
      + 'Exposed ice can sublimate, allowing scarps to retreat and pits to grow. The crew would document possible layers, '
      + 'the debris cover and signs of retreat with cameras and close-up imaging, without touching the face.',
  },
  {
    heading: 'Why it matters',
    text: 'Mid-latitude ice at studied scarps likely fell as snow during past periods when Mars\' tilt was larger, so its layers '
      + 'may record recent Martian climate. Some studied ice sheets begin 1–2 m below the surface and exceed 100 m in thickness; '
      + 'neither depth nor thickness has been established at this viewpoint.',
  },
  {
    heading: 'Why the drone takes the tall middle of the main cliff',
    text: 'The main cliff\'s middle is its tallest (60–72 m) and among its bluest stretches in the team\'s analysis; possible layers there need confirmation. It also sits '
      + 'above an enclosed, rough pit floor the crew vehicle cannot cross within the spacewalk budget, and its rockfall risk is the '
      + 'highest. The planned drone perch is about 130 m from its foot; in this simulated mission, the drone would image it '
      + 'while the crew observes the lower, reachable second cliff.',
  },
  {
    heading: 'How sure we are',
    text: 'Consistent with ice, not confirmed. In the team\'s HiRISE enhanced-color analysis (ESP_071006_2345), pending independent review, the main cliff\'s west and middle show bluish '
      + 'tones (22–89% of face pixels); its east end does not (0–13%). The second cliff, where the crew looks, is bluish along the '
      + 'stretch they face (29–43% of face pixels). Dundas et al. (2018) found ice sheets exposed at eight such scarps; CRISM spectra '
      + 'detected water ice at 3 of those 8, and none has been confirmed for either cliff here.',
  },
  {
    heading: 'How the color was measured',
    text: 'In the team\'s analysis, pending independent review, a pixel counts as bluish when blue exceeds red by 25 and green by 15 in the HiRISE enhanced-color browse (about 2.8 m per '
      + 'pixel), registered to the team\'s traced cliff lines, counted between each cliff\'s traced top edge and foot. Along the second '
      + 'cliff, west to east, the bluish share rises from 4% to a peak of 43% (147.8962–147.8955°W) and falls to 6% at the east end; '
      + 'the viewpoint was moved about 90 m west to face that peak.',
  },
];

export const SCIENCE_SOURCES: Source[] = [
  { label: 'Dundas, C. M. et al. (2018), Exposed subsurface ice sheets in the Martian mid-latitudes, Science 359, 199–201',
    url: 'https://doi.org/10.1126/science.aao1619' },
  { label: 'Dundas, C. M. et al. (2021), Widespread exposures of extensive clean shallow ice in the mid-latitudes of Mars, JGR Planets 126',
    url: 'https://doi.org/10.1029/2020JE006617' },
  { label: 'HiRISE ESP_071006_2345 (image) and DTEEC_071085_2345_071006_2345_A01 (elevation model), NASA/JPL-Caltech/University of Arizona',
    url: 'https://www.uahirise.org/ESP_071006_2345' },
];

export const SCIENCE_CREDIT = 'Science text: Geury (Terps to Mars), from his HiRISE enhanced-color analysis.';

// One line for the evidence card of the traced cliff faces.
export const ICE_EVIDENCE =
  'Ice evidence: consistent with ice, not confirmed. Team HiRISE enhanced-color analysis (pending independent review): main cliff west and middle 22–89% bluish face '
  + 'pixels, east end 0–13%; second cliff 29–43% where the crew looks. CRISM detected water ice at 3 of the 8 scarps in '
  + 'Dundas et al. (2018); none has been confirmed for either cliff here.';
