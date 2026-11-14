# Implementation Plan

Terrapin Trekkers · NASA Space Apps Challenge 2026 · *Interplanetary Survival Guide: Martian Map*

This is the working engineering plan for the app and the data pipeline. The data contract (section 4) is binding: both the Python pipeline and the React app follow it exactly, and any change is agreed between the two owners first.

---

## 1. What we are building

An astronaut-facing map for planning one Marswalk to the exposed water-ice scarp in **Milankovič crater**. Robots scout first and the map shows how their reconnaissance changes the crew's route.

**The chain every feature must support:**

> Real NASA observation → modeled hazard → rover reconnaissance → updated evidence → revised astronaut route → informed crew decision

**Real vs concept:**

| Real and working | Concept (CAD, specs, mission logic, labeled simulation) |
| --- | --- |
| Map, NASA data layers, terrain analysis, hazard zones, routes, route statistics | Rover and drone hardware, their sensor readings, the discovery event |

**Mission objective (proposed, pending team confirmation):** observation and reconnaissance only. Astronauts reach a safe observation point to image and study the exposed ice layers. No sampling or drilling.

## 2. Site

| Item | Value |
| --- | --- |
| Name | Scarps in Milankovic Crater (Arcadia Planitia) |
| Center | 54.144°N, 212.106°E (= −147.894 in −180..180 longitude) |
| DTM | `DTEEC_071085_2345_071006_2345_A01`, 0.99 m/px, 381 MB (.IMG) — [DTM page](https://hirise.lpl.arizona.edu/dtm/ESP_071085_2345) |
| Overlay image | `ESP_071006_2345`, map-projected, 25 cm/px, equirectangular, north up — [image page](https://hirise.lpl.arizona.edu/ESP_071006_2345) |
| Image coverage | Black and white about 5 km wide; enhanced color strip about 1 km wide |
| Acquisition | 19 Sep 2021, local Mars time 15:26, Ls 101.2° (northern summer), Sun about 42° above the horizon |
| Ice evidence | Milankovič is the only northern-hemisphere site among the eight ice scarps of Dundas et al. (2018, *Science*). Exposed ice is visible in HiRISE color and reported as water ice by CRISM. Blue tones in HiRISE enhanced color alone are **not** proof of ice; cite the spectral evidence. |
| Resolution limit | HiRISE resolves objects of about 92 cm at best; the DTM cannot see individual rocks under about 1 m |

Mars Trek has no HiRISE data for this spot: HiRISE comes from the HiRISE/PDS links above; CTX, MOLA, THEMIS and geology come from [Mars Trek](https://trek.nasa.gov/mars/).

Mission season and time: northern summer, mid-afternoon, matching the image. The shadow layer uses the image's own Sun geometry.

## 3. Architecture

```
Terps-To-Mars/
├─ src/                React + TypeScript + react-leaflet app        (Yasser)
├─ public/data/        contract files: pipeline writes, app reads    (Nic writes)
│   └─ SCHEMA.md       short copy of section 4
├─ pipeline/           Python: rasterio, numpy, scikit-image          (Nic)
│   ├─ raw/            downloaded NASA files, git-ignored
│   ├─ hazard_rules.json   versioned thresholds (section 5)
│   └─ tests/          synthetic-grid tests (section 8)
└─ docs/               this plan and methodology
```

- **Stack:** Vite + React + TypeScript + react-leaflet, deployed to GitHub Pages by GitHub Actions. Python for all data processing.
- **Branches:** `ui/...` (Yasser), `pipeline/...` and `data/...` (Nic). Merge by pull request at each sync point.
- **Large files never enter git.** GitHub rejects files over 100 MB. Only processed, web-sized outputs are committed.

## 4. Data contract

All files live in `public/data/`. Every file carries `"schema_version": "1.0"` (as a top-level member in GeoJSON). Every hazard, route and coverage zone has a stable `id`.

> **Coordinate order:** GeoJSON is `[longitude, latitude]`. JSON objects outside GeoJSON use `{"lat": …, "lon": …}`. All longitudes are −180..180.

### `hirise.jpg` + `hirise.bounds.json`, `slope.png` + `slope.bounds.json`

```json
{ "schema_version": "1.0", "south": 54.10, "west": -147.95, "north": 54.19, "east": -147.84,
  "source": "HiRISE ESP_071006_2345", "processing": "cropped, reprojected to Mars lat/lon, downsampled" }
```

### `hazards.geojson` (Polygon or Point features)

| Property | Values |
| --- | --- |
| `id` | stable string, e.g. `hz-slope-004` |
| `type` | `U` under their feet · `O` over their heads · `S` in shadow |
| `category` | `slope` · `roughness` · `rockfall` · `edge` · `soft_ground` · `void` · `shadow` · `no_data` · `artifact` |
| `severity` | `exclude` · `caution` |
| `evidence` | `nasa_derived` · `inferred` · `simulated` |
| `agent` | `crew` · `rover` · `both` |
| `stage` | first stage it appears in: `orbital` · `rover` · `drone` · `eva` |
| `source` | dataset or scenario ID, e.g. `HiRISE DTEEC_071085_2345_071006_2345_A01` |
| `note` | one plain sentence, including known limitations |

### `routes.geojson` (LineString features)

| Property | Values |
| --- | --- |
| `id` | stable string, e.g. `rt-crew-main-v1` |
| `kind` | `orbital_guess` · `main` · `backup` · `rover_path` |
| `agent` | `crew` · `rover` |
| `version` | `before` · `after` (around the discovery event) |
| `status` | `ok` · `no_viable_route` · `backup_unavailable` · `inspection_required` |
| `stats` | `{ "length_m", "round_trip_m", "est_time_min", "elevation_gain_m", "max_slope_deg", "shared_with_main_m" }` (Mars geometry, radius 3,389.5 km) |

A route with a non-`ok` status may have empty geometry. The app must show the status, never hide it.

### `coverage.geojson` (Polygon features)

| Property | Values |
| --- | --- |
| `id` | stable string |
| `state` | `orbit_only` · `rover_checked` · `drone_checked` · `unscouted` · `inspection_required` |
| `simulated` | `true` for every `rover_checked` and `drone_checked` zone in this demo |
| `sensor` | `stereo_cam` · `hazard_cam` · `thermal` · `drone_cam` · `none` |

"Scouted" means **inside a modeled sensor footprint** along the robot's path (section 6), not merely near it. Unscouted terrain is never shown as safe.

### `mission.json`

```json
{
  "schema_version": "1.0",
  "site": { "name": "Scarps in Milankovic Crater", "lat": 54.144, "lon": -147.894,
            "dtm_id": "DTEEC_071085_2345_071006_2345_A01", "image_id": "ESP_071006_2345" },
  "sun": { "ls_deg": 101.2, "local_time": "15:26", "elevation_deg": 42, "source": "ESP_071006_2345 metadata" },
  "endpoints": { "habitat": { "lat": 0, "lon": 0 },
                 "observation_primary": { "lat": 0, "lon": 0 },
                 "observation_backup": { "lat": 0, "lon": 0 } },
  "stages": [
    { "id": "orbital", "title": "Orbital planning", "text": "", "stats": {} },
    { "id": "rover",   "title": "Rover reconnaissance", "text": "", "stats": {} },
    { "id": "drone",   "title": "Drone inspection", "text": "", "stats": {} },
    { "id": "eva",     "title": "Astronaut mission review", "text": "", "stats": {} }
  ],
  "alerts": { "eva": ["Overwatch: cliff clear", "Backup route ready"] },
  "drone": { "perch": { "lat": 0, "lon": 0 }, "view_cone_id": "cov-drone-perch" },
  "discovery": {
    "id": "disc-001", "hazard_id": "hz-sim-001",
    "before_route_id": "rt-crew-main-v1", "after_route_id": "rt-crew-main-v2",
    "location": { "lat": 0, "lon": 0 },
    "sensor_evidence": { "wheel_slip_pct": 38, "thermal": "low thermal inertia (inferred loose material)" },
    "evidence": "simulated", "uncertainty": "high",
    "decision": "request_input",
    "options": [
      { "id": "opt-reroute", "label": "Reroute around the area", "consequence": "+120 m" },
      { "id": "opt-drone", "label": "Send the drone to inspect", "consequence": "+15 min" },
      { "id": "opt-continue", "label": "Continue slowly", "consequence": "risk accepted by crew" }
    ],
    "chosen_option": "opt-reroute"
  }
}
```

Placeholder versions of every file are committed first, in this exact format, so the app can be built before real data exists.

## 5. Hazard rules v1

Stored in `pipeline/hazard_rules.json` (versioned). Values marked *assumption* are modeling choices, labeled as such in the app.

| Rule | Value | Agent | Checked by | Basis |
| --- | --- | --- | --- | --- |
| Astronaut max slope (exclude) | 20° | crew | DTM | NASA exploration EVA planning value (2021); planning figure, not a measured limit |
| Astronaut caution slope | 15–20° | crew | DTM | *Assumption*: Mars gravity 0.38 g, suited crew carrying gear |
| Rover max tilt (exclude) | 24° | rover | DTM | Reported Perseverance driving limit (Oct 2026); verify against NASA |
| Rover wheel drop | 35 cm | rover | rover sensors only | Perseverance AutoNav example; below DTM resolution |
| Rover belly clearance | 20 cm | rover | rover sensors only | Reported Perseverance value (Oct 2026); verify |
| Rockfall buffer | max(visible boulder apron, 0.5 × scarp height) from the scarp foot | both | DTM + image | *Assumption*, scaled to the measured scarp; scarps actively retreat |
| Cliff-top setback | 20 m from the edge | crew | DTM | *Assumption*: edge collapse |
| Roughness | elevation range > 0.5 m within a 3 × 3 m window → caution | both | DTM | *Assumption*; tune on real data |
| No-data / artifact cells | exclude → `inspection_required` | both | DTM QC | Missing or suspect data is never safe |
| Max excursion | round trip under 5 km; hard cap 10 km from habitat | crew | route stats | NASA Walkback test (10 km assumption from Apollo) |
| Time reserve | ≥ 30% of planned EVA time kept for return | crew | route stats | *Assumption*; no oxygen modeling |
| Wheel slip → stop and request input | > 35% | rover | rover sensors (scenario) | Scenario value, `simulated` |

Route cost: hard exclusions first, then a weighted cost over the remaining cells (slope, roughness, distance to rockfall buffer, unscouted penalty, length). A short route never compensates for a safety violation.

## 6. Robots: sensors, coverage and decisions

### Sensor → software map

| Sensor (CAD) | Detects | Shown as | Stand-in this weekend | Evidence |
| --- | --- | --- | --- | --- |
| Stereo cameras (mast) | 3D terrain, rocks, slopes | `rover_checked` coverage | HiRISE DTM + image | `nasa_derived` / `simulated` |
| Hazard cameras | obstacles at the wheels | discovery event | planted test hazard | `simulated` |
| Thermal camera (mast, drone) | loose vs solid ground, shadowed hazards | `S` hazards, soft ground | THEMIS (orbital analog) | `inferred` |
| Ground-penetrating radar | voids under the route | `U` hazards | SWIM regional context | `inferred` |
| Wheel-slip sensing | soft ground that looks firm | triggers request-input card | scenario values | `simulated` |
| Drone camera (survey) | cliff face, areas the rover cannot see | `O` hazards, `drone_checked` | HiRISE 25 cm image | `nasa_derived` / `inferred` |
| Drone camera (perched) | rockfall, dust devils during the EVA | alert bar | scripted alerts | `simulated` |

Sensor ranges (modeled, per sensor) define the coverage footprint along each path.

### Sensor coverage model (v1, for `coverage.geojson`)

Planning values for our concept rover and drone, anchored to the closest flown instrument. Values marked *assumption* are ours and are labeled as modeled in the app.

| Sensor | Flown analog and published figure | Coverage rule we use |
| --- | --- | --- |
| Mast stereo cameras | Perseverance Navcam: 96° × 73° field of view, 42.4 cm stereo baseline | `rover_checked` = rover path buffered **10 m each side** (*assumption*: range where stereo 3D is reliable enough to see rocks near the 35 cm wheel-drop limit) |
| Hazard cameras | Perseverance Hazcam: 136° × 102° field of view; earlier MER Hazcams mapped terrain about 3 m ahead | Used only for the discovery event (wheel-level obstacles); no extra coverage area |
| Thermal camera | No Perseverance thermal imager to copy | Same 10 m corridor as the stereo cameras (*assumption*); findings stay `inferred` |
| Ground-penetrating radar | Perseverance RIMFAX: depth ≤ 10 m, vertical resolution 15–30 cm, soundings every 10–20 cm along the path | A line under the rover only; confirms the path itself, adds no width |
| Wheel-slip sensing | Rover visual odometry vs wheel turns | The rover's own track only |
| Drone survey camera | Ingenuity at 10 m altitude: Navcam about 3.6 cm/pixel, color camera about 0.53 cm/pixel; typical scouting altitude 10–12 m | `drone_checked` = the planned survey box (flight lines about 20 m apart, *assumption*) |
| Drone perched camera | No flown analog (Ingenuity never perched to watch) | View cone toward the scarp, about 150 m range (*assumption*); used for overwatch alerts, not for `drone_checked` |

Everything outside these footprints stays `orbit_only` or `unscouted`.

### Rover decision states

| State | Condition | Result |
| --- | --- | --- |
| `continue` | terrain within all limits | keep driving |
| `reroute` | blocked, viable alternative exists | replan locally |
| `request_input` | uncertain reading (e.g. slip > 35% on terrain that looks firm) | stop, send evidence to the habitat |
| `stop` | critical hazard or no viable route | stop safely, keep observations |

Communication loss: continue only within pre-approved limits; otherwise `stop` and store observations.

Routine decisions are deterministic code. An LLM (stretch goal) only writes the crew briefing for `request_input`, from mission data, on the habitat computer, never on the rover, and never decides.

### Discovery scenario (one, end to end)

1. Orbital data gives the prior assessment of the corridor.
2. The simulated rover finds a hazard on the planned crew route (`hz-sim-001`, `simulated`).
3. Both records are kept: the orbital prediction and the rover observation.
4. The planner re-runs with the new hazard: `rt-crew-main-v1` → `rt-crew-main-v2`.
5. The app shows before, the request-input card, and after.

The pipeline precomputes both versions; nothing is simulated live in the browser.

## 7. Pipeline steps (Nic)

1. Download DTM `.IMG` and the RED_C orthoimage into `pipeline/raw/`.
2. **Validate:** projection (equirectangular), datum, pixel size, no-data value, longitude convention (212.106°E → −147.894), image/DTM alignment on visible landmarks.
3. Locate the actual scarp in the image (not the scene center); crop to the scarp, its foot and the route area.
4. **DTM quality control:** mask no-data; flag artifact patterns (seams, box-shaped errors, faceting in shadow) → `artifact` hazards with `inspection_required`.
5. Terrain analysis: slope, roughness, scarp height, distance to scarp foot and edge.
6. Hazards from `hazard_rules.json`, each with evidence and source.
7. Crew main route; backup route by penalizing the main corridor and re-running; report shared length and shared hazards; emit `no_viable_route` / `backup_unavailable` when true.
8. Rover path derived from the crew route where rover-traversable; gaps → drone coverage or `inspection_required`.
9. Coverage from modeled sensor footprints.
10. Discovery scenario: insert the simulated hazard, re-run, export before/after.
11. Shadow layer from the DTM using the image's Sun geometry (labeled illustrative lighting).
12. Reproject outputs to Mars lat/lon, downsample, export, validate against the schema.

Route search: cost grid from step 6, `skimage.graph.route_through_array` on the metric grid; convert the path to lat/lon only at export.

## 8. Validation

- **Automated (Python):** schema validation of every output; synthetic-grid tests (steep wall, no-data hole, blocked corridor, no backup possible); identical outputs for identical inputs; route stats recomputed from geometry match `stats`.
- **Manual (Yasser):** every layer overlays the right terrain on the basemap; the discovery scenario visibly changes the route.
- A correct-looking overlay does not prove the numbers are right; both checks are required.
- The app shows a visible warning when a file is missing or has the wrong `schema_version`, never a silent empty layer.

## 9. App (Yasser)

- Default view: crew route and critical hazards only; everything else behind the layers panel (progressive disclosure).
- Four stage buttons (`orbital`, `rover`, `drone`, `eva`) showing and hiding layers.
- Hazards styled by `type` and `evidence`; legend that says "simulated" in words, not color alone.
- Coverage layer; crew vs rover route styles; route status messages.
- Request-input card: location, sensor evidence, hazard type, uncertainty, options, affected routes.
- Evidence panel: clicking a layer or hazard shows source, evidence type and limitations.
- Drone perch and view cone, alert bar, camera panel with ground photos (labeled example terrain), robot pop-ups with CAD images.
- Optional: NASA DONKI space-weather feed, labeled "space weather context", not a local radiation reading.

## 10. Schedule and cut lines

| When | Yasser | Nic | Sync |
| --- | --- | --- | --- |
| Sat, start | Placeholders per section 4; Mars Trek tiles | Scaffold + Pages deploy; downloads | Contract frozen |
| Sat, block 2 | Stages, layers, legends | Validate, QC, slope, hazards | One real overlay aligned |
| Sat, evening | Coverage and route display | Crew main + backup routes, stats | Real route visible |
| Sun, morning | Request-input card, drone, alerts, evidence panel | Rover path, coverage, discovery, shadow | Before/after passes |
| Sun, ~11 AM | Full integration | Final exports + validation | End-to-end test |
| Sun, lunch | **Feature freeze** | **Feature freeze** | Go/no-go (Yasser) |
| Sun, afternoon | Recording, submission | Tests, methodology | Public link verified |

**If behind, drop in this order:** shadow layer → communication-loss rule → optimized rover path (use "follows crew route, gaps marked") → AI briefings.
**Never drop:** alignment validation, no-data masking, evidence labels, safe failure states, the one discovery scenario.

## 11. Acceptance criteria (feature freeze)

- [ ] Deployed map with correctly aligned NASA data at Milankovič
- [ ] Hazards visible and labeled by type and evidence
- [ ] Crew main route plus backup, or an honest `backup_unavailable`, with stats
- [ ] Coverage layer showing unscouted terrain
- [ ] One before/after discovery scenario that visibly changes the route
- [ ] Validation script passes and the manual overlay check is done

## 12. Sources

- Software: [NumPy](https://numpy.org/doc/), [Rasterio](https://rasterio.readthedocs.io/), [SciPy ndimage](https://docs.scipy.org/doc/scipy/reference/ndimage.html), [scikit-image](https://scikit-image.org/docs/stable/), [pytest](https://docs.pytest.org/); versions in `pipeline/requirements.txt`.
- [Challenge statement](https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/)
- [HiRISE DTM: Scarps in Milankovic Crater](https://hirise.lpl.arizona.edu/dtm/ESP_071085_2345) · [ESP_071006_2345](https://hirise.lpl.arizona.edu/ESP_071006_2345) (NASA/JPL-Caltech/UArizona)
- Dundas et al. (2018), *Exposed subsurface ice sheets in the Martian mid-latitudes*, Science
- [LPSC abstract on ice scarps (DLR)](https://elib.dlr.de/217131/1/2071.pdf)
- [JPL Mars Trek](https://trek.nasa.gov/mars/) · [USGS-NASA geologic maps](https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars)
- [NASA exploration EVA testing and analogs (NTRS)](https://ntrs.nasa.gov/api/citations/20210000827/downloads/Exporation%20EVA%20Testing%20and%20Analogs%2020210000827.pdf)
- [NASA Walkback test (NTRS)](https://ntrs.nasa.gov/api/citations/20080013604/downloads/20080013604.pdf)
- [Perseverance driving updates (Oct 2026)](https://newspaceeconomy.ca/2026/10/22/perseverance-driving-updates-support-longer-autonomous-travel-on-mars/?amp=1)
- [JPL Open Source Rover](https://github.com/nasa-jpl/open-source-rover) (Apache-2.0)
