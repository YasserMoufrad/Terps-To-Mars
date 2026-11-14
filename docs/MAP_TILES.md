# Basemap tiles

Tested 2026-11-14 at the Milankovic site (54.144°N, −147.894). All three layers return real tiles there.

| Layer | URL template (`{z}/{y}/{x}` = zoom / row / column) | Format | Max native zoom at the site | Use |
| --- | --- | --- | --- | --- |
| MOLA color hillshade (463 m) | `https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg` | jpg | 7 | Regional context, elevation feel |
| THEMIS day IR (100 m) | `https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018/1.0.0/default/default028mm/{z}/{y}/{x}.png` | png | 9 | Regional infrared context; not local bearing-strength evidence |
| Viking MDIM 2.1 color mosaic (232 m) | `https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg` | jpg | 7 | Real Mars color, blended over CTX with CSS `mix-blend-mode: color` (tested 2026-11-14; the MGS MOC color atlas `msss_atlas_simp_clon` is fully gray at this site) |
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

## Infrared imagery is not a thermal-inertia measurement

THEMIS infrared sampling is approximately 100 m/pixel ([ASU fact sheet](https://themis.mars.asu.edu/factsheet)). A day/night infrared basemap is a regional display product, not automatically a quantitative thermal-inertia map or a rover-scale soft-ground classification. Quantitative thermal inertia requires an identified processed product and a defensible thermal model with its assumptions and uncertainties ([USGS THEMIS-derived thermal-inertia product](https://astrogeology.usgs.gov/search/map/mars-themis-derived-global-thermal-inertia-mosaic)). No rover-scale exclusion polygon is generated from tile brightness.

A single simulated thermal-camera reading does not establish thermal inertia. The demo's primary rover observation is simulated 38% wheel slip; loose/soft ground remains a suspected interpretation. Rover dimensions and obstacle limits must come from Brianna's CAD/sensor model. Day/night context can inform human review without certifying traversability. Color-altimetry previews help locate a scarp, but numeric height must be measured from a validated DTM, not from display colors.

## THEMIS Night IR (candidate layer, not yet in the app)

The THEMIS Night IR Controlled Mosaic is listed in NASA Mars Trek (100 m/pixel, covers 54°N). The app does not use it yet, and the exact tile URL has not been confirmed to return images; test tile loading in a browser before adding it as a separate toggle. A 2026 study of the controlled mosaics reports roughly 200 m average horizontal absolute location accuracy, so brightness must not be aligned to individual ~1 m HiRISE/DTM cells. USGS describes these mosaics as qualitative imagery, not calibrated thermal inertia. Use it only as a regional background: no meter-scale soft-ground hazards and no bearing-strength interpretation from pixel brightness.

## Weather context (not implemented)

The Mars Climate Database chart (LMD/CNRS with ESA/CNES support) is modeled climatology near Ls 100° at 10 m altitude, not observed weather at this cliff and not simultaneous with the Ls 101.2° HiRISE image. Wind maxima are modeled climatological values, not gust limits. No wind-speed exclusion threshold is justified without a defined drone envelope and an uncertainty model. Any display must carry the scenario and altitude.

## Imagery resolution

The map-projected HiRISE product is 25 cm/pixel, but native image resolution is about 30.6 cm/pixel; small objects need several pixels to resolve. The downloaded DTM-folder ORTHO is ~1 m/pixel.
