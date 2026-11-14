// Makes basemap tile failures observable (CLAUDE.md section 16) without flooding the
// log: the first failure per layer is logged with its tile address, later ones are
// only counted. The CTX server, for example, repeatedly fails one zoom-10 tile.

import type { Logger } from '../lib/logger.ts';

export interface TileCoords {
  z: number;
  x: number;
  y: number;
}

export interface TileErrorReporter {
  report: (coords: TileCoords) => void;
  count: () => number;
}

export function createTileErrorReporter(logger: Logger, layer: string): TileErrorReporter {
  // Purpose: one reporter per basemap layer. `layer` names it in the log; `failures`
  // counts every failed tile so the total can be inspected without one event each.
  let failures = 0;
  return {
    report: (coords) => {
      // Purpose: record one failed tile; only the first failure emits a log event.
      failures += 1;
      if (failures === 1) {
        logger.warn('map', 'tiles.error', {
          layer,
          tile: `${coords.z}/${coords.y}/${coords.x}`,
          note: 'first failure for this layer; later failures are counted, not logged',
        });
      }
    },
    count: () => {
      // Purpose: total failed tiles for this layer so far.
      return failures;
    },
  };
}
