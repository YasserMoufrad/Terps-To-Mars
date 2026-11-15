// Map navigation and HiRISE status: "Mission overview", "Inspect scarp" (the traced scarp face) and
// "Inspect observation point" (the selected waypoint), the imagery load state, and the sampling/registration
// disclosures shown as text (not only in a tooltip).

import { useMap } from 'react-leaflet';
import type { LatLon, OverlayBounds } from '../data/types';
import { appLogger } from '../lib/appLogger';
import { collectPositions } from './FitToMission';
import { IMAGERY_STATUS_TEXT, INSPECT_ZOOM, SAMPLING_DISCLOSURE, type ImageryLoadState } from './imageryState';
import type { ScarpTarget } from './scarpTarget';

interface ImageryControlsProps {
  overview: { geometries: unknown[]; points: LatLon[] }; // route/hazard coordinates and named endpoints
  hiriseBounds: OverlayBounds | null; // native image footprint; null when not published
  scarp: ScarpTarget; // resolved scarp-face target (null target = disabled, with a reason)
  observation: LatLon | null; // selected observation waypoint
  state: ImageryLoadState; // combined HiRISE load state
  registration: string; // visible alignment note (registrationNote)
  onRetry: () => void; // re-requests the HiRISE layers after a failure
}

export function ImageryControls({ overview, hiriseBounds, scarp, observation, state, registration, onRetry }: ImageryControlsProps) {
  // Purpose: explicit views instead of an automatic re-fit on every stage change. The two inspect buttons
  // go to different objectives: the scarp face (from scarp geometry) and the observation waypoint.
  const map = useMap();
  const narrow = typeof window !== 'undefined' && window.matchMedia?.('(max-width: 640px)').matches;
  const imageryOff = ['disabled', 'unavailable', 'failed'].includes(state);
  const scarpDisabledReason = scarp.target === null ? scarp.reason : imageryOff ? 'Turn on the HiRISE layer to inspect the scarp.' : undefined;

  const showOverview = () => {
    const positions: [number, number][] = overview.points.map((p) => [p.lat, p.lon]);
    for (const g of overview.geometries) collectPositions(g, positions);
    if (positions.length > 1) map.flyToBounds(positions, { padding: [40, 40] });
    appLogger.info('map', 'view.overview', { points: positions.length });
  };
  const inspectScarp = () => {
    if (!scarp.target || scarpDisabledReason) return;
    map.flyTo([scarp.target.lat, scarp.target.lon], INSPECT_ZOOM);
    appLogger.info('map', 'view.inspect_scarp', {
      zoom: INSPECT_ZOOM, target: scarp.target, source: scarp.source, evidence: scarp.evidence, imagery_state: state,
    });
  };
  const inspectObservation = () => {
    if (!observation) return;
    map.flyTo([observation.lat, observation.lon], INSPECT_ZOOM);
    appLogger.info('map', 'view.inspect_observation', { zoom: INSPECT_ZOOM, target: observation });
  };

  return (
    <div className="leaflet-top leaflet-right">
      <div className="leaflet-control imagery-controls">
        <div className="imagery-buttons">
          <button type="button" onClick={showOverview}>Mission overview</button>
          <button type="button" onClick={inspectScarp} disabled={scarpDisabledReason !== undefined}
            title={scarpDisabledReason ?? scarp.note}>
            Inspect scarp
          </button>
          <button type="button" onClick={inspectObservation} disabled={!observation}
            title="Centre on the candidate observation point (not the scarp)">
            Inspect observation point
          </button>
        </div>
        {scarp.target === null && scarp.reason && <p className="imagery-reason">{scarp.reason}</p>}
        {hiriseBounds !== null || state !== 'unavailable' ? (
          <div className="imagery-status" role="status" aria-live="polite">
            <span className={`imagery-state imagery-${state}`}>HiRISE: {IMAGERY_STATUS_TEXT[state]}</span>
            {(state === 'failed' || state === 'partial') && (
              <button type="button" className="link-btn" onClick={onRetry}>Retry</button>
            )}
            {state !== 'disabled' && state !== 'failed' && (
              // Open by default on wider screens; on phones one tap away so the map stays visible.
              <details className="imagery-notes" open={!narrow}>
                <summary>About this image</summary>
                <p>{SAMPLING_DISCLOSURE}</p>
                <p>{registration}</p>
                {scarp.target && <p>Scarp target: {scarp.note}</p>}
              </details>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
