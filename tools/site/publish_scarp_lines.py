import json
pub = json.load(open("public/data/scarp_lines.geojson", encoding="utf-8"))
site = json.load(open("data/site/scarp_lines.geojson", encoding="utf-8"))
pub["features"] = [f for f in pub["features"] if not f["properties"]["id"].startswith("upper-")]
pub["features"] += [f for f in site["features"] if f["properties"]["id"].startswith("upper-")]
pub["provenance"]["second_scarp"] = "upper-scarp-edge/foot: traced on the HiRISE DTM (cells >= 30 deg, 54.1660-54.1690 N, median-filtered) where Geury found a second bluish band; tools/site/second_scarp_viewpoints.py (PR #17)"
open("public/data/scarp_lines.geojson", "w", encoding="utf-8").write(json.dumps(pub, indent=1, ensure_ascii=False) + "\n")
print([f["properties"]["id"] for f in pub["features"]])
