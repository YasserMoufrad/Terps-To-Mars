// Checkboxes for the optional map layers. Pipeline layers that do not exist yet
// are shown as unavailable instead of disappearing, so nobody wonders where they went.

import { LAYER_LABELS, type LayerVisibility } from '../map/layers';

interface LayerTogglesProps {
  layers: LayerVisibility;
  available: Record<keyof LayerVisibility, boolean>;
  onChange: (next: LayerVisibility) => void;
}

export function LayerToggles({ layers, available, onChange }: LayerTogglesProps) {
  // Purpose: one checkbox per optional layer. `available` disables layers whose data
  // does not exist yet; `onChange` receives the whole new visibility object.
  const keys = Object.keys(LAYER_LABELS) as (keyof LayerVisibility)[];
  return (
    <section className="card toggles">
      <h3>Layers</h3>
      {keys.map((key) => (
        <label key={key} className={available[key] ? undefined : 'unavailable'}>
          <input
            type="checkbox"
            checked={layers[key] && available[key]}
            disabled={!available[key]}
            onChange={(e) => onChange({ ...layers, [key]: e.target.checked })}
          />
          {LAYER_LABELS[key]}
          {!available[key] && <span className="muted"> (waiting for pipeline)</span>}
        </label>
      ))}
    </section>
  );
}
