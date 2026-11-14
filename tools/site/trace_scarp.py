"""Trace the shadowed scarp face (dark, rough band) in Nic's HiRISE crop.

For each image column strip, the face is the run of rows whose smoothed brightness is
well below the smooth plain south of it. The southern boundary of that run is the
scarp top edge, the northern boundary the scarp foot. Outputs GeoJSON lines plus a
debug overlay. Imagery-only: no elevations; height and apron need the DTM.
"""
import json
import sys
import numpy as np
from PIL import Image, ImageDraw

img_path, bounds_path, out_geojson, out_debug = sys.argv[1:5]
b = json.load(open(bounds_path))
gray = np.asarray(Image.open(img_path).convert("L"), dtype=np.float32)
H, W = gray.shape
lat_of = lambda r: b["north"] - (r + 0.5) / H * (b["north"] - b["south"])
lon_of = lambda c: b["west"] + (c + 0.5) / W * (b["east"] - b["west"])
row_of = lambda lat: int((b["north"] - lat) / (b["north"] - b["south"]) * H)

STRIP = 120  # columns per sample (~27 m)
SMOOTH = 41  # rows (~10 m) moving average
plain = gray[row_of(54.1600):row_of(54.1575), :]  # smooth high plain south of the face
plain_mean, plain_std = float(plain.mean()), float(plain.std())
thresh = 95.0  # calibrated from profiles: plain 115-140, shadowed face < 90
search_top, search_bot = row_of(54.1662), row_of(54.1620)  # rows to search (north..south)

edge, foot = [], []
for c0 in range(0, W - STRIP, STRIP):
    prof = gray[search_top:search_bot, c0:c0 + STRIP].mean(axis=1)
    padded = np.pad(prof, SMOOTH // 2, mode="edge")  # edge padding, so the ends are not artificially dark
    prof = np.convolve(padded, np.ones(SMOOTH) / SMOOTH, mode="valid")
    dark = prof < thresh
    # Walk north from the plain: first long dark run is the face.
    r = len(dark) - 1
    while r > 0 and not dark[r]:
        r -= 1
    if r <= 0:
        continue
    south = r
    while r > 0 and dark[r]:
        r -= 1
    north = r
    if south - north < 40:  # < ~10 m: noise, not the face
        continue
    c = c0 + STRIP // 2
    edge.append([lon_of(c), lat_of(search_top + south)])
    foot.append([lon_of(c), lat_of(search_top + north)])

def smooth_line(pts, k=5):
    """Median-filter the latitudes so single noisy strips do not spike the line."""
    lats = np.array([p[1] for p in pts])
    out = []
    for i, p in enumerate(pts):
        lo, hi = max(0, i - k // 2), min(len(pts), i + k // 2 + 1)
        out.append([round(p[0], 6), round(float(np.median(lats[lo:hi])), 6)])
    return out

edge, foot = smooth_line(edge), smooth_line(foot)
# West of about -147.913 the dark run continues into shadowed hills north of the face;
# cap the foot at the median face width + 20 m so it stays on the face.
widths = sorted(f[1] - e[1] for e, f in zip(edge, foot))
cap = widths[len(widths) // 2] + 20 / 59160
foot = [[f[0], round(min(f[1], e[1] + cap), 6)] for e, f in zip(edge, foot)]
heights_m = [(f[1] - e[1]) * 59160 for e, f in zip(edge, foot)]
meta = {"strips": len(edge), "plain_mean": round(plain_mean, 1), "threshold": round(thresh, 1),
        "face_width_m_median": round(float(np.median(heights_m)), 1),
        "lon_range": [edge[0][0], edge[-1][0]] if edge else None,
        "edge_lat_range": [min(p[1] for p in edge), max(p[1] for p in edge)] if edge else None,
        "foot_lat_range": [min(p[1] for p in foot), max(p[1] for p in foot)] if foot else None}
src = "Traced from HiRISE ESP_071006_2345_RED_A (Nic's 0.25 m crop, registration RMS 0.86 m): shadowed face boundaries, imagery only"
fc = {"type": "FeatureCollection", "name": "scarp_lines", "description": src, "meta": meta, "features": [
    {"type": "Feature", "properties": {"id": "scarp-edge", "name": "Scarp top edge (south boundary of the shadowed face)", "evidence": "inferred"},
     "geometry": {"type": "LineString", "coordinates": edge}},
    {"type": "Feature", "properties": {"id": "scarp-foot", "name": "Scarp foot (north boundary of the shadowed face)", "evidence": "inferred"},
     "geometry": {"type": "LineString", "coordinates": foot}}]}
json.dump(fc, open(out_geojson, "w"), indent=1)

im = Image.open(img_path).convert("RGB").resize((1000, int(1000 * H / W)))
d = ImageDraw.Draw(im)
sx, sy = 1000 / W, im.size[1] / H
to_px = lambda lon, lat: ((lon - b["west"]) / (b["east"] - b["west"]) * 1000, (b["north"] - lat) / (b["north"] - b["south"]) * im.size[1])
d.line([to_px(*p) for p in edge], fill=(255, 140, 0), width=3)
d.line([to_px(*p) for p in foot], fill=(0, 255, 120), width=3)
im.save(out_debug, quality=90)
print(json.dumps(meta))
