# Terps To Mars

**NASA Space Apps Challenge 2026 · Interplanetary Survival Guide: Martian Map · Team Terps to Mars**

A Mars spacewalk planning map built on real NASA data. Simulated robots scout first so a crew can evaluate candidate routes to possible ice exposures in Milankovič crater, a place no rover or human has visited.

> Status: in development during the hackathon (November 14-15, 2026). Live app link: coming soon.

## The idea

In 2018, Mars Reconnaissance Orbiter observations established exposed ice at studied mid-latitude scarps. That regional finding does not confirm ice at either face traced in this map. Orbital data also cannot see every hazard a suited astronaut would face. Our map plans one Marswalk to an observation point near a Milankovič scarp candidate and shows how simulated robotic scouting changes the plan:

1. **Orbital planning:** a first route from NASA terrain data, with hazards and unscouted areas marked.
2. **Rover reconnaissance:** a scout rover drives the route (and returns on the backup route), detecting hazards astronauts can't see: under their feet, over their heads, and in the dark.
3. **Drone inspection:** a drone launched from the rover inspects what the rover can't reach, including the cliff face.
4. **Astronaut mission review:** the crew reviews a proposed route to an observation point, with backup options. Nothing shown is crew clearance.

> Real NASA observation → modeled hazard → rover reconnaissance → updated evidence → revised astronaut route → informed crew decision

The map, data layers, terrain analysis, hazards and routes are real and computed from NASA data. The rover and drone are mission concepts (CAD, specifications and mission logic); their observations are clearly labeled as simulated.

## Site

**Scarps in Milankovic Crater**, 54.14°N, 212.11°E (147.89°W), Arcadia Planitia: the only northern-hemisphere site among the original eight ice scarps (Dundas et al., 2018).

- Terrain: HiRISE DTM `DTEEC_071085_2345_071006_2345_A01` (0.99 m/px)
- Imagery: HiRISE `ESP_071006_2345` (25 cm/px)

The published 4093 × 4088 HiRISE crop has approximately 0.23–0.25 m ground sampling, not 25 cm object resolution. Its registration is diagnostic and unverified (0.86 m RMS, 1.05 m maximum offset against a companion orthoimage). The original observation's stated object resolution is about 0.92 m. Color measurements at the selected second-cliff viewpoint await Geury's independent check. `science_targets.json` still marks the active target unresolved.

The conservative all-unscouted `feasibility_report.json` finds no route. Route audit and itinerary reports assess separate provisional route candidates and budgets; conditional green after simulated scouting is a planning state, never astronaut clearance.

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

Our engineers were the creative brain in the loop; AI coding assistants were the builders.

**Designed and decided by the team:** the concept (robots scout first, the crew follows, four planning steps), the site (a Milankovič scarp candidate), the habitat landing spot, the candidate ice viewpoint (from Geury's color analysis of HiRISE images, awaiting independent check), the drive-then-walk plan with a crew vehicle, the rule that only fully scouted routes turn green as conditional plans, the scout's route back along the backup, the safety rules (slope limits, cliff setback, rockfall zone, time budget), and the scout rover concept. The team also orchestrated the exact parking spot, primary viewpoint and backup viewpoint: we set the goals and criteria (flat ground, outside every hazard, facing the bluest candidate exposure, within the time budget) and reviewed the results.

**Built with AI assistance:** AI coding assistants (Claude Code, by Anthropic) wrote most of the software under the team's direction and review: the web app, the data-processing pipeline, and the scripts that trace the cliffs, compute the exact parking and viewpoint cells from the team's criteria, and compute routes from NASA's elevation data. AI also drafted most of the interface wording and documentation, and drew the small map icons (scout rover, crew vehicle, drone) in code.

**Not AI:** the app uses no AI while it runs (no chatbot, no generated text or images at runtime). All map imagery, elevation data and ground photos come from NASA and its mission teams (see Data and credits). The route lines are not hand-drawn by anyone: they are computed by a least-cost path algorithm on NASA's elevation data.

## Team

Terps to Mars: Yasser, Nic, Brianna, Geury, Samar and Kenneth.
