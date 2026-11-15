// Which optional layers the user has switched on. The crew routes and the
// markers are always shown; everything else can be toggled (progressive disclosure).

export interface LayerVisibility {
  color: boolean; // real Mars color (Viking MDIM 2.1 color mosaic) blended over the CTX detail
  hirise: boolean; // sharp HiRISE image (Nic's pipeline)
  slope: boolean; // colored slope map (Nic's pipeline)
  hazards: boolean;
  coverage: boolean;
  nightIr: boolean; // THEMIS night-time infrared (Mars Trek, 100 m/px): relative firm-vs-loose ground context
}

export const DEFAULT_LAYERS: LayerVisibility = {
  color: true,
  hirise: true,
  slope: true, // on at load (orbital planning starts here); stage changes never touch the user's toggle
  hazards: true,
  coverage: false, // off by default; the route and hazards tell the story first
  nightIr: false, // off by default: coarse regional context, switched on to compare
};

// Shown under a layer's checkbox while it is on: how to read it and what it cannot tell you.
export const LAYER_EXPLANATIONS: Partial<Record<keyof LayerVisibility, string>> = {
  nightIr:
    'Orange = ground that stays warmer through the night (rock, crusted or ice-cemented soil: firmer); blue = ground that '
    + 'cools fast (dust, loose sand: looser). Contrast stretched and false-colored for this site, so colors are relative '
    + 'to the area around the walk, not a temperature; about 100 m per pixel, so it shows regional patterns, not a soft '
    + 'patch or a rock on the route. At this latitude the mosaic is noisy.',
};

// Night-IR display stretch: the 2nd and 98th percentile of tile brightness (0-255) around the mission area, measured
// 2026-11-16 from the zoom-9 THEMIS Night IR tiles (3,060 pixels). Values outside clip to the ramp ends.
export const NIGHT_IR_STRETCH = { low: 78, high: 168 };

// Color ramp from cools fast (loose, blue) to stays warm (firm, orange), as [r, g, b] in 0..1; used by the SVG
// filter on the map and by the key under the checkbox, so the two always match.
export const NIGHT_IR_RAMP: [number, number, number][] = [
  [0.17, 0.35, 0.75],
  [0.45, 0.68, 0.9],
  [0.93, 0.9, 0.78],
  [0.99, 0.62, 0.22],
  [0.85, 0.28, 0.1],
];

export function nightIrStretch(low: number, high: number): { slope: number; intercept: number } {
  // Purpose: linear map so brightness `low` → 0 and `high` → 1 (inputs 0..255, as the filter sees them in 0..1).
  const slope = 255 / (high - low);
  return { slope, intercept: -low / (high - low) };
}

export function rampGradient(ramp = NIGHT_IR_RAMP): string {
  // Purpose: the same ramp as a CSS linear-gradient for the color key.
  return `linear-gradient(to right, ${ramp.map(([r, g, b]) => `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`).join(', ')})`;
}

export const LAYER_LABELS: Record<keyof LayerVisibility, string> = {
  color: 'Mars color (Viking color mosaic)',
  hirise: 'HiRISE image (0.25 m sampling)', // map sampling, not optical resolution (~1 m objects)
  slope: 'Slope map',
  hazards: 'Hazards',
  coverage: 'Scouting coverage',
  nightIr: 'Night infrared (THEMIS, firm vs loose ground)',
};
