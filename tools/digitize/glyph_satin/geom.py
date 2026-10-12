"""Geometry core: smooth outlines, medial axis, stroke chains, satin rails and rungs.

All coordinates are SVG px (the 2752 x 1536 viewBox of the source JPG, 13.29 px/mm).
"""
import math
import numpy as np
import networkx as nx
import shapely
from shapely.geometry import Polygon, LineString, Point, MultiPoint
from shapely.ops import unary_union
from scipy import ndimage as ndi
from scipy.spatial import Voronoi, cKDTree
from skimage import measure

PPM = 2752 / 207.07


# --------------------------------------------------------------------------- outlines
def load_polygons(jpg, sigma=1.0, level=127.5, min_area_mm2=0.4, min_hole_mm2=1.2):
    from PIL import Image
    g = np.asarray(Image.open(jpg).convert("L")).astype(float)
    g = ndi.gaussian_filter(g, sigma)
    cs = measure.find_contours(np.pad(g, 1, constant_values=0), level)
    rings = []
    for c in cs:
        if len(c) < 8 or not np.allclose(c[0], c[-1]):
            continue
        pts = [(x - 1, y - 1) for y, x in c[:-1]]
        p = Polygon(pts)
        if p.is_valid and p.area > 0:
            rings.append(p)
    rings.sort(key=lambda p: -p.area)
    depth = []
    parent = []
    for i, p in enumerate(rings):
        d = 0
        par = None
        for j in range(i):
            if rings[j].contains(p.representative_point()):
                d += 1
                par = j  # last (smallest) container wins since sorted by area desc
        depth.append(d)
        parent.append(par)
    outers = {}
    for i, p in enumerate(rings):
        if depth[i] % 2 == 0:
            outers[i] = [p, []]
    for i, p in enumerate(rings):
        if depth[i] % 2 == 1 and parent[i] in outers:
            if p.area / PPM ** 2 >= min_hole_mm2:
                outers[parent[i]][1].append(p)
    polys = []
    for i, (p, holes) in outers.items():
        if p.area / PPM ** 2 < min_area_mm2:
            continue
        poly = Polygon(p.exterior.coords, [h.exterior.coords for h in holes])
        polys.append(poly.buffer(0))
    return polys


# --------------------------------------------------------------------------- medial axis
def _sample_ring(coords, step):
    ls = LineString(coords)
    n = max(int(ls.length / step), 8)
    return np.array([ls.interpolate(i * ls.length / n).coords[0] for i in range(n)])


def medial_graph(poly, step=1.6):
    """Voronoi medial axis of ``poly`` as an nx.Graph with node attrs pos, r."""
    pts, ring_id, ring_start, ring_len = [], [], [], []
    rings = [poly.exterior] + list(poly.interiors)
    for k, r in enumerate(rings):
        s = _sample_ring(r.coords, step)
        ring_start.append(len(pts))
        ring_len.append(len(s))
        pts.extend(s.tolist())
        ring_id.extend([k] * len(s))
    pts = np.array(pts)
    ring_id = np.array(ring_id)
    vor = Voronoi(pts)
    V = vor.vertices
    inside = shapely.contains_xy(poly, V[:, 0], V[:, 1])
    tree = cKDTree(pts)
    rad, _ = tree.query(V)
    G = nx.Graph()
    for (p, q), (a, b) in zip(vor.ridge_points, vor.ridge_vertices):
        if a < 0 or b < 0 or not (inside[a] and inside[b]):
            continue
        if ring_id[p] == ring_id[q]:
            n = ring_len[ring_id[p]]
            d = abs(p - q)
            d = min(d, n - d)
            if d <= 2:
                continue
        L = float(np.hypot(*(V[a] - V[b])))
        G.add_node(a, pos=V[a], r=float(rad[a]))
        G.add_node(b, pos=V[b], r=float(rad[b]))
        G.add_edge(a, b, length=L)
    return G


