#!/usr/bin/env python3
"""Generate a starter per-image YAML config for the digitize pipeline.

Detects the image palette (same k-means used by vectorize.py), prints the colors
in light->dark order, and writes a starter <name>.yaml the user can edit to
override stitch order / density / skip / border / trim.

Usage:
  python tools/digitize/make_config.py <image> [--colors N] [--out <name>.yaml]

Prints the run command to apply the config:
  tools/digitize/run.sh --config <out> <image>
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.cluster.vq import kmeans2
from skimage import morphology

_VALUE_FLAGS = {"--colors", "--out"}
_argc = sys.argv[1:]
args = []
_flags = {}
_i = 0
while _i < len(_argc):
    _a = _argc[_i]
    if _a.startswith("--"):
        if "=" in _a:
            _name, _val = _a[2:].split("=", 1)
            _flags[_name] = _val
        elif _a in _VALUE_FLAGS and _i + 1 < len(_argc) and not _argc[_i + 1].startswith("--"):
            _flags[_a[2:]] = _argc[_i + 1]
            _i += 1
        else:
            _flags[_a[2:]] = True
    elif _a.startswith("-") and _a != "-":
        pass
    else:
        args.append(_a)
    _i += 1

IMG = args[0] if len(args) > 0 else "Scavenger's_Daughter_by_the_dusty_druid.webp"
N_COLORS = int(_flags.get("colors", "5"))
BASE = os.path.splitext(os.path.basename(IMG))[0]
OUT = _flags.get("out", f"{BASE}.yaml")

SIZE_MM = 100.0
BORDER_MM = 2.5


def luma(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def kmeans_palette(pixels, k):
    pix = pixels.astype(float)
    if len(pix) == 0:
        return np.zeros((0, 3), dtype=int)
    idx = np.random.default_rng(0).choice(len(pix), min(len(pix), 200000), replace=False)
    cen, _ = kmeans2(pix[idx], k, minit="++", seed=0, iter=30)
    return np.clip(cen.round().astype(int), 0, 255)


im = Image.open(IMG).convert("RGBA")
arr = np.array(im)
alpha = arr[..., 3]
transparent = alpha < 128
has_transparency = bool(transparent.any())
silhouette = ~transparent if has_transparency else np.ones(arr.shape[:2], dtype=bool)
rgb = arr[..., :3].astype(int)

if has_transparency:
    disc = morphology.disk(3)
    rgb = np.stack([ndimage.median_filter(rgb[..., i], footprint=disc) for i in range(3)], axis=-1)

# exclude the border ring band so the palette matches vectorize.py's interior palette
px_per_mm = max(arr.shape[:2]) / SIZE_MM
border_px = BORDER_MM * px_per_mm
if has_transparency:
    dt = ndimage.distance_transform_edt(silhouette)
    ring = silhouette & (dt > 0) & (dt <= max(2, border_px))
    interior = silhouette & (~ring if ring.any() else silhouette)
else:
    interior = silhouette

pix = rgb[interior]
centroids = kmeans_palette(pix, N_COLORS)
colors = sorted(
    (tuple(int(v) for v in c) for c in centroids),
    key=luma,
    reverse=True,
)
hexes = ["#%02x%02x%02x" % c for c in colors]

print("detected palette (light -> dark):")
for h in hexes:
    print(f"  {h}")

yaml_text = f"""# {BASE}.yaml — overrides for digitizing {IMG}
# Stitch order, first = bottom. Unlisted colors keep the default luma sort.
order:
""" + "".join(f"  - {h!r}\n" for h in hexes) + f"""
# Colors to never stitch (e.g. background/white):
skip_colors: []

# Per-color fill density (row_spacing_mm). Omit a color to use the default (0.5).
density: {{}}

# Border: mode = auto | off | force_black
border:
  mode: auto
  thickness_mm: 2.5

# Trim: cut when a jump is longer than threshold_mm (0 = after every object).
trim:
  enabled: false
  threshold_mm: 5.0
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(yaml_text)

print(f"\nwrote {OUT}")
print(f"run: tools/digitize/run.sh --config {OUT} {IMG}")
