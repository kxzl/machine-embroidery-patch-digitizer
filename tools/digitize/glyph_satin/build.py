"""Desperado Club digitizer: components -> satin columns (rails + rungs) -> Ink/Stitch SVG."""
import math, os, pickle, sys, json
import numpy as np
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union
from geom import *

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
JPG = REPO + "/input/desperado_club.jpg"
OLD_SVG = REPO + "/output_inkstitch_svg/desperado_club.svg"
PX_MM = PPM


def comp_info(p):
    b = p.bounds
    return dict(x=b[0] / PPM, y=b[1] / PPM, w=(b[2] - b[0]) / PPM, h=(b[3] - b[1]) / PPM, a=p.area / PPM ** 2)


def classify(p):
    """Return one of ring, star, pommel, guard, grip, blade, letter."""
    i = comp_info(p)
    if i["a"] > 200 and i["w"] > 80:
        return "ring"
    if 83 < i["y"] < 86 and 6 < i["w"] < 8 and 6 < i["h"] < 8:
        return "star"
    cx = (p.bounds[0] + p.bounds[2]) / 2 / PPM
    # dagger column: centre x ~ 103.5 mm
    if abs(cx - 103.5) < 1.2 and i["y"] < 41:
        if i["y"] < 17 and i["w"] > 6:
            return "pommel"
        return "grip"
    return "letter"


# --------------------------------------------------------------------------- special shapes
def fit_star(p):
    """Regular five point star fitted to a polygon: returns centre, R_out, R_in, rot (tip 0 angle)."""
    pts = np.array(p.exterior.coords)
    c = np.array(p.centroid.coords[0])
    d = np.hypot(*(pts - c).T)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    # outer radius: mean of the top-5 local maxima of radius vs angle
    order = np.argsort(ang)
    ang_s, d_s = ang[order], d[order]
    # fit tips by search over rotation maximising sum of d at tip angles
    best = None
    for rot in np.linspace(0, 2 * math.pi / 5, 721):
        tips = rot + np.arange(5) * 2 * math.pi / 5
        v = sum(np.interp(t, np.concatenate([ang_s - 2 * math.pi, ang_s, ang_s + 2 * math.pi]),
                          np.concatenate([d_s, d_s, d_s])) for t in tips)
        if best is None or v > best[0]:
            best = (v, rot)
    rot = best[1]
    tips = rot + np.arange(5) * 2 * math.pi / 5
    A3 = np.concatenate([ang_s - 2 * math.pi, ang_s, ang_s + 2 * math.pi])
    D3 = np.concatenate([d_s, d_s, d_s])
    Ro = float(np.mean([np.interp(t, A3, D3) for t in tips]))
    inn = tips + math.pi / 5
    Ri = float(np.mean([np.interp(t, A3, D3) for t in inn]))
    return c, Ro, Ri, rot


def star_satins(p, ext_px=3.0):
    """Five arm triangles (stitches parallel to each arm's base) plus a centre pentagon of chords."""
    c, Ro, Ri, rot = fit_star(p)
    out = []
    P = lambda r, a: c + r * np.array([math.cos(a), math.sin(a)])
    for k in range(5):
        a = rot + k * 2 * math.pi / 5
        tip = P(Ro, a)
        vl = P(Ri, a - math.pi / 5)
        vr = P(Ri, a + math.pi / 5)
        # extend the base a little along the outline edges into the core so arms overlap it
        el = vl + (vl - tip) / np.linalg.norm(vl - tip) * ext_px
        er = vr + (vr - tip) / np.linalg.norm(vr - tip) * ext_px
        n = 4
        Lr = [el + (tip - el) * i / n for i in range(n + 1)]
        Rr = [er + (tip - er) * i / n for i in range(n + 1)]
        out.append(dict(L=np.array(Lr), R=np.array(Rr), rung_idx=[], kind="star", centers=None))
    pent = Polygon([tuple(P(Ri, rot + math.pi / 5 + k * 2 * math.pi / 5)) for k in range(5)])
    pc = circle_satin(pent.buffer(0.4), n=6)
    pc["kind"] = "star"
    out.append(pc)
    return out


