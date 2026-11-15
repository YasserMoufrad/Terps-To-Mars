import json, sys
s = sys.argv[1]
F = json.load(open(f"{s}/geo/final_v2.json"))
up = sorted(F["upper_profiles"], key=lambda p: p["lon"])
L = json.load(open("data/site/scarp_lines.geojson"))
L["features"] = [f for f in L["features"] if not f["properties"]["id"].startswith("upper-")]
src = "Traced on the HiRISE DTM (cells >= 30 deg between 54.1660 and 54.1690 N, median-filtered) where Geury found a second bluish band (ice_zone_v2 ice_upper_band)"
L["features"] += [
  {"type": "Feature", "properties": {"id": "upper-scarp-edge", "name": "Second scarp top edge", "evidence": "nasa_derived", "source": src}, "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["edge_lat"]] for p in up]}},
  {"type": "Feature", "properties": {"id": "upper-scarp-foot", "name": "Second scarp foot", "evidence": "nasa_derived", "source": src}, "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["foot_lat"]] for p in up]}}]
open("data/site/scarp_lines.geojson", "w").write(json.dumps(L, indent=1) + "\n")
M = json.load(open("data/site/scarp_measurements.json"))
M["upper_scarp"] = {**F["upper_scarp"], "profiles": up, "note": "Second north-facing scarp on the lobe's north-east margin. Apron capped at 100 m (rough floor). The old east-end viewpoint sat 20.0 m from its edge."}
M["routes_on_dtm"]["walk_main"] = {k: v for k, v in F["walk_main"].items() if k != "coords"}
M["routes_on_dtm"]["walk_backup"] = {k: v for k, v in F["walk_backup"].items() if k != "coords"}
open("data/site/scarp_measurements.json", "w").write(json.dumps(M, indent=1) + "\n")
print("lines:", [f["properties"]["id"] for f in L["features"]])
