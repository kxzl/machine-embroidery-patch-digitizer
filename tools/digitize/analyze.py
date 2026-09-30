#!/usr/bin/env python3
"""Analyze a raster image: separate into a small palette and report connected
component statistics per color, to decide satin (linework) vs fill regions.

Outputs:
  - work/posterized.png   : posterized preview for human review
  - work/regions.json     : per-color component stats
"""
import json
import os
import sys

from PIL import Image
import numpy as np
from scipy import ndimage

IMG = sys.argv[1] if len(sys.argv) > 1 else "Scavenger's_Daughter_by_the_dusty_druid.webp"
N_COLORS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
OUTDIR = "work"
os.makedirs(OUTDIR, exist_ok=True)

im = Image.open(IMG).convert("RGB")
q = im.quantize(colors=N_COLORS, method=Image.MEDIANCUT)
pal = q.getpalette()
indices = np.array(q)

# map palette index -> rgb
palette_rgb = [tuple(pal[i * 3:i * 3 + 3]) for i in range(256)]

# posterized preview
q_rgb = q.convert("RGB")
q_rgb.save(os.path.join(OUTDIR, "posterized.png"))

# count per index
hist = q.histogram()
print("== palette (index, count, rgb) ==")
for i, cnt in enumerate(hist):
    if cnt:
        print(f"  idx={i} count={cnt:8d} rgb={palette_rgb[i]}")

# classify background = lightest color (max sum), skip it
ordered = sorted((i for i in range(256) if hist[i]), key=lambda i: sum(palette_rgb[i]), reverse=True)
bg_idx = ordered[0]
print(f"background (skipped) = idx {bg_idx} rgb {palette_rgb[bg_idx]}")

regions = {}
for idx in ordered[1:]:
    rgb = palette_rgb[idx]
    mask = (indices == idx)
    mask = ndimage.binary_opening(mask, structure=np.ones((3, 3)))
    labels, n = ndimage.label(mask)
    comps = []
    for lab in range(1, n + 1):
        c = (labels == lab)
        area = int(c.sum())
        if area < 20:  # ignore specks
            continue
        ys, xs = np.where(c)
        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        # distance transform = distance to nearest background pixel inside component
        dt = ndimage.distance_transform_edt(c)
        maxdt = float(dt.max()) if area else 0.0
        comps.append({
            "area": area,
            "bbox": bbox,
            "width": bbox[2] - bbox[0] + 1,
            "height": bbox[3] - bbox[1] + 1,
            "max_thickness_half": round(maxdt, 2),
        })
    comps.sort(key=lambda c: -c["area"])
    regions["#%02x%02x%02x" % rgb] = {
        "rgb": list(rgb),
        "components": len(comps),
        "components_detail": comps,
    }
    print(f"\n== color {rgb} : {len(comps)} components ==")
    for c in comps[:12]:
        print(f"   area={c['area']:8d} bbox={c['bbox']} w={c['width']} h={c['height']} halfthick={c['max_thickness_half']}")

with open(os.path.join(OUTDIR, "regions.json"), "w") as f:
    json.dump(regions, f, indent=2)

print(f"\nwrote {OUTDIR}/posterized.png and {OUTDIR}/regions.json")
