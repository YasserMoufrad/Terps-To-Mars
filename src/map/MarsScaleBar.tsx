// Scale bars in Mars metres. Leaflet's own scale control assumes Earth's radius (it would overstate lengths ~1.9x).
// This map is plain lat/lon (EPSG:4326): a pixel spans equal degrees both ways, so at 54°N it covers ~1.7x more ground
// north-south than east-west. One bar would be wrong in one direction, so there are two, measured across the centre.

import { useState } from 'react';
import { useMap, useMapEvents } from 'react-leaflet';
import { marsDistanceM, niceScale } from './coordinates';

export function MarsScaleBar() {
  // Purpose: re-measure after every zoom, pan or resize. `scales.ew` / `scales.ns` = round length, bar width, label.
  const map = useMap();
  const measure = () => {
    const size = map.getSize();
    const cx = size.x / 2, cy = size.y / 2;
    const ll = (x: number, y: number) => { const p = map.containerPointToLatLng([x, y]); return { lat: p.lat, lon: p.lng }; };
    return {
      ew: niceScale(marsDistanceM(ll(cx - 50, cy), ll(cx + 50, cy)) / 100, 90),
      ns: niceScale(marsDistanceM(ll(cx, cy - 50), ll(cx, cy + 50)) / 100, 60), // vertical bar: at most 60 px tall
    };
  };
  const [scales, setScales] = useState(measure);
  useMapEvents({ zoomend: () => setScales(measure()), moveend: () => setScales(measure()), resize: () => setScales(measure()) });

  return (
    <div className="mars-scale" aria-label={`Scale on Mars: ${scales.ew.label} east-west, ${scales.ns.label} north-south`}>
      <div className="mars-scale-row">
        <div className="mars-scale-bar" style={{ width: scales.ew.px }} />
        <span>{scales.ew.label} east–west</span>
      </div>
      <div className="mars-scale-row">
        <div className="mars-scale-vbar" style={{ height: scales.ns.px }} />
        <span>{scales.ns.label} north–south</span>
      </div>
      <span className="muted">Mars metres; map stretches east–west at this latitude</span>
    </div>
  );
}
