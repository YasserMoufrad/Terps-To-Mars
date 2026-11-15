// Checkboxes for the optional map layers. Pipeline layers that do not exist yet
// are shown as unavailable instead of disappearing, so nobody wonders where they went.

import { LAYER_LABELS, type LayerVisibility } from '../map/layers';

interface LayerTogglesProps {
  layers: LayerVisibility;
  available: Record<keyof LayerVisibility, boolean>;
  onChange: (next: LayerVisibility) => void;
  notes?: Partial<Record<keyof LayerVisibility, string>>; // load problems, e.g. HiRISE "failed to load"
}

export function LayerToggles({ layers, available, onChange, notes = {} }: LayerTogglesProps) {
  // Purpose: one checkbox per optional layer. `available` disables layers whose data
  // does not exist yet; `onChange` receives the whole new visibility object; `notes` says when a
  // checked layer is not actually showing, so a ticked box never implies a failed image loaded.
  const keys = Object.keys(LAYER_LABELS) as (keyof LayerVisibility)[];
  return (
    <section className="card toggles">
      <h3>Layers</h3>
      <p className="muted">Slope map shows DTM terrain classes; scouting coverage is simulated. Switch them on to compare evidence, not to clear a route.</p>
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
          {available[key] && notes[key] && <span className="layer-note"> ({notes[key]})</span>}
        </label>
      ))}
    </section>
  );
}
