"""Write data/site outputs: DTM-checked points, scarp measurements, and audit configs."""
import json
import sys
from pathlib import Path

final_path, report_path, site_dir = sys.argv[1:4]
F, R = json.load(open(final_path)), json.load(open(report_path))
site = Path(site_dir)
P = F["points"]
perch = R["candidates"]["drone_perch"]
SRC = "Checked on HiRISE DTM DTEEC_071085_2345_071006_2345_A01 by Yasser's agent (pipeline slope code); 0 cells >= 20 deg in the 15 m uncertainty disc"
feat = lambda pid, name, lon, lat, where, z: {"type": "Feature", "properties": {"id": pid, "name": name, "where": where, "elevation_m": z, "source": SRC},
                                              "geometry": {"type": "Point", "coordinates": [lon, lat]}}
pts = [
    feat("habitat", "Habitat", P["habitat"]["lon"], P["habitat"]["lat"], "Geury's habitat moved 59 m to flat ground (his spot had 24 cells >= 20 deg within 15 m)", P["habitat"]["elevation_m"]),
    feat("parking", "Crew-rover parking", P["parking"]["lon"], P["parking"]["lat"], "High plain just SE of the scarp's east end; reachable by rover (< 24 deg, roughness <= 0.5 m)", P["parking"]["elevation_m"]),
    feat("observation_primary", "Viewpoint", P["observation_primary"]["lon"], P["observation_primary"]["lat"],
         (f"Faces the {F['view'].get('target', 'scarp')}: face {F['view']['face_height_m']:.0f} m tall here, viewpoint {F['view']['distance_from_foot_m']:.0f} m from its foot "
          f"(rockfall zone {F['view']['rockfall_buffer_m']:.0f} m). Moved from the east-end bench: that spot faced the non-bluish east end and sat 20 m from the second scarp's edge"),
         P["observation_primary"]["elevation_m"]),
    feat("observation_backup", "Backup viewpoint", P["observation_backup"]["lon"], P["observation_backup"]["lat"],
         (f"Faces the same bluish second scarp; {F['backup_view']['separation_m']:.0f} m from the primary (independent), {F['backup_view']['walk_from_parking_m']:.0f} m walk from parking"
          if F.get("backup_view") else "Same bench, separate approach"), P["observation_backup"]["elevation_m"]),
    feat("drone_perch", "Drone perch", perch["lon"], perch["lat"], f"Pit floor facing the tallest part of the face ({perch['scarp_height_here_m']:.0f} m), {perch['distance_from_foot_m']:.0f} m from the foot; drone access only", perch["elevation_m"]),
]
json.dump({"type": "FeatureCollection", "name": "site_points_dtm", "description": "DTM-checked candidate points (replace Geury's first pass). Candidates only; nothing here is crew clearance.",
           "features": pts}, open(site / "site_points_dtm.geojson", "w"), indent=1)
summary = {k: R[k] for k in ("dtm", "resolution_m", "thresholds_deg", "uncertainty_radius_m", "scarp_height_m_median", "scarp_height_m_range", "apron_m_median", "rockfall_rule")}
summary["note"] = ("Per traced profile (data/site/scarp_lines.geojson): top_z = median elevation 15 m south of the edge, floor_z = 15 m north of the foot, "
                   "height = top_z - floor_z, apron = distance north of the foot until slope stays < 15 deg for 10 m (rough pit floor inflates it in the west). "
                   "Rockfall zone per profile = max(apron, 1 x height) from the foot.")
summary["profiles"] = R["profiles"]
summary["geury_first_pass_points_disc_status_exclude_caution_invalid"] = R["geury_points_disc_status_exclude_caution_invalid"]
summary["routes_on_dtm"] = {k: {kk: vv for kk, vv in F[k].items() if kk != "coords"} for k in ("drive_v1", "drive_v2", "walk_main", "walk_backup")}
json.dump(summary, open(site / "scarp_measurements.json", "w"), indent=1)

pt = lambda name: {"lat": P[name]["lat"], "lon": P[name]["lon"]}
base = {"dtm": "pipeline/raw/DTEEC_071085_2345_071006_2345_A01.IMG", "speed_m_min": 20, "observation_minutes": 20, "position_uncertainty_m": 15}
walk_only = {"_note": "Habitat -> viewpoints walking the whole way (expected infeasible: ~4 km straight-line round trip). DTM-checked points.",
             "window_latlon": {"south": 54.120, "west": -147.925, "north": 54.172, "east": -147.885},
             "points": {"habitat": pt("habitat"), "observation_primary": pt("observation_primary"), "observation_backup": pt("observation_backup")},
             "eva_minutes": 240, **base}
drive_min = round(2 * F["drive_v2"]["length_m"] / (5000 / 60), 1)
from_parking = {"_note": f"Walking part of drive-then-walk: 'habitat' here is the crew-rover PARKING point. Drive {F['drive_v2']['length_m']:.0f} m each way "
                         f"({drive_min} min round trip at 5 km/h) is not audited here; eva_minutes = (168 - {drive_min}) / 0.7 so the audit's 70% matches what is left after the drive.",
                "window_latlon": {"south": 54.158, "west": -147.905, "north": 54.176, "east": -147.885},
                "points": {"habitat": pt("parking"), "observation_primary": pt("observation_primary"), "observation_backup": pt("observation_backup")},
                "eva_minutes": int((168 - drive_min) / 0.7), **base}
json.dump(walk_only, open(site / "feasibility_audit.json", "w"), indent=2)
json.dump(from_parking, open(site / "feasibility_audit_from_parking.json", "w"), indent=2)
for p in ("site_points_dtm.geojson", "scarp_measurements.json", "feasibility_audit.json", "feasibility_audit_from_parking.json"):
    (site / p).write_text((site / p).read_text() + "\n")
print("eva_minutes from parking:", from_parking["eva_minutes"], "drive round trip min:", drive_min)
