#!/usr/bin/env python3
"""Fill component -> satin columns, for small/elongated shapes.

The Scavenger's Daughter centipede is drawn as one green fill path whose
sections are mostly 1-4 mm wide.  A tatami fill at 0.3 mm leaves those
sections looking striped and lets the base fabric peek through at the edges;
the operator asked for satin instead, "1-3 satin stitch rows" per section.

How it works, per component:
  * rasterise the polygon at 0.1 mm/px
  * skeletonise and measure the local width from the distance transform
  * cut the skeleton into ~2 mm chunks, give each chunk a width (p95 of the
    local width) and merge neighbouring chunks whose widths agree; the
    centreline is extended to the tips
  * a component too wide for one column (width > ``max_row_mm``) is covered by
    2..``max_rows`` parallel strips across its minimum rotated rectangle
  * verify the emitted bands cover the component (and do not spill far outside
    it); a component that cannot be covered well stays a fill

Everything here works in millimetres, in the pipeline's fitted coordinate
system.  The output is a list of satin items for ``svg_digitize.py`` to emit as
``inkstitch:satin_column`` single-subpath paths (width = ``stroke-width``).
"""
import math

import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize, disk
from shapely import contains_xy
from shapely.geometry import LineString
from shapely.ops import substring

PX = 0.1          # raster resolution, mm/px
_MARGIN_MM = 0.5  # raster padding
PRUNE_MM = 1.0    # drop skeleton spurs shorter than this
CHUNK_MM = 2.0    # skeleton chunk length for the local-width estimate
WIDTH_JUMP_MM = 0.6    # merge chunks whose widths differ by less than this
MIN_RUN_MM = 2.5  # merge runs shorter than this into a neighbour
MIN_ROW_MM = 0.6  # below Ink/Stitch's 1.0 mm gate, so the output metadata must
                  # carry min_satin_stroke_width_mm <= 0.5 (satinize callers do)
WIDTH_QUANTILE = 95   # p95 local width; the p50 under-covers tapered runs
SIMPLIFY_MM = 0.02    # collinear cleanup before the rail-offset check
OVERLAP_FRAC = 0.25   # drop a row whose band overlaps a longer row by more than this
CURVATURE_FACTOR = 1.2  # keep satin width below (curve radius / this)

_NEIGH = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def _rasterize(poly):
    x0, y0, x1, y1 = poly.bounds
    xs = np.arange(x0 - _MARGIN_MM, x1 + _MARGIN_MM + 1e-9, PX)
    ys = np.arange(y0 - _MARGIN_MM, y1 + _MARGIN_MM + 1e-9, PX)
    if len(xs) < 2 or len(ys) < 2:
        return None, 0.0, 0.0
    xx, yy = np.meshgrid(xs, ys)
    return contains_xy(poly, xx, yy), float(xs[0]), float(ys[0])


def _pixel_graph(skel):
    pts = np.argwhere(skel)
    n = len(pts)
    if n == 0:
        return pts, []
    idx = np.full(skel.shape, -1, dtype=int)
    idx[skel] = np.arange(n)
    adj = [[] for _ in range(n)]
    for i, (r, c) in enumerate(pts):
        for dr, dc in _NEIGH:
            rr, cc = r + dr, c + dc
            if 0 <= rr < skel.shape[0] and 0 <= cc < skel.shape[1]:
                j = idx[rr, cc]
                if j >= 0:
                    adj[i].append(j)
    return pts, adj


def _trace(pts, adj):
    """Skeleton pixel graph -> simple branches (lists of node indices)."""
    n = len(pts)
    deg = [len(a) for a in adj]
    used = set()
    branches = []

    def key(a, b):
        return (min(a, b), max(a, b))

    def walk(a, b):
        path = [a, b]
        prev, cur = a, b
        while deg[cur] == 2:
            nxt = adj[cur][0] if adj[cur][0] != prev else adj[cur][1]
            prev, cur = cur, nxt
            path.append(cur)
            if cur == a or len(path) > n + 2:
                break
        return path

    for s in range(n):
        if deg[s] == 2:
            continue
        for b in adj[s]:
            if key(s, b) in used:
                continue
            p = walk(s, b)
            for i in range(len(p) - 1):
                used.add(key(p[i], p[i + 1]))
            branches.append(p)
    for s in range(n):
        if deg[s] != 2:
            continue
        for b in adj[s]:
            if key(s, b) in used:
                continue
            p = walk(s, b)
            for i in range(len(p) - 1):
                used.add(key(p[i], p[i + 1]))
            branches.append(p)
    return branches, deg


