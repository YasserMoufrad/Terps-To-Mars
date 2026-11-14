# Terps To Mars

**NASA Space Apps Challenge 2026 · Interplanetary Survival Guide: Martian Map · Team Terrapin Trekkers**

A Mars spacewalk planning map built on real NASA data. Robots scout first so astronauts can safely reach the exposed water-ice cliffs in Milankovič crater, a place no rover or human has ever visited.

> Status: in development during the hackathon (November 14-15, 2026). Live app link: coming soon.

## The idea

In 2018, NASA's Mars Reconnaissance Orbiter revealed cliffs of nearly pure water ice in the Martian mid-latitudes. Orbital data shows the ice, but it cannot see every hazard a suited astronaut would face. Our map plans one Marswalk to the Milankovič ice scarp and shows how robotic scouts improve it:

1. **Orbital planning:** a first route from NASA terrain data, with hazards and unscouted areas marked.
2. **Rover reconnaissance:** a scout rover drives the route (and returns on the backup route), detecting hazards astronauts can't see: under their feet, over their heads, and in the dark.
3. **Drone inspection:** a drone launched from the rover inspects what the rover can't reach, including the cliff face.
4. **Astronaut mission review:** the crew follows a confirmed route to a safe observation point, with a backup route home.

> Real NASA observation → modeled hazard → rover reconnaissance → updated evidence → revised astronaut route → informed crew decision

The map, data layers, terrain analysis, hazards and routes are real and computed from NASA data. The rover and drone are mission concepts (CAD, specifications and mission logic); their observations are clearly labeled as simulated.

## Site

**Scarps in Milankovic Crater**, 54.14°N, 212.11°E (147.89°W), Arcadia Planitia: the only northern-hemisphere site among the original eight ice scarps (Dundas et al., 2018).

- Terrain: HiRISE DTM `DTEEC_071085_2345_071006_2345_A01` (0.99 m/px)
- Imagery: HiRISE `ESP_071006_2345` (25 cm/px)

## Repository layout

```
src/            web app (React + TypeScript + react-leaflet)
public/data/    data files the pipeline produces and the app reads
pipeline/       Python data pipeline (terrain analysis, hazards, routes)
docs/           implementation plan and methodology
```

The full engineering plan, data contract and hazard rules are in [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md).

## Running locally

Use Node.js 22 or newer:

```bash
npm ci
npm run dev
npm run typecheck
npm test
npm run build
```

The Python contract checks use Python 3.11 or newer:

```bash
uv sync --locked --python 3.11
uv run --no-sync python -m pipeline.validate_contract
uv run --no-sync pytest
```

The app builds for the `/Terps-To-Mars/` GitHub Pages path. The `CI` workflow runs frontend and pipeline checks on pull requests to `main`; `full-suite` succeeds only after both pass. The Pages workflow runs only from `main` and validates before deployment. Yasser must enable GitHub Pages with **GitHub Actions** as its source and protect `main` with `full-suite` required before merging.

## Data and credits

- HiRISE images and DTM: NASA/JPL-Caltech/UArizona ([HiRISE](https://hirise.lpl.arizona.edu/))
- CTX, MOLA and THEMIS layers: [JPL Mars Trek](https://trek.nasa.gov/mars/)
- Geologic map: [USGS-NASA Planetary Geologic Mapping Program](https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars)
- Ground-view example images: NASA Perseverance, Phoenix and Viking missions
- Rover CAD base: [NASA JPL Open Source Rover](https://github.com/nasa-jpl/open-source-rover) (Apache-2.0); drone dock, sensor mast and instrument rack designed by our team
- Science: Dundas et al. (2018), *Exposed subsurface ice sheets in the Martian mid-latitudes*, Science

A complete source list is maintained in [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md#12-sources).

## Use of AI tools

AI assistants were used to help plan the project, research sources, draft documentation and write parts of the code. Any AI-generated crew briefings in the app are labeled as such and are generated only from our mission data.

## Team

Terrapin Trekkers: Yasser, Nic, Brianna, Geury, Samar and Kenneth.
