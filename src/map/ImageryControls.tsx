// Map navigation and HiRISE status: "Mission overview" and "Inspect scarp", the imagery load state,
// and the sampling/registration disclosures shown as text (not only in a tooltip).

import { useMap } from 'react-leaflet';
import type { LatLon, OverlayBounds } from '../data/types';
import { appLogger } from '../lib/appLogger';
import { collectPositions } from './FitToMission';
import {
  IMAGERY_STATUS_TEXT, INSPECT_ZOOM, SAMPLING_DISCLOSURE, inspectTarget, type ImageryLoadState,
} from './imageryState';

interface ImageryControlsProps {
  overview: { geometries: unknown[]; points: LatLon[] }; // route/hazard coordinates and named endpoints
  hiriseBounds: OverlayBounds | null; // native image footprint; null when not published
  inspectCandidates: LatLon[]; // preferred inspection centres, used only if inside the image
  state: ImageryLoadState; // combined HiRISE load state
  registration: string; // visible alignment note (registrationNote)
  onRetry: () => void; // re-requests the HiRISE layers after a failure
}

export function ImageryControls({ overview, hiriseBounds, inspectCandidates, state, registration, onRetry }: ImageryControlsProps) {
  // Purpose: two explicit views instead of an automatic re-fit on every stage change.
  // "Inspect scarp" is disabled whenever the native imagery is off, unpublished or failed.
  const map = useMap();
  const narrow = typeof window !== 'undefined' && window.matchMedia?.('(max-width: 640px)').matches;
  const canInspect =hiriseBounds !== null && !['disabled', 'unavailable', 'failed'].includes(state);

  const showOverview = () => {
    const positions: [number, number][] = overview.points.map((p) => [p.lat, p.lon]);
    for (const g of overview.geometries) collectPositions(g, positions);
    if (positions.length > 1) map.flyToBounds(positions, { padding: [40, 40] });
    appLogger.info('map', 'view.overview', { points: positions.length });
  };
  const inspect = () => {
    if (!hiriseBounds) return;
    const target = inspectTarget(hiriseBounds, inspectCandidates);
    map.flyTo([target.lat, target.lon], INSPECT_ZOOM);
    appLogger.info('map', 'view.inspect_scarp', { zoom: INSPECT_ZOOM, target, imagery_state: state });
  };

  return (
    <div className="leaflet-top leaflet-right">
      <div className="leaflet-control imagery-controls">
        <div className="imagery-buttons">
          <button type="button" onClick={showOverview}>Mission overview</button>
          {hiriseBounds && (
            <button type="button" onClick={inspect} disabled={!canInspect}
              title={canInspect ? undefined : 'Turn on the HiRISE layer to inspect the scarp'}>
              Inspect scarp
            </button>
          )}
        </div>
        {hiriseBounds && (
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
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
