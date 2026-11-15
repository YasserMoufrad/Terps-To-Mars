import json, sys
s = sys.argv[1]
F = json.load(open(f"{s}/geo/final.json")); O = json.load(open(f"{s}/geo/option1.json"))
p, b = O["upper_scarp__current_parking"], O["backup_facing_upper"]
F["points"]["observation_primary"] = {"lon": p["lon"], "lat": p["lat"], "elevation_m": O["points_elevation_m"]["primary"]}
F["points"]["observation_backup"] = {"lon": b["lon"], "lat": b["lat"], "elevation_m": O["points_elevation_m"]["backup"]}
F["walk_main"] = {k: O["primary_walk"][k] for k in ("coords", "length_m", "max_slope_deg")}
F["walk_backup"] = {k: O["backup_walk"][k] for k in ("coords", "length_m", "max_slope_deg", "fraction_within_25m_of_main")}
F["view"] = {k: O["primary_view"][k] for k in ("face_height_m", "distance_from_foot_m", "rockfall_buffer_m")}
F["view"]["target"] = "second (upper) scarp, bluish in HiRISE color (Geury ice_upper_band)"
F["upper_profiles"] = O["upper_profiles"]
F["upper_scarp"] = O["upper_scarp"]
F["backup_view"] = {"walk_from_parking_m": b["walk_m"], "separation_m": b["separation_m"]}
F["steep_cells_in_15m_disc"].update({"observation_primary": O["steep_cells_in_15m_disc"]["primary"], "observation_backup": O["steep_cells_in_15m_disc"]["backup"]})
json.dump(F, open(f"{s}/geo/final_v2.json", "w"), indent=1)
print("merged", F["points"]["observation_primary"], F["view"])
