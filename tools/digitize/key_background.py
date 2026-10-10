#!/usr/bin/env python3
"""Key a flat background colour out of a raster image -> RGBA PNG.

The raster path classifies opaque images as flat art and drops the LIGHTEST
cluster as paper.  That is wrong when the background is dark (Book Burner) or
when the artwork should be treated as a patch with a satin border (Earth's
black ring).  Keying the background to alpha makes the pipeline take the
transparent-patch path instead: silhouette from alpha, and the dark outer ring
detected and stitched as the satin border.

The background colour is auto-detected as the median of four corner blocks
unless ``--bg`` is given.  Edge pixels are un-blended against the background so
anti-aliased rims keep their true colour instead of a dark halo.

Usage:
    key_background.py <input> <output.png> [--bg RRGGBB] [--t0 N] [--t1 N]

    tools/digitize/key_background.py input/earth.jpg work/earth.png
    tools/digitize/run.sh --key-background --size-mm 60 input/earth.jpg
"""
import argparse

import numpy as np
from PIL import Image
from scipy import ndimage


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--bg", help="background colour RRGGBB "
                                 "(default: median of the four corner blocks)")
    ap.add_argument("--t0", type=float, default=10.0,
                    help="fully transparent below this RGB distance (default 10)")
    ap.add_argument("--t1", type=float, default=40.0,
                    help="fully opaque above this RGB distance (default 40)")
    ap.add_argument("--keep-enclosed", action="store_true",
                    help="only background connected to the image edge becomes "
                         "transparent; pale colours enclosed by the artwork stay opaque "
                         "(default off: every pixel near the background colour is keyed)")
    args = ap.parse_args()

    im = Image.open(args.input).convert("RGB")
    arr = np.asarray(im).astype(float)

    if args.bg:
        hexv = args.bg.lstrip("#")
        bg = np.array([int(hexv[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)
    else:
        p = 8
        corners = np.concatenate([
            arr[:p, :p].reshape(-1, 3), arr[:p, -p:].reshape(-1, 3),
            arr[-p:, :p].reshape(-1, 3), arr[-p:, -p:].reshape(-1, 3)])
        bg = np.median(corners, axis=0)

    dist = np.sqrt(((arr - bg) ** 2).sum(axis=-1))
    alpha = np.clip((dist - args.t0) / max(args.t1 - args.t0, 1e-6), 0.0, 1.0)
    # With --keep-enclosed only background connected to the image edge may become transparent. A pale
    # colour enclosed by the artwork (an off-white symbol on a black disc, on a white
    # image margin) can sit within t1 of the background colour and would otherwise be
    # keyed out in part. Pixels not reachable from the edge stay fully opaque.
    if args.keep_enclosed:
        near_bg = dist < args.t1
        comps, _n = ndimage.label(near_bg, structure=np.ones((3, 3), dtype=int))
        edge_ids = np.unique(np.concatenate([comps[0], comps[-1], comps[:, 0], comps[:, -1]]))
        outside = np.isin(comps, edge_ids[edge_ids > 0])
        alpha = np.where(near_bg & ~outside, 1.0, alpha)

    # un-blend the feather: observed = a * foreground + (1 - a) * background
    a3 = alpha[..., None]
    fg = np.where(a3 > 0, (arr - (1 - a3) * bg) / np.maximum(a3, 1e-6), arr)
    out = np.dstack([np.clip(fg, 0, 255), alpha * 255]).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(args.output)

    print(f"keyed {args.input} -> {args.output}: "
          f"bg #{int(bg[0]):02x}{int(bg[1]):02x}{int(bg[2]):02x}, "
          f"{100 * (alpha < 0.5).mean():.1f}% transparent, "
          f"{100 * ((alpha >= 0.5) & (alpha < 1)).mean():.2f}% feathered")


if __name__ == "__main__":
    main()