def _branch_len(pts, path):
    return sum(math.dist(pts[path[i]], pts[path[i + 1]])
               for i in range(len(path) - 1)) * PX


def _prune(pts, adj, branches):
    """Drop short spurs hanging off junctions (skeletonisation noise)."""
    keep = list(branches)
    changed = True
    while changed:
        changed = False
        deg = [0] * len(pts)
        for p in keep:
            deg[p[0]] += 1
            deg[p[-1]] += 1
        for p in list(keep):
            if _branch_len(pts, p) < PRUNE_MM and (
                    (deg[p[0]] == 1 and deg[p[-1]] >= 3) or
                    (deg[p[-1]] == 1 and deg[p[0]] >= 3)):
                keep.remove(p)
                changed = True
    return keep


def _chunks_to_runs(pts, dt, path):
    """One skeleton branch -> runs of (indices, length_mm, width_mm)."""
    n = len(path)
    if n < 2:
        return []
    total = _branch_len(pts, path)
    nch = max(1, int(round(total / CHUNK_MM)))
    chunks = []
    for c in range(nch):
        a = int(round(c * n / nch))
        b = min(n - 1, int(round((c + 1) * n / nch)))
        idxs = path[a:b + 1]
        if len(idxs) < 2:
            continue
        ws = [2.0 * dt[tuple(pts[i])] * PX for i in idxs if dt[tuple(pts[i])] > 0]
        if not ws:
            continue
        chunks.append((idxs, _branch_len(pts, idxs), float(np.percentile(ws, WIDTH_QUANTILE))))
    runs = []
    for idxs, length, width in chunks:
        if runs and abs(runs[-1][2] - width) <= WIDTH_JUMP_MM and runs[-1][0][-1] == idxs[0]:
            prev = runs[-1]
            prev[0].extend(idxs[1:])
            prev[1] += length
            prev[2] = (prev[2] + width) / 2.0
        else:
            runs.append([list(idxs), length, width])
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, (idxs, length, width) in enumerate(runs):
            if length >= MIN_RUN_MM:
                continue
            left = runs[i - 1] if i > 0 else None
            right = runs[i + 1] if i + 1 < len(runs) else None
            if left is not None and (right is None or abs(left[2] - width) <= abs(right[2] - width)):
                cand = left
            elif right is not None:
                cand = right
            else:
                continue
            if cand is left:
                cand[0].extend(idxs[1:])          # idxs[0] == left[-1]
            else:
                cand[0] = idxs[:-1] + cand[0]      # idxs[-1] == right[0]
            cand[1] += length
            cand[2] = (cand[2] + width) / 2.0
            runs.pop(i)
            changed = True
            break
    return runs


def _simplify(line, tol_mm=0.15):
    """Drop points that barely move (keeps emitted path data small)."""
    if len(line) <= 2:
        return line
    keep = [line[0]]
    for p in line[1:-1]:
        if math.dist(p, keep[-1]) >= tol_mm:
            keep.append(p)
    keep.append(line[-1])
    return np.asarray(keep)


def _extend_line_to_mask(line, mask, ox, oy, max_extra_mm):
    """Push both ends of ``line`` outward until they leave the raster mask.

    A skeleton stops short of a plate's flat ends (its medial axis is shorter
    than the shape), so a satin built on the raw skeleton leaves the ends bare.
    Walking the local tangent outward recovers the missing length.
    """
    if len(line) < 2:
        return line

    def walk(end, inward):
        d = end - inward
        ln = np.linalg.norm(d)
        if ln == 0:
            return end
        d = d / ln
        steps = int(round(max_extra_mm / PX))
        last_inside = end
        exited = False
        for k in range(1, steps + 1):
            p = end + d * (k * PX)
            c = int(round((p[0] - ox) / PX))
            r = int(round((p[1] - oy) / PX))
            if 0 <= r < mask.shape[0] and 0 <= c < mask.shape[1] and mask[r, c]:
                last_inside = p
            else:
                exited = True
                break
        if not exited:
            # the tangent runs along the shape (a junction, not a tip): an
            # extension would just follow the interior, so do not add one
            return end
        return last_inside

    start = walk(line[0], line[1])
    end = walk(line[-1], line[-2])
    out = np.vstack([start, line, end])
    keep = [out[0]]
    for p in out[1:]:
        if math.dist(p, keep[-1]) > 1e-6:
            keep.append(p)
    return np.asarray(keep)


