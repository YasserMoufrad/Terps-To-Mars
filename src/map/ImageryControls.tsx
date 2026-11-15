// Map navigation and HiRISE status. "Stage overview" frames this stage's geometry; the "Inspect" list holds the
// geographic targets (the active science target, each traced scarp, the crew's ice face, the observation point
// and the simulated rover incident), each with its own coordinates, source and evidence; "Locate rover incident"
// jumps to the simulated stop. Navigation never changes the mission stage (PR #20). Imagery load state and the
// sampling/registration disclosures are shown as text, not only in a tooltip.

import L from 'leaflet';
import { useState } from 'react';
import { useMap } from 'react-leaflet';
import type { LatLon, OverlayBounds, StageId } from '../data/types';
import { appLogger } from '../lib/appLogger';
import { collectPositions } from './FitToMission';
import { IMAGERY_STATUS_TEXT, SAMPLING_DISCLOSURE, type ImageryLoadState } from './imageryState';
import type { InspectionTarget } from './scienceTargets';

interface ImageryControlsProps {
  overview: { geometries: unknown[]; points: LatLon[] }; // this stage's route/hazard coordinates and named endpoints
  hiriseBounds: OverlayBounds | null; // native image footprint; null when not published
  targets: InspectionTarget[]; // inspection choices; a null target is disabled and its `reason` says why
  stage: StageId; // shown for context only; never changed here
  state: ImageryLoadState; // combined HiRISE load state
  registration: string; // visible alignment note (registrationNote)
  onRetry: () => void; // re-requests the HiRISE layers after a failure
  onInspect: (target: InspectionTarget | null) => void; // highlights the chosen target (null clears)
}

export function ImageryControls({ overview, hiriseBounds, targets, stage, state, registration, onRetry, onInspect }: ImageryControlsProps) {
  // Purpose: explicit views instead of an automatic re-fit on every stage change. `choice` is the selected target
  // id; `viewport` names what the map currently frames, so the stage and the view are never confused.
  const map = useMap();
  // Opens on the crew's ice face (what the walk is for); the unresolved "active science target" stays in the list.
  const [choice, setChoice] = useState(() => (targets.some((t) => t.id === 'crew-face' && t.target) ? 'crew-face' : 'active'));
  const [viewport, setViewport] = useState('Stage overview');
  const selected = targets.find((t) => t.id === choice) ?? targets[0];
  const narrow = typeof window !== 'undefined' && window.matchMedia?.('(max-width: 640px)').matches;
  // Collapsible: starts closed on phones, where the open panel covers half the map.
  const [open, setOpen] = useState(!narrow);
  const reason = selected?.reason ?? (!selected?.target ? 'Target not available.' : undefined);

  const inspect = () => {
    // Fly to the selected feature's own bounds; asymmetric padding leaves room for the map controls.
    if (!selected?.target || !selected.bounds || reason) return;
    const size = map.getSize();
    const left = Math.min(45, size.x * 0.12);
    const top = Math.min(narrow ? 220 : 170, size.y * 0.4);
    map.flyToBounds(selected.bounds, { maxZoom: 17, paddingTopLeft: [left, top], paddingBottomRight: [35, 55] });
    onInspect(selected);
    setViewport(selected.name);
    appLogger.info('map', 'view.inspect_target', { target_id: selected.science_target_id ?? selected.id, target: selected.target,
      bounds: selected.bounds, source: selected.source, evidence: selected.evidence, mission_stage: stage });
  };
  const overviewView = () => {
    // This stage's geometry only, so a rover incident view stays distinct from the scarp view.
    const positions: [number, number][] = overview.points.map((p) => [p.lat, p.lon]);
    for (const g of overview.geometries) collectPositions(g, positions);
    if (positions.length > 1) map.flyToBounds(positions, { padding: [45, 65], maxZoom: 16 });
    onInspect(null);
    setViewport('Stage overview');
    appLogger.info('map', 'view.overview', { points: positions.length, mission_stage: stage });
  };
  const locateIncident = () => {
    // The rover coordinate is a simulated observation, not the selected scarp.
    const incident = targets.find((t) => t.id === 'discovery');
    if (!incident?.target || !incident.bounds) return;
    map.flyToBounds(incident.bounds, { maxZoom: 17, padding: [45, 85] });
    onInspect(incident);
    setViewport(incident.name);
    setChoice('discovery');
    appLogger.info('map', 'view.rover_incident', { target: incident.target, evidence: 'simulated', mission_stage: stage });
  };

  return (
    <div className="leaflet-top leaflet-right">
      <div className="leaflet-control imagery-controls"
        ref={(node) => { if (node) { L.DomEvent.disableClickPropagation(node); L.DomEvent.disableScrollPropagation(node); } }}>
        <button type="button" className="imagery-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? '▾' : '▸'} Map view
        </button>
        {open && (<>
        <div className="imagery-buttons">
          <button type="button" onClick={overviewView}>Stage overview</button>
          <label>Inspect{' '}
            <select aria-label="Inspection target" value={choice} onChange={(e) => setChoice(e.target.value)}>
              {targets.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <button type="button" onClick={inspect} disabled={Boolean(reason)} title={reason ?? selected?.note}>Go</button>
          <button type="button" onClick={locateIncident}>Locate rover incident</button>
        </div>
        <p className="inspection-context">Stage: {stage} · Viewport: {viewport}</p>
        {reason && <p className="imagery-reason">{reason}</p>}
        {selected?.target && (
          <p className="inspection-coordinates">
            {selected.name}: {selected.target.lat.toFixed(6)}°, {selected.target.lon.toFixed(6)}° · {selected.evidence}<br />{selected.source}
          </p>
        )}
        {(hiriseBounds !== null || state !== 'unavailable') && (
          <div className="imagery-status" role="status" aria-live="polite">
            <span className={`imagery-state imagery-${state}`}>HiRISE: {IMAGERY_STATUS_TEXT[state]}</span>
            {(state === 'failed' || state === 'partial') && <button type="button" className="link-btn" onClick={onRetry}>Retry</button>}
            {/* Open by default on wider screens; on phones one tap away so the map stays visible. */}
            {/* Collapsed at load: open, it covered the viewpoint. */}
            <details className="imagery-notes">
              <summary>Image source and alignment</summary>
              <p>{SAMPLING_DISCLOSURE}</p>
              <p>{registration}</p>
            </details>
          </div>
        )}
        </>)}
      </div>
    </div>
  );
}
