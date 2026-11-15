// Measuring tool: switch it on with the ruler button, click point A, click point B, and the map draws the straight
// line between them with its Mars-surface distance and walking time. A third click starts a new measurement.
// Distances use the Mars radius (coordinates.ts), never Leaflet's Earth-based distance.

import { useEffect, useState } from 'react';
import { CircleMarker, Polyline, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import { appLogger } from '../lib/appLogger';
import { measureText, type LatLonPoint } from './coordinates';

export function MeasureLayer({ active }: { active: boolean }) {
  // Purpose: inside the map: collects the clicked points while `active` and draws them. `points` holds 0, 1 or 2
  // clicked positions; switching the tool off clears them.
  const [points, setPoints] = useState<LatLonPoint[]>([]);
  const map = useMap();
  useEffect(() => {
    // Crosshair cursor while measuring, and no double-click zoom (two quick clicks would zoom instead of placing B);
    // switching off restores both and clears the measurement.
    map.getContainer().classList.toggle('measuring', active);
    if (active) map.doubleClickZoom.disable(); else map.doubleClickZoom.enable();
    if (!active) setPoints([]);
  }, [active, map]);

  useMapEvents({
    click: (e) => {
      if (!active) return;
      const p = { lat: e.latlng.lat, lon: e.latlng.lng };
      setPoints((prev) => {
        const next = prev.length >= 2 ? [p] : [...prev, p];
        if (next.length === 2) {
          const m = measureText(next[0], next[1]);
          appLogger.info('analysis', 'measure.distance', { a: next[0], b: next[1], metres: Math.round(m.metres), method: 'mars_great_circle' });
        }
        return next;
      });
    },
  });

  if (!active || points.length === 0) return null;
  const [a, b] = points;
  const m = b ? measureText(a, b) : null;
  const dot = { color: '#0b0d10', fillColor: '#62ddff', fillOpacity: 1, weight: 2 };
  return (
    <>
      {b && m && (
        <Polyline positions={[[a.lat, a.lon], [b.lat, b.lon]]} pathOptions={{ color: '#62ddff', weight: 3, dashArray: '6 6' }} interactive={false}>
          <Tooltip permanent direction="center" className="measure-label">{m.distance} · {m.walk}</Tooltip>
        </Polyline>
      )}
      <CircleMarker center={[a.lat, a.lon]} radius={5} pathOptions={dot} interactive={false} />
      {b && <CircleMarker center={[b.lat, b.lon]} radius={5} pathOptions={dot} interactive={false} />}
    </>
  );
}

export function MeasureButton({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  // Purpose: the ruler button under the zoom buttons, plus a one-line hint while the tool is on.
  return (
    <>
      <button type="button" className={`measure-btn${active ? ' on' : ''}`} onClick={onToggle}
        aria-pressed={active} title={active ? 'Stop measuring' : 'Measure the distance between two points'}>
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M3 17 17 3l4 4L7 21z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          <path d="M7 13l2 2M10 10l2 2M13 7l2 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
      {active && (
        <div className="measure-hint">
          Click two points to measure. Straight line over the Mars surface, not a route: it ignores slopes and hazards.
        </div>
      )}
    </>
  );
}
