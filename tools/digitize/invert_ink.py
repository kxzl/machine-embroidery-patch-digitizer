#!/usr/bin/env python3
"""invert_ink.py -- derive an "inverted" machine-ready artwork from black-ink
line art.

The normal reading of a black-ink drawing is "stitch the ink".  On black fabric
that comes out as a photographic negative: the black ink is sewn in thread and
the white paper is left bare.  This script derives the opposite reading:

  * every colour listed in ``--ink`` is **dropped** -- the black fabric *is*
    the ink, no path is emitted for it;
  * the paper (everything inside the art silhouette that is neither ink nor a
    plate colour) becomes a **white fill**;
  * every connected component of the colours listed in
    ``--plate-satin-colors`` becomes its own **rail satin column**, so each
    body plate / fang is a separate satin and the bare-fabric seams between
    them stay visible;
  * a **white satin border**, centred just outside the art silhouette, hugs
    every horn and wraps the black bottom-edge legs so they stay visible.

The geometry is computed in shapely.  Curves are flattened with inkex at
<= 0.05 mm, ``fill-rule`` is honoured (``evenodd`` = XOR of the subpaths,
``nonzero`` = union minus the enclosed reversed subpaths).  Scaling to the fit
box happens *first*, so every later mm value is a real sewn mm.

Generic CLI (example for the Scavenger's Daughter job)::

    .venv/bin/python tools/digitize/invert_ink.py \
      --ink "#030503" --paper "#ffffff" \
      --plate-satin-colors "#87f70f" \
      --border-mm 2.0 --fit-mm 260x200 \
      "input/Scavenger's Daughter Upgrade Patch2.svg" \
      "input/Scavenger's Daughter Inverted.svg"

``--dump-dir DIR`` additionally writes a target raster and target masks
(``target.png``, ``target_masks.npz``) for the coverage verification.
"""
import argparse
import math
import os
import re
import sys

import numpy as np
from lxml import etree
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
from shapely.affinity import affine_transform
from shapely import make_valid, maximum_inscribed_circle
from PIL import Image, ImageDraw

import inkex
from inkex.bezier import cspsubdiv

INK_NS = "http://inkstitch.org/namespace"
SVG_NS = "http://www.w3.org/2000/svg"

_HEX3 = re.compile(r"^#([0-9a-fA-F]{3})$")
_HEX6 = re.compile(r"^#([0-9a-fA-F]{6})")
_HEX8 = re.compile(r"^#([0-9a-fA-F]{8})")
_RGB = re.compile(r"rgb\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)")


def norm_color(c):
    if c is None:
        return None
    c = c.strip().lower()
    if c in ("none", "transparent", ""):
        return None
    if c.startswith("url("):
        return None
    m = _HEX3.match(c)
    if m:
        return "#" + "".join(ch * 2 for ch in m.group(1)).lower()
    m = _HEX6.match(c)
    if m:
        return "#" + m.group(1).lower()
    m = _HEX8.match(c)
    if m:
        return "#" + m.group(1)[:6].lower()
    m = _RGB.match(c)
    if m:
        return "#%02x%02x%02x" % tuple(int(x) for x in m.groups())
    return None


def element_style(el):
    d = {}
    for k, v in el.attrib.items():
        name = etree.QName(k).localname if "}" in k else k
        if name in ("fill", "stroke", "stroke-width", "display", "fill-rule",
                    "opacity"):
            d[name] = v
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            d[k.strip()] = v.strip()
    return d


# --- path flattening ---------------------------------------------------------
def flatten_path(el, tol_mm):
    """Flatten an inkex path element in root user units (mm here)."""
    path = el.path.transform(el.composed_transform())
    csp = path.to_superpath()
    cspsubdiv(csp, tol_mm)
    subs = []
    for sp in csp:
        pts = [seg[1] for seg in sp]
        arr = np.asarray(pts, dtype=float)
        if len(arr) >= 3 and np.allclose(arr[0], arr[-1], atol=1e-6):
            arr = arr[:-1]
        if len(arr) >= 3:
            subs.append(arr)
    return subs


def _valid_polys(subs):
    out = []
    for arr in subs:
        try:
            p = Polygon(arr)
        except Exception:
            continue
        if p.is_empty:
            continue
        if not p.is_valid:
            g = make_valid(p)
            if g.geom_type == "Polygon":
                out.append(g)
            elif g.geom_type == "MultiPolygon":
                out.extend(g.geoms)
            continue
        out.append(p)
    return out


def polys_to_geom(polys, rule):
    """Combine subpath polygons honouring the SVG fill rule."""
    if not polys:
        return None
    if rule == "evenodd":
        g = None
        for p in polys:
            g = p if g is None else g.symmetric_difference(p)
        return _polygonal(g)
    # nonzero: union of every subpath minus the reversed subpaths that are
    # enclosed by a larger one (a hole drawn opposite to its body).  A reversed
    # subpath that is not enclosed is itself filled (winding != 0).
    allu = unary_union(polys)
    holes = []
    for i, p in enumerate(polys):
        if p.exterior.is_ccw:
            continue
        for j, q in enumerate(polys):
            if i != j and q.area > p.area and q.contains(p.representative_point()):
                holes.append(p)
                break
    if holes:
        allu = allu.difference(unary_union(holes))
    return _polygonal(allu)


def _polygonal(geom):
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    if geom.geom_type == "GeometryCollection":
        parts = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not parts:
            return None
        return unary_union(parts)
    return None


