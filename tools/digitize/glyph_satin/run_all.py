import sys, pickle, time, json
import numpy as np
from shapely.geometry import Point
from build import *
from view import render

TRIM_MM = 2.0
PULL_OVERRIDE = [(99.5, 61.7, 0.07)]   # lower blade: four strips with ~0.5 mm grooves
PATCH = True
CORNER_EXT = 0.0

import geom
geom.EXCLUDE[:] = [(83.85, 46.8, 1.1)]


def main(out_svg, tag):
    t0 = time.time()
    polys = load_polygons(JPG)
    items = []   # (comp_index, kind, satin)
    for ci, p in enumerate(polys):
        kind = classify(p)
        if kind == "star":
            for s in star_satins(p): items.append((ci, kind, s))
        elif kind == "pommel":
            items.append((ci, kind, circle_satin(p)))
        else:
            sat, G = stroke_satins(p, corner_ext=CORNER_EXT)
            if PATCH:
                sat = sat + patch_residuals(p, sat)
            for s in sat: items.append((ci, kind, s))
    print("components", len(polys), "satins", len(items), "%.1fs" % (time.time() - t0))
    # pull compensation from the nearest-neighbour gap
    for ci, k, s in items:
        s["comp"] = ci
        gap = min(polys[ci].distance(polys[cj]) for cj in range(len(polys)) if cj != ci) / PPM
        s["pull_mm"] = round(float(np.clip((gap - 0.3) / 2, 0.06, 0.2)), 3)
    # inner grooves of one shape (blade strips) are not seen by the component gap: override by position
    for ci, k, s in items:
        b = polys[ci].bounds
        for (px, py, pm) in PULL_OVERRIDE:
            if abs(b[0] / PPM - px) < 0.3 and abs(b[1] / PPM - py) < 0.3:
                s["pull_mm"] = pm
    # order: greedy by component, starting at pommel; rings last
    comp_kind = {ci: classify(polys[ci]) for ci in range(len(polys))}
    groups = {}
    for ci, k, s in items: groups.setdefault(ci, []).append(s)
    def ends(s):
        return ((s["L"][0] + s["R"][0]) / 2, (s["L"][-1] + s["R"][-1]) / 2)
    order_c = [c for c in groups if comp_kind[c] != "ring"]
    rings = [c for c in groups if comp_kind[c] == "ring"]
    pom = [c for c in order_c if comp_kind[c] == "pommel"][0]
    seq = [pom]; rest = set(order_c) - {pom}
    cur = np.array(polys[pom].centroid.coords[0])
    while rest:
        nxt = min(rest, key=lambda c: np.hypot(*(np.array(polys[c].centroid.coords[0]) - cur)))
        seq.append(nxt); rest.remove(nxt); cur = np.array(polys[nxt].centroid.coords[0])
    # rings: inner (smaller) first then outer
    rings.sort(key=lambda c: polys[c].area)
    seq += rings
    ordered = []
    pos = None
    for c in seq:
        g = list(groups[c])
        while g:
            if pos is None: s = g.pop(0)
            else:
                best = None
                for j, s2 in enumerate(g):
                    a, b = ends(s2)
                    for rev, e in ((False, a), (True, b)):
                        d = np.hypot(*(e - pos))
                        if best is None or d < best[0]: best = (d, j, rev)
                _, j, rev = best
                s = g.pop(j)
                if rev:
                    s = dict(s); s["L"] = s["L"][::-1].copy(); s["R"] = s["R"][::-1].copy()
                    n = len(s["L"]); s["rung_idx"] = sorted(n - 1 - i for i in s.get("rung_idx", []))
            ordered.append(s); pos = ends(s)[1]
    for a, b2 in zip(ordered[:-1], ordered[1:]):
        gap = np.hypot(*(ends(a)[1] - ends(b2)[0])) / PPM
        a["trim_after"] = bool(gap > TRIM_MM or a.get("comp") != b2.get("comp"))
    ordered[-1]["trim_after"] = True
    print("trims:", sum(1 for s in ordered if s["trim_after"]))
    write_svg(ordered, out_svg)
    pickle.dump(dict(polys=polys, satins=ordered), open(f"{tag}.pkl", "wb"))
    print("wrote", out_svg, len(ordered), "satins")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