def _branches(G):
    """Split graph into branches between nodes with degree != 2.  Returns list of node-id lists."""
    seen = set()
    out = []
    special = [n for n in G if G.degree(n) != 2]
    for s in special:
        for nb in G[s]:
            e = frozenset((s, nb))
            if e in seen:
                continue
            path = [s, nb]
            seen.add(e)
            prev, cur = s, nb
            while G.degree(cur) == 2:
                nxt = [x for x in G[cur] if x != prev][0]
                seen.add(frozenset((cur, nxt)))
                path.append(nxt)
                prev, cur = cur, nxt
            out.append(path)
    # pure cycles
    for comp in nx.connected_components(G):
        if all(G.degree(n) == 2 for n in comp):
            n0 = next(iter(comp))
            path = [n0]
            prev, cur = None, n0
            while True:
                nxt = [x for x in G[cur] if x != prev]
                nxt = nxt[0] if prev is not None else nxt[0]
                if nxt == n0:
                    path.append(n0)
                    break
                path.append(nxt)
                prev, cur = cur, nxt
            out.append(path)
    return out


def _path_len(G, path):
    return sum(G.edges[a, b]["length"] for a, b in zip(path[:-1], path[1:]))


def prune(G, k=1.6, passes=20):
    """Remove short leaf branches (corner spurs) until stable."""
    G = G.copy()
    for _ in range(passes):
        changed = False
        for path in _branches(G):
            a, b = path[0], path[-1]
            if a == b:
                continue
            da, db = G.degree(a), G.degree(b)
            if (da == 1) == (db == 1):
                continue
            leaf, junc = (a, b) if da == 1 else (b, a)
            L = _path_len(G, path)
            rj = G.nodes[junc]["r"]
            if L < k * rj:
                for n in path[1:-1]:
                    G.remove_node(n)
                G.remove_node(leaf)
                changed = True
        G.remove_nodes_from([n for n in list(G) if G.degree(n) == 0])
        if not changed:
            break
    return G