def circle_satin(p, n=28):
    """Satin for a roundish blob: rails = left/right half outline, rungs horizontal (chords)."""
    b = p.bounds
    top = (b[1] + b[3]) / 2 - (b[3] - b[1]) / 2
    ys = np.linspace(b[1] + 0.3, b[3] - 0.3, n)
    L, R = [], []
    for y in ys:
        ln = LineString([(b[0] - 5, y), (b[2] + 5, y)]).intersection(p)
        xs = [c[0] for g in getattr(ln, "geoms", [ln]) for c in g.coords]
        L.append((min(xs), y))
        R.append((max(xs), y))
    L = np.array(L)
    R = np.array(R)
    return dict(L=L, R=R, rung_idx=[], kind="circle", centers=None)


# --------------------------------------------------------------------------- stroke satin for a polygon
def stroke_satins(poly, prune_k=1.6, pair_deg=40.0, butt=True, overlap_px=3.0, **kw):
    man = manual_for(poly)
    if man is not None:
        print('   manual strokes for a letter at x=%.1f' % (poly.bounds[0] / PPM))
        return manual_satins(poly, man, overlap_px=overlap_px, **{k: v for k, v in kw.items() if k in ('h','rung_every','smooth_k','reach_mult')}), None
    G0 = medial_graph(poly)
    G = prune(G0, k=prune_k)
    chains = build_chains(G, pair_deg=pair_deg)
    prepared = []
    for ch in chains:
        nodes = ch["nodes"]
        if ch["closed"] and nodes[0] == nodes[-1] and len(nodes) > 8:
            m = nodes[:-1]
            k = int(np.argmin([G.nodes[n]["r"] for n in m]))
            nodes = m[k:] + m[:k] + [m[k]]
        closed = len(nodes) > 2 and nodes[0] == nodes[-1]
        jends = 0 if closed else int(G.degree(nodes[0]) >= 3) + int(G.degree(nodes[-1]) >= 3)
        length = sum(G.edges[a, b]["length"] for a, b in zip(nodes[:-1], nodes[1:]))
        prepared.append((jends, -length, nodes))
    # through strokes first (leaf-to-leaf), then strokes that end at a junction, longest first
    prepared.sort(key=lambda t: (t[0], t[1]))
    ctx = Ctx(overlap_px) if butt else None
    out = []
    for jends, _, nodes in prepared:
        for s in chain_to_satins(G, poly, nodes, ctx=ctx, **kw):
            s["kind"] = "stroke"
            pr = satin_quality(s)
            if pr and len(s["L"]) <= 40:
                print("   drop satin:", pr, "len", len(s["L"]), "at mm", np.round(s["L"][0] / PPM, 1))
                continue
            if pr:
                print("   WARN kept long satin:", pr, "len", len(s["L"]), "at mm", np.round(s["L"][0] / PPM, 1))
            out.append(s)
    return out, G


def manual_satins(poly, strokes, overlap_px=3.0, **kw):
    """Explicit strokes: list of dict(pts=[(x_mm, y_mm), ...], r=half-width mm, k0, k1), in priority order.
    Later strokes are clipped against the bands of earlier ones (butt joints)."""
    ctx = Ctx(overlap_px)
    out = []
    for st in strokes:
        pos = np.array(st["pts"], float) * PPM
        rad = np.full(len(pos), st["r"] * PPM)
        s = polyline_to_satin(poly, pos, rad, st.get("k0", "leaf"), st.get("k1", "leaf"), ctx=ctx, **kw)
        if s:
            for t in repair_rungs(s):
                t["kind"] = "stroke"
                ctx.add(t)
                out.append(t)
    return out


# letters digitized by hand: key = (x_mm of bbox left, tolerance), value = strokes
MANUAL = {
    "N_FUN": dict(x=91.78, y=73.7, strokes=[
        dict(pts=[(92.275, 73.9), (92.275, 80.05)], r=0.49),
        dict(pts=[(94.695, 73.9), (94.695, 80.05)], r=0.5),
        dict(pts=[(92.76, 73.95), (94.46, 80.0)], r=0.44),
    ]),
}


