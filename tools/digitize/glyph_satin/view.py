import numpy as np
from PIL import Image, ImageDraw
from geom import PPM

def render(polys, satins, box, scale, out, show_graph=None):
    """box = (x0,y0,x1,y1) in svg px.  satins = list of dict(L,R,rung_idx)."""
    x0, y0, x1, y1 = box
    W, H = int((x1 - x0) * scale), int((y1 - y0) * scale)
    im = Image.new("RGB", (W, H), (20, 20, 20))
    d = ImageDraw.Draw(im)
    T = lambda p: ((p[0] - x0) * scale, (p[1] - y0) * scale)
    for poly in polys:
        d.polygon([T(p) for p in poly.exterior.coords], fill=(70, 70, 70))
        for h in poly.interiors:
            d.polygon([T(p) for p in h.coords], fill=(20, 20, 20))
    if show_graph is not None:
        for a, b in show_graph.edges:
            d.line([T(show_graph.nodes[a]["pos"]), T(show_graph.nodes[b]["pos"])], fill=(0, 140, 255), width=1)
    cols = [(255, 80, 80), (80, 255, 80), (255, 220, 60), (255, 120, 255), (80, 255, 255), (255, 160, 60)]
    for k, s in enumerate(satins):
        col = cols[k % len(cols)]
        L, R = s["L"], s["R"]
        for i in range(len(L)):
            d.line([T(L[i]), T(R[i])], fill=tuple(int(c * 0.55) for c in col), width=1)
        d.line([T(p) for p in L], fill=col, width=2)
        d.line([T(p) for p in R], fill=col, width=2)
        for i in s.get("rung_idx", []):
            d.line([T(L[i]), T(R[i])], fill=(255, 255, 255), width=1)
    im.save(out)
    return im
