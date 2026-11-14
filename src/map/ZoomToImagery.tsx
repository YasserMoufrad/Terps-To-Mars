// "Zoom to HiRISE" button: flies the map onto the native-resolution image footprint.

import { useMap } from 'react-leaflet';
import type { OverlayBounds } from '../data/types';
import { appLogger } from '../lib/appLogger';

export function ZoomToImagery({ bounds, caption }: { bounds: OverlayBounds; caption: string }) {
  // Purpose: one-click navigation to the HD image so viewers find the sharp area.
  // bounds: the image's south/west/north/east corners; caption: the honest resolution note.
  const map = useMap();
  const zoomIn = () => {
    map.flyToBounds([[bounds.south, bounds.west], [bounds.north, bounds.east]], { padding: [16, 16] });
    appLogger.info('map', 'imagery.zoom_to', { source: bounds.source });
  };
  return (
    <div className="leaflet-top leaflet-right">
      <div className="leaflet-control zoom-imagery">
        <button type="button" onClick={zoomIn} title={caption}>Zoom to HiRISE detail</button>
      </div>
    </div>
  );
}