def _strip_rows(poly, max_row_mm, max_rows, overlap_mm=0.3):
    """Cover a wide/blob component with parallel strips along its long axis.

    Used when the skeleton method would need rows wider than ``max_row_mm``:
    the minimum rotated rectangle gives the long axis, the rectangle is split
    into ``k`` strips across the short axis, and each strip midline is clipped
    to the component.  Returns [(line_mm, width_mm)].
    """
    rect = poly.minimum_rotated_rectangle
    if rect.is_empty or rect.geom_type != "Polygon":
        return []
    coords = list(rect.exterior.coords)[:4]
    e1 = np.asarray(coords[1]) - np.asarray(coords[0])
    e2 = np.asarray(coords[2]) - np.asarray(coords[1])
    if np.linalg.norm(e1) >= np.linalg.norm(e2):
        u, v = e1, e2
    else:
        u, v = e2, e1
    lu, lv = np.linalg.norm(u), np.linalg.norm(v)
    if lu < 1e-6 or lv < 1e-6:
        return []
    u = u / lu
    v = v / lv
    W = lv
    k = max(1, min(max_rows, int(math.ceil(W / max_row_mm - 1e-9))))
    if k <= 1 and W <= max_row_mm:
        return []          # let the skeleton method handle narrow shapes
    strip_w = (W + (k - 1) * overlap_mm) / k
    spacing = strip_w - overlap_mm
    centre = np.asarray(rect.centroid.coords[0])
    rows = []
    for i in range(k):
        off = (i - (k - 1) / 2.0) * spacing
        p0 = centre + v * off - u * (lu + 1.0)
        p1 = centre + v * off + u * (lu + 1.0)
        clipped = LineString([p0, p1]).intersection(poly)
        geoms = [clipped]
        if clipped.geom_type in ("MultiLineString", "GeometryCollection"):
            geoms = list(clipped.geoms)
        for g in geoms:
            if g.geom_type != "LineString" or g.length < 1.0:
                continue
            line = _simplify(np.asarray(g.coords))
            rows.append((line, strip_w))
    return rows


def centreline_ok(line, width):
    """True when a centreline will survive rail building (see _valid_rows)."""
    pts = np.round(np.asarray(line, float), 2)
    keep = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - keep[-1][0]) > 1e-9 or abs(p[1] - keep[-1][1]) > 1e-9:
            keep.append(p)
    if len(keep) < 2:
        return False
    length = float(np.sum(np.linalg.norm(np.diff(np.asarray(keep), axis=0), axis=1)))
    return length >= max(0.8, width)


_PX_PER_MM = 96.0 / 25.4    # inkex user units per mm, as Ink/Stitch sees it


def _offset_converts(line, width):
    """Mirror Ink/Stitch's ``convert_path_to_satin`` success test.

    Ink/Stitch offsets the centreline by +/-width/2; when the offset comes out
    as anything but a LineString (self-intersection at a kink) it halves the
    path and retries, up to depth 20.  If every recursive piece fails, the
    element ends up with a single "rail" and the export crashes later.

    This must run in inkex user units (px), not mm: the offset's geometry is
    scale-invariant but GEOS' splitting at vertices is not, so a straight
    centreline that offsets to one LineString in mm can still split into a
    MultiLineString at Ink/Stitch's scale.
    """
    return _offset_converts_px([(x * _PX_PER_MM, y * _PX_PER_MM) for x, y in line],
                               width * _PX_PER_MM, 0)


def _offset_converts_px(px, width_px, depth):
    if len(px) < 2:
        return False
    if math.dist(px[0], px[-1]) < 1.0:          # path_to_satin raises
        return False
    ls = LineString(px)
    try:
        a = ls.offset_curve(width_px / 2.0, join_style="round")
        b = ls.offset_curve(-width_px / 2.0, join_style="round")
    except Exception:  # noqa: BLE001
        return False
    if a.geom_type == "LineString" and b.geom_type == "LineString":
        return True
    if depth >= 20 or ls.length < 1.0:
        return False
    h1 = substring(ls, 0, 0.5, normalized=True)
    h2 = substring(ls, 0.5, 1, normalized=True)
    return (_offset_converts_px(list(h1.coords), width_px, depth + 1) or
            _offset_converts_px(list(h2.coords), width_px, depth + 1))


