#!/usr/bin/env python3
"""Design-level fabric-pull simulation for raster-path SVGs (M/L/Z paths only).

Every ``fill`` is rasterised and eroded ALONG its stitch direction
(``inkstitch:angle``, default 0 = horizontal rows) by ``--fill-pull`` mm per side,
minus the authored ``inkstitch:pull_compensation_mm``.  That is what fabric pull
does to a tatami fill, and it is the only metric that reproduces the colour-seam
defect the operator saw.  Every ``satin`` is drawn at
``stroke-width + 2*pull_compensation - 2*satin_pull``.  Reports the silhouette
pixels left with no thread; ``--out`` writes a map (red = opens only with pull,
blue = already open without pull).

Known artefact: the even-odd silhouette is built by XOR-ing each sub-ring, so
where two sub-rings coincide the result is a thin *rectangle outline* that no
thread can cover.  Fills leave ~0.1-0.2 % uncovered at the measurement floor;
treat that as zero, and judge by the gaps >= 0.5 mm2 count instead.

Usage:
    pullsim.py <design.svg> <keyed_art.png> [--fill-pull 0.25] [--satin-pull 0.15]
               [--res 10] [--out map.png]
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
    ap.add_argument("svg", help="pre-digitized Ink/Stitch SVG")
    ap.add_argument("art", help="keyed artwork PNG (alpha = silhouette)")
    ap.add_argument("--fill-pull", type=float, default=0.25,
                    help="pull per side on fills, mm (default 0.25)")
    ap.add_argument("--satin-pull", type=float, default=0.15,
                    help="pull per side on satins, mm (default 0.15)")
    ap.add_argument("--res", type=float, default=10.0, help="px per mm (default 10)")
    ap.add_argument("--out", help="write a coverage map PNG")
    a = ap.parse_args()

    import math
    import re

    import numpy as np
    from lxml import etree
    from PIL import Image, ImageDraw
    from scipy import ndimage

    NS = "{http://inkstitch.org/namespace}"
    root = etree.parse(a.svg).getroot()
    vb = [float(v) for v in root.get("viewBox").split()]
    wmm = float(root.get("width").replace("mm", ""))
    ppm = vb[2] / wmm                       # svg units per mm
    S = a.res / ppm                         # svg unit -> raster px
    W, H = int(vb[2] * S) + 1, int(vb[3] * S) + 1

    def subpaths(d):
        out, cur = [], []
        for tok in re.findall(r"[MLZ]|-?[\d.]+,-?[\d.]+", d):
            if tok == "M":
                if cur:
                    out.append(cur)
                cur = []
            elif tok in ("L", "Z"):
                continue
            else:
                x, y = map(float, tok.split(","))
                cur.append((x * S, y * S))
        if cur:
            out.append(cur)
        return out

    def line_struct(angle_deg, r):
        n = 2 * r + 1
        st = np.zeros((n, n), bool)
        t = math.radians(angle_deg)
        for k in range(-r, r + 1):
            st[int(round(r - k * math.sin(t))), int(round(r + k * math.cos(t)))] = True
        return st

    cov = np.zeros((H, W), bool)
    cov_nopull = np.zeros((H, W), bool)
    for el in root.iter("{http://www.w3.org/2000/svg}path"):
        d = el.get("d")
        style = el.get("style", "")
        if el.get(NS + "satin_column") == "true":
            wpx = float(re.search(r"stroke-width:([\d.]+)", style).group(1))
            pc = el.get(NS + "pull_compensation_mm")
            pc = float(pc.split()[0]) if pc else 0.0
            for sp in subpaths(d):
                closed = d.strip().endswith("Z")
                pts = sp + sp[:1] if closed else sp
                w0 = wpx * S + 2 * pc * a.res
                w1 = max(1, w0 - 2 * a.satin_pull * a.res)
                for target, w in ((cov, w1), (cov_nopull, w0)):
                    img = Image.new("L", (W, H), 0)
                    ImageDraw.Draw(img).line(pts, fill=255,
                                             width=max(1, int(round(w))), joint="curve")
                    target |= np.array(img) > 0
            continue
        # even-odd: xor each ring
        m = np.zeros((H, W), bool)
        for sp in subpaths(d):
            if len(sp) < 3:
                continue
            ri = Image.new("L", (W, H), 0)
            ImageDraw.Draw(ri).polygon(sp, fill=255)
            m ^= np.array(ri) > 0
        cov_nopull |= m
        ang = float(el.get(NS + "angle", 0) or 0)
        pc = el.get(NS + "pull_compensation_mm")
        pc = float(pc.split()[0]) if pc else 0.0
        net = a.fill_pull - pc
        if net > 0:
            r = int(round(net * a.res))
            if r:
                m = ndimage.binary_erosion(m, structure=line_struct(ang, r))
        elif net < 0:
            r = int(round(-net * a.res))
            if r:
                m = ndimage.binary_dilation(m, structure=line_struct(ang, r))
        cov |= m

    art = Image.open(a.art).convert("RGBA")
    art = art.resize((W, H), Image.BILINEAR)
    sil = np.array(art)[..., 3] > 128
    sil = ndimage.binary_erosion(sil, iterations=2)   # ignore the AA fringe
    for name, c in (("no pull", cov_nopull),
                    (f"fill pull {a.fill_pull} / satin pull {a.satin_pull}", cov)):
        unc = sil & ~c
        lab, n = ndimage.label(unc)
        ar = (ndimage.sum(np.ones_like(lab), lab, index=range(1, n + 1)) / a.res ** 2
              if n else np.array([]))
        print(f"{name:40s}: uncovered {100 * unc.sum() / sil.sum():5.2f}%  "
              f"gaps>=0.1mm2 {int((ar >= 0.1).sum()):4d}  >=0.5mm2 {int((ar >= 0.5).sum()):3d}  "
              f"area in gaps>=0.1mm2 {ar[ar >= 0.1].sum():6.1f} mm2")
    if a.out:
        vis = np.array(art.convert("RGB")).astype(float) * 0.4 + 150
        vis[~sil] = 255
        vis = vis.astype(np.uint8)
        vis[sil & ~cov] = (255, 0, 0)
        vis[sil & ~cov_nopull] = (0, 0, 255)
        Image.fromarray(vis).save(a.out)
        print("wrote", a.out)


if __name__ == "__main__":
    main()
