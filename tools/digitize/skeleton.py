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
_TAPER_WIDTH_JUMP_MM = 0.6         # pieces this close in width stay one satin
_TAPER_MIN_RUN_MM = 2.5            # a piece shorter than this is merged away


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
                   extend_ends=False, free_ext_mm=0.3, raw_widths=False, taper_mm=0.0):
    """Skeletonize a mask into (path_d, point_array, width_px) satin candidates.

    Segments whose own median width exceeds ``wmax_mm`` are the cores of solid
    regions, so they are skipped (they stay fills).  Thinner segments are widened
    up to ``wmin_mm`` so Ink/Stitch registers them as satin.

    With ``extend_ends`` the polyline ends are pushed outward first: junction
    ends by half the local line width, free ends by ``free_ext_mm`` (see
    ``_extend_ends``).  Default ``False`` leaves the output byte-identical.

    With ``raw_widths`` each result is a 4-tuple ``(path_d, points, width_px, raw_px)``
    where ``raw_px`` is the measured width before widening to ``wmin_mm``.

    ``taper_mm`` splits each run into pieces about that long, each with the width
    its own stretch of line measures, so a satin follows the line as it thickens
    and thins (a sword blade) instead of taking one median width for the whole
    run.  0 (the default) keeps one width per run.
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

    if taper_mm > 0:
        kept = _taper([(np.asarray(p, dtype=float), w) for p, w in kept],
                      dist, taper_mm * px_per_mm, wmin, wmax, px_per_mm)

    segs = []
    for arr, w_raw in kept:
        arr = np.asarray(arr, dtype=float)
        poly = measure.approximate_polygon(arr, tolerance=max(1.0, tolerance))
        if len(poly) < 2:
            poly = arr
        w = max(w_raw, wmin)
        d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in poly)
        segs.append((d, poly, w, w_raw) if raw_widths else (d, poly, w))
    return segs


def _taper(runs, dist, chunk_px, wmin, wmax, px_per_mm):
    """Split each run into ~chunk_px pieces, each with the width it measures.

    A piece takes p95 of the distance transform over its own stretch of line, so a
    piece running along a flare is wider than the one before it.  Neighbouring
    pieces whose widths agree stay one piece (a constant-width line still gives
    one satin, not twenty), and a piece too short to be a satin on its own is
    merged into its neighbour.  Returns [(points, width_px)].
    """
    jump = _TAPER_WIDTH_JUMP_MM * px_per_mm
    min_run = _TAPER_MIN_RUN_MM * px_per_mm
    out = []
    for arr, _w_run in runs:
        total = float(np.hypot(*np.diff(arr, axis=0).T).sum())
        n = max(1, int(round(total / chunk_px))) if total > 0 else 1
        pieces = []                      # [indices, length, width]
        for c in range(n):
            a = int(round(c * len(arr) / n))
            b = min(len(arr) - 1, int(round((c + 1) * len(arr) / n)))
            idxs = list(range(a, b + 1))
            if len(idxs) < 2:
                continue
            ys = arr[idxs][:, 0].astype(int)
            xs = arr[idxs][:, 1].astype(int)
            w = 2.0 * float(np.percentile(dist[ys, xs], 95))
            length = float(np.hypot(*np.diff(arr[idxs], axis=0).T).sum())
            if pieces and abs(pieces[-1][2] - w) <= jump:
                pieces[-1][0] += idxs[1:]
                pieces[-1][1] += length
                pieces[-1][2] = (pieces[-1][2] + w) / 2.0
            else:
                pieces.append([idxs, length, w])
        changed = True
        while changed and len(pieces) > 1:
            changed = False
            for i, p in enumerate(pieces):
                if p[1] >= min_run:
                    continue
                left, right = pieces[i - 1] if i else None, pieces[i + 1] if i + 1 < len(pieces) else None
                if left is None and right is None:
                    continue
                if right is None or (left is not None
                                     and abs(left[2] - p[2]) <= abs(right[2] - p[2])):
                    left[0] += p[0][1:]
                    left[1] += p[1]
                    left[2] = (left[2] + p[2]) / 2.0
                else:
                    right[0] = p[0][:-1] + right[0]
                    right[1] += p[1]
                    right[2] = (right[2] + p[2]) / 2.0
                pieces.pop(i)
                changed = True
                break
        for idxs, _length, w in pieces:
            piece = arr[idxs]
            if len(piece) >= 2:
                # the measured width, capped at the run's ceiling; the satin floor
                # is applied by the caller, so a tip can still narrow below it
                out.append((piece, float(np.clip(w, 0.0, wmax))))
    return out


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

    # taper: a wedge (narrow at one end, wide at the other) comes out as several
    # satins of different widths, where one median width would be right nowhere
    wedge = np.zeros((80, 80), bool)
    for x in range(10, 70):
        half = 1 + (x - 10) * 9 // 60
        wedge[40 - half:40 + half, x] = True
    wkw = dict(px_per_mm=7.0, min_len_mm=1.0, wmin_mm=0.6, wmax_mm=9.0,
               tolerance=0.5, extend_ends=False)
    flat = satin_segments(wedge, **wkw)
    tapered = satin_segments(wedge, taper_mm=2.0, **wkw)
    assert len(flat) == 1, flat
    assert len(tapered) > 1, tapered
    widths = sorted(w / 7.0 for _, _, w in tapered)
    assert widths[-1] - widths[0] > 1.0, widths       # the wedge really tapers
    # the pieces tile the run: one ends where the next begins
    spans = sorted((min(p[1] for p in poly), max(p[1] for p in poly))
                   for _, poly, _ in tapered)
    assert all(abs(a[1] - b[0]) <= 1 for a, b in zip(spans, spans[1:])), spans

    print("skeleton.py: all checks passed")


if __name__ == "__main__":
    demo()