def _valid_rows(rows):
    """Drop degenerate or unoffsettable centrelines.

    Ink/Stitch builds rails by offsetting the centreline; a centreline with
    fewer than two distinct points (after the 0.01 mm path rounding) makes a
    one-point rail, and a self-intersecting offset makes a single-rail satin --
    both abort the whole export.  A satin shorter than its own width is not
    stitchable either.
    """
    def _dedupe(pts):
        keep = [pts[0]]
        for p in pts[1:]:
            if abs(p[0] - keep[-1][0]) > 1e-9 or abs(p[1] - keep[-1][1]) > 1e-9:
                keep.append(p)
        return np.asarray(keep)

    out = []
    for line, width in rows:
        # the emitter writes 2 decimals, so validate exactly what will be
        # written: round, then drop the duplicates rounding may create
        pts = _dedupe(np.round(np.asarray(line, float), 2))
        if len(pts) < 2:
            continue
        # collapse collinear points: a straight run represented by two points
        # offsets cleanly, while GEOS can split a many-point collinear line
        simple = LineString(pts).simplify(SIMPLIFY_MM, preserve_topology=False)
        pts = _dedupe(np.round(np.asarray(simple.coords, float), 2))
        if len(pts) < 2:
            continue
        # keep the satin narrower than the curve it follows, or the inner rail
        # folds and Ink/Stitch fans the cross stitches
        radius = _min_curvature_mm(pts)
        if radius < CURVATURE_FACTOR * width:
            width = radius / CURVATURE_FACTOR
            if width < MIN_ROW_MM:
                continue
        length = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
        # a satin much shorter than it is wide stitches as a knot of short
        # cross stitches plus locks (measured: 70 mm of thread in a 1 mm cell)
        if length < max(2.5, 1.5 * width):
            continue
        if not _offset_converts(pts.tolist(), float(width)):
            continue
        out.append((pts, width))
    return out


def _drop_overlaps(rows, max_frac=None):
    max_frac = OVERLAP_FRAC if max_frac is None else max_frac
    """Keep the longest rows, dropping rows whose band overlaps a kept one.

    Skeleton branches of a crescent can run into each other, so several rows
    would otherwise stitch the same millimetres of fabric twice.
    """
    kept = []
    kept_bands = []
    for line, width in sorted(rows, key=lambda r: -_line_length(r[0])):
        band = LineString(line).buffer(max(width / 2.0, 0.05), cap_style=2)
        if band.is_empty:
            continue
        duplicate = False
        for kb in kept_bands:
            if band.intersection(kb).area > max_frac * band.area:
                duplicate = True
                break
        if not duplicate:
            kept.append((line, width))
            kept_bands.append(band)
    return kept


def _line_length(line):
    return float(np.sum(np.linalg.norm(np.diff(np.asarray(line, float), axis=0), axis=1)))


def _min_curvature_mm(line, step_mm=0.5):
    """Smallest circumradius of the polyline, sampled every ``step_mm``.

    A satin whose centreline bends tighter than its own width folds its inner
    rail; Ink/Stitch then pairs the rails into a radial fan of cross stitches.
    Sampling at 0.5 mm keeps rounding noise from looking like curvature.
    """
    ls = LineString(line)
    if ls.length < 3 * step_mm:
        return float("inf")
    n = max(3, int(ls.length / step_mm))
    pts = [ls.interpolate(t, normalized=True) for t in np.linspace(0, 1, n)]
    arr = np.array([[p.x, p.y] for p in pts])
    rmin = float("inf")
    for i in range(len(arr) - 2):
        a, b, c = arr[i], arr[i + 1], arr[i + 2]
        ab = float(np.linalg.norm(b - a))
        bc = float(np.linalg.norm(c - b))
        ca = float(np.linalg.norm(c - a))
        area = abs((b[0] - a[0]) * (c[1] - a[1]) -
                   (c[0] - a[0]) * (b[1] - a[1])) / 2.0
        if area > 1e-9:
            rmin = min(rmin, ab * bc * ca / (4.0 * area))
    return rmin


