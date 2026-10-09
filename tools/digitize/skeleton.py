"""Skeleton -> polyline extraction, used to turn thin outlines into satin.

Kept separate from vectorize.py so the graph-walking logic can be checked
without running the whole raster pipeline:

    .venv/bin/python tools/digitize/skeleton.py

``satin_segments(..., extend_ends=True)`` additionally pushes every polyline end
outward along its end tangent (E3, review.md §2.7): an end that stops at a
skeleton junction moves by half the local line width so it reaches past the
junction and tucks under the crossing satin, a free end moves by
``free_ext_mm``.  Off by default, so the traced geometry is unchanged unless
asked for.
"""
import math

import numpy as np
from scipy import ndimage
from skimage import measure, morphology

_NEIGHBORS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
_FREE_END_CLIP_MM = 0.3            # a free end may leave the mask by at most this


def trace_skeleton(skel, robust=False):
    """Split a 1px skeleton into simple polylines (lists of (y, x)).

    ``robust`` lets a branch walk step onto an already-visited junction so that
    every branch meeting a junction is reported as ending on the junction pixel
    (the default stops a branch one pixel short once an earlier walk claimed the
    junction).
    """
    pts = set(map(tuple, np.argwhere(skel)))
    if not pts:
        return

    def nbrs(p):
        return [q for q in ((p[0] + dy, p[1] + dx) for dy, dx in _NEIGHBORS) if q in pts]

    deg = {p: len(nbrs(p)) for p in pts}
    junctions = {p for p, d in deg.items() if d >= 3}
    visited = set()

    def cands(cur, prev):
        if robust:
            return [q for q in nbrs(cur) if q != prev and (q in junctions or q not in visited)]
        return [q for q in nbrs(cur) if q != prev and q not in visited]

    def walk(start, nxt):
        path = [start, nxt]
        visited.add(start); visited.add(nxt)
        prev, cur = start, nxt
        while cur not in junctions:
            cand = cands(cur, prev)
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
            if q not in visited or (robust and q in junctions):
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


