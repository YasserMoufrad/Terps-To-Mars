// The one logger the app uses. DEBUG is on only in the dev server (`npm run dev`),
// never in the production build that GitHub Pages serves.

import { createLogger } from './logger.ts';

export const appLogger = createLogger({ debug: import.meta.env.DEV });
