// "Conditions at the site": season, temperature and light for the Marswalk, from cited NASA sources.
// No instrument has measured this crater, so every temperature here is a measurement from a named lander on the same
// northern plains (Viking 2 at 48°N, Phoenix at 68°N; our site is at 54°N). Never state a temperature for the site itself:
// tests/conditions.test.mjs checks that every °C figure names the lander it came from (no invented precision).

import type { ScienceSection, Source } from './science';

export const CONDITIONS_TITLE = 'Conditions at the site';

export const CONDITIONS_LEAD =
  'No instrument has measured this crater. The closest measurements come from two landers on the same northern plains: '
  + 'Viking 2 at 48°N and Phoenix at 68°N. Our site, at 54°N, lies between them, so we plan from their records, not a forecast.';

export const CONDITIONS_SECTIONS: ScienceSection[] = [
  {
    heading: 'When to go: northern spring or summer',
    text: 'Mars is closest to the Sun near the end of southern spring, which makes southern spring and summer the dustiest part of '
      + 'the Martian year and the season of global dust storms. On the northern plains that is autumn and winter, when a thin frost '
      + 'covered the ground at Viking 2 for about 100 days each winter. We plan the walk for northern late spring or summer, the '
      + 'season Phoenix measured.',
  },
  {
    heading: 'How cold: what the nearby landers measured',
    text: 'Phoenix (68°N), late spring into early summer: average daily highs of about -30 °C and lows of about -79 °C. '
      + 'Viking 2 (48°N): its coldest predawn reading was about -120 °C, near the temperature at which carbon dioxide freezes. '
      + 'These are measurements from those landers, not from this site; the app does not model the temperature at the cliff.',
  },
  {
    heading: 'Why the cliff the crew faces is colder',
    text: 'At 54°N the midday Sun is always in the southern sky, so a north-facing cliff gets less direct sunlight than the plain '
      + 'around it. The ice scarps Dundas et al. (2018) describe face the pole, which is part of why ice stays exposed there. The crew '
      + 'views it from about 230 m back on the open plain.',
  },
];

export const CONDITIONS_SOURCES: Source[] = [
  { label: 'NASA/JPL (2008), PIA11003: Sixty-one Martian days of weather monitoring (Phoenix Lander, Canadian weather station)',
    url: 'https://photojournal.jpl.nasa.gov/catalog/PIA11003' },
  { label: 'NASA Viking Mission to Mars fact sheet (Viking 2 temperatures), reproduced by Solar Views',
    url: 'https://solarviews.com/eng/vikingfs.htm' },
  { label: 'NASA/JPL, Martian frost (Viking Lander 2 winter frost)',
    url: 'https://www.jpl.nasa.gov/news/martian-frost/' },
  { label: 'NASA/JPL, NASA Mars orbiters reveal seasonal dust storm pattern',
    url: 'https://www.jpl.nasa.gov/news/nasa-mars-orbiters-reveal-seasonal-dust-storm-pattern/' },
  { label: 'Dundas, C. M. et al. (2018), Exposed subsurface ice sheets in the Martian mid-latitudes, Science 359, 199–201',
    url: 'https://doi.org/10.1126/science.aao1619' },
];
