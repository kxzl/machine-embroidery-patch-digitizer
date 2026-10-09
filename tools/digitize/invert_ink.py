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


def split_rails(poly):
    """Split a polygon's exterior into two rails along the MRR long axis."""
    ext = np.asarray(poly.exterior.coords, float)
    if len(ext) >= 2 and np.allclose(ext[0], ext[-1]):
        ext = ext[:-1]
    mrr = poly.minimum_rotated_rectangle
    mc = np.asarray(mrr.exterior.coords, float)
    edges = np.diff(mc, axis=0)
    lens = np.linalg.norm(edges, axis=1)
    u = edges[int(np.argmax(lens))]
    n = np.linalg.norm(u)
    if n <= 0:
        return None
    u = u / n
    proj = ext @ u
    i0 = int(np.argmin(proj))
    i1 = int(np.argmax(proj))
    if i0 == i1:
        return None

    def chain(start, end, step):
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

    r1 = chain(i0, i1, 1)
    r2 = chain(i0, i1, -1)
    return r1, r2


def try_plate_satin(comp, zigzag):
    """Return (subpaths, stats) for a rail satin, or (None, reason)."""
    simplified = Polygon(comp.exterior).simplify(0.05)
    if simplified.is_empty or simplified.geom_type != "Polygon":
        simplified = Polygon(comp.exterior)
    res = split_rails(simplified)
    if res is None:
        return None, "degenerate rails"
    r1, r2 = res
    if not LineString(r1).is_simple or not LineString(r2).is_simple:
        return None, "self-intersecting rail"
    # Cross-stitch length = local band width.  Sample along each rail and take
    # the distance to the opposite rail (nearest point, i.e. perpendicular-ish
    # width, not the equal-fraction pairing which pinches on a curved band).
    # The rails meet at the two MRR-axis tips by construction, so ignore 8 % at
    # each end.
    ls1, ls2 = LineString(r1), LineString(r2)
    ties = np.linspace(0.0, 1.0, 65)
    ties = ties[(ties >= 0.08) & (ties <= 0.92)]
    seps = []
    for t in ties:
        seps.append(float(ls2.distance(Point(_at_fraction(r1, t)))))
        seps.append(float(ls1.distance(Point(_at_fraction(r2, t)))))
    smax = max(seps)
    smin = min(seps)
    if os.environ.get("INVERT_DEBUG"):
        print(f"    [dbg] area {comp.area:.1f} r1 {len(r1)} r2 {len(r2)} "
              f"L1 {LineString(r1).length:.1f} L2 {LineString(r2).length:.1f} "
              f"sep {smin:.2f}..{smax:.2f}")
    if smin < 1.0:
        return None, f"rail separation {smin:.2f} mm < 1.0"
    if smax > 9.0:
        return None, f"rail separation {smax:.2f} mm > 9.0"
    l1, l2 = LineString(r1).length, LineString(r2).length
    n_rung = int(np.clip(round(max(l1, l2) / 4.0), 3, 6))
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
        rungs.append(np.array([a - 0.1 * v, b + 0.1 * v]))
    subpaths = [r1, r2] + rungs
    return subpaths, dict(sep_min=smin, sep_max=smax, n_rung=len(rungs),
                          rail_len=0.5 * (l1 + l2))


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
    ap.add_argument("--fit-mm", default="260x200", help="WxH fit box in mm")
    ap.add_argument("--tol-mm", type=float, default=0.02)
    ap.add_argument("--white-dilate-mm", type=float, default=0.10)
    ap.add_argument("--green-clear-mm", type=float, default=0.05)
    ap.add_argument("--min-white-mic-mm", type=float, default=0.8)
    ap.add_argument("--min-white-area-mm2", type=float, default=1.0)
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
            sub, st = try_plate_satin(comp, 0.35)
            if sub is None:
                fallback.append((c, round(comp.area, 2), st,
                                 round(comp.centroid.x, 1), round(comp.centroid.y, 1)))
                fill_list.append(comp)
            else:
                sat_list.append((sub, st, comp))
        green_satin_subpaths[c] = sat_list
        green_satin_comps[c] = [sc for _, _, sc in sat_list]
        green_fill_geoms[c] = fill_list
        n_plate_satin += len(sat_list)
        n_plate_fill += len(fill_list)

    print(f"green: {n_plate_satin} plate satin(s), {n_plate_fill} fill(s), "
          f"{n_plate_drop} dropped (<0.5 mm2, {sum(d[2] for d in dropped):.2f} mm2)")
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
    n_wdrop = 0
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
            kept_white.append(comp)
    print(f"white: {len(kept_white)} fill component(s), "
          f"{n_wdrop} dropped (< {args.min_white_mic_mm} mm mic or "
          f"< {args.min_white_area_mm2} mm2; {wdrop_area:.2f} mm2)")
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
        centres.append(np.asarray(p.exterior.simplify(0.05).coords, float))
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
    def path_fill(color, geom):
        return (f'<path style="fill:{color};fill-rule:evenodd;stroke:none" '
                f'd="{geom_to_d(geom)}"/>')

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
        'inkstitch:center_walk_underlay="true" '
        'inkstitch:contour_underlay="true" '
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
    for poly in kept_white:
        out.append("  " + path_fill("#ffffff", poly) + "\n")
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

    # min/median/max plate stitch length (rail separation medians)
    seps = [st["sep_max"] for c in plate_colors
            for _, st, _ in green_satin_subpaths.get(c, [])]
    if seps:
        print(f"plate stitch length (max sep per plate): "
              f"min {min(seps):.2f} / median {np.median(seps):.2f} / "
              f"max {max(seps):.2f} mm")

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
