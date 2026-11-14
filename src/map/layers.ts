// Which optional layers the user has switched on. The crew routes and the
// markers are always shown; everything else can be toggled (progressive disclosure).

export interface LayerVisibility {
  hirise: boolean; // sharp HiRISE image (Nic's pipeline)
  slope: boolean; // colored slope map (Nic's pipeline)
  hazards: boolean;
  coverage: boolean;
}

export const DEFAULT_LAYERS: LayerVisibility = {
  hirise: true,
  slope: false, // off by default so the map is not cluttered
  hazards: true,
  coverage: false, // off by default; the route and hazards tell the story first
};

export const LAYER_LABELS: Record<keyof LayerVisibility, string> = {
  hirise: 'HiRISE image (25 cm)',
  slope: 'Slope map',
  hazards: 'Hazards',
  coverage: 'Scouting coverage',
};
