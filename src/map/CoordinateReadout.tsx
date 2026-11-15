// Shows the coordinates under the cursor, and pins (and copies) them when the map is clicked, so the team
// can read exact positions off the map (for example when choosing or checking a site point).

import { useState } from 'react';
import { useMapEvents } from 'react-leaflet';
import { copyText, formatLatLon, type LatLonPoint } from './coordinates';

export function CoordinateReadout() {
  // Purpose: `hover` = position under the cursor (null when it leaves the map); `pinned` = last clicked point,
  // kept until the next click; `copied` = whether that point reached the clipboard.
  const [hover, setHover] = useState<LatLonPoint | null>(null);
  const [pinned, setPinned] = useState<LatLonPoint | null>(null);
  const [copied, setCopied] = useState(false);

  useMapEvents({
    mousemove: (e) => setHover({ lat: e.latlng.lat, lon: e.latlng.lng }),
    mouseout: () => setHover(null),
    click: (e) => {
      const p = { lat: e.latlng.lat, lon: e.latlng.lng };
      setPinned(p);
      setCopied(false);
      // Clipboard access can be refused (permissions, insecure origin); the pinned text stays visible either way.
      navigator.clipboard?.writeText(copyText(p)).then(() => setCopied(true), () => setCopied(false));
    },
  });

  return (
    // Bottom-right, above the attribution line: the legend is bottom-left, buttons top-right, slope key top-left.
    <div className="coord-readout" aria-live="polite">
      <div>{hover ? formatLatLon(hover) : 'Hover over the map for coordinates'}</div>
      {pinned && (
        <div className="coord-pinned">
          Clicked: {copyText(pinned)} {copied ? '(copied)' : ''}
        </div>
      )}
    </div>
  );
}