def manual_for(poly):
    b = poly.bounds
    for name, m in MANUAL.items():
        if abs(b[0] / PPM - m["x"]) < 0.25 and abs(b[1] / PPM - m["y"]) < 0.25:
            return m["strokes"]
    return None


# --------------------------------------------------------------------------- SVG emit
def fmt(pts):
    return " ".join("L %.2f,%.2f" % (x, y) if i else "M %.2f,%.2f" % (x, y) for i, (x, y) in enumerate(pts))


def emit_rungs(s):
    """Rung indices to write.  Ink/Stitch cannot tell rails from rungs when there are exactly
    two rungs (four subpaths) and guesses 'the two longest', which on short pieces picks rungs
    and sews a bow-tie.  So never emit exactly two: use three instead."""
    n = len(s["L"])
    idx = [i for i in s.get("rung_idx", []) if 0 < i < n - 1]
    if len(idx) == 2 and n >= 5:
        idx = sorted({max(1, round(n * 0.25)), round(n * 0.5), min(n - 2, round(n * 0.75))})
        if len(idx) == 2:
            idx = idx[:1]
    return idx


def satin_path(s, pull_mm=0.2, extra_attrs=""):
    L, R = s["L"], s["R"]
    d = fmt(L) + " " + fmt(R)
    for i in emit_rungs(s):
        a, b = L[i], R[i]
        v = b - a
        d += " M %.2f,%.2f L %.2f,%.2f" % (a[0] - v[0] * 0.04, a[1] - v[1] * 0.04, b[0] + v[0] * 0.04, b[1] + v[1] * 0.04)
    return d


def svg_header(w=2752, h=1536):
    mmw = w / PPM
    mmh = h / PPM
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkstitch="http://inkstitch.org/namespace" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd" '
            f'width="{mmw:.2f}mm" height="{mmh:.2f}mm" viewBox="0 0 {w} {h}" inkscape:document-units="mm" sodipodi:docname="design.svg">\n'
            f'  <sodipodi:namedview id="namedview1" pagecolor="#ffffff" units="mm" inkscape:document-units="mm" pagewidth="{mmw:.2f}" pageheight="{mmh:.2f}" '
            'inkscape:pageopacity="0.0" inkscape:pagecheckerboard="0" showgrid="false"/>\n'
            '  <metadata id="metadata1"><inkstitch:inkstitch_svg_version>4</inkstitch:inkstitch_svg_version>'
            '<inkstitch:collapse_len_mm>3</inkstitch:collapse_len_mm></metadata>\n'
            '  <g inkscape:label="#fcfcfc" inkscape:groupmode="layer" id="color0">\n')


def width_mm(s):
    return float(np.median(np.hypot(*(s["L"] - s["R"]).T))) / PPM


def underlay_attrs(w_mm):
    a = ""
    if w_mm >= 1.8:
        a += ' inkstitch:center_walk_underlay="true" inkstitch:center_walk_underlay_stitch_length_mm="2.5"'
    if w_mm >= 3.2:
        a += ' inkstitch:zigzag_underlay="true" inkstitch:zigzag_underlay_spacing_mm="2.0" inkstitch:zigzag_underlay_inset_mm="0.4"'
    return a


def write_svg(satins, path, pull_mm=0.2, ring_xml=""):
    out = [svg_header()]
    for i, s in enumerate(satins):
        d = satin_path(s)
        w = width_mm(s)
        attrs = underlay_attrs(w)
        trim = ' inkstitch:trim_after="true"' if s.get("trim_after") else ""
        pm = s.get("pull_mm", pull_mm)
        out.append(f'    <path id="s{i}" style="fill:none;stroke:#fcfcfc;stroke-width:{max(w,1.0)*PPM:.2f}" inkstitch:satin_column="true" '
                   f'inkstitch:pull_compensation_mm="{pm} {pm}"{attrs}{trim} d="{d}"/>\n')
    out.append(ring_xml)
    out.append("  </g>\n</svg>\n")
    open(path, "w").write("".join(out))
