#!/usr/bin/env python3
"""Generate a starter per-image YAML config for the digitize pipeline.

Detects the image palette (same S3 Lab palette vectorize.py uses by default),
prints the colors in light->dark order, and writes a starter <name>.yaml the user
can edit to override stitch order / density / skip / border / trim.

If a prompt file is given with ``--prompt`` (or a ``patch_descriptions/prompts/<name>.md``
matching the image's basename exists), its ``**Palette:**`` line is parsed and
written as a pinned ``palette:`` list; vectorize.py then assigns every pixel to
the nearest pinned hex in CIELAB instead of clustering.

Usage:
  python tools/digitize/make_config.py <image> [--colors N] [--out <name>.yaml]
                                              [--prompt patch_descriptions/prompts/<name>.md]

Prints the run command to apply the config:
  tools/digitize/run.sh --config <out> <image>
"""
import os
import re
import sys

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import morphology

from vectorize import auto_palette

_VALUE_FLAGS = {"--colors", "--out", "--prompt"}
_argc = sys.argv[1:]
args = []
_flags = {}
_i = 0
while _i < len(_argc):
    _a = _argc[_i]
    if _a in ("-h", "--help"):
        print(__doc__.split("Usage:")[0].strip())
        print("\nUsage:\n  python tools/digitize/make_config.py <image> "
              "[--colors N] [--out <name>.yaml] [--prompt <prompt.md>]")
        sys.exit(0)
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


def luma_hex(h):
    return luma([int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)])


def parse_prompt_palette(path):
    """Return the deduped hex list from the prompt's ``**Palette:**`` line."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if "**palette:**" in line.lower():
                out, seen = [], set()
                for h in re.findall(r"#[0-9a-fA-F]{6}", line):
                    h = h.lower()
                    if h not in seen:
                        seen.add(h)
                        out.append(h)
                return out
    return []


# prompt palette: explicit --prompt wins, else look next to the image's basename
PROMPT = _flags.get("prompt")
if PROMPT is True:
    sys.exit("error: --prompt needs a path")
if not PROMPT:
    _cand = os.path.join("patch_descriptions", "prompts", BASE + ".md")
    if os.path.exists(_cand):
        PROMPT = _cand
pinned = []
if PROMPT:
    if os.path.exists(PROMPT):
        pinned = parse_prompt_palette(PROMPT)
        if pinned:
            print(f"prompt palette (pinned, light -> dark):")
            for h in sorted(pinned, key=luma_hex, reverse=True):
                print(f"  {h}")
        else:
            print(f"note: no **Palette:** line found in {PROMPT}")
    else:
        print(f"warning: prompt file {PROMPT} not found")


if pinned:
    # pinned colours are emitted verbatim; order them light -> dark like the default
    hexes = sorted(pinned, key=luma_hex, reverse=True)
else:
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

    # vectorize.py clusters S3 on the whole opaque silhouette
    pix = rgb[silhouette]
    centroids = auto_palette(pix, N_COLORS) if len(pix) else np.zeros((0, 3), dtype=int)
    colors = sorted(
        (tuple(int(v) for v in c) for c in centroids),
        key=luma,
        reverse=True,
    )
    hexes = ["#%02x%02x%02x" % c for c in colors]

    print("detected palette (light -> dark):")
    for h in hexes:
        print(f"  {h}")

palette_block = ""
if pinned:
    palette_block = ("\n# Pinned thread colours (from the prompt's **Palette:** line).\n"
                     "# vectorize.py assigns every pixel to the nearest hex in CIELAB.\n"
                     "palette:\n" + "".join(f"  - {h!r}\n" for h in pinned))

yaml_text = f"""# {BASE}.yaml — overrides for digitizing {IMG}
{palette_block}
# Stitch order, first = bottom. Unlisted colors keep the default luma sort.
order:
""" + "".join(f"  - {h!r}\n" for h in hexes) + f"""
# Colors to never stitch (e.g. background/white):
skip_colors: []

# Per-color fill density (row_spacing_mm). Omit a color to use the default (0.4).
density: {{}}

# Border: mode = auto | off | force_black
border:
  mode: auto
  thickness_mm: 2.5

# Trim: cut when a jump is longer than threshold_mm (0 = after every object).
# Jumps shorter than 2mm are never cut, and exposed jumps are cut regardless.
trim:
  enabled: true
  threshold_mm: 4.0
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(yaml_text)

print(f"\nwrote {OUT}")
print(f"run: tools/digitize/run.sh --config {OUT} {IMG}")