# --------------------------------------------------------------------------- chains
def _dir_from(G, path, d_px):
    """Unit vector from path[0] along the path, measured over ~d_px of arc."""
    p0 = G.nodes[path[0]]["pos"]
    acc = 0.0
    last = p0
    for a, b in zip(path[:-1], path[1:]):
        acc += G.edges[a, b]["length"]
        last = G.nodes[b]["pos"]
        if acc >= d_px:
            break
    v = last - p0
    n = np.hypot(*v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def build_chains(G, pair_deg=40.0):
    """Return list of chains: dict(nodes=[graph node ids in order], closed=bool).

    Branches meeting at a junction are paired through it when they continue within
    ``pair_deg`` of straight; unpaired branches end at the junction."""
    br = _branches(G)
    pure = [i for i, p in enumerate(br) if p[0] == p[-1] and G.degree(p[0]) == 2]
    inc = {}
    for i, p in enumerate(br):
        if i in pure:
            continue
        inc.setdefault(p[0], []).append((i, 0))
        inc.setdefault(p[-1], []).append((i, 1))
    link = {}
    for node, lst in inc.items():
        if len(lst) == 2:
            link[lst[0]] = lst[1]
            link[lst[1]] = lst[0]
            continue
        if len(lst) < 3:
            continue
        r = G.nodes[node]["r"]
        dirs = {}
        for (i, e) in lst:
            p = br[i] if e == 0 else br[i][::-1]
            dirs[(i, e)] = _dir_from(G, p, max(1.5 * r, 8.0))
        cands = []
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                d = float(np.dot(dirs[lst[x]], dirs[lst[y]]))
                dev = math.degrees(math.acos(max(-1.0, min(1.0, -d))))
                if dev <= pair_deg:
                    cands.append((dev, lst[x], lst[y]))
        cands.sort()
        used = set()
        for dev, x, y in cands:
            if x in used or y in used:
                continue
            link[x] = y
            link[y] = x
            used.update((x, y))
    visited = set()
    chains = []
    for i in range(len(br)):
        if i in visited:
            continue
        if i in pure:
            visited.add(i)
            chains.append(dict(nodes=list(br[i]), closed=True))
            continue
        seen = {i}
        back = []
        cb, ce = i, 0
        closed = False
        while True:
            nxt = link.get((cb, ce))
            if nxt is None:
                break
            nb, ne = nxt
            if nb in seen:
                closed = nb == i
                break
            seen.add(nb)
            back.append((nb, ne == 0))
            cb, ce = nb, 1 - ne
        fwd = [(i, False)]
        cb, ce = i, 1
        while True:
            nxt = link.get((cb, ce))
            if nxt is None:
                break
            nb, ne = nxt
            if nb in seen:
                closed = closed or nb == i or (nb in seen and not back)
                break
            seen.add(nb)
            fwd.append((nb, ne == 1))
            cb, ce = nb, 1 - ne
        order = back[::-1] + fwd
        nodes = []
        for b, flip in order:
            visited.add(b)
            p = br[b][::-1] if flip else br[b]
            nodes.extend(p if not nodes else p[1:])
        chains.append(dict(nodes=nodes, closed=closed or nodes[0] == nodes[-1]))
    return chains


# --------------------------------------------------------------------------- satin from a chain
def _resample(pts, h):
    pts = np.asarray(pts, float)
    seg = np.hypot(*(pts[1:] - pts[:-1]).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < 1e-6:
        return pts[:1], np.array([0.0])
    n = max(int(round(s[-1] / h)), 1)
    t = np.linspace(0, s[-1], n + 1)
    return np.stack([np.interp(t, s, pts[:, 0]), np.interp(t, s, pts[:, 1])], 1), t


def _gauss_smooth(a, sigma_samples):
    if sigma_samples < 0.5:
        return a
    return ndi.gaussian_filter1d(a, sigma_samples, axis=0, mode="nearest")


def cross_rails(poly, centers, tangents, reach, radius_mult=1.7):
    """For each centre, cast +-normal rays; return (L, R) boundary points."""
    bd = poly.boundary
    L, R = [], []
    for c, t, rc in zip(centers, tangents, reach):
        n = np.array([-t[1], t[0]])
        out = []
        for sgn in (1, -1):
            far = c + sgn * n * rc * radius_mult
            seg = LineString([tuple(c), tuple(far)])
            it = seg.intersection(bd)
            if it.is_empty:
                out.append(far)
            else:
                geoms = getattr(it, "geoms", [it])
                best = None
                bd_d = 1e18
                for g in geoms:
                    for q in (g.coords if g.geom_type != "Point" else [g.coords[0]]):
                        d = math.hypot(q[0] - c[0], q[1] - c[1])
                        if d < bd_d:
                            bd_d, best = d, np.array(q)
                out.append(best)
        L.append(out[0])
        R.append(out[1])
    return np.array(L), np.array(R)


def extend_to_boundary(poly, pt, direction, max_len):
    """Distance from ``pt`` along ``direction`` to the outline; 0 if pt is outside or nothing is hit."""
    if not poly.buffer(0.5).contains(Point(*pt)):
        return 0.0
    ray = LineString([tuple(pt), tuple(pt + direction * max_len)])
    it2 = ray.intersection(poly.boundary)
    if it2.is_empty:
        return 0.0
    geoms = getattr(it2, "geoms", [it2])
    d = 1e18
    for g in geoms:
        for q in (g.coords if g.geom_type != "Point" else [g.coords[0]]):
            d = min(d, math.hypot(q[0] - pt[0], q[1] - pt[1]))
    return d


def _tangent_end(c, end, span, h):
    if end == 0:
        seg = c[: max(2, int(span / h) + 1)]
        v = seg[0] - seg[-1]
    else:
        seg = c[-max(2, int(span / h) + 1):]
        v = seg[-1] - seg[0]
    n = np.hypot(*v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


CORNER_DEG = 60.0
CORNER_WIN = 1.4


def find_corners(pos, rad, win_mult=None, deg=None, h=3.3):
    win_mult = CORNER_WIN if win_mult is None else win_mult
    deg = CORNER_DEG if deg is None else deg
    """Arc positions (in px along the polyline) of hairpin turns: total turning within a window
    of win_mult * local radius exceeds ``deg``."""
    seg = np.hypot(*(pos[1:] - pos[:-1]).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    total = s[-1]
    if total < 6 * h:
        return []
    t = np.arange(0, total + 1e-6, h / 2)
    c = np.stack([np.interp(t, s, pos[:, 0]), np.interp(t, s, pos[:, 1])], 1)
    r = np.interp(t, s, rad)
    c = ndi.gaussian_filter1d(c, 1.5, axis=0, mode="nearest")
    d = np.gradient(c, axis=0)
    ang = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    out = []
    n = len(t)
    turn = np.zeros(n)
    for i in range(n):
        half = max(int(win_mult * r[i] / (h / 2) / 2), 2)
        a, b = max(i - half, 0), min(i + half, n - 1)
        if i - half < 0 or i + half > n - 1:
            continue
        turn[i] = abs(ang[b] - ang[a])
    thr = math.radians(deg)
    i = 0
    while i < n:
        if turn[i] > thr:
            j = i
            while j < n and turn[j] > thr:
                j += 1
            k = i + int(np.argmax(turn[i:j]))
            out.append(float(t[k]))
            i = j
        else:
            i += 1
    return out


EXCLUDE = []   # (x_mm, y_mm, r_mm) circles where satin is not laid; residual patches fill them


class Ctx:
    """Shared state while stitching one shape: union of the bands laid so far."""
    def __init__(self, overlap_px=3.0):
        self.prior = None
        self.overlap = overlap_px

    def add(self, satin):
        b = band_union([satin])
        self.prior = b if self.prior is None else self.prior.union(b)


def polyline_to_satin(poly, pos, rad, kind0, kind1, h=3.3, rung_every=4, end_pull_px=5.0,
                      smooth_k=1.0, reach_mult=1.8, corner_ext=0.9, min_len_px=6.0, ctx=None, spike_mult=1.5):
    """Satin along one stroke centreline.  kind0/kind1 describe the two ends:
    'leaf' extend to the outline, 'junction' stop (r - end_pull) short of the node,
    'corner' extend tangentially by corner_ext * r, 'closed' (no ends)."""
    seg = np.hypot(*(pos[1:] - pos[:-1]).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    total = s[-1]
    s0, s1 = 0.0, total
    if ctx is None:
        if kind0 == "junction":
            s0 = max(rad[0] - end_pull_px, 0.0)
        if kind1 == "junction":
            s1 = total - max(rad[-1] - end_pull_px, 0.0)
    if s1 - s0 < min_len_px:
        return None
    t = np.linspace(s0, s1, max(int(round((s1 - s0) / h)), 1) + 1)
    c = np.stack([np.interp(t, s, pos[:, 0]), np.interp(t, s, pos[:, 1])], 1)
    r = np.interp(t, s, rad)
    pre, post = [], []
    for end, kind in ((0, kind0), (1, kind1)):
        if kind not in ("leaf", "corner"):
            continue
        span = max(r[0 if end == 0 else -1] * 1.2, 10.0)
        d = _tangent_end(c, end, span, h)
        p0 = c[0] if end == 0 else c[-1]
        reach = extend_to_boundary(poly, p0, d, 6 * max(r.max(), 5))
        reach = max(reach - 0.6, 0.0)
        if kind == "corner":
            reach = min(reach, corner_ext * float(r[0 if end == 0 else -1]))
        if reach < 0.5:
            continue
        steps = max(int(round(reach / h)), 1)
        ext = [p0 + d * (reach * k / steps) for k in range(1, steps + 1)]
        if end == 0:
            pre = ext[::-1]
        else:
            post = ext
    if len(pre) or len(post):
        c = np.vstack([np.array(pre).reshape(-1, 2), c, np.array(post).reshape(-1, 2)])
        r = np.concatenate([np.full(len(pre), r[0]), r, np.full(len(post), r[-1])])
    length = float(np.sum(np.hypot(*(c[1:] - c[:-1]).T)))
    r_typ = float(np.percentile(r, 60))
    sig = min(max(smooth_k * float(np.median(r)) / h, 0.6), max(length / h / 7.0, 0.6))
    cs = _gauss_smooth(c, sig)
    cs[0], cs[-1] = c[0], c[-1]
    tang = np.gradient(cs, axis=0)
    nrm = np.hypot(*tang.T)
    tang = tang / np.where(nrm[:, None] < 1e-9, 1, nrm[:, None])
    dist = np.array([poly.boundary.distance(Point(*q)) for q in cs])
    reach = np.maximum(np.maximum(dist, 0.9 * r_typ), 2.0)
    Lp, Rp = cross_rails(poly, cs, tang, reach, radius_mult=reach_mult)
    # spike clamp: a ray that crossed a junction and hit a far boundary gives an isolated wide station
    nrm_ = np.stack([-tang[:, 1], tang[:, 0]], 1)
    dL = ((Lp - cs) * nrm_).sum(1)
    dR = -((Rp - cs) * nrm_).sum(1)
    for d in (dL, dR):
        med = ndi.median_filter(d, size=7, mode="nearest")
        m = d > spike_mult * med + 1.5
        d[m] = med[m]
    Lp = cs + nrm_ * dL[:, None]
    Rp = cs - nrm_ * dR[:, None]
    if ctx is not None and ctx.prior is not None and not ctx.prior.is_empty:
        er = ctx.prior.buffer(-ctx.overlap)
        if not er.is_empty:
            inside = np.array([er.contains(Point(*q)) for q in cs])
            keep = np.ones(len(cs), bool)
            i0 = 0
            while i0 < len(cs) and inside[i0]:
                i0 += 1
            i1 = len(cs)
            while i1 > i0 and inside[i1 - 1]:
                i1 -= 1
            if i1 - i0 < 2:
                return None
            sl = slice(max(i0 - 1, 0), min(i1 + 1, len(cs)))
            cs, tang, Lp, Rp = cs[sl], tang[sl], Lp[sl], Rp[sl]
            for arr in (Lp, Rp):
                for k in range(len(cs)):
                    seg = LineString([tuple(cs[k]), tuple(arr[k])])
                    if seg.length < 1e-6 or not seg.intersects(er):
                        continue
                    it = seg.intersection(er)
                    best, bd = None, 1e18
                    for gm in getattr(it, "geoms", [it]):
                        for q in (gm.coords if gm.geom_type != "Point" else [gm.coords[0]]):
                            d = math.hypot(q[0] - cs[k][0], q[1] - cs[k][1])
                            if d < bd:
                                bd, best = d, np.array(q)
                    if best is not None:
                        arr[k] = best
    rung_idx = list(range(rung_every, len(cs) - 1, rung_every))
    out = dict(L=Lp, R=Rp, centers=cs, rung_idx=rung_idx, closed=(kind0 == "closed"))
    if EXCLUDE:
        out = _apply_exclusions(out)
    return out


def chain_to_satins(G, poly, nodes, split_corners=True, ctx=None, **kw):
    """One chain -> list of satin dicts (split at hairpin corners)."""
    pos = np.array([G.nodes[n]["pos"] for n in nodes])
    rad = np.array([G.nodes[n]["r"] for n in nodes])
    closed = len(nodes) > 2 and nodes[0] == nodes[-1]
    d0, d1 = G.degree(nodes[0]), G.degree(nodes[-1])
    k0 = "closed" if closed else ("leaf" if d0 == 1 else "junction")
    k1 = "closed" if closed else ("leaf" if d1 == 1 else "junction")
    cuts = find_corners(pos, rad) if split_corners and not closed else []
    if not cuts:
        s = polyline_to_satin(poly, pos, rad, k0, k1, ctx=ctx, **kw)
        if not s:
            return []
        pieces = repair_rungs(s)
        if ctx is not None:
            for t in pieces:
                ctx.add(t)
        return pieces
    seg = np.hypot(*(pos[1:] - pos[:-1]).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    bounds = [0.0] + cuts + [s[-1]]
    kinds = [k0] + ["corner"] * len(cuts) + [k1]
    out = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        m = (s > a) & (s < b)
        xs = np.concatenate([[a], s[m], [b]])
        P = np.stack([np.interp(xs, s, pos[:, 0]), np.interp(xs, s, pos[:, 1])], 1)
        Rr = np.interp(xs, s, rad)
        kk0 = kinds[i] if i == 0 else "corner"
        kk1 = kinds[i + 1] if i + 1 == len(bounds) - 1 else "corner"
        sat = polyline_to_satin(poly, P, Rr, kk0, kk1, ctx=ctx, **kw)
        if sat:
            for t in repair_rungs(sat):
                out.append(t)
                if ctx is not None:
                    ctx.add(t)
    return out


# --------------------------------------------------------------------------- residual patches
def band_union(satins):
    quads = []
    for s in satins:
        L, R = s["L"], s["R"]
        for i in range(len(L) - 1):
            q = Polygon([tuple(L[i]), tuple(L[i + 1]), tuple(R[i + 1]), tuple(R[i])])
            if not q.is_valid:
                q = q.buffer(0)
            if not q.is_empty:
                quads.append(q)
    return unary_union(quads) if quads else Polygon()


def chord_satin(region, axis_deg=None, step=2.6, min_width_px=3.0):
    """Satin across the short axis of ``region`` (a Polygon): rails follow the long sides."""
    mrr = region.minimum_rotated_rectangle
    pts = np.array(mrr.exterior.coords)[:4]
    e0, e1 = pts[1] - pts[0], pts[2] - pts[1]
    major = e0 if np.hypot(*e0) >= np.hypot(*e1) else e1
    major = major / np.hypot(*major)
    minor = np.array([-major[1], major[0]])
    cen = np.array(region.centroid.coords[0])
    proj = (np.array(region.exterior.coords) - cen) @ major
    lo, hi = proj.min(), proj.max()
    n = max(int((hi - lo) / step), 2)
    Ls, Rs = [], []
    for k in range(n + 1):
        t = lo + (hi - lo) * (0.02 + 0.96 * k / n)
        a = cen + major * t - minor * 400
        b = cen + major * t + minor * 400
        it = LineString([tuple(a), tuple(b)]).intersection(region)
        if it.is_empty:
            continue
        parts = [g for g in getattr(it, "geoms", [it]) if g.geom_type == "LineString"]
        if not parts:
            continue
        g = max(parts, key=lambda g: g.length)
        if g.length < 0.5:
            continue
        c0, c1 = np.array(g.coords[0]), np.array(g.coords[-1])
        if (c1 - c0) @ minor < 0:
            c0, c1 = c1, c0
        Ls.append(c0)
        Rs.append(c1)
    if len(Ls) < 2:
        return None
    L, R = np.array(Ls), np.array(Rs)
    if np.median(np.hypot(*(L - R).T)) < min_width_px:
        return None
    return dict(L=L, R=R, rung_idx=list(range(3, len(L) - 1, 3)), centers=None, kind="patch")


def patch_residuals(poly, satins, min_area_px=17.0, grow=1.6, open_px=0.8, min_solidity=0.62):
    bu = band_union(satins)
    resid = poly.difference(bu.buffer(0.4))
    if resid.is_empty:
        return []
    resid = resid.buffer(-open_px).buffer(open_px)
    parts = [g for g in getattr(resid, "geoms", [resid]) if g.geom_type == "Polygon" and g.area >= min_area_px]
    out = []
    for g in parts:
        g2 = g.buffer(grow).intersection(poly)
        if g2.geom_type != "Polygon":
            g2 = max(getattr(g2, "geoms", []), key=lambda x: x.area, default=None)
            if g2 is None:
                continue
        if g.convex_hull.area > 0 and g.area / g.convex_hull.area < min_solidity:
            continue
        s = chord_satin(g2)
        if s:
            out.append(s)
    # forced hub patches inside exclusion zones, whatever their shape
    for (x, y, r) in EXCLUDE:
        zone = Point(x * PPM, y * PPM).buffer((r + 0.45) * PPM)
        if not poly.intersects(zone):
            continue
        reg = poly.intersection(zone).difference(bu.buffer(0.4))
        reg = reg.buffer(-0.5).buffer(0.5)
        parts = [g for g in getattr(reg, "geoms", [reg]) if g.geom_type == "Polygon" and g.area > 25]
        if not parts:
            continue
        g0 = max(parts, key=lambda g: g.area)
        g2 = g0.buffer(grow).intersection(poly)
        if g2.geom_type != "Polygon":
            g2 = max(getattr(g2, "geoms", []), key=lambda x: x.area, default=None)
            if g2 is None:
                continue
        s = chord_satin(g2)
        if s:
            s["kind"] = "patch"
            out.append(s)
    return out


def satin_quality(s):
    """Return a list of problems: rails reversing, crossing quads, width jumps."""
    L, R = s["L"], s["R"]
    probs = []
    w = np.hypot(*(L - R).T)
    if len(L) < 3:
        return probs
    dl, dr = L[1:] - L[:-1], R[1:] - R[:-1]
    dots = np.einsum("ij,ij->i", dl, dr)
    if (dots < -1e-6).mean() > 0.1:
        probs.append("rails-opposed")
    # width jump
    ww = np.maximum(w, 1.5)
    ratio = np.maximum(ww[1:] / ww[:-1], ww[:-1] / ww[1:])
    if (ratio > 2.4).sum() >= 2:
        probs.append("width-jumps")
    # crossing: a rail turning back on itself
    for rail, name in ((L, "L"), (R, "R")):
        d = rail[1:] - rail[:-1]
        n = np.hypot(*d.T)
        ok = n > 1e-6
        d = d[ok] / n[ok][:, None]
        if len(d) > 3 and (np.einsum("ij,ij->i", d[1:], d[:-1]) < -0.2).sum() >= 2:
            probs.append("rail-doubles-back-" + name)
    if len(w) >= 8:
        sw = ndi.gaussian_filter1d(np.maximum(w, 1.5), 1.0)
        ext = [sw[0]]
        for k in range(1, len(sw) - 1):
            if (sw[k] - sw[k - 1]) * (sw[k + 1] - sw[k]) < 0:
                ext.append(sw[k])
        ext.append(sw[-1])
        swings = sum(1 for a, b in zip(ext[:-1], ext[1:]) if max(a, b) / min(a, b) > 2.2)
        if swings >= 3:
            probs.append("erratic-width")
    return probs


def _apply_exclusions(s):
    cs = s["centers"]
    keep = np.ones(len(cs), bool)
    for (x, y, r) in EXCLUDE:
        d = np.hypot(cs[:, 0] - x * PPM, cs[:, 1] - y * PPM)
        keep &= d > r * PPM
    if keep.all():
        return s
    # mark as 'multi': keep the longest run only here; the others are re-created by repair via 'bad'
    s["_keep"] = keep
    return s


def _seg_intersect(a, b, c, d):
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    return (ccw(a, c, d) * ccw(b, c, d) < 0) and (ccw(a, b, c) * ccw(a, b, d) < 0)


def repair_rungs(s, min_run=4, spin_deg=26.0, jump_mult=3.0):
    """Drop stations where neighbouring rungs cross or the quad flips; return the good runs."""
    L, R = s["L"], s["R"]
    n = len(L)
    if n < 4:
        return [s]
    bad = np.zeros(n, bool)
    if "_keep" in s and len(s["_keep"]) == n:
        bad |= ~s["_keep"]
    sign = []
    for i in range(n - 1):
        a = (L[i + 1] - L[i]) @ np.array([0, 0]) if False else 0
        q = np.array([L[i], L[i + 1], R[i + 1], R[i]])
        x, y = q[:, 0], q[:, 1]
        sign.append(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    sign = np.array(sign)
    ref = np.sign(np.median(sign)) or 1.0
    for i in range(n - 1):
        if sign[i] * ref < 0:
            bad[i] = bad[i + 1] = True
        if _seg_intersect(L[i], R[i], L[i + 1], R[i + 1]):
            bad[i] = bad[i + 1] = True
    # rung direction spinning faster than a real bend allows, or width jumping
    ang = np.arctan2(R[:, 1] - L[:, 1], R[:, 0] - L[:, 0])
    dang = np.abs(np.angle(np.exp(1j * (ang[1:] - ang[:-1]))))
    w = np.maximum(np.hypot(*(R - L).T), 1.5)
    wr = np.maximum(w[1:] / w[:-1], w[:-1] / w[1:])
    cen = s.get("centers")
    step = np.hypot(*(cen[1:] - cen[:-1]).T) if cen is not None and len(cen) == n else np.full(n - 1, 3.3)
    jl = np.hypot(*(L[1:] - L[:-1]).T)
    jr = np.hypot(*(R[1:] - R[:-1]).T)
    lim = jump_mult * np.maximum(step, 2.0) + 2.0
    for i in range(n - 1):
        if dang[i] > math.radians(spin_deg) or wr[i] > 2.6 or jl[i] > lim[i] or jr[i] > lim[i]:
            bad[i] = bad[i + 1] = True
    for i in range(n):
        for j in range(i + 2, min(i + 9, n)):
            if _seg_intersect(L[i], R[i], L[j], R[j]):
                for k in range(i, j + 1):
                    bad[k] = True
    if not bad.any():
        return [s]
    grow = bad.copy()
    grow[1:] |= bad[:-1]
    grow[:-1] |= bad[1:]
    runs, start = [], None
    for i in range(n + 1):
        ok = i < n and not grow[i]
        if ok and start is None:
            start = i
        if not ok and start is not None:
            if i - start >= min_run:
                runs.append((start, i))
            start = None
    out = []
    for a, b in runs:
        t = dict(s)
        t["L"], t["R"] = L[a:b].copy(), R[a:b].copy()
        if s.get("centers") is not None:
            t["centers"] = s["centers"][a:b]
        t["rung_idx"] = [i - a for i in s.get("rung_idx", []) if a < i - 0 < b - 1 and a < i < b - 1]
        out.append(t)
    return out
