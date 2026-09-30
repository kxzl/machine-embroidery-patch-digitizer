"""Skeleton -> polyline extraction, used to turn thin outlines into satin.

Kept separate from vectorize.py so the graph-walking logic can be checked
without running the whole raster pipeline:

    .venv/bin/python tools/digitize/skeleton.py
"""
import numpy as np
from scipy import ndimage
from skimage import measure, morphology

_NEIGHBORS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def trace_skeleton(skel):
    """Split a 1px skeleton into simple polylines (lists of (y, x))."""
    pts = set(map(tuple, np.argwhere(skel)))
    if not pts:
        return

    def nbrs(p):
        return [q for q in ((p[0] + dy, p[1] + dx) for dy, dx in _NEIGHBORS) if q in pts]

    deg = {p: len(nbrs(p)) for p in pts}
    junctions = {p for p, d in deg.items() if d >= 3}
    visited = set()

    def walk(start, nxt):
        path = [start, nxt]
        visited.add(start); visited.add(nxt)
        prev, cur = start, nxt
        while cur not in junctions:
            cand = [q for q in nbrs(cur) if q != prev and q not in visited]
            if not cand:
                break
            prev, cur = cur, cand[0]
            visited.add(cur)
            path.append(cur)
        return path

    for p in pts:                      # endpoints first
        if p in visited or p in junctions or deg[p] != 1:
            continue
        for q in nbrs(p):
            if q not in visited:
                yield walk(p, q)
                break
    for p in pts:                      # then leftover loops / stubs
        if p in visited or p in junctions:
            continue
        nb = [q for q in nbrs(p) if q not in visited and q not in junctions]
        if nb:
            yield walk(p, nb[0])
        else:
            visited.add(p)
            yield [p]


def satin_segments(thin, px_per_mm, min_len_mm, wmin_mm, wmax_mm, tolerance):
    """Skeletonize a thin mask into (path_d, point_array, width_px) satin candidates."""
    skel = morphology.skeletonize(thin)
    dist = ndimage.distance_transform_edt(thin)
    min_len = min_len_mm * px_per_mm
    wmin = wmin_mm * px_per_mm
    wmax = wmax_mm * px_per_mm
    segs = []
    for path in trace_skeleton(skel):
        if len(path) < 2:
            continue
        arr = np.asarray(path, dtype=float)
        seglen = float(np.hypot(*np.diff(arr, axis=0).T).sum())
        if seglen < min_len:
            continue
        poly = measure.approximate_polygon(arr, tolerance=max(1.0, tolerance))
        if len(poly) < 2:
            poly = arr
        w = 2.0 * float(np.median(dist[arr[:, 0].astype(int), arr[:, 1].astype(int)]))
        w = min(max(w, wmin), wmax)
        d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in poly)
        segs.append((d, poly, w))
    return segs


def demo():
    # a straight horizontal line -> one segment
    m = np.zeros((5, 21), bool)
    m[2, 0:21] = True
    segs = list(trace_skeleton(m))
    assert len(segs) == 1, segs
    assert len(segs[0]) == 21, len(segs[0])

    # a plus: 4 arms meeting at the centre -> 4 segments
    m = np.zeros((11, 11), bool)
    m[5, 0:11] = True
    m[0:11, 5] = True
    segs = list(trace_skeleton(m))
    assert len(segs) == 4, [len(s) for s in segs]
    assert all(s[0] in ((5, 0), (5, 10), (0, 5), (10, 5)) for s in segs), segs

    # satin_segments returns one runnable path for a thin bar
    m = np.zeros((40, 40), bool)
    m[18:22, 5:35] = True
    out = satin_segments(m, px_per_mm=7.0, min_len_mm=1.0, wmin_mm=0.6, wmax_mm=2.5, tolerance=0.5)
    assert len(out) == 1, out
    assert out[0][2] >= 0.6 * 7.0, out[0][2]

    print("skeleton.py: all checks passed")


if __name__ == "__main__":
    demo()
