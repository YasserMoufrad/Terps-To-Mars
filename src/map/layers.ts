// Which optional layers the user has switched on. The crew routes and the
// markers are always shown; everything else can be toggled (progressive disclosure).

export interface LayerVisibility {
  color: boolean; // real Mars color (Viking MDIM 2.1 color mosaic) blended over the CTX detail
  hirise: boolean; // sharp HiRISE image (Nic's pipeline)
  slope: boolean; // colored slope map (Nic's pipeline)
  hazards: boolean;
  coverage: boolean;
}

export const DEFAULT_LAYERS: LayerVisibility = {
  color: true,
  hirise: true,
  slope: true, // on at load (orbital planning starts here); stage changes never touch the user's toggle
  hazards: true,
  coverage: false, // off by default; the route and hazards tell the story first
};

export const LAYER_LABELS: Record<keyof LayerVisibility, string> = {
  color: 'Mars color (Viking color mosaic)',
  hirise: 'HiRISE image (0.25 m sampling)', // map sampling, not optical resolution (~1 m objects)
  slope: 'Slope map',
  hazards: 'Hazards',
  coverage: 'Scouting coverage',
};
