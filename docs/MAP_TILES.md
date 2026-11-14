# Basemap tiles

Tested 2026-11-14 at the Milankovic site (54.144°N, −147.894). All three layers return real tiles there.

| Layer | URL template (`{z}/{y}/{x}` = zoom / row / column) | Format | Max native zoom at the site | Use |
| --- | --- | --- | --- | --- |
| MOLA color hillshade (463 m) | `https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg` | jpg | 7 | Regional context, elevation feel |
| THEMIS day IR (100 m) | `https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018/1.0.0/default/default028mm/{z}/{y}/{x}.png` | png | 9 | Thermal layer (soft ground context) |
| CTX global mosaic, uncontrolled (5 m, Caltech) | `https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer/tile/{z}/{y}/{x}` | png | 10 | Main basemap |

Sources: [Mars Trek API layer list](https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars) and each layer's `WMTSCapabilities.xml`. The CTX layer's capabilities point to the Esri OnMars service above.

## How the tiling works

- Equirectangular (plain lat/lon), longitudes −180..180.
- Zoom 0 is 2 columns × 1 row; each zoom doubles both. Tile size in degrees = 180 / 2^z.
- Row 0 starts at the north pole; column 0 starts at −180.
- This matches Leaflet's `L.CRS.EPSG4326`, so Trek zoom levels map directly to Leaflet zoom levels.

## In react-leaflet

```tsx
<MapContainer crs={L.CRS.EPSG4326} center={[54.144, -147.894]} zoom={9} maxZoom={14}>
  <TileLayer url="https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer/tile/{z}/{y}/{x}"
             maxNativeZoom={10} attribution="CTX: NASA/JPL/MSSS, Caltech Murray Lab, Esri" />
</MapContainer>
```

`maxNativeZoom` lets the map zoom past the deepest real tiles by enlarging them; the HiRISE overlay (25 cm) supplies real detail at those zooms.

## Still to verify on screen

- The CTX tiles come from a different server than the Trek layers; check visually that CTX, MOLA and the HiRISE overlay line up at the scarp.
- Confirm the attribution text each provider asks for.