def fill_holes(geom):
    """Remove interior rings: the outer art edge, holes filled."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return Polygon(geom.exterior)
    parts = [Polygon(p.exterior) for p in geom.geoms]
    return _polygonal(unary_union(parts))


def ring_d(ring):
    c = list(ring.coords)
    if len(c) > 1 and c[0] == c[-1]:
        c = c[:-1]
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in c) + " Z"


def geom_to_d(geom):
    parts = []
    if geom.geom_type == "Polygon":
        parts.append(ring_d(geom.exterior))
        parts.extend(ring_d(r) for r in geom.interiors)
    elif geom.geom_type == "MultiPolygon":
        for p in geom.geoms:
            parts.append(ring_d(p.exterior))
            parts.extend(ring_d(r) for r in p.interiors)
    return " ".join(parts)


def subpaths_d(subpaths):
    return " ".join(
        "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in sp)
        for sp in subpaths if len(sp) >= 2)


def _at_fraction(pts, t):
    pts = np.asarray(pts, float)
    d = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    c = np.concatenate([[0.0], np.cumsum(d)])
    if c[-1] <= 0:
        return pts[0]
    target = float(np.clip(t, 0.0, 1.0)) * c[-1]
    k = int(np.searchsorted(c, target))
    k = min(max(k, 1), len(pts) - 1)
    seg = c[k] - c[k - 1]
    f = 0.0 if seg <= 0 else (target - c[k - 1]) / seg
    return pts[k - 1] + f * (pts[k] - pts[k - 1])


def _ring_chain(ext, start, end, step):
    """Boundary chain from vertex ``start`` to ``end`` stepping by ``step``."""
    idx = []
    i = start
    while True:
        idx.append(i)
        if i == end:
            break
        i = (i + step) % len(ext)
        if len(idx) > len(ext):
            return None
    return ext[idx]


def _polyline_len(pts):
    return float(np.linalg.norm(np.diff(np.asarray(pts, float), axis=0),
                                axis=1).sum())


def _min_near(r1, r2, lo, hi, n=41):
    """Smallest nearest-point distance between the rails over the middle of
    the column -- catches rails that interleave or pinch (thread packing)."""
    ls1, ls2 = LineString(r1), LineString(r2)
    vals = []
    for t in np.linspace(lo, hi, n):
        vals.append(ls2.distance(Point(_at_fraction(r1, t))))
        vals.append(ls1.distance(Point(_at_fraction(r2, t))))
    return min(vals)


def _split_on_axis(poly, axis):
    """Split a polygon's exterior into two chains at the extreme points of
    ``axis`` (the two split vertices)."""
    ext = np.asarray(poly.exterior.coords, float)
    if len(ext) >= 2 and np.allclose(ext[0], ext[-1]):
        ext = ext[:-1]
    n = np.linalg.norm(axis)
    if n <= 0:
        return None
    axis = np.asarray(axis, float) / n
    proj = ext @ axis
    i0 = int(np.argmin(proj))
    i1 = int(np.argmax(proj))
    if i0 == i1:
        return None
    r1 = _ring_chain(ext, i0, i1, 1)
    r2 = _ring_chain(ext, i0, i1, -1)
    if r1 is None or r2 is None:
        return None
    return r1, r2


def _search_split(poly, min_sep, max_sep, max_ratio, max_cand=18):
    """Search split vertices for the *two long edges* that stay furthest
    apart: the MRR axis split can land both vertices on the same horn of a
    bent / C-shaped plate, so the rails interleave and the satin fans from a
    point (measured: a 26 mm2 plate at the centipede head packed 61 mm of
    thread into one 1 mm cell).  Brute force over a bounded vertex subset,
    scored by the smallest nearest-point rail gap."""
    ext = np.asarray(poly.exterior.coords, float)
    if len(ext) >= 2 and np.allclose(ext[0], ext[-1]):
        ext = ext[:-1]
    n = len(ext)
    if n < 8:
        return None
    step = max(1, n // max_cand)
    cands = list(range(0, n, step))
    best = None
    for ai, i0 in enumerate(cands):
        for i1 in cands[ai + 1:]:
            r1 = _ring_chain(ext, i0, i1, 1)
            r2 = _ring_chain(ext, i0, i1, -1)
            if r1 is None or r2 is None:
                continue
            l1, l2 = _polyline_len(r1), _polyline_len(r2)
            if min(l1, l2) < 2.0:
                continue
            if max(l1, l2) / min(l1, l2) > max_ratio:
                continue
            seps = _paired_seps(r1, r2, 0.15, 0.85, n=25)
            if min(seps) < min_sep or max(seps) > max_sep:
                continue
            score = _min_near(r1, r2, 0.08, 0.92, n=25)
            if best is None or score > best[0]:
                best = (score, r1, r2, min(seps), max(seps))
    return best


def _fix_local_necks(pts, neck_mm, min_arc_mm, max_bridges=4):
    """Bridge the deepest tight hair-pins of a closed border ring.

    Where the ring passes back close to a non-adjacent part of itself (a narrow
    bay, most strongly the skull's fur comb) Ink/Stitch offsets the two sides of
    the hair-pin into crossing rails and fans the zigzag (measured: 35 mm of
    thread in one 1 mm cell, cross-stitches to 9.9 mm).  The deepest such
    excursion is replaced by its chord, which changes the centreline only at the
    neck; the ring stays a single closed path, so the silhouette-hugging border
    is preserved everywhere else.
    """
    pts = np.asarray(pts, float)
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    n = len(pts)
    if n < 8 or neck_mm <= 0:
        return np.vstack([pts, pts[:1]])
    tree = cKDTree(pts)
    mean_edge = float(np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0),
                                     axis=1).mean())
    removed = np.zeros(n, bool)
    bridged = 0
    while bridged < max_bridges:
        best = None                      # (arc_len, i, j) - deepest neck
        for i in range(n):
            if removed[i]:
                continue
            for j in tree.query_ball_point(pts[i], neck_mm):
                if j == i or removed[j]:
                    continue
                arc = min((i - j) % n, (j - i) % n) * mean_edge
                if arc <= min_arc_mm:
                    continue
                if best is None or arc > best[0]:
                    best = (arc, i, j)
        if best is None:
            break
        _, i, j = best
        fwd = (j - i) % n
        bwd = (i - j) % n
        span = min(fwd, bwd)
        for k in range(1, span):
            removed[(i + k) % n if fwd <= bwd else (j + k) % n] = True
        bridged += 1
    if os.environ.get("INVERT_DEBUG") and bridged:
        print(f"    [dbg neck] bridged {bridged} hair-pin(s)")
    keep = [pts[k] for k in range(n) if not removed[k]]
    if len(keep) < 3:
        return np.vstack([pts, pts[:1]])
    return np.vstack([keep, keep[:1]])


def split_rails(poly):
    """Split a polygon's exterior into two rails along the MRR long axis."""
    mrr = poly.minimum_rotated_rectangle
    mc = np.asarray(mrr.exterior.coords, float)
    edges = np.diff(mc, axis=0)
    lens = np.linalg.norm(edges, axis=1)
    return _split_on_axis(poly, edges[int(np.argmax(lens))])


def _split_variants(poly):
    """Candidate rail splits: the MRR long axis first, then the polygon's
    diameter (farthest pair), which can pick better split vertices on a very
    bent / concave plate."""
    out = []
    res = split_rails(poly)
    if res is not None:
        out.append(res)
    hull = poly.convex_hull
    hp = np.asarray(hull.exterior.coords, float)
    if len(hp) >= 3:
        d2 = ((hp[:, None, :] - hp[None, :, :]) ** 2).sum(-1)
        i0, i1 = np.unravel_index(int(np.argmax(d2)), d2.shape)
        res = _split_on_axis(poly, hp[i1] - hp[i0])
        if res is not None:
            out.append(res)
    return out


def _paired_seps(r1, r2, lo, hi, n=65):
    """Rail separation exactly as Ink/Stitch stitches it: both rails are
    interpolated by the same arc-length fraction (``plot_points_on_rails``),
    so this is the real cross-stitch length -- unlike a nearest-point distance,
    which collapses to ~0 across a concave bay that the satin bridges."""
    return [float(np.linalg.norm(_at_fraction(r1, t) - _at_fraction(r2, t)))
            for t in np.linspace(lo, hi, n)]


SPLIT_ROW_MM = 6.0          # a row wider than this needs another parallel row
MAX_ROWS = 3
ROW_OVERLAP_MM = 0.3        # adjacent rows share this much so no fabric shows
ROW_END_MIN_MM = 1.0        # stop a row's stitching before the rails pinch


def _trim_pinched_ends(r1, r2, min_width):
    """Cut both rails back to the longest central run whose cross-stitch is at
    least ``min_width``.  Ink/Stitch fans its zigzag where the rails pinch to a
    point; trimming there removes the fan (and the sub-1 mm stitches) at the
    cost of a thread-thin sliver of bare plate at the very tip."""
    ts = np.linspace(0.0, 1.0, 101)
    seps = [float(np.linalg.norm(_at_fraction(r1, t) - _at_fraction(r2, t)))
            for t in ts]
    good = [s >= min_width for s in seps]
    if not any(good):
        return r1, r2
    c = len(ts) // 2
    if not good[c]:
        c = min((i for i in range(len(good)) if good[i]),
                key=lambda i: abs(i - len(ts) // 2))
    i0 = c
    while i0 > 0 and good[i0 - 1]:
        i0 -= 1
    i1 = c
    while i1 < len(good) - 1 and good[i1 + 1]:
        i1 += 1
    if ts[i1] - ts[i0] < 0.5:
        # the plate is thin for most of its length; trimming would leave a big
        # bare gap, so keep the whole column (the tip fan is small there)
        return r1, r2
    tt = np.linspace(ts[i0], ts[i1], 25)
    return (np.array([_at_fraction(r1, t) for t in tt]),
            np.array([_at_fraction(r2, t) for t in tt]))


def _build_satin(r1, r2, trim_ends=True):
    """Rails + rungs for one satin column, and its stats."""
    if trim_ends:
        r1, r2 = _trim_pinched_ends(r1, r2, ROW_END_MIN_MM)
    l1, l2 = _polyline_len(r1), _polyline_len(r2)
    n_rung = int(np.clip(round(max(l1, l2) / 4.0), 3, 6))
    ls1, ls2 = LineString(r1), LineString(r2)
    rungs = []
    for i in range(1, n_rung + 1):
        t = i / (n_rung + 1.0)
        a = _at_fraction(r1, t)
        b = _at_fraction(r2, t)
        v = b - a
        nv = np.linalg.norm(v)
        if nv <= 1e-9:
            continue
        v = v / nv
        # A rung must cross each rail once.  Ink/Stitch cuts both rails at the
        # rung projections and zips the two cut lists; a rung that touches a
        # rail twice makes those lists unequal and raises (measured: a trimmed
        # row with a pinched end aborted the whole VP3 export).
        seg = LineString([a - 0.1 * v, b + 0.1 * v])
        if not seg.crosses(ls1) or not seg.crosses(ls2):
            continue
        rungs.append(np.array([a - 0.1 * v, b + 0.1 * v]))
    seps = _paired_seps(r1, r2, 0.15, 0.85)
    return [r1, r2] + rungs, dict(sep_min=min(seps), sep_max=max(seps),
                                  n_rung=len(rungs), rail_len=0.5 * (l1 + l2))


def _plate_rows(r1, r2, smax):
    """Split a plate into 1/2/3 parallel satin rows.

    A plate whose cross-stitch is wider than ``SPLIT_ROW_MM`` is cut with
    intermediate rails interpolated at equal fractional arc length between the
    two edge rails, so each row stitches 1.5-6 mm wide instead of relying on
    Ink/Stitch's length split.  Adjacent rows overlap by ``ROW_OVERLAP_MM``
    (each inner boundary is pushed 0.15 mm into the neighbour) and alternate
    direction so the needle continues from one row's end into the next."""
    ts = np.linspace(0.0, 1.0, 49)
    # sample both rails at the SAME arc-length fraction: Ink/Stitch pairs the
    # rails that way, so the intermediate rails stay exactly between them
    P1 = np.array([_at_fraction(r1, t) for t in ts])
    P2 = np.array([_at_fraction(r2, t) for t in ts])
    d = P2 - P1
    dl = np.linalg.norm(d, axis=1, keepdims=True)
    d = d / np.where(dl > 1e-9, dl, 1.0)

    def boundary(fr):
        return P1 + fr * (P2 - P1)

    def build(n_rows):
        rows = []
        for j in range(n_rows):
            lo = P1 if j == 0 else boundary(j / n_rows) - 0.5 * ROW_OVERLAP_MM * d
            hi = P2 if j == n_rows - 1 else boundary((j + 1) / n_rows) + 0.5 * ROW_OVERLAP_MM * d
            if j % 2 == 1:
                lo, hi = hi[::-1], lo[::-1]
            rows.append(_build_satin(lo, hi))
        return rows

    n_rows = (1 if smax <= SPLIT_ROW_MM
              else min(MAX_ROWS, int(math.ceil(smax / SPLIT_ROW_MM))))
    rows = build(n_rows)
    # the rails' arc-length distributions differ, so the stitched width (equal
    # arc-fraction pairing) can exceed smax/n; add a row until it fits
    while n_rows < MAX_ROWS and max(r["sep_max"] for _, r in rows) > SPLIT_ROW_MM:
        n_rows += 1
        rows = build(n_rows)
    if os.environ.get("INVERT_DEBUG"):
        print(f"    [dbg rows] n_rows={n_rows} plate_smax={smax:.2f} "
              f"rowmax={max(r['sep_max'] for _, r in rows):.2f}")
    return rows, n_rows


def try_plate_satin(comp, zigzag, min_sep=0.4, max_sep=14.0,
                    max_rail_ratio=2.5, min_gap=0.4, use_search=True):
    """Return (subpaths, stats) for a rail satin, or (None, reason).

    A plate is accepted when, over the body of the column:

    * the cross-stitch length (rails paired by equal arc fraction, exactly as
      Ink/Stitch stitches them) stays inside ``min_sep..max_sep``.  ``max_sep``
      is 14 mm: a wider plate is not a fill fallback, it is a *split* satin --
      Ink/Stitch cuts every cross-stitch longer than
      ``inkstitch:max_stitch_length_mm`` (7 mm here) into shorter stitches;
    * the two rails have comparable length (``max_rail_ratio``): a branched
      claw has one "rail" wrapping the whole boundary and its satin fans from
      a point;
    * the rails never come closer than ``min_gap`` (nearest-point distance):
      interleaving rails pack the needle.

    The split vertices are searched (``_search_split``) when the cheap MRR /
    diameter splits leave the rails interleaved.
    """
    simplified = Polygon(comp.exterior).simplify(0.05)
    if simplified.is_empty or simplified.geom_type != "Polygon":
        simplified = Polygon(comp.exterior)

    candidates = list(_split_variants(simplified))
    # Only search for better split vertices when a cheap split is already a
    # plausible satin (balanced rails and no deep interleave).  Without the
    # gate the search "rescues" branched claws by choosing two similar-length
    # chains that wrap different fingers -- the rows then overlap and pack
    # 70+ mm of thread into one 1 mm cell.
    if use_search:
        base_ok = False
        for r1, r2 in candidates:
            l1, l2 = _polyline_len(r1), _polyline_len(r2)
            if (max(l1, l2) / max(min(l1, l2), 1e-9) <= max_rail_ratio and
                    _min_near(r1, r2, 0.08, 0.92) >= 0.5):
                base_ok = True
                break
        if base_ok:
            search = _search_split(simplified, min_sep, max_sep, max_rail_ratio)
            if search is not None:
                candidates.append((search[1], search[2]))

    best = None
    reason = "degenerate rails"
    for r1, r2 in candidates:
        if not LineString(r1).is_simple or not LineString(r2).is_simple:
            reason = "self-intersecting rail"
            continue
        l1, l2 = LineString(r1).length, LineString(r2).length
        ratio = max(l1, l2) / max(min(l1, l2), 1e-9)
        if ratio > max_rail_ratio:
            reason = f"unequal rails {l1:.1f}/{l2:.1f} mm"
            continue
        # The rails meet at the split vertices by construction, so ignore the
        # pinched tips.  15 % each end also clears the innermost satin rung
        # (1/(6+1) ~ 14 %).
        seps = _paired_seps(r1, r2, 0.15, 0.85)
        smin, smax = min(seps), max(seps)
        gap = _min_near(r1, r2, 0.08, 0.92)
        if os.environ.get("INVERT_DEBUG"):
            print(f"    [dbg] area {comp.area:.1f} L1 {l1:.1f} L2 {l2:.1f} "
                  f"sep {smin:.2f}..{smax:.2f} gap {gap:.2f}")
        if smin < min_sep or smax > max_sep:
            reason = f"rail separation {smin:.2f}..{smax:.2f} mm"
            continue
        if gap < min_gap:
            reason = f"rails interleave (gap {gap:.2f} mm)"
            continue
        score = (gap, smin)
        if best is None or score > best[0]:
            best = (score, r1, r2, smin, smax)
    if best is None:
        return None, reason
    _, r1, r2, smin, smax = best
    rows, n_rows = _plate_rows(r1, r2, smax)
    return rows, dict(sep_min=smin, sep_max=smax, n_rows=n_rows,
                      rail_len=0.5 * (_polyline_len(r1) + _polyline_len(r2)))


# --- parse input -------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--ink", required=True,
                    help="comma-separated ink fill colours to drop (bare fabric)")
    ap.add_argument("--paper", default="#ffffff",
                    help="paper colour (default #ffffff); never stitched as-is")
    ap.add_argument("--plate-satin-colors", default="",
                    help="comma-separated fill colours whose components become satins")
    ap.add_argument("--border-mm", type=float, default=2.0)
    ap.add_argument("--border-neck-mm", type=float, default=2.2,
                    help="bridge the deepest border hair-pin whose two sides "
                         "pass this close (0 disables)")
    ap.add_argument("--border-neck-min-arc-mm", type=float, default=6.0,
                    help="only necks at least this deep along the ring are bridged")
    ap.add_argument("--fit-mm", default="260x200", help="WxH fit box in mm")
    ap.add_argument("--tol-mm", type=float, default=0.02)
    ap.add_argument("--white-dilate-mm", type=float, default=0.10)
    ap.add_argument("--green-clear-mm", type=float, default=0.05)
    ap.add_argument("--min-white-mic-mm", type=float, default=0.8)
    ap.add_argument("--min-white-area-mm2", type=float, default=1.0)
    ap.add_argument("--max-plate-sep-mm", type=float, default=14.0,
                    help="plates wider than this are not satin (split is used up "
                         "to here; above it a fill is kept)")
    ap.add_argument("--min-plate-sep-mm", type=float, default=0.4,
                    help="bulk rail separation below this falls back to fill")
    ap.add_argument("--min-plate-gap-mm", type=float, default=0.4,
                    help="nearest rail gap below this (interleaving) falls back")
    ap.add_argument("--no-plate-search", action="store_true",
                    help="do not search split vertices for interleaved rails")
    ap.add_argument("--underlay-off-mic-mm", type=float, default=2.5,
                    help="white components thinner than this get no fill underlay")
    ap.add_argument("--underlay-off-area-mm2", type=float, default=6.0,
                    help="white components smaller than this get no fill underlay")
    ap.add_argument("--skip-outline-label", default="Outline",
                    help="skip any layer with this inkscape:label entirely")
    ap.add_argument("--dump-dir", default=None)
    ap.add_argument("--px-per-mm", type=float, default=10.0)
    args = ap.parse_args()

    ink_colors = {norm_color(c) for c in args.ink.split(",") if c.strip()}
    ink_colors.discard(None)
    paper = norm_color(args.paper) or "#ffffff"
    plate_colors = [norm_color(c) for c in args.plate_satin_colors.split(",")
                    if c.strip()]
    plate_colors = [c for c in plate_colors if c]
    fit = args.fit_mm.lower().replace("×", "x").split("x")
    fit_w, fit_h = float(fit[0]), float(fit[1])
    if len(fit) > 2:
        fit_h = float(fit[1])
    tol = args.tol_mm

    # --- walk the SVG ---
    doc = inkex.load_svg(args.input)
    root = doc.getroot()
    SKIP = {"defs", "symbol", "image", "metadata", "namedview", "title", "desc",
            "style", "filter", "clippath", "mask"}

    colour_geoms = {}      # colour -> list of shapely geoms (document order)
    colour_order = []
    n_paths = 0

    def walk(el, ignore):
        nonlocal n_paths
        tag = etree.QName(el).localname.lower()
        if tag in SKIP:
            return
        style = element_style(el)
        label = (el.get("{%s}label" % "http://www.inkscape.org/namespaces/inkscape")
                 or el.get("inkscape:label") or "")
        if style.get("display") == "none":
            return
        if ignore or label == args.skip_outline_label:
            return
        if tag == "path":
            d = el.get("d") or ""
            if not d.strip():
                return
            fill = norm_color(style.get("fill"))
            if fill is None:
                return
            rule = (el.get("fill-rule") or style.get("fill-rule") or "nonzero").strip().lower()
            if rule not in ("evenodd", "nonzero"):
                rule = "nonzero"
            n_paths += 1
            try:
                subs = flatten_path(el, tol)
            except Exception as exc:
                print(f"warning: skipping path {el.get('id')!r}: {exc}")
                return
            geom = polys_to_geom(_valid_polys(subs), rule)
            if geom is None:
                return
            if fill not in colour_geoms:
                colour_geoms[fill] = []
                colour_order.append(fill)
            colour_geoms[fill].append(geom)
            return
        for ch in el:
            walk(ch, ignore)

    for child in root:
        walk(child, False)

    union = {c: _polygonal(unary_union(gs)) for c, gs in colour_geoms.items()}

    print(f"parsed {n_paths} visible fill path(s); colours: "
          f"{', '.join(colour_order)}")
    for c in colour_order:
        if union[c] is not None:
            print(f"  {c}: {union[c].area:.1f} mm2")

    # --- ink, plates, art silhouette ---
    ink = _polygonal(unary_union([union[c] for c in ink_colors
                                  if c in union and union[c] is not None]))
    if ink is None:
        sys.exit("error: no ink geometry found for --ink colours")
    plates = {}
    for c in plate_colors:
        if c in union and union[c] is not None:
            plates[c] = union[c]
    art_parts = [union[c] for c in colour_order
                 if c != paper and union[c] is not None]
    art = _polygonal(unary_union(art_parts)) if art_parts else None
    if art is None:
        sys.exit("error: no art geometry (besides paper) found")

    # silhouette S = art exterior, holes filled
    S0 = fill_holes(art)
    print(f"silhouette: {S0.geom_type}, area {S0.area:.1f} mm2, "
          f"ink {ink.area:.1f} mm2")
    for c, g in plates.items():
        print(f"  plate colour {c}: {g.area:.1f} mm2")

    # --- scale first, so later mm values are real ---
    bb = S0.buffer(args.border_mm, join_style=1).bounds
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    scale = min(fit_w / bw, fit_h / bh)
    W, H = bw * scale, bh * scale
    offx, offy = -bb[0] * scale, -bb[1] * scale

    def xf(g):
        if g is None:
            return None
        return _polygonal(affine_transform(g, [scale, 0, 0, scale, offx, offy]))

    ink = xf(ink)
    plates = {c: xf(g) for c, g in plates.items()}
    art = xf(art)
    S = fill_holes(art)
    bb2 = S.buffer(args.border_mm, join_style=1).bounds
    W, H = bb2[2] - bb2[0], bb2[3] - bb2[1]
    print(f"scale x{scale:.4f} -> fit {W:.1f} x {H:.1f} mm "
          f"(box {fit_w:g}x{fit_h:g})")

    # --- green visible and its components ---
    green_vis = {}
    n_plate_satin = n_plate_fill = n_plate_drop = 0
    row_hist = {}                  # rows per plate -> count
    satin_area = 0.0               # plate area stitched as satin
    green_satin_subpaths = {}      # colour -> list of (subpaths, stats, centroid)
    green_satin_comps = {}         # colour -> list of the plate polygons
    green_fill_geoms = {}          # colour -> list of polygons
    dropped = []
    fallback = []
    for c, g in plates.items():
        vis = _polygonal(g.difference(ink))
        if vis is None or vis.is_empty:
            continue
        comps = list(vis.geoms) if vis.geom_type == "MultiPolygon" else [vis]
        sat_list = []
        fill_list = []
        for comp in comps:
            if comp.geom_type != "Polygon" or comp.is_empty:
                continue
            if comp.area < 0.5:
                n_plate_drop += 1
                dropped.append(("plate", c, comp.area, comp.centroid.x, comp.centroid.y))
                continue
            if comp.area < 2.0:
                fill_list.append(comp)
                continue
            rows, st = try_plate_satin(comp, 0.35,
                                       min_sep=args.min_plate_sep_mm,
                                       max_sep=args.max_plate_sep_mm,
                                       min_gap=args.min_plate_gap_mm,
                                       use_search=not args.no_plate_search)
            if rows is None:
                fallback.append((c, round(comp.area, 2), st,
                                 round(comp.centroid.x, 1), round(comp.centroid.y, 1)))
                fill_list.append(comp)
            else:
                for sub, rstat in rows:
                    sat_list.append((sub, rstat, comp))
                row_hist[st["n_rows"]] = row_hist.get(st["n_rows"], 0) + 1
                satin_area += comp.area
        green_satin_subpaths[c] = sat_list
        green_satin_comps[c] = [sc for _, _, sc in sat_list]
        green_fill_geoms[c] = fill_list
        n_plate_satin += len(sat_list)
        n_plate_fill += len(fill_list)

    print(f"green: {n_plate_satin} plate satin row(s), {n_plate_fill} fill(s), "
          f"{n_plate_drop} dropped (<0.5 mm2, {sum(d[2] for d in dropped):.2f} mm2)")
    if row_hist:
        fill_area = sum(f.area for fl in green_fill_geoms.values() for f in fl)
        area_total = satin_area + fill_area
        dist = ", ".join(f"{k} row(s): {v} plate(s)"
                         for k, v in sorted(row_hist.items()))
        print(f"  rows per plate: {dist}; satin plate area {satin_area:.1f}/"
              f"{area_total:.1f} mm2 "
              f"({100.0 * satin_area / area_total if area_total else 0:.1f}%)")
    if fallback:
        print(f"  {len(fallback)} plate(s) fell back to fill:")
        for c, a, why, cx, cy in fallback:
            print(f"    {c} {a} mm2 at ({cx},{cy}): {why}")

    # guarantee at least one green fill so svg_digitize emits green before
    # white (its colour order is fills-first, then fill-less satin colours)
    has_green_fill = any(green_fill_geoms.get(c) for c in plate_colors)
    if not has_green_fill and any(green_satin_subpaths.get(c) for c in plate_colors):
        # convert the smallest satin plate to a fill
        smallest = None
        for c in plate_colors:
            for i, (sub, st, cen) in enumerate(green_satin_subpaths.get(c, [])):
                if smallest is None or st["rail_len"] < smallest[3]:
                    smallest = (c, i, sub, st["rail_len"])
        if smallest is not None:
            c, i, sub, _ = smallest
            # rebuild the component polygon from its rails is lossy; keep the
            # rail satin AND add the plate footprint as a fill underneath
            band = band_from_rails(sub[:2])
            if band is not None:
                green_fill_geoms.setdefault(c, []).append(band)
                print(f"note: no green fill existed; added plate footprint as "
                      f"green fill under {c} satin to keep stitch order green->white")

    # --- white fills ---
    white = S.difference(ink.buffer(args.white_dilate_mm, join_style=2))
    gvis_all = _polygonal(unary_union(
        [g for c in plates for g in [plates[c]] if g is not None]).difference(ink)) \
        if plates else None
    if gvis_all is not None:
        white = white.difference(gvis_all.buffer(args.green_clear_mm, join_style=2))
    white = _polygonal(white)

    kept_white = []
    white_no_underlay = []      # parallel flags, see below
    n_wdrop = 0
    n_nounderlay = 0
    wdrop_area = 0.0
    if white is not None:
        comps = list(white.geoms) if white.geom_type == "MultiPolygon" else [white]
        for comp in comps:
            if comp.geom_type != "Polygon" or comp.is_empty:
                continue
            try:
                mic = 2.0 * maximum_inscribed_circle(comp).length
            except Exception:
                mic = float("inf")
            if mic < args.min_white_mic_mm or comp.area < args.min_white_area_mm2:
                n_wdrop += 1
                wdrop_area += comp.area
                continue
            # A narrow or tiny white detail cannot carry a tatami fill plus an
            # underlay without packing the needle: on the skull's "fur" comb the
            # underlay of one thin stroke packed a 1 mm cell with ~35 mm of
            # thread and sewed 8-10 mm stitches across the black gap.  Drop the
            # underlay (the top fill still gives full coverage on the detail).
            off = (mic < args.underlay_off_mic_mm or
                   comp.area < args.underlay_off_area_mm2)
            kept_white.append(comp)
            white_no_underlay.append(off)
            n_nounderlay += int(off)
    print(f"white: {len(kept_white)} fill component(s), "
          f"{n_wdrop} dropped (< {args.min_white_mic_mm} mm mic or "
          f"< {args.min_white_area_mm2} mm2; {wdrop_area:.2f} mm2), "
          f"{n_nounderlay} without underlay (mic < {args.underlay_off_mic_mm} mm "
          f"or area < {args.underlay_off_area_mm2} mm2)")
    if kept_white:
        wu = unary_union(kept_white)
        print(f"  white area {wu.area:.1f} mm2")

    # --- border ---
    border_centre = None
    border_band = None
    bridged = []
    bridge_area = 0.0
    bc = args.border_mm / 2.0
    Sc = S.buffer(bc + 0.6, join_style=1).buffer(-0.6, join_style=1)
    Sc = _polygonal(Sc)
    if Sc is None or Sc.is_empty:
        Sc = S
    # islands: one border per component >= 30 mm perimeter
    sc_parts = sorted(Sc.geoms, key=lambda p: p.area, reverse=True) \
        if Sc.geom_type == "MultiPolygon" else [Sc]
    centres = []
    for p in sc_parts:
        if p.exterior.length < 30.0 and len(sc_parts) > 1:
            print(f"note: skipping border island perimeter {p.exterior.length:.1f} mm")
            continue
        ring = np.asarray(p.exterior.simplify(0.05).coords, float)
        centres.append(_fix_local_necks(ring, args.border_neck_mm,
                                        args.border_neck_min_arc_mm))
    # bridge locations: closing filled a notch (Sc extends inside S.buffer(bc))
    try:
        base = S.buffer(bc, join_style=1)
        added = Sc.difference(base)
        if not added.is_empty:
            acomp = list(added.geoms) if added.geom_type == "MultiPolygon" else [added]
            for a in acomp:
                if a.area > 0.05:
                    bridged.append((round(a.centroid.x, 1), round(a.centroid.y, 1),
                                    round(a.area, 2)))
                    bridge_area += a.area
    except Exception:
        pass
    border_centre = centres[0] if len(centres) == 1 else centres

    # band footprint (for dump / coverage): centreline buffered by border/2
    bands = [LineString(c).buffer(args.border_mm / 2.0, join_style=1)
             for c in centres]
    border_band = _polygonal(unary_union(bands)) if bands else None
    perim = sum(LineString(c).length for c in centres)
    # how much of the band sits on ink
    band_on_ink = 0.0
    if border_band is not None:
        band_on_ink = border_band.intersection(ink).area
    print(f"border: {len(centres)} centreline(s), perimeter {perim:.1f} mm, "
          f"band {args.border_mm} mm; band∩ink {band_on_ink:.2f} mm2 "
          f"(limit {0.2 * perim:.1f})")
    if bridged:
        print(f"  closing bridged {len(bridged)} notch(es) "
              f"({bridge_area:.2f} mm2): {bridged[:12]}")

    # --- emit ---
    def path_fill(color, geom, extra=""):
        return (f'<path style="fill:{color};fill-rule:evenodd;stroke:none" '
                f'{extra}d="{geom_to_d(geom)}"/>')

    plate_attr = (
        'inkstitch:satin_column="true" inkstitch:zigzag_spacing_mm="0.35" '
        'inkstitch:pull_compensation_mm="0.15 0.15" '
        'inkstitch:center_walk_underlay="true" '
        'inkstitch:contour_underlay="true" '
        'inkstitch:contour_underlay_inset_mm="0.4" '
        'inkstitch:max_stitch_length_mm="7" inkstitch:split_method="default"')
    border_attr = (
        'inkstitch:satin_column="true" inkstitch:zigzag_spacing_mm="0.35" '
        'inkstitch:pull_compensation_mm="0.1 0.1" '
        'inkstitch:center_walk_underlay="false" '
        'inkstitch:contour_underlay="false" '
        'inkstitch:max_stitch_length_mm="7" '
        'inkstitch:short_stitch_inset="20"')

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.append(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:inkstitch="http://inkstitch.org/namespace" '
        f'width="{W:.2f}mm" height="{H:.2f}mm" viewBox="0 0 {W:.2f} {H:.2f}">\n')
    out.append('<metadata id="metadata1">'
               '<inkstitch:inkstitch_svg_version>4</inkstitch:inkstitch_svg_version>'
               '</metadata>\n')

    out.append('<g inkscape:groupmode="layer" inkscape:label="green" id="green">\n')
    for c in plate_colors:
        for poly in green_fill_geoms.get(c, []):
            out.append("  " + path_fill(c, poly) + "\n")
        for sub, st, cen in green_satin_subpaths.get(c, []):
            out.append(f'  <path style="fill:none;stroke:{c};stroke-width:0.1" '
                       f'{plate_attr} d="{subpaths_d(sub)}"/>\n')
    out.append('</g>\n')

    out.append('<g inkscape:groupmode="layer" inkscape:label="white" id="white">\n')
    for poly, off in zip(kept_white, white_no_underlay):
        extra = 'inkstitch:fill_underlay="false" ' if off else ""
        out.append("  " + path_fill("#ffffff", poly, extra) + "\n")
    out.append('</g>\n')

    out.append('<g inkscape:groupmode="layer" inkscape:label="border" id="border">\n')
    for cen in centres:
        out.append(f'  <path style="fill:none;stroke:#ffffff;'
                   f'stroke-width:{args.border_mm:.2f}" {border_attr} '
                   f'd="{ring_d(LineString(cen))}"/>\n')
    out.append('</g>\n')
    out.append('</svg>\n')

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("".join(out))
    print(f"wrote {args.output}")

    # per-row satin cross-stitch length (rail separation) distribution
    seps = [st["sep_max"] for c in plate_colors
            for _, st, _ in green_satin_subpaths.get(c, [])]
    lo = [st["sep_min"] for c in plate_colors
          for _, st, _ in green_satin_subpaths.get(c, [])]
    if seps:
        over = sum(1 for s in seps if s > 6.0)
        under = sum(1 for s in lo if s < 1.5)
        print(f"satin row stitch length (max sep): min {min(seps):.2f} / "
              f"median {np.median(seps):.2f} / max {max(seps):.2f} mm; "
              f"{over} row(s) > 6 mm, {under} row(s) < 1.5 mm at the pinch")
        print(f"  row min sep: min {min(lo):.2f} / median {np.median(lo):.2f} / "
              f"max {max(lo):.2f} mm")

    # --- dump target for verification ---
    if args.dump_dir:
        dump_targets(args.dump_dir, W, H, args.px_per_mm, ink, plates, ink_colors,
                     kept_white, border_band, S, green_satin_subpaths,
                     green_satin_comps, green_fill_geoms, plate_colors, art)
        print(f"dumped target masks to {args.dump_dir}")


def band_from_rails(rails):
    strips = []
    for r in rails:
        if len(r) >= 2:
            strips.append(LineString(np.asarray(r, float)).buffer(0.3, join_style=2))
    if not strips:
        return None
    return _polygonal(unary_union(strips))


def dump_targets(dump_dir, W, H, px, ink, plates, ink_colors, kept_white,
                 border_band, S, green_satin_subpaths, green_satin_comps,
                 green_fill_geoms, plate_colors, art):
    os.makedirs(dump_dir, exist_ok=True)
    iw, ih = int(math.ceil(W * px)), int(math.ceil(H * px))

    def mask_of(geom):
        img = Image.new("L", (iw, ih), 0)
        if geom is None or geom.is_empty:
            return img
        d = ImageDraw.Draw(img)
        parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for p in parts:
            if p.geom_type != "Polygon":
                continue
            pts = [(x * px, y * px) for x, y in p.exterior.coords]
            d.polygon(pts, fill=255)
            for r in p.interiors:
                d.polygon([(x * px, y * px) for x, y in r.coords], fill=0)
        return img

    # green kept: the full plate polygons (fills + satin plates), i.e. G
    gpolys = []
    for c in plate_colors:
        gpolys.extend(green_fill_geoms.get(c, []))
        gpolys.extend(green_satin_comps.get(c, []))
    green_keep = _polygonal(unary_union(gpolys)) if gpolys else None
    white_keep = _polygonal(unary_union(kept_white)) if kept_white else None

    m_white = mask_of(white_keep)
    m_green = mask_of(green_keep)
    m_ink = mask_of(ink)
    m_border = mask_of(border_band)
    m_inside = mask_of(S)

    np.savez_compressed(os.path.join(dump_dir, "target_masks.npz"),
                        white=np.asarray(m_white) > 0,
                        green=np.asarray(m_green) > 0,
                        ink=np.asarray(m_ink) > 0,
                        border=np.asarray(m_border) > 0,
                        inside=np.asarray(m_inside) > 0,
                        W=np.array([W]), H=np.array([H]), px=np.array([px]))

    # visual target: bg #101010, ink bare (bg), green green, white+border white
    vis = Image.new("RGB", (iw, ih), (16, 16, 16))
    vis.paste((135, 247, 15), (0, 0), m_green)
    vis.paste((255, 255, 255), (0, 0), m_white)
    vis.paste((255, 255, 255), (0, 0), m_border)
    vis.save(os.path.join(dump_dir, "target.png"))


if __name__ == "__main__":
    main()