def _rows_coverage(rows, mask, ox, oy):
    band = np.zeros_like(mask)
    for line, width in rows:
        r = max(1, int(round((width / 2.0 + 0.1) / PX)))
        one = np.zeros_like(mask)
        # rasterise the whole polyline, not just its vertices: a simplified
        # two-point centreline would otherwise become two dots
        for i in range(len(line) - 1):
            a = np.asarray(line[i], float)
            b = np.asarray(line[i + 1], float)
            n = max(2, int(np.linalg.norm(b - a) / PX) + 1)
            for t in np.linspace(0.0, 1.0, n):
                p = a + (b - a) * t
                c = int(round((p[0] - ox) / PX))
                rr = int(round((p[1] - oy) / PX))
                if 0 <= rr < mask.shape[0] and 0 <= c < mask.shape[1]:
                    one[rr, c] = True
        if one.any():
            band |= ndimage.binary_dilation(one, structure=disk(r))
    covered = float((band & mask).sum()) / float(mask.sum())
    overhang = float((band & ~mask).sum()) / float(max(band.sum(), 1))
    return covered, overhang


def component_to_satins(geom, max_row_mm=3.5, max_rows=3, min_coverage=0.85,
                        max_overhang=0.3):
    """Try to cover one polygon with satin columns.

    Returns a list of ``dict(centreline=<(N,2) mm>, width_mm=<float>)`` when the
    component is well covered, else ``None`` (leave it as a fill).
    """
    if geom.geom_type == "MultiPolygon":
        polys = list(geom.geoms)
    else:
        polys = [geom]
    all_mask = None
    all_origin = None
    main_poly = None
    for poly in polys:
        if poly.is_empty or poly.area <= 0:
            continue
        mask, ox, oy = _rasterize(poly)
        if mask is None or not mask.any():
            continue
        if all_mask is None or mask.sum() > all_mask.sum():
            all_mask, all_origin, main_poly = mask, (ox, oy), poly
    if all_mask is None:
        return None
    mask = all_mask
    ox, oy = all_origin

    skel = skeletonize(mask)
    dt = ndimage.distance_transform_edt(mask)
    pts, adj = _pixel_graph(skel)
    if len(pts) == 0:
        return None
    branches, deg = _trace(pts, adj)
    branches = _prune(pts, adj, branches)

    rows = []   # (line_mm, width_mm) -- one satin column per skeleton run
    for path in branches:
        for idxs, _length, width in _chunks_to_runs(pts, dt, path):
            width = float(np.clip(width, MIN_ROW_MM, max_row_mm))
            line = np.array([[ox + pts[i][1] * PX, oy + pts[i][0] * PX] for i in idxs])
            # a skeleton stops short of flat plate ends; push the centreline out
            # to the boundary so the satin actually reaches the tips
            line = _extend_line_to_mask(line, mask, ox, oy,
                                        max_extra_mm=max(2.0, width))
            line = _simplify(line)
            if len(line) < 2:
                continue
            rows.append((line, width))

    rows = _drop_overlaps(_valid_rows(rows))
    if rows:
        covered, overhang = _rows_coverage(rows, mask, ox, oy)
        if covered >= min_coverage and overhang <= max_overhang:
            return [dict(centreline=line, width_mm=width) for line, width in rows]

    # wide or blobby: parallel strips across the long axis
    if main_poly is not None:
        strips = _drop_overlaps(_valid_rows(_strip_rows(main_poly, max_row_mm, max_rows)))
        if strips:
            covered, overhang = _rows_coverage(strips, mask, ox, oy)
            if covered >= min_coverage and overhang <= max_overhang:
                return [dict(centreline=line, width_mm=width)
                        for line, width in strips]
    return None


if __name__ == "__main__":
    # smoke test: a 10 x 3 mm capsule -> one row; a 10 x 7 mm blob -> two rows
    from shapely.geometry import box
    one = component_to_satins(box(0, 0, 10, 3))
    print("capsule:", None if one is None else
          [(len(s["centreline"]), round(s["width_mm"], 2)) for s in one])
    two = component_to_satins(box(0, 0, 10, 7))
    print("plate:  ", None if two is None else
          [(len(s["centreline"]), round(s["width_mm"], 2)) for s in two])
