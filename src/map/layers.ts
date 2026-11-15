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
    'Brighter = ground that stays warmer through the night (rock, crusted or ice-cemented soil); darker = ground that cools '
    + 'fast (dust, loose sand). Relative brightness, not a temperature; about 100 m per pixel, so it shows regional patterns, '
    + 'not a soft patch or a rock on the route. At this latitude the mosaic is noisy.',
};

export const LAYER_LABELS: Record<keyof LayerVisibility, string> = {
  color: 'Mars color (Viking color mosaic)',
  hirise: 'HiRISE image (0.25 m sampling)', // map sampling, not optical resolution (~1 m objects)
  slope: 'Slope map',
  hazards: 'Hazards',
  coverage: 'Scouting coverage',
  nightIr: 'Night infrared (THEMIS, firm vs loose ground)',
};
