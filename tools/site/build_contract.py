"""Write the app's placeholder contract files (schema 1.1) from DTM-derived geometry.

Inputs: final.json (points + routes on the DTM), site_report.json (scarp profiles), the current
public/data/mission.json (Nic-reviewed wording kept). Still `placeholder: true`: Nic's pipeline
replaces these with its official export. Lengths use the pipeline's own mars_distance.
"""
import json
import sys
from pathlib import Path
from pipeline.routing import mars_distance

final_path, report_path, data_dir = sys.argv[1:4]
F, R = json.load(open(final_path)), json.load(open(report_path))
data = Path(data_dir)
WALK, DRIVE, WORK, EVA = 20.0, 5000 / 60, 20, 240
TRAVEL = EVA * 0.7
DEG_M = 59160.0
P = F["points"]
pt = lambda name: [P[name]["lon"], P[name]["lat"]]


def length(coords):
    """Metres along a [lon, lat] polyline on the Mars sphere (pipeline mars_distance)."""
    return sum(mars_distance(a, b) for a, b in zip(coords, coords[1:]))


def crew_route(rid, kind, version, legs, max_slope):
    """Crew route feature from ordered legs [(mode, coords)], with per-leg stats and walkback."""
    coords, out_legs = [], []
    for mode, c in legs:
        start = 0 if not coords else len(coords) - 1
        coords += c if not coords else c[1:]
        L = length(c)
        out_legs.append({"mode": mode, "from": start, "to": len(coords) - 1, "length_m": round(L, 1),
                         "est_time_min": round(L / (DRIVE if mode == "drive" else WALK), 1)})
    one_way = sum(l["est_time_min"] for l in out_legs)
    drive_m = sum(l["length_m"] for l in out_legs if l["mode"] == "drive")
    total = length(coords)
    props = {"id": rid, "kind": kind, "agent": "crew", "version": version, "status": "inspection_required",
             "stats": {"length_m": round(total, 3), "round_trip_m": round(2 * total, 3), "est_time_min": round(2 * one_way, 1),
                       "elevation_gain_m": round(abs(P["observation_primary"]["elevation_m"] - P["habitat"]["elevation_m"]), 1),
                       "max_slope_deg": max_slope, "shared_with_main_m": 0},
             "legs": out_legs}
    if drive_m:
        props["walkback_min"] = round(drive_m / WALK, 1)
    return {"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}}


d1, d2 = F["drive_v1"]["coords"], F["drive_v2"]["coords"]
w1, w2 = F["walk_main"]["coords"], F["walk_backup"]["coords"]
main_v1 = crew_route("rt-crew-main-v1", "main", "before", [("drive", d1), ("walk", w1)], max(F["drive_v1"]["max_slope_deg"], F["walk_main"]["max_slope_deg"]))
main_v2 = crew_route("rt-crew-main-v2", "main", "after", [("drive", d2), ("walk", w1)], max(F["drive_v2"]["max_slope_deg"], F["walk_main"]["max_slope_deg"]))
backup = crew_route("rt-crew-backup-v2", "backup", "after", [("walk", w2), ("drive", d2[::-1])], max(F["drive_v2"]["max_slope_deg"], F["walk_backup"]["max_slope_deg"]))
backup["properties"]["stats"]["shared_with_main_m"] = round(length(d2), 1)
guess_coords = [pt("habitat"), pt("observation_primary")]
guess = {"type": "Feature", "properties": {"id": "rt-orbital-guess-v1", "kind": "orbital_guess", "agent": "crew", "version": "before",
         "status": "inspection_required", "stats": {"length_m": round(length(guess_coords), 3), "round_trip_m": round(2 * length(guess_coords), 3),
         "est_time_min": round(2 * length(guess_coords) / WALK, 1), "elevation_gain_m": 120, "max_slope_deg": 70, "shared_with_main_m": 0}},
         "geometry": {"type": "LineString", "coordinates": guess_coords}}
sim = F["sim_discovery"]["center"]
i_sim = min(range(len(d1)), key=lambda i: mars_distance(d1[i], sim))
rover = lambda rid, version, c: {"type": "Feature", "properties": {"id": rid, "kind": "rover_path", "agent": "rover", "version": version, "status": "ok",
    "stats": {"length_m": round(length(c), 3), "round_trip_m": round(length(c), 3), "est_time_min": round(length(c) / 2.5, 1),
              "elevation_gain_m": 120, "max_slope_deg": 15, "shared_with_main_m": 0}}, "geometry": {"type": "LineString", "coordinates": c}}
rover_v2 = d2 + w1[1:] + w2[1:] + d2[::-1][1:]
routes = [guess, main_v1, main_v2, backup, rover("rt-rover-v1", "before", d1[:i_sim + 1]), rover("rt-rover-v2", "after", rover_v2)]

# ---- Hazards from the measured scarp ----
prof = sorted(R["profiles"], key=lambda p: p["lon"])
edge = [[p["lon"], p["edge_lat"]] for p in prof]
foot = [[p["lon"], p["foot_lat"]] for p in prof]
setback = [[p["lon"], p["edge_lat"] - 20 / DEG_M] for p in prof]
buffer_line = [[p["lon"], p["foot_lat"] + max(p["apron_m"], p["height_m"]) / DEG_M] for p in prof]
band = lambda south, north: [south + north[::-1] + [south[0]]]
hz = lambda hid, t, cat, sev, ev, stage, src, note, coords: {"type": "Feature", "properties": {"id": hid, "type": t, "category": cat, "severity": sev,
    "evidence": ev, "agent": "both", "stage": stage, "source": src, "note": note}, "geometry": {"type": "Polygon", "coordinates": coords}}
heights = sorted(p["height_m"] for p in prof)
DTM = "HiRISE DTM DTEEC_071085_2345_071006_2345_A01 (1 m), measured by Yasser's agent with the pipeline's slope code"
sw, ne = F["sim_discovery"]["box_sw_ne"]
hazards = [
    hz("hz-face-001", "U", "slope", "exclude", "nasa_derived", "orbital", DTM + "; face traced in HiRISE ESP_071006_2345 (0.25 m)",
       f"North-facing ice scarp face: {heights[0]:.0f}-{heights[-1]:.0f} m tall (median {R['scarp_height_m_median']:.0f} m), steepest 64-75 degrees. Far beyond the 20 degree crew limit.", band(edge, foot)),
    hz("hz-edge-001", "U", "edge", "exclude", "inferred", "orbital", "20 m cliff setback rule (hazard_rules.json) applied to the traced edge",
       "Cliff-top setback: edge collapse risk within 20 m of the scarp top.", band(setback, edge)),
    hz("hz-rockfall-001", "O", "rockfall", "exclude", "inferred", "orbital", "Rockfall rule max(apron, 1 x scarp height) from the foot (hazard_rules.json, provisional) on DTM-measured heights",
       "Rockfall zone below the actively retreating face; width varies with the measured height and apron.", band(foot, buffer_line)),
    hz("hz-shadow-001", "S", "shadow", "caution", "inferred", "orbital", "Illustrative: pole-facing face, sun about 42 degrees up (image geometry)",
       "Ground at the foot of the pole-facing cliff is in shadow much of the day; illustrative lighting, not a forecast.",
       band(foot, [[p["lon"], p["foot_lat"] + p["height_m"] / 0.9 / DEG_M] for p in prof])),
    hz("hz-sim-001", "U", "soft_ground", "exclude", "simulated", "rover", "Simulated rover observation, discovery scenario disc-001",
       "Simulated: rover wheel slip of 38 percent on ground that looked firm from orbit.",
       [[[sw[0], sw[1]], [ne[0], sw[1]], [ne[0], ne[1]], [sw[0], ne[1]], [sw[0], sw[1]]]]),
]
# Second (upper) scarp, traced on the DTM where Geury found a second bluish band (ice_zone_v2 ice_upper_band).
if F.get("upper_profiles"):
    up = sorted(F["upper_profiles"], key=lambda p: p["lon"])
    u_edge = [[p["lon"], p["edge_lat"]] for p in up]
    u_foot = [[p["lon"], p["foot_lat"]] for p in up]
    u_setback = [[p["lon"], p["edge_lat"] - 20 / DEG_M] for p in up]
    u_buffer = [[p["lon"], p["foot_lat"] + p["buffer_m"] / DEG_M] for p in up]
    uh = sorted(p["height_m"] for p in up)
    hazards += [
        hz("hz-face-002", "U", "slope", "exclude", "nasa_derived", "orbital", DTM + "; band found bluish by Geury in HiRISE color (ice_zone_v2)",
           f"Second north-facing ice-consistent scarp: {uh[0]:.0f}-{uh[-1]:.0f} m tall on the DTM, faces up to about 64-67 degrees.", band(u_edge, u_foot)),
        hz("hz-edge-002", "U", "edge", "exclude", "inferred", "orbital", "20 m cliff setback rule applied to the second scarp's traced edge",
           "Cliff-top setback of the second scarp: edge collapse risk within 20 m of its top.", band(u_setback, u_edge)),
        hz("hz-rockfall-002", "O", "rockfall", "exclude", "inferred", "orbital", "Rockfall rule max(apron, 1 x height) from the second scarp's foot (apron capped at 100 m)",
           "Rockfall zone below the second scarp.", band(u_foot, u_buffer)),
    ]
old = json.load(open(data / "hazards.geojson"))
keep = [f for f in old["features"] if f["properties"]["id"] == "hz-slope-003"]  # Geury's southern scarp (inferred)
json.dump({"type": "FeatureCollection", "schema_version": "1.1", "placeholder": True, "features": hazards + keep}, open(data / "hazards.geojson", "w"), indent=2)

# ---- Coverage ----
def bbox(coords, pad_m=25):
    """Padded bounding box polygon around coords."""
    lons, lats = [c[0] for c in coords], [c[1] for c in coords]
    dl, dn = pad_m / (DEG_M * 0.585), pad_m / DEG_M
    w, s, e, n = min(lons) - dl, min(lats) - dn, max(lons) + dl, max(lats) + dn
    return [[[w, s], [e, s], [e, n], [w, n], [w, s]]]
perch = R["candidates"]["drone_perch"]
cone = [[[perch["lon"], perch["lat"]], [-147.9060, 54.16365], [-147.8960, 54.16360], [perch["lon"], perch["lat"]]]]
cov = lambda cid, state, simulated, sensor, coords: {"type": "Feature", "properties": {"id": cid, "state": state, "simulated": simulated, "sensor": sensor},
    "geometry": {"type": "Polygon", "coordinates": coords}}
coverage = [
    cov("cov-orbit-001", "orbit_only", False, "none", [[[-147.925, 54.124], [-147.880, 54.124], [-147.880, 54.172], [-147.925, 54.172], [-147.925, 54.124]]]),
    cov("cov-rover-001", "rover_checked", True, "stereo_cam", bbox(d2)),
    cov("cov-rover-002", "rover_checked", True, "stereo_cam", bbox(w1 + w2)),
    cov("cov-drone-001", "drone_checked", True, "drone_cam", band(edge, buffer_line)),
    cov("cov-drone-perch", "drone_checked", True, "drone_cam", cone),
    cov("cov-unscouted-001", "unscouted", False, "none", [[[-147.918, 54.1655], [-147.904, 54.1655], [-147.904, 54.1710], [-147.918, 54.1710], [-147.918, 54.1655]]]),
]
json.dump({"type": "FeatureCollection", "schema_version": "1.1", "placeholder": True, "features": coverage}, open(data / "coverage.geojson", "w"), indent=2)
json.dump({"type": "FeatureCollection", "schema_version": "1.1", "placeholder": True, "features": routes}, open(data / "routes.geojson", "w"), indent=2)

# ---- mission.json ----
m = json.load(open(data / "mission.json"))
m["schema_version"] = "1.1"
m["site"]["lat"], m["site"]["lon"] = 54.1640, -147.8990
m["endpoints"] = {"habitat": {"lat": P["habitat"]["lat"], "lon": P["habitat"]["lon"]},
                  "observation_primary": {"lat": P["observation_primary"]["lat"], "lon": P["observation_primary"]["lon"]},
                  "observation_backup": {"lat": P["observation_backup"]["lat"], "lon": P["observation_backup"]["lon"]}}
m["drone"]["perch"] = {"lat": perch["lat"], "lon": perch["lon"]}
m["discovery"]["location"] = {"lat": sim[1], "lon": sim[0]}
v1p, v2p = main_v1["properties"], main_v2["properties"]
dd = v2p["legs"][0]["length_m"] - v1p["legs"][0]["length_m"]
m["discovery"]["options"][0]["consequence"] = f"+{dd:.0f} m of driving, +{dd / DRIVE:.1f} min each way"
st = {s["id"]: s for s in m["stages"]}
st["rover"]["text"] = ("In the sols before the walk, the rover drives the crew-rover route out and checks the walking paths. "
                       "It finds soft ground the orbit could not see and the drive is replanned.")
st["drone"]["text"] = ("The simulated drone perches on the pit floor facing the tallest part of the ice cliff (about 70 m), which the crew cannot "
                       "reach on this EVA, and images the face and rockfall zone.")
walk_one_way = sum(l["length_m"] for l in main_v2["properties"]["legs"] if l["mode"] == "walk")
st["eva"]["text"] = (f"Review the proposed trip: two astronauts drive the crew rover 2.3 km to a parking point on the plain, then walk about "
                     f"{round(walk_one_way, -1):.0f} m around the cliffs to a viewpoint facing a bluish, ice-consistent cliff face. "
                     "None of this is crew clearance.")
legsum = lambda p, mode, key: sum(l[key] for l in p["legs"] if l["mode"] == mode)
travel = v2p["stats"]["est_time_min"]
walkback_total = legsum(v2p, "drive", "est_time_min") + 2 * legsum(v2p, "walk", "est_time_min") + WORK + v2p["walkback_min"]
fp = min(prof, key=lambda p: abs(p["lon"] - P["observation_primary"]["lon"]))
st["eva"]["stats"] = {
    "Drive (crew rover)": f"{legsum(v2p, 'drive', 'length_m') / 1000:.2f} km each way, assumed 5 km/h",
    "Walk": f"{legsum(v2p, 'walk', 'length_m'):.0f} m each way at 20 m/min",
    "Travel time": f"{travel:.0f} min round trip + {WORK} min at the site",
    "Budget": f"Within modeled budget ({travel + WORK:.0f} of {TRAVEL:.0f} min)" if travel + WORK <= TRAVEL else f"Exceeds modeled budget ({travel + WORK:.0f} of {TRAVEL:.0f} min)",
    "Walkback": f"{v2p['walkback_min']:.0f} min on foot if the crew rover fails; {walkback_total:.0f} of {EVA} min EVA",
    "View": f"Bluish cliff {F['view'].get('face_height_m', fp['height_m']):.0f} m tall here, viewpoint {F['view']['distance_from_foot_m']:.0f} m from its foot (rockfall zone {F['view']['rockfall_buffer_m']:.0f} m)",
    "Route status": "Needs inspection: budgets fit, but the crew-rover drive is not yet modeled",
}
st["orbital"]["stats"] = {"Detail": "1 m terrain, 25 cm imagery", "Ice cliff": f"{R['scarp_height_m_median']:.0f} m tall (median), 64-75 degree face", "Route": "Unverified"}
json.dump(m, open(data / "mission.json", "w"), indent=2)
for p in (data / "routes.geojson", data / "hazards.geojson", data / "coverage.geojson", data / "mission.json"):
    p.write_text(p.read_text() + "\n")
print(json.dumps({"travel_plus_work": travel + WORK, "walkback_total": walkback_total, "walk_m_round_trip": 2 * legsum(v2p, "walk", "length_m"),
                  "drive_detour_m": round(dd, 1), "routes": [f["properties"]["id"] for f in routes]}, indent=1))
