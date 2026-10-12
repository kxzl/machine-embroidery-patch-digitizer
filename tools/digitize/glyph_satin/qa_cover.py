"""Geometry QA: satin bands (union of rung quads) vs the source polygons."""
import sys, pickle
import numpy as np
from PIL import Image, ImageDraw
from geom import PPM

def bands_mask(satins, W, H, S):
    im = Image.new("L", (W * S, H * S), 0)
    d = ImageDraw.Draw(im)
    for s in satins:
        L, R = s["L"], s["R"]
        for i in range(len(L) - 1):
            q = [tuple(L[i] * S), tuple(L[i + 1] * S), tuple(R[i + 1] * S), tuple(R[i] * S)]
            d.polygon(q, fill=255)
    return np.asarray(im) > 0

def poly_mask(polys, W, H, S):
    im = Image.new("L", (W * S, H * S), 0)
    d = ImageDraw.Draw(im)
    for p in polys:
        d.polygon([tuple(np.array(c) * S) for c in p.exterior.coords], fill=255)
        for h in p.interiors:
            d.polygon([tuple(np.array(c) * S) for c in h.coords], fill=0)
    return np.asarray(im) > 0

def run(tag, S=2, out=None, box=None):
    D = pickle.load(open(f"{tag}.pkl", "rb"))
    polys, sat = D["polys"], D["satins"]
    W, H = 2752, 1536
    pm = poly_mask(polys, W, H, S)
    bm = bands_mask(sat, W, H, S)
    px_mm2 = 1.0 / (PPM * S) ** 2
    unc = pm & ~bm
    spill = bm & ~pm
    print(f"{tag}: poly {pm.sum()*px_mm2:.1f} mm2, uncovered {unc.sum()*px_mm2:.2f} mm2 ({100*unc.sum()/pm.sum():.2f}%), spill {spill.sum()*px_mm2:.2f} mm2 ({100*spill.sum()/pm.sum():.2f}%)")
    rgb = np.zeros(pm.shape + (3,), np.uint8)
    rgb[pm & bm] = (90, 90, 90)
    rgb[unc] = (255, 40, 40)
    rgb[spill] = (40, 220, 255)
    im = Image.fromarray(rgb)
    if box:
        im = im.crop(tuple(int(v * S) for v in box))
    if out:
        im.save(out)
    return unc, spill

if __name__ == "__main__":
    tag = sys.argv[1]
    box = tuple(float(v) for v in sys.argv[3].split(",")) if len(sys.argv) > 3 else (700, 100, 2100, 1450)
    run(tag, out=sys.argv[2], box=box)
