#!/usr/bin/env python3
"""Stitched-coverage check: which parts of the artwork silhouette end up bare.

Aligns the VP3 to the artwork by bounding-box centre (scale = ``size_mm`` /
longest side of the alpha bbox, the same rule ``vectorize.py`` uses), draws every
sewn segment at ``--thread`` mm width, and reports the uncovered fraction of the
silhouette plus hole clusters.  ``--pull`` shortens each segment at both ends to
model fabric pull.

This is a *gross-miss* gate, not a seam metric: sub-0.3 mm row pinstripes (the
shuttle gaps between tatami rows) are closed first (``--close-mm``), so at
``--pull 0`` it reports ~0 % for everything and only fires when a whole colour,
layer or region failed to stitch.  For colour seams use ``pullsim.py`` instead.

Usage:
    coverage.py <file.vp3> <artwork.png (RGBA keyed or posterized)> <size_mm>
                [--thread 0.4] [--pull 0.0] [--out map.png] [--res 10]
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vp3", help="machine file to inspect")
    ap.add_argument("art", help="keyed/posterized artwork PNG (alpha = silhouette)")
    ap.add_argument("size_mm", type=float, help="longest side of the design, mm")
    ap.add_argument("--thread", type=float, default=0.4, help="thread width, mm (default 0.4)")
    ap.add_argument("--pull", type=float, default=0.0,
                    help="shorten every segment by this many mm per end (default 0)")
    ap.add_argument("--res", type=float, default=10.0, help="px per mm (default 10)")
    ap.add_argument("--out", help="write a coverage map PNG")
    ap.add_argument("--close-mm", type=float, default=0.15,
                    help="close gaps narrower than 2x this (row pinstripes are not visible holes)")
    ap.add_argument("--erode-mm", type=float, default=0.0,
                    help="ignore this much of the silhouette edge (anti-alias fringe)")
    a = ap.parse_args()

    import math

    import numpy as np
    import pystitch
    from PIL import Image, ImageDraw
    from scipy import ndimage

    art = Image.open(a.art).convert("RGBA")
    arr = np.array(art)
    sil = arr[..., 3] > 128
    ys, xs = np.where(sil)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    ppm_src = max(x1 - x0, y1 - y0) / a.size_mm
    # resample silhouette to res px/mm
    W = int(math.ceil((x1 - x0) / ppm_src * a.res))
    H = int(math.ceil((y1 - y0) / ppm_src * a.res))
    crop = art.crop((x0, y0, x1, y1)).resize((W, H), Image.NEAREST)
    carr = np.array(crop)
    silr = carr[..., 3] > 128
    if a.erode_mm:
        silr = ndimage.binary_erosion(silr, iterations=max(1, int(round(a.erode_mm * a.res))))

    pat = pystitch.read(a.vp3)
    recs = []
    for s in pat.stitches:
        c = s[2] & pystitch.COMMAND_MASK if len(s) > 2 else pystitch.STITCH
        recs.append((s[0] / 10.0, s[1] / 10.0, c))
    sx = [r[0] for r in recs if r[2] == pystitch.STITCH]
    sy = [r[1] for r in recs if r[2] == pystitch.STITCH]
    bx0, bx1, by0, by1 = min(sx), max(sx), min(sy), max(sy)
    # centre alignment
    cx_s, cy_s = (bx0 + bx1) / 2, (by0 + by1) / 2
    cx_a, cy_a = W / a.res / 2, H / a.res / 2

    def tomap(x, y):
        return ((x - cx_s + cx_a) * a.res, (y - cy_s + cy_a) * a.res)

    img = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(img)
    wpx = max(1, int(round(a.thread * a.res)))
    r = a.thread * a.res / 2
    prev = None
    for x, y, c in recs:
        if c != pystitch.STITCH:
            prev = None if c in (pystitch.TRIM, pystitch.COLOR_CHANGE, pystitch.JUMP) else prev
            continue
        if prev is not None:
            px_, py_ = prev
            L = math.hypot(x - px_, y - py_)
            if L <= 8.0:
                if a.pull and L > 2 * a.pull:
                    ux, uy = (x - px_) / L, (y - py_) / L
                    p0 = (px_ + ux * a.pull, py_ + uy * a.pull)
                    p1 = (x - ux * a.pull, y - uy * a.pull)
                else:
                    p0, p1 = (px_, py_), (x, y)
                q0, q1 = tomap(*p0), tomap(*p1)
                dr.line([q0, q1], fill=255, width=wpx)
                for q in (q0, q1):
                    dr.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=255)
        prev = (x, y)

    cov = np.array(img) > 0
    if a.close_mm:
        rr = max(1, int(round(a.close_mm * a.res)))
        yy_, xx_ = np.ogrid[-rr:rr + 1, -rr:rr + 1]
        cov = ndimage.binary_closing(cov, structure=(xx_ ** 2 + yy_ ** 2) <= rr * rr,
                                     border_value=1)
    unc = silr & ~cov
    lab, n = ndimage.label(unc)
    areas = (ndimage.sum(np.ones_like(lab), lab, index=range(1, n + 1)) / a.res ** 2
             if n else np.array([]))
    big = sorted([(float(ar), i + 1) for i, ar in enumerate(areas) if ar >= 0.25],
                 reverse=True)
    print(f"{a.vp3}: thread {a.thread} mm, pull {a.pull} mm -> uncovered "
          f"{100 * unc.sum() / silr.sum():.2f}% of silhouette; "
          f"holes >=0.25 mm2: {len(big)}, >=1 mm2: {sum(1 for b in big if b[0] >= 1)}, "
          f"total hole area >=0.25: {sum(b[0] for b in big):.1f} mm2; "
          f"largest {big[0][0] if big else 0:.2f} mm2")
    if a.out:
        vis = carr[..., :3].copy()
        vis[~silr] = 255
        vis = (vis * 0.45 + 140).astype(np.uint8)
        vis[unc] = (255, 0, 0)
        for ar, i in big[:40]:
            yy, xx = np.where(lab == i)
            cy, cx = int(yy.mean()), int(xx.mean())
            vis[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3] = (255, 0, 255)
        Image.fromarray(vis).save(a.out)
        print("wrote", a.out)


if __name__ == "__main__":
    main()
