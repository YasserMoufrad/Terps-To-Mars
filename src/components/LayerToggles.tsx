// Checkboxes for the optional map layers. Pipeline layers that do not exist yet
// are shown as unavailable instead of disappearing, so nobody wonders where they went.

import { Fragment } from 'react';
import { LAYER_EXPLANATIONS, LAYER_LABELS, rampGradient, type LayerVisibility } from '../map/layers';

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
        <Fragment key={key}>
        <label className={available[key] ? undefined : 'unavailable'}>
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
        {/* How to read the layer, shown under its checkbox only while it is on. */}
        {layers[key] && available[key] && key === 'nightIr' && (
          // Color key for the night-IR ramp (same colors as the map filter, from rampGradient).
          <div className="ir-key" aria-label="Night infrared color key: blue cools fast, looser; orange stays warm, firmer">
            <div className="ir-key-bar" style={{ background: rampGradient() }} />
            <div className="ir-key-labels"><span>Cools fast: looser</span><span>Stays warm: firmer</span></div>
          </div>
        )}
        {layers[key] && available[key] && LAYER_EXPLANATIONS[key] && <p className="layer-explain">{LAYER_EXPLANATIONS[key]}</p>}
        </Fragment>
      ))}
    </section>
  );
}