def _unit(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n else (0.0, 0.0)


def _junction_pixels(skel):
    """The 8-connected pixels where three or more skeleton branches meet."""
    pts = set(map(tuple, np.argwhere(skel)))
    return {p for p in pts
            if sum((p[0] + dy, p[1] + dx) in pts for dy, dx in _NEIGHBORS) >= 3}


def _free_extent(end, d, want, out_dist, clip):
    """Largest step along ``d`` from ``end`` that keeps the tip within ``clip``
    of the mask (``out_dist`` is the distance-to-mask transform)."""
    last = 0.0
    t = 0.0
    while t < want:
        t = min(t + 0.5, want)
        y = int(round(end[0] + d[0] * t))
        x = int(round(end[1] + d[1] * t))
        if not (0 <= y < out_dist.shape[0] and 0 <= x < out_dist.shape[1]):
            break
        if out_dist[y, x] > clip:
            break
        last = t
    return last


def _extend_ends(chains, dist, junctions, free_ext, clip, out_dist):
    """Push each polyline end outward along its end tangent (review.md §2.7).

    An end sitting on a skeleton junction is extended by half the local line
    width (``dist`` at the junction, so ``2 * dist`` is the width).  A free end
    is extended by ``free_ext`` px, clipped so the tip never leaves the mask by
    more than ``clip`` px.
    """
    out = []
    for chain in chains:
        if len(chain) < 2:
            out.append(chain)
            continue
        ch = list(chain)
        for side in (0, 1):
            end = ch[0] if side == 0 else ch[-1]
            near = ch[1] if side == 0 else ch[-2]
            d = _unit((end[0] - near[0], end[1] - near[1]))
            if end in junctions:
                ext = float(dist[end])
            else:
                ext = _free_extent(end, d, free_ext, out_dist, clip)
            if ext <= 0.0:
                continue
            tip = (end[0] + d[0] * ext, end[1] + d[1] * ext)
            if side == 0:
                ch.insert(0, tip)
            else:
                ch.append(tip)
        out.append(ch)
    return out


def satin_segments(thin, px_per_mm, min_len_mm, wmin_mm, wmax_mm, tolerance,
                   extend_ends=False, free_ext_mm=0.3):
    """Skeletonize a mask into (path_d, point_array, width_px) satin candidates.

    Segments whose own median width exceeds ``wmax_mm`` are the cores of solid
    regions, so they are skipped (they stay fills).  Thinner segments are widened
    up to ``wmin_mm`` so Ink/Stitch registers them as satin.

    With ``extend_ends`` the polyline ends are pushed outward first: junction
    ends by half the local line width, free ends by ``free_ext_mm`` (see
    ``_extend_ends``).  Default ``False`` leaves the output byte-identical.
    """
    skel = morphology.skeletonize(thin)
    dist = ndimage.distance_transform_edt(thin)
    min_len = min_len_mm * px_per_mm
    wmin = wmin_mm * px_per_mm
    wmax = wmax_mm * px_per_mm

    if extend_ends:
        junctions = _junction_pixels(skel)
        out_dist = ndimage.distance_transform_edt(~thin)
        free_ext = free_ext_mm * px_per_mm
        clip = _FREE_END_CLIP_MM * px_per_mm
        paths = [p for p in trace_skeleton(skel, robust=True) if len(p) >= 2]
    else:
        paths = trace_skeleton(skel)

    kept = []                          # (path, w_raw) after the length/width gates
    for path in paths:
        if len(path) < 2:
            continue
        arr = np.asarray(path, dtype=float)
        seglen = float(np.hypot(*np.diff(arr, axis=0).T).sum())
        if seglen < min_len:
            continue
        w_raw = 2.0 * float(np.median(dist[arr[:, 0].astype(int), arr[:, 1].astype(int)]))
        if w_raw > wmax:
            continue
        kept.append((path, w_raw))

    if extend_ends:
        kept = list(zip(
            _extend_ends([c for c, _ in kept], dist, junctions, free_ext, clip, out_dist),
            [w for _, w in kept]))

    segs = []
    for path, w_raw in kept:
        arr = np.asarray(path, dtype=float)
        poly = measure.approximate_polygon(arr, tolerance=max(1.0, tolerance))
        if len(poly) < 2:
            poly = arr
        w = max(w_raw, wmin)
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

    # extend_ends: a T's stem stops at the junction, or reaches past its centre
    m = np.zeros((41, 41), bool)
    m[17:23, 0:41] = True              # bar
    m[23:41, 20] = True                # stem down, joins the bar near (19, 20)
    jpx = _junction_pixels(morphology.skeletonize(m))
    cy = sum(p[0] for p in jpx) / len(jpx)

    def stem_top(segs):
        return min(min(p[0] for p in poly) for _, poly, _ in segs
                   if all(abs(p[1] - 20) <= 1.5 for p in poly))

    tkw = dict(px_per_mm=7.0, min_len_mm=0.1, wmin_mm=0.6, wmax_mm=30.0, tolerance=0.5)
    assert stem_top(satin_segments(m, extend_ends=False, **tkw)) > cy
    assert stem_top(satin_segments(m, extend_ends=True, **tkw)) < cy

    # extend_ends: a bar's free ends grow by ~free_ext_mm
    bar = np.zeros((40, 40), bool)
    bar[18:22, 5:35] = True
    bkw = dict(px_per_mm=7.0, min_len_mm=1.0, wmin_mm=0.6, wmax_mm=2.5, tolerance=0.5)

    def left_x(segs):
        return min(min(poly[0][1], poly[-1][1]) for _, poly, _ in segs)

    tight = satin_segments(bar, extend_ends=False, **bkw)
    wide = satin_segments(bar, extend_ends=True, free_ext_mm=0.3, **bkw)
    grow = left_x(tight) - left_x(wide)
    assert abs(grow - 0.3 * 7.0) < 1.0, grow

    print("skeleton.py: all checks passed")


if __name__ == "__main__":
    demo()
