#!/usr/bin/env python3
"""SVG -> pre-digitized embroidery SVG (Ink/Stitch).

The native-vector sibling of ``vectorize.py``.  Where the raster path invents
geometry by tracing an image, this path reads the artist's ``<path>`` elements
directly and never skeletonises: an authored ``fill`` is stitched as a fill.

What it does:
  * lxml parse, walk from the root accumulating transforms (including the
    document's Layer matrices)
  * ``<path>`` only; ``defs``/``symbol``/``image`` and ``display:none`` skipped
  * every coordinate converted to mm early via the root viewBox/width ratio
  * full ``d`` support, curves flattened to polylines at TOLERANCE_MM (0.15 mm)
  * thread colours = distinct fill hexes, first-seen document order
  * stroked paths narrower than Ink/Stitch's 1.0 mm satin gate are dropped
  * Artwork bbox scaled to fit a box (default longest side 100 mm)
  * a satin border carved out of the fills and stitched last
  * each colour carved out from beneath the colours stitched after it, and each
    colour edge pulled back by half a thread width so the later colour's thread
    finishes on the drawn edge instead of over the earlier colour
  * nearest-neighbour travel within each colour layer, needle carried across
  * trim = cut a jump that is long OR exposed (not covered by a later object)

Usage:
  python tools/digitize/svg_digitize.py [--width-mm W] [--height-mm H]
                                        [--border-mm W] [--border-color HEX] [--no-border]
                                        [--density MM] [--trim-mm N] [--no-trim]
                                        [--skip-colors HEX[,HEX]] [--config F]
                                        [--fill-angle DEG] [--overlap-mm MM]
                                        [--seam-pull-mm MM]
                                        [input.svg] [output.svg]

Note: ``--colors`` is accepted but ignored (colours come from the artwork), and
YAML ``order`` is ignored (stitch order is SVG document order).

YAML keys: ``skip_colors``, ``density`` (number or colour map), ``border``,
``trim``, ``seam_pull_mm``, ``angle`` (colour map) and ``angle_cycle``
(colour -> list of angles cycled across that colour's components, for
stitch-direction depth).  An authored ``inkstitch:satin_column`` path is kept
as a satin; an authored rail satin that follows the whole silhouette becomes
the border instead of a synthetic one, and fills keep their full footprint
beneath it.
"""
import math
import os
import re
import sys

import yaml
import numpy as np
from lxml import etree
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, MultiLineString, Point, LineString
from shapely.ops import unary_union
from shapely.affinity import affine_transform
from shapely.prepared import prep
from shapely import make_valid, maximum_inscribed_circle

import satinize

# --- CLI parsing (same shape as vectorize.py) --------------------------------
_VALUE_FLAGS = {"--width-mm", "--height-mm", "--border-mm", "--border-color",
                "--trim-mm", "--config", "--density", "--skip-colors", "--overlap-mm",
                "--seam-pull-mm", "--fill-angle", "--satinize-colors"}
_argc = sys.argv[1:]
args = []
_flags = {}
_i = 0
while _i < len(_argc):
    _a = _argc[_i]
    if _a.startswith("--"):
        if "=" in _a:
            _name, _val = _a[2:].split("=", 1)
            _flags[_name] = _val
        elif _a in _VALUE_FLAGS and _i + 1 < len(_argc) and not _argc[_i + 1].startswith("--"):
            _flags[_a[2:]] = _argc[_i + 1]
            _i += 1
        else:
            _flags[_a[2:]] = True
    elif _a.startswith("-") and _a != "-":
        pass  # ignore short flags
    else:
        args.append(_a)
    _i += 1

SVG_IN = args[0] if len(args) > 0 else "input/Scavenger's Daughter Upgrade Patch2.svg"
OUT = args[1] if len(args) > 1 else "work/design.svg"
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)


def flag(name, default):
    return _flags.get(name, default)


def load_config(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# --- constants (mirrors vectorize.py where they overlap) ---------------------
SIZE_MM = 100.0            # default longer side of finished design (mm)
ROW_SPACING_MM = 0.3       # fill density; 0.4 left the base fabric showing
                           # through on the Scavenger's Daughter test, 0.25 is
                           # what the hand-digitized reference used, 0.30 is the
                           # documented needle-safe floor
SATIN_GATE_MM = 1.0        # Ink/Stitch min_satin_stroke_width_mm (strict >)
SATIN_PULL_MM = 0.2        # satin pull compensation per side
SATIN_ZIGZAG_MM = 0.3      # zigzag spacing on the authored rail satin; at the
                           # 0.4 default the fan at horn tips leaves gaps between
                           # the thread ends along the outer rail (sawtooth edge)
SMALL_FILL_MM2 = 2.5       # fills smaller than this get no underlay and no ties
                           # (each tiny element otherwise packs underlay + lock
                           # stitches into a few mm2 -> needle-breaking hotspots)
SMALL_FILL_MIC_MM = 1.0    # ... same for any component thinner than this even
                           # if it is long (slivers are the worst hotspots)
SATIN_MIN_GATE_MM = 0.5    # metadata min_satin_stroke_width_mm used when a
                           # satin column is narrower than Ink/Stitch's 1 mm
                           # default gate (otherwise it silently runs as a
                           # running stitch)
OVERLAP_MM = float(flag("overlap-mm", "1.0"))  # under-colours are carved out from
                           # beneath later colours, leaving this much registration
                           # margin (a later colour may overlap an earlier one by
                           # up to 2x this, no more; see section 7b)
SEAM_PULL_MM = float(flag("seam-pull-mm", "0.2"))  # thread is laid centred on its
                            # path, so a fill's stitched edge finishes half a thread
                            # width outside the drawn geometry; pull the later colour
                            # back by this much at every colour edge so the stitched
                            # edge lands on the drawn edge (see section 7d)
_SEAM_MARGIN_MM = 0.05     # slack on "buried under the later colour" when the
                            # seam source is built (section 7d): the seam is
                            # only where the two colours really meet
BORDER_CLOSE_MM = 12.0     # bridge contour V-notches/bays narrower than 2x this
                           # before tracing the border centreline (see section 7)
BORDER_OPEN_MM = 5.0       # bridge contour necks/hairpins narrower than 2x this
                           # before tracing the border centreline (see section 7)
BORDER_OVERHANG_MM = 1.0   # inset the border centreline by this much so Ink/Stitch's
                           # satin rails (corner overshoot + pull compensation) stay
                           # inside the fit box; the outer fill ring keeps the full size
TOLERANCE_MM = 0.25        # curve flattening / simplification (mm); 0.25 measured
                           # 1.5x faster export vs 0.15 with ~0.8% fewer stitches
                           # and no visible difference (docs/adr/0002-export-performance.md)
TRIM_MIN_MM = 1.5          # never cut jumps shorter than this
SVG_NS = "http://www.w3.org/2000/svg"
INK_NS = "http://inkstitch.org/namespace"
XLINK_NS = "http://www.w3.org/1999/xlink"
NS = {"svg": SVG_NS}

# --- flags / config ----------------------------------------------------------
NO_BORDER = flag("no-border", False) is True
BORDER_MM = float(flag("border-mm", "2.5"))
BORDER_COLOR_ARG = flag("border-color", None)
NO_TRIM = flag("no-trim", False) is True
TRIM = not NO_TRIM
TRIM_MM = flag("trim-mm", None)
DENSITY_MM = flag("density", None)
WIDTH_MM_ARG = flag("width-mm", None)
HEIGHT_MM_ARG = flag("height-mm", None)
CONFIG = flag("config", None)
SKIP_ARG = flag("skip-colors", None)

if flag("colors", None) is not None:
    print("note: --colors is ignored on the native SVG path; colours are read from the artwork")

cfg = load_config(CONFIG)
_ORDER = cfg.get("order") or []
if _ORDER:
    print("note: YAML 'order' is ignored on the native SVG path; stitch order is SVG document order")

_SKIP = {str(s).lower() for s in (cfg.get("skip_colors") or [])}
if SKIP_ARG:
    for s in str(SKIP_ARG).split(","):
        if s.strip():
            _SKIP.add(s.strip().lower())

_dens = cfg.get("density") or {}
_DENSITY = {}
if isinstance(_dens, (int, float)):
    ROW_SPACING_MM = float(_dens)
elif isinstance(_dens, dict):
    for _k, _v in _dens.items():
        try:
            _DENSITY[str(_k).lower()] = float(_v)
        except (TypeError, ValueError):
            print(f"warning: ignoring non-numeric density {_v!r} for {_k}")
elif _dens:
    print(f"warning: ignoring non-numeric density {_dens!r}")
if DENSITY_MM is not None:
    ROW_SPACING_MM = float(DENSITY_MM)

# fill angle: a later source overrides an earlier one, CLI wins over YAML, and
# an explicit value overrides the angle the artist authored on the path
FILL_ANGLE = flag("fill-angle", None)
_ANGLE = {}        # color -> angle for every fill of that colour
_ANGLE_CYCLE = {}  # color -> [angles] cycled across that colour's components
_ang = cfg.get("angle") or {}
if isinstance(_ang, dict):
    for _k, _v in _ang.items():
        try:
            _ANGLE[str(_k).lower()] = float(_v)
        except (TypeError, ValueError):
            print(f"warning: ignoring non-numeric angle {_v!r} for {_k}")
_angc = cfg.get("angle_cycle") or {}
if isinstance(_angc, dict):
    for _k, _v in _angc.items():
        try:
            _ANGLE_CYCLE[str(_k).lower()] = [float(x) for x in _v]
        except (TypeError, ValueError):
            print(f"warning: ignoring non-numeric angle_cycle {_v!r} for {_k}")
elif _angc:
    print(f"warning: ignoring non-mapping angle_cycle {_angc!r}")
if FILL_ANGLE is not None:
    try:
        FILL_ANGLE = float(FILL_ANGLE)
    except (TypeError, ValueError):
        print(f"warning: ignoring non-numeric --fill-angle {FILL_ANGLE!r}")
        FILL_ANGLE = None

# satinize: turn thin/elongated fills of the listed colours into satin columns
_sat_cfg = cfg.get("satinize") or {}
if isinstance(_sat_cfg, list):
    _sat_cfg = {"colors": _sat_cfg}
elif not isinstance(_sat_cfg, dict):
    print(f"warning: ignoring non-mapping satinize {_sat_cfg!r}")
    _sat_cfg = {}
_SATINIZE_COLORS = {str(c).lower() for c in (_sat_cfg.get("colors") or [])}
_sat_arg = flag("satinize-colors", None)
if _sat_arg:
    for _s in str(_sat_arg).split(","):
        if _s.strip():
            _SATINIZE_COLORS.add(_s.strip().lower())
if _sat_cfg.get("enabled") is False:
    _SATINIZE_COLORS = set()
SAT_MAX_ROW_MM = float(_sat_cfg.get("max_row_mm", 4.5))
SAT_MAX_ROWS = int(_sat_cfg.get("max_rows", 3))
SAT_MIN_COVERAGE = float(_sat_cfg.get("min_coverage", 0.9))
SAT_MAX_OVERHANG = float(_sat_cfg.get("max_overhang", 0.45))
SAT_MIN_COMP_MM2 = float(_sat_cfg.get("min_component_mm2", 1.0))

for _name, _val in [("global", ROW_SPACING_MM)] + list(_DENSITY.items()):
    if not 0.3 <= _val <= 0.6:
        print(f"warning: density {_val} mm ({_name}) is outside the safe 0.3-0.6 mm range "
              f"(too dense breaks needles, too open leaves gaps)")

_border_cfg = cfg.get("border") or {}
if isinstance(_border_cfg, dict):
    if _border_cfg.get("mode") == "off" or _border_cfg.get("enabled") is False:
        NO_BORDER = True
    if _border_cfg.get("thickness_mm") is not None and flag("border-mm", None) is None:
        BORDER_MM = float(_border_cfg["thickness_mm"])
    if _border_cfg.get("color") and BORDER_COLOR_ARG is None:
        BORDER_COLOR_ARG = _border_cfg["color"]
if BORDER_MM <= 0:
    NO_BORDER = True

_trim_cfg = cfg.get("trim") or {}
if flag("trim", False) is True:
    TRIM = True
if isinstance(_trim_cfg, dict) and "enabled" in _trim_cfg and flag("trim", False) is not True and not NO_TRIM:
    TRIM = bool(_trim_cfg["enabled"])
_extratrim = TRIM_MM if TRIM_MM is not None else (cfg.get("trim") or {}).get("threshold_mm")
TRIM_THRESHOLD_MM = float(_extratrim) if _extratrim is not None else 4.0
if TRIM_THRESHOLD_MM < 0:
    TRIM_THRESHOLD_MM = 0.0

# colour-seam pull: a later colour is stitched on top of an earlier one, and
# thread is laid centred on the path, so its stitched edge overshoots the drawn
# edge by half a thread width and eats the earlier colour's detail.  YAML
# `seam_pull_mm` sets it; the CLI wins (section 7d).
if flag("seam-pull-mm", None) is None and cfg.get("seam_pull_mm") is not None:
    try:
        SEAM_PULL_MM = float(cfg["seam_pull_mm"])
    except (TypeError, ValueError):
        print(f"warning: ignoring non-numeric seam_pull_mm "
              f"{cfg['seam_pull_mm']!r}")
if SEAM_PULL_MM < 0:
    SEAM_PULL_MM = 0.0


# ===========================================================================
# 1. transforms
# ===========================================================================
def parse_transform(s):
    """SVG transform list -> 3x3 homogeneous matrix (row-vector convention: M@p)."""
    m = np.eye(3)
    for name, raw in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", s or ""):
        vals = [float(x) for x in re.split(r"[\s,]+", raw.strip()) if x]
        t = np.eye(3)
        if name == "matrix" and len(vals) == 6:
            a, b, c, d, e, f = vals
            t = np.array([[a, c, e], [b, d, f], [0.0, 0.0, 1.0]])
        elif name == "translate" and vals:
            t[0, 2] = vals[0]
            t[1, 2] = vals[1] if len(vals) > 1 else 0.0
        elif name == "scale" and vals:
            t[0, 0] = vals[0]
            t[1, 1] = vals[1] if len(vals) > 1 else vals[0]
        elif name == "rotate" and vals:
            a = math.radians(vals[0])
            ca, sa = math.cos(a), math.sin(a)
            r = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
            if len(vals) == 3:
                cx, cy = vals[1], vals[2]
                t = (np.array([[1, 0, cx], [0, 1, cy], [0, 0, 1.0]]) @ r
                     @ np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1.0]]))
            else:
                t = r
        elif name == "skewX" and vals:
            t[0, 1] = math.tan(math.radians(vals[0]))
        elif name == "skewY" and vals:
            t[1, 0] = math.tan(math.radians(vals[0]))
        m = m @ t
    return m


def apply_pts(mat, pts):
    """(N,2) array of (x,y) through a 3x3 matrix -> (N,2)."""
    if len(pts) == 0:
        return np.zeros((0, 2))
    p = np.asarray(pts, dtype=float)
    x = mat[0, 0] * p[:, 0] + mat[0, 1] * p[:, 1] + mat[0, 2]
    y = mat[1, 0] * p[:, 0] + mat[1, 1] * p[:, 1] + mat[1, 2]
    return np.column_stack([x, y])


def mat_scale(mat):
    return math.sqrt(abs(mat[0, 0] * mat[1, 1] - mat[0, 1] * mat[1, 0]))


# ===========================================================================
# 2. path parsing + curve flattening
# ===========================================================================
_NUM = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
_TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(" + _NUM + r")")


def _tokens(d):
    for m in _TOKEN.finditer(d):
        yield m.group(1) if m.group(1) else float(m.group(2))


def _mid(a, b):
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)


def _pt_seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _flat_cubic(p0, p1, p2, p3, tol):
    return max(_pt_seg_dist(p1, p0, p3), _pt_seg_dist(p2, p0, p3)) <= tol


def _flatten_cubic(p0, p1, p2, p3, tol, depth, out):
    if depth >= 18 or _flat_cubic(p0, p1, p2, p3, tol):
        out.append(p3)
        return
    p01 = _mid(p0, p1)
    p12 = _mid(p1, p2)
    p23 = _mid(p2, p3)
    p012 = _mid(p01, p12)
    p123 = _mid(p12, p23)
    p0123 = _mid(p012, p123)
    _flatten_cubic(p0, p01, p012, p0123, tol, depth + 1, out)
    _flatten_cubic(p0123, p123, p23, p3, tol, depth + 1, out)


def _arc_to_points(p0, radii, large, sweep, p1, tol, out):
    """Endpoint-parameterised elliptical arc -> sampled points (SVG F.6.5)."""
    x1, y1 = p0
    x2, y2 = p1
    rx, ry = abs(radii[0]), abs(radii[1])
    if rx == 0.0 or ry == 0.0 or (x1 == x2 and y1 == y2):
        out.append(p1)
        return
    phi = math.radians(radii[2] % 360.0)
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    cp, sp = math.cos(phi), math.sin(phi)
    x1p = cp * dx + sp * dy
    y1p = -sp * dx + cp * dy
    lam = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if lam > 1.0:
        s = math.sqrt(lam)
        rx *= s
        ry *= s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2.0
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2.0

    def angle(ux, uy, vx, vy):
        dot = (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))
        a = math.acos(max(-1.0, min(1.0, dot)))
        return -a if ux * vy - uy * vx < 0 else a

    theta1 = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                   (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi

    rmax = max(rx, ry)
    if rmax <= tol:
        out.append(p1)
        return
    tmax = 2 * math.acos(max(-1.0, min(1.0, 1.0 - tol / rmax)))
    if tmax <= 0:
        tmax = math.pi / 8
    n = max(1, int(math.ceil(abs(dtheta) / tmax)))
    for k in range(1, n + 1):
        th = theta1 + dtheta * k / n
        x = cx + rx * math.cos(th) * cp - ry * math.sin(th) * sp
        y = cy + rx * math.cos(th) * sp + ry * math.sin(th) * cp
        out.append((x, y))


def parse_path(d, tol):
    """Parse an SVG ``d`` into a list of polylines (user-space (x,y) tuples)."""
    toks = list(_tokens(d))
    n = len(toks)
    idx = 0
    subpaths = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    pts = None
    prev_c = None
    prev_q = None
    cmd = None

    def num():
        nonlocal idx
        v = toks[idx]
        idx += 1
        return v

    while idx < n:
        t = toks[idx]
        if isinstance(t, str):
            cmd = t
            idx += 1
        else:
            if cmd is None:
                raise ValueError("path data must start with a moveto")
            if cmd == "M":
                cmd = "L"
            elif cmd == "m":
                cmd = "l"

        if cmd in ("M", "m"):
            x, y = num(), num()
            if cmd == "m":
                x, y = x + cur[0], y + cur[1]
            if pts:
                subpaths.append(pts)
            pts = [(x, y)]
            cur = (x, y)
            start = (x, y)
            prev_c = prev_q = None
        elif cmd in ("L", "l"):
            x, y = num(), num()
            if cmd == "l":
                x, y = x + cur[0], y + cur[1]
            pts.append((x, y))
            cur = (x, y)
            prev_c = prev_q = None
        elif cmd in ("H", "h"):
            x = num()
            if cmd == "h":
                x += cur[0]
            pts.append((x, cur[1]))
            cur = (x, cur[1])
            prev_c = prev_q = None
        elif cmd in ("V", "v"):
            y = num()
            if cmd == "v":
                y += cur[1]
            pts.append((cur[0], y))
            cur = (cur[0], y)
            prev_c = prev_q = None
        elif cmd in ("C", "c"):
            x1, y1, x2, y2, x, y = (num(), num(), num(), num(), num(), num())
            if cmd == "c":
                x1 += cur[0]; y1 += cur[1]; x2 += cur[0]; y2 += cur[1]; x += cur[0]; y += cur[1]
            _flatten_cubic(cur, (x1, y1), (x2, y2), (x, y), tol, 0, pts)
            cur = (x, y)
            prev_c, prev_q = (x2, y2), None
        elif cmd in ("S", "s"):
            x2, y2, x, y = num(), num(), num(), num()
            if cmd == "s":
                x2 += cur[0]; y2 += cur[1]; x += cur[0]; y += cur[1]
            if prev_c is not None:
                x1, y1 = 2 * cur[0] - prev_c[0], 2 * cur[1] - prev_c[1]
            else:
                x1, y1 = cur
            _flatten_cubic(cur, (x1, y1), (x2, y2), (x, y), tol, 0, pts)
            cur = (x, y)
            prev_c, prev_q = (x2, y2), None
        elif cmd in ("Q", "q"):
            x1, y1, x, y = num(), num(), num(), num()
            if cmd == "q":
                x1 += cur[0]; y1 += cur[1]; x += cur[0]; y += cur[1]
            c1 = (cur[0] + 2 / 3 * (x1 - cur[0]), cur[1] + 2 / 3 * (y1 - cur[1]))
            c2 = (x + 2 / 3 * (x1 - x), y + 2 / 3 * (y1 - y))
            _flatten_cubic(cur, c1, c2, (x, y), tol, 0, pts)
            cur = (x, y)
            prev_q, prev_c = (x1, y1), None
        elif cmd in ("T", "t"):
            x, y = num(), num()
            if cmd == "t":
                x += cur[0]; y += cur[1]
            if prev_q is not None:
                x1, y1 = 2 * cur[0] - prev_q[0], 2 * cur[1] - prev_q[1]
            else:
                x1, y1 = cur
            c1 = (cur[0] + 2 / 3 * (x1 - cur[0]), cur[1] + 2 / 3 * (y1 - cur[1]))
            c2 = (x + 2 / 3 * (x1 - x), y + 2 / 3 * (y1 - y))
            _flatten_cubic(cur, c1, c2, (x, y), tol, 0, pts)
            cur = (x, y)
            prev_q, prev_c = (x1, y1), None
        elif cmd in ("A", "a"):
            rx, ry, xrot, laf, sf, x, y = (num(), num(), num(), num(), num(), num(), num())
            if cmd == "a":
                x += cur[0]; y += cur[1]
            _arc_to_points(cur, (rx, ry, xrot), int(laf) != 0, int(sf) != 0, (x, y), tol, pts)
            cur = (x, y)
            prev_c = prev_q = None
        elif cmd in ("Z", "z"):
            if pts:
                if pts[0] != cur:
                    pts.append(pts[0])
                subpaths.append(pts)
            pts = None
            cur = start
            prev_c = prev_q = None
        else:
            raise ValueError(f"unsupported path command {cmd!r}")

    if pts:
        subpaths.append(pts)
    return subpaths


# ===========================================================================
# 3. style / colour helpers
# ===========================================================================
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
    """Presentation attributes overridden by the inline ``style`` attribute."""
    d = {}
    for k, v in el.attrib.items():
        name = etree.QName(k).localname if "}" in k else k
        if name in ("fill", "stroke", "stroke-width", "display", "fill-rule", "opacity"):
            d[name] = v
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def parse_len_uu(v):
    """Strip a CSS length down to its number (user units)."""
    if v is None:
        return None
    m = re.match(r"^\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)", v)
    return float(m.group(1)) if m else None


# ===========================================================================
# 4. geometry helpers
# ===========================================================================
def rings_to_geom(rings):
    """Rings under the even-odd fill rule -> (Multi)Polygon, or None.

    A point is filled iff an odd number of subpath boundaries enclose it, so the
    region is the symmetric difference (XOR) of each subpath's own even-odd
    region.  ``make_valid`` gives that per-subpath region and repairs the
    self-intersecting subpaths this artwork is full of.
    """
    result = None
    for r in rings:
        if len(r) < 3:
            continue
        try:
            p = Polygon(r)
        except Exception:
            continue
        if p.is_empty:
            continue
        if not p.is_valid:
            p = polygonal(make_valid(p))
        else:
            p = polygonal(p)
        if p is None or p.is_empty:
            continue
        result = p if result is None else result.symmetric_difference(p)
    if result is None or result.is_empty:
        return None
    return polygonal(result)


def polygonal(geom):
    """Keep only polygonal parts of a possibly mixed geometry."""
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


def geom_points(geom):
    """All boundary vertices as an (N,2) array."""
    arrs = []

    def add(ring):
        c = np.asarray(ring.coords, dtype=float)
        if len(c) > 1 and np.allclose(c[0], c[-1]):
            c = c[:-1]
        if len(c):
            arrs.append(c)

    if geom.geom_type == "Polygon":
        add(geom.exterior)
        for r in geom.interiors:
            add(r)
    elif geom.geom_type == "MultiPolygon":
        for p in geom.geoms:
            add(p.exterior)
            for r in p.interiors:
                add(r)
    return np.vstack(arrs) if arrs else np.zeros((0, 2))


def _ring_d(ring):
    c = list(ring.coords)
    if len(c) > 1 and c[0] == c[-1]:
        c = c[:-1]
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in c) + " Z"


def geom_to_d(geom):
    parts = []
    if geom.geom_type == "Polygon":
        parts.append(_ring_d(geom.exterior))
        parts.extend(_ring_d(r) for r in geom.interiors)
    elif geom.geom_type == "MultiPolygon":
        for p in geom.geoms:
            parts.append(_ring_d(p.exterior))
            parts.extend(_ring_d(r) for r in p.interiors)
    return " ".join(parts)


def line_geom_to_d(geom):
    if geom.geom_type == "LineString":
        lines = [geom]
    elif geom.geom_type in ("MultiLineString", "GeometryCollection"):
        lines = [g for g in geom.geoms if g.geom_type == "LineString"]
    else:
        lines = []
    return " ".join("M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in ln.coords)
                    for ln in lines)


def _centreline(geom):
    """Exterior ring(s) of a polygon as a (Multi)LineString centreline."""
    if geom.geom_type == "Polygon":
        rings = [geom.exterior]
    elif geom.geom_type == "MultiPolygon":
        rings = [p.exterior for p in geom.geoms]
    else:
        return geom
    return MultiLineString([list(r.coords) for r in rings])


# ===========================================================================
# 5. read the input SVG
# ===========================================================================
tree = etree.parse(SVG_IN)
root = tree.getroot()
if etree.QName(root).localname != "svg":
    sys.exit("error: input is not an SVG document")

# --- authored global metadata (copied verbatim to the output) ----------------
input_metadata = []   # (localname, text) for inkstitch:* children of <metadata>
for _el in root.iter():
    if etree.QName(_el).localname != "metadata":
        continue
    for _ch in _el:
        _k = _ch.tag
        if isinstance(_k, str) and _k.startswith("{" + INK_NS + "}"):
            input_metadata.append((_k.split("}", 1)[1], _ch.text or ""))

# --- units -------------------------------------------------------------------
def _root_mm(v, fallback):
    if not v:
        return fallback
    m = re.match(r"^\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)\s*([a-zA-Z%]*)", v)
    if not m:
        return fallback
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit in ("mm", ""):
        return val
    if unit == "cm":
        return val * 10.0
    if unit == "in":
        return val * 25.4
    if unit == "pt":
        return val * 25.4 / 72.0
    if unit == "pc":
        return val * 25.4 / 6.0
    if unit == "px":
        return val * 25.4 / 96.0
    return val


_vb = (root.get("viewBox") or "").replace(",", " ").split()
if len(_vb) == 4:
    vb_w = float(_vb[2])
else:
    vb_w = None
_w_mm = _root_mm(root.get("width"), vb_w if vb_w is not None else 1.0)
if vb_w and vb_w > 0:
    uu_per_mm = vb_w / _w_mm
else:
    uu_per_mm = 1.0
# coordinates are (user units) -> mm by dividing by uu_per_mm
MM = 1.0 / uu_per_mm
print(f"canvas: width {_w_mm:g} mm, viewBox width {vb_w if vb_w else '?'} "
      f"-> 1 user unit = {MM:.4g} mm")

SKIP_TAGS = {"defs", "symbol", "image", "metadata", "namedview", "title", "desc", "style", "filter", "clipPath", "mask"}
NON_PATH_DRAWABLE = {"rect", "circle", "ellipse", "polygon", "polyline", "line"}

fill_paths = []     # (color, geom_mm)
authored_colors = []  # first-seen
authored_set = set()
satin_items = []    # dicts: color, lines (centreline union) or rails (list of
                    # (N,2) mm polylines), width_mm, attrs
satinize_candidates = []   # (color, polygon_mm, attrs) authored subpaths of the
                           # colours listed in the satinize config
n_path = 0
n_dropped_stroke = 0
n_widened_satin = 0
n_skipped_nonpath = 0

# An authored satin is narrower than Ink/Stitch's satin gate; widen it to this
# instead of letting it silently become a running stitch.
SATIN_MIN_EMIT_MM = 1.5


def handle_path(el, mat, style):
    global n_path, n_dropped_stroke, n_widened_satin
    n_path += 1
    d = el.get("d") or ""
    if not d.strip():
        return
    authored = {}
    for _k, _v in el.attrib.items():
        if isinstance(_k, str) and _k.startswith("{" + INK_NS + "}"):
            authored[_k.split("}", 1)[1]] = _v
    fill = style.get("fill", "#000000")   # SVG initial fill is black
    fill_c = norm_color(fill)
    stroke = norm_color(style.get("stroke"))
    s = mat_scale(mat)
    sw_uu = parse_len_uu(style.get("stroke-width"))
    if sw_uu is None:
        sw_uu = 1.0
    sw_mm = sw_uu * s * MM
    authored_satin = str(authored.get("satin_column", "")).strip().lower() in ("true", "1", "yes")

    if fill_c is not None and not authored_satin:
        if fill_c not in authored_set:
            authored_set.add(fill_c)
            authored_colors.append(fill_c)
        tol_user = TOLERANCE_MM / (s * MM) if s * MM > 0 else TOLERANCE_MM
        try:
            subs = parse_path(d, tol_user)
        except Exception as exc:
            print(f"warning: skipping path {el.get('id')!r}: {exc}")
            return
        rings = [apply_pts(mat, sp) * MM for sp in subs]
        if fill_c.lower() in _SATINIZE_COLORS:
            # satin candidates are the authored subpaths, NOT the even-odd XOR
            # geometry: overlapping subpaths XOR into crescent slivers with
            # holes, which skeletonise badly (see work/PLAN_round3.md)
            _subs = []
            for r in rings:
                if len(r) < 3:
                    continue
                try:
                    p = Polygon(r)
                except Exception:
                    continue
                if not p.is_valid:
                    p = polygonal(make_valid(p))
                if p is None or p.is_empty:
                    continue
                for part in (p.geoms if p.geom_type == "MultiPolygon" else [p]):
                    if part.geom_type == "Polygon" and part.area >= SAT_MIN_COMP_MM2:
                        _subs.append(part)
            for i, p in enumerate(_subs):
                pb = p.bounds
                if any(j != i and q.area > p.area and
                       q.bounds[0] <= pb[0] and q.bounds[1] <= pb[1] and
                       q.bounds[2] >= pb[2] and q.bounds[3] >= pb[3] and
                       q.contains(p)
                       for j, q in enumerate(_subs)):
                    continue   # a hole subpath, not a stitched shape
                satinize_candidates.append((fill_c, p, {}))
        geom = rings_to_geom(rings)
        geom = polygonal(geom)
        if geom is not None and not geom.is_valid:
            geom = polygonal(geom.buffer(0))
        if geom is not None:
            fill_paths.append((fill_c, geom, authored))
        else:
            print(f"warning: fill path {el.get('id')!r} produced no geometry; skipped")
        return

    # no fill: a stroke-only path
    if stroke is not None:
        tol_user = TOLERANCE_MM / (s * MM) if s * MM > 0 else TOLERANCE_MM
        try:
            subs = parse_path(d, tol_user)
        except Exception as exc:
            print(f"warning: skipping stroke path {el.get('id')!r}: {exc}")
            return
        mm_subs = []
        for sp in subs:
            p = apply_pts(mat, sp) * MM
            if len(p) >= 2:
                mm_subs.append(p)

        # An authored satin column keeps its geometry: with two or more subpaths
        # Ink/Stitch treats the first two as rails and the rest as rungs, so the
        # width comes from the rails (the artist's `Outline` layer is exactly
        # this).  A single-subpath satin is a centreline whose width is the
        # stroke-width; below Ink/Stitch's strict > 1 mm gate it silently
        # becomes running stitch, so widen it instead of dropping it.
        if authored_satin and len(mm_subs) >= 2:
            satin_items.append(dict(color=stroke, lines=None, rails=mm_subs,
                                    width_mm=0.0, attrs=authored))
            return
        if authored_satin and len(mm_subs) == 1:
            if sw_mm <= SATIN_GATE_MM:
                sw_mm = SATIN_MIN_EMIT_MM
                n_widened_satin += 1
                print(f"note: widening authored satin {el.get('id')!r} from "
                      f"{sw_mm:.2f} mm to {SATIN_MIN_EMIT_MM:.1f} mm "
                      f"(Ink/Stitch gate is strictly > {SATIN_GATE_MM:.1f} mm)")
            satin_items.append(dict(color=stroke, lines=LineString(mm_subs[0]),
                                    rails=None, width_mm=sw_mm, attrs=authored))
            return
        if sw_mm <= SATIN_GATE_MM:
            n_dropped_stroke += 1
            print(f"note: dropping sub-gate stroke {el.get('id')!r} "
                  f"({sw_mm:.3f} mm <= {SATIN_GATE_MM:.1f} mm satin gate)")
            return
        lines = [LineString(p) for p in mm_subs]
        if lines:
            satin_items.append(dict(color=stroke, lines=unary_union(lines),
                                    rails=None, width_mm=sw_mm, attrs=authored))


def satin_footprint(item):
    """Best-effort polygon footprint of a satin item (for fit box, trim, stats)."""
    if item.get("rails"):
        rails = item["rails"]
        rings = []
        for sp in rails[:2]:
            if len(sp) >= 3 and np.allclose(sp[0], sp[-1], atol=0.5):
                p = polygonal(make_valid(Polygon(sp)))
                if p is not None and not p.is_empty:
                    rings.append(p)
        if len(rings) == 2:
            band = polygonal(rings[0].symmetric_difference(rings[1]))
            if band is not None and not band.is_empty:
                return band
        strips = [LineString(sp).buffer(0.25, join_style=2)
                  for sp in rails if len(sp) >= 2]
        if strips:
            return polygonal(unary_union(strips))
        return None
    if item.get("lines") is not None:
        return polygonal(item["lines"].buffer(max(item["width_mm"], 0.2) / 2.0,
                                              join_style=2))
    return None


def walk(el, mat, display):
    global n_skipped_nonpath
    tag = etree.QName(el).localname
    if tag in SKIP_TAGS:
        return
    style = element_style(el)
    disp = style.get("display", display)
    if disp == "none":
        return
    m = parse_transform(el.get("transform"))
    mat = mat @ m
    if tag == "path":
        handle_path(el, mat, style)
    elif tag in NON_PATH_DRAWABLE:
        sys.exit(f"error: <{tag}> is not supported on the native SVG path; "
                 f"convert it to <path> (Inkscape: Path > Object to Path)")
    else:
        for child in el:
            walk(child, mat, disp)


for child in root:
    walk(child, np.eye(3), "inline")

if not fill_paths and not satin_items:
    sys.exit("error: no stitchable geometry found")

n_rail_satin = sum(1 for it in satin_items if it.get("rails"))
print(f"elements: {n_path} path(s) visible, {len(fill_paths)} fill object(s), "
      f"{len(satin_items)} satin(s) ({n_rail_satin} rail-based), "
      f"{n_dropped_stroke} sub-gate stroke(s) dropped")


# ===========================================================================
# 6. scale to the fit box
# ===========================================================================
fill_union = polygonal(unary_union([g for _, g, _ in fill_paths]))
_satin_fps = [(it, satin_footprint(it)) for it in satin_items]
art = polygonal(unary_union([g for _, g, _ in fill_paths] +
                            [fp for _, fp in _satin_fps if fp is not None]))
minx, miny, maxx, maxy = art.bounds
art_w = maxx - minx
art_h = maxy - miny
# satin pull compensation widens every satin band by SATIN_PULL_MM per side;
# budget for it here so the fitted design does not exceed the fit box
if satin_items:
    art_w += 2.0 * SATIN_PULL_MM
    art_h += 2.0 * SATIN_PULL_MM

if WIDTH_MM_ARG is not None or HEIGHT_MM_ARG is not None:
    sx = (float(WIDTH_MM_ARG) / art_w) if WIDTH_MM_ARG is not None else None
    sy = (float(HEIGHT_MM_ARG) / art_h) if HEIGHT_MM_ARG is not None else None
    if sx is not None and sy is not None:
        scale = min(sx, sy)
    elif sx is not None:
        scale = sx
    else:
        scale = sy
else:
    scale = SIZE_MM / max(art_w, art_h)
fit_w = art_w * scale
fit_h = art_h * scale
print(f"artwork: {art_w:.1f} x {art_h:.1f} mm -> scaled {fit_w:.1f} x {fit_h:.1f} mm "
      f"(x{scale:.4f})")


def to_fit(geom):
    if geom is None or geom.is_empty:
        return geom
    return affine_transform(geom, [scale, 0, 0, scale, -minx * scale, -miny * scale])


def to_fit_pts(p):
    return p * scale - np.array([minx * scale, miny * scale])


fill_paths = [(c, to_fit(g), a) for c, g, a in fill_paths]
satinize_candidates = [(c, to_fit(g), a) for c, g, a in satinize_candidates]
_scaled_items = []
for _it in satin_items:
    _it = dict(_it)
    if _it.get("rails"):
        _it["rails"] = [to_fit_pts(p) for p in _it["rails"]]
        if not _it.get("width_mm"):
            _it["width_mm"] = 2.0   # decorative for rail satins; > Ink/Stitch's gate
    if _it.get("lines") is not None:
        _it["lines"] = to_fit(_it["lines"])
    _it["width_mm"] = _it["width_mm"] * scale
    _scaled_items.append(_it)
satin_items = _scaled_items
fill_union = to_fit(fill_union)
art = to_fit(art)
minx = miny = 0.0


# ===========================================================================
# 7. satin border: an authored rail satin if there is one, else synthetic
# ===========================================================================
border_geom = None      # the satin band footprint (for coverage)
border_centre = None    # centreline ring emitted as the synthetic satin path
authored_border = None  # authored rail satin used as the border
if not NO_BORDER:
    if BORDER_COLOR_ARG is None:
        sys.exit("error: --border-color is required when the satin border is enabled "
                 "(or pass --no-border)")
    bcol = norm_color(BORDER_COLOR_ARG)
    if bcol is None:
        sys.exit(f"error: could not parse --border-color {BORDER_COLOR_ARG!r}")
    if bcol not in authored_set:
        sys.exit(f"error: --border-color {bcol} does not match any authored fill "
                 f"({', '.join(authored_colors)})")

    # The artist's own outline satin follows the true silhouette (horns, notches
    # and all) and the reference design stitches it as the border.  Detect it:
    # a rail satin whose footprint spans nearly the whole fill silhouette.
    if fill_union is not None and not fill_union.is_empty:
        _fx0, _fy0, _fx1, _fy1 = fill_union.bounds
        _fw, _fh = max(_fx1 - _fx0, 1e-9), max(_fy1 - _fy0, 1e-9)
        for _it in satin_items:
            if not _it.get("rails"):
                continue
            _fp = satin_footprint(_it)
            if _fp is None or _fp.is_empty:
                continue
            _bx0, _by0, _bx1, _by1 = _fp.bounds
            _cov_w = (min(_bx1, _fx1) - max(_bx0, _fx0)) / _fw
            _cov_h = (min(_by1, _fy1) - max(_by0, _fy0)) / _fh
            if _cov_w >= 0.95 and _cov_h >= 0.95:
                authored_border = _it
                border_geom = _fp
                break

if not NO_BORDER and authored_border is not None:
    _rail_len = sum(LineString(sp).length for sp in authored_border["rails"][:2])
    print(f"border: using the authored rail satin ({len(authored_border['rails'])} "
          f"subpaths, rails {_rail_len:.0f} mm) instead of a synthetic border; "
          f"fills keep their full footprint beneath it")

if not NO_BORDER and authored_border is None:
    if art.geom_type == "Polygon":
        outer = art.exterior
    else:
        polys = sorted(art.geoms, key=lambda p: p.area, reverse=True)
        print(f"warning: artwork is {art.geom_type} ({len(polys)} components); "
              f"bordering the largest component only")
        outer = polys[0].exterior

    # The border follows the outer boundary only (holes are ignored, exactly as
    # ``union.exterior`` implies).  Wrap the ring in a Polygon first: a shapely
    # LinearRing is 1-D, so ring.buffer(-d) is empty.
    #
    # Morphologically close then open the filled silhouette before tracing:
    # closing bridges narrow V-notches/bays (e.g. the notch between a serpent
    # head and its body), opening bridges narrow necks/protrusions.  Without
    # them the centreline dives into a notch and hair-pins, and Ink/Stitch's
    # rail offsetting renders that as crossing spikes (verified on this
    # artwork: 26 mm runaway stitches, starbursts at both serpent heads).
    silhouette = Polygon(outer)
    closed = silhouette.buffer(BORDER_CLOSE_MM, join_style=2).buffer(
        -BORDER_CLOSE_MM, join_style=2)
    if closed.is_empty:
        closed = silhouette
    if closed.geom_type == "MultiPolygon":
        closed = max(closed.geoms, key=lambda p: p.area)
    opened = closed.buffer(-BORDER_OPEN_MM, join_style=2).buffer(BORDER_OPEN_MM, join_style=2)
    if opened.is_empty:
        opened = closed  # tiny artwork: never let opening erase the border
    if opened.geom_type == "Polygon":
        opened_outer = opened.exterior
    else:
        opened_outer = max(opened.geoms, key=lambda p: p.area).exterior
    centre = Polygon(opened_outer).buffer(
        -(BORDER_MM / 2.0 + BORDER_OVERHANG_MM), join_style=2).buffer(0)
    if centre.is_empty:
        sys.exit(f"error: satin border {BORDER_MM} mm is wider than the artwork; "
                 f"nothing left to trace (use a smaller --border-mm or --no-border)")
    carve = centre.buffer(BORDER_MM / 2.0, join_style=2).difference(
        centre.buffer(-BORDER_MM / 2.0, join_style=2))
    carve = polygonal(carve)

    # carve the band out of every fill
    carved = []
    for c, g, a in fill_paths:
        g2 = polygonal(g.difference(carve)) if carve is not None else g
        if g2 is not None and not g2.is_empty:
            carved.append((c, g2, a))
    fill_paths = carved

    border_geom = carve
    border_centre = _centreline(centre)
    print(f"border: colour {bcol} width {BORDER_MM} mm, "
          f"centreline {border_centre.length:.1f} mm")


# ===========================================================================
# 7b. colour overlap: carve under-colours out from beneath later colours
# ===========================================================================
# A later colour may overlap an earlier one by OVERLAP_MM at the edges
# (registration margin), but nothing beyond that: the artwork's black was
# drawn over the green body, leaving 138 green fragments (383 mm2) fully
# hidden under black -- stitches with nothing to show for them, and bulk
# under the top layer.  Carve each colour by the union of the colours
# stitched after it, shrunk by OVERLAP_MM.
_rank = {c: i for i, c in enumerate(authored_colors)}
# the colours as drawn, before the overlap carve: section 7d needs the drawn
# edge of the earlier colour (not its stitched footprint -- a satinized leg
# overhangs its own outline and would pull the later colour back off the black
# that is not really there)
_drawn = {c: unary_union([g for cc, g, _ in fill_paths if cc == c])
          for c in authored_colors
          if any(cc == c for cc, _, _ in fill_paths)}
if len(authored_colors) > 1 and OVERLAP_MM > 0:
    _before = sum(g.area for _, g, _ in fill_paths)
    for _k, _c in enumerate(authored_colors):
        if _k == len(authored_colors) - 1:
            break
        _later = [g for cc, g, _ in fill_paths if _rank.get(cc, -1) > _k]
        if not _later:
            continue
        _cover = unary_union(_later).buffer(-OVERLAP_MM, join_style=2)
        if _cover.is_empty:
            continue
        _new = []
        for cc, g, a in fill_paths:
            if cc == _c:
                g2 = polygonal(g.difference(_cover))
                if g2 is not None and not g2.is_empty:
                    _new.append((cc, g2, a))
            else:
                _new.append((cc, g, a))
        fill_paths = _new
    _after = sum(g.area for _, g, _ in fill_paths)
    print(f"overlap: carved under-colours {OVERLAP_MM} mm inside later colours "
          f"({_before - _after:.0f} mm2 hidden fill removed)")


# ===========================================================================
# 7c. satinize: thin/elongated authored subpaths -> satin columns
# ===========================================================================
# The centipede is drawn as one green fill; its legs and segments are 0.5-4 mm
# wide, where a tatami fill is a 1-2 stitch ladder.  Satin covers those with
# 1-3 columns each.  Candidates are the authored subpaths (not the XOR
# geometry); a component the satinizer cannot cover stays part of the fill.
if satinize_candidates:
    _new_sats = []
    _covered_polys = []
    _n_ok = _n_fail = 0
    _ok_area = _fail_area = 0.0
    for _c, _g, _a in satinize_candidates:
        _parts = list(_g.geoms) if _g.geom_type == "MultiPolygon" else [_g]
        for _part in _parts:
            _res = satinize.component_to_satins(
                _part, max_row_mm=SAT_MAX_ROW_MM, max_rows=SAT_MAX_ROWS,
                min_coverage=SAT_MIN_COVERAGE, max_overhang=SAT_MAX_OVERHANG)
            if _res and not all(
                    satinize.centreline_ok(_r["centreline"], _r["width_mm"])
                    for _r in _res):
                # a degenerate centreline makes Ink/Stitch raise while building
                # rails and aborts the whole export; leave the shape as fill
                print(f"note: satinized component near {_part.centroid.x:.1f},"
                      f"{_part.centroid.y:.1f} has a degenerate centreline; kept as fill")
                _res = None
            if _res:
                _n_ok += 1
                _ok_area += _part.area
                _covered_polys.append(_part)
                for _r in _res:
                    _new_sats.append(dict(color=_c,
                                          lines=LineString(_r["centreline"]),
                                          rails=None, width_mm=_r["width_mm"],
                                          attrs={}))
            else:
                _n_fail += 1
                _fail_area += _part.area
    if _covered_polys:
        # remove the satinized shapes from the fill entirely: carving only the
        # bands would leave sub-mm fill slivers between them, each a new
        # element with its own underlay/ties (measured hotspot source)
        _carve_sat = polygonal(unary_union(_covered_polys))
        _kept = []
        for _c, _g, _a in fill_paths:
            if _c.lower() in _SATINIZE_COLORS:
                _g2 = polygonal(_g.difference(_carve_sat))
                if _g2 is None or _g2.is_empty:
                    continue
                _kept.append((_c, _g2, _a))
            else:
                _kept.append((_c, _g, _a))
        fill_paths = _kept
    satin_items.extend(_new_sats)
    _w_min = min((s["width_mm"] for s in _new_sats), default=2.0)
    print(f"satinize: {_n_ok} component(s) -> {len(_new_sats)} satin column(s) "
          f"({_ok_area:.0f} mm2), {_n_fail} left as fill ({_fail_area:.0f} mm2), "
          f"narrowest column {_w_min:.2f} mm")

# Split each authored path into its connected components.  Ink/Stitch stitches
# one element as a single stitch group, so travels between the components of a
# multi-component path are never trimmed (verified: the artist's reference has
# 85 intra-element travels > 8 mm, ours had 88 — the loose threads the machine
# leaves for the operator to clip).  One element per component lets the NN
# sweep order them and the trim pass cut the long gaps.  The authored
# ``trim_after`` is dropped here: the trim pass below decides per gap.
_later_union = {}
for _c in authored_colors:
    _later = [g for cc, g, _ in fill_paths if _rank.get(cc, -1) > _rank.get(_c, -1)]
    _later_union[_c] = unary_union(_later) if _later else None

_components = []
_n_speck = 0
_n_hidden = 0
for c, g, a in fill_paths:
    comps = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
    for comp in comps:
        if comp.geom_type != "Polygon" or comp.area <= 0:
            continue
        cx0, cy0, cx1, cy1 = comp.bounds
        if max(cx1 - cx0, cy1 - cy0) < 0.5:
            # sub-0.5 mm specks cannot produce a stitch; keeping them would
            # poison the trim chain (Ink/Stitch silently skips empty elements,
            # so the "next object" the trim pass sees is not the next stitched
            # one — verified: a 74 mm untrimmed travel came from this).
            _n_speck += 1
            continue
        _later = _later_union.get(c)
        if _later is not None and not _later.is_empty:
            # After the 1 mm carve, a component fully covered by later colours
            # is a bare stub of thread with nothing to show -- and each stub
            # gets its own underlay + tie locks, the measured hotspot cause.
            # The underlap that matters (at the colour edge) stays attached to
            # the visible component and is kept.
            if comp.difference(_later).area < 0.01:
                _n_hidden += 1
                continue
        _components.append((c, comp, {k: v for k, v in a.items() if k != "trim_after"}))
fill_paths = _components
print(f"components: {len(fill_paths)} fill component(s) after splitting "
      f"({_n_speck} unstitchable speck(s) dropped, "
      f"{_n_hidden} fully-hidden fragment(s) dropped)")


# ===========================================================================
# 7d. colour seam: pull the later colour back by half a thread width
# ===========================================================================
# A fill lays thread centred on its path, so the *stitched* edge of a later
# colour finishes half a thread width outside the geometry the artist drew
# (0.2 mm for 0.4 mm round thread, 0.25 mm once flattened on fabric).  On the
# Scavenger's Daughter artwork that bleed ate 17-19 % of the artwork's visible
# green -- 573 of 3,008 mm2 -- and because 32 % of the green lies within 0.5 mm
# of a colour edge the centipede's thin legs lost half their width: the green
# was stitched everywhere the artwork shows it, the black simply finished on top
# of it.  (The hand-digitized reference loses the same 19 %, so this is not
# "match the reference": the fix is to put the *stitched* edge of the later
# colour back onto the drawn edge.)
#
# Move the seam SEAM_PULL_MM into the later colour, only where it abuts the
# earlier colour *as drawn*: the outer silhouette and the artwork's white
# highlights are untouched, so the black still covers the artwork's black out to
# its edge (measured 100 % -> 99.8 % at 0.5 mm thread), and the earlier colour's
# own thread finishes a little wide, so no seam opens.  The under-colour keeps
# OVERLAP_MM - SEAM_PULL_MM = 0.8 mm of underlap beneath the later colour
# (docs/adr/0003 wants 0.5-1 mm).
#
# This runs after the component split so the hidden-fragment test above still
# judges "fully hidden under the later colour" against the *drawn* black: a
# fragment that only pokes out because the black was pulled back is still under
# the black's thread and must not come back as its own element.
if SEAM_PULL_MM > 0 and len(authored_colors) > 1:
    _seam_area = 0.0
    for _k in range(1, len(authored_colors)):
        _earlier_d = None
        for _c in authored_colors[:_k]:
            _d = _drawn.get(_c)
            if _d is not None and not _d.is_empty:
                _earlier_d = _d if _earlier_d is None else _earlier_d.union(_d)
        _later_d = None
        for _c in authored_colors[_k:]:
            _d = _drawn.get(_c)
            if _d is not None and not _d.is_empty:
                _later_d = _d if _later_d is None else _later_d.union(_d)
        if _earlier_d is None:
            continue
        # Only the part of the earlier colour *deep* under the later colour (a
        # fully hidden fragment) is excluded from the seam source.  Excluding all
        # of it loses the underlap that sits right at the seam; excluding none of
        # it notches the middle of the later colour wherever a hidden fragment
        # happens to lie.  Measured: 91.0 % vs 92.5 % of the artwork's green
        # visible, at the same black coverage.
        _deep = None
        if _later_d is not None:
            _deep = _later_d.buffer(-(SEAM_PULL_MM + _SEAM_MARGIN_MM), join_style=2)
        _vis = _earlier_d if _deep is None or _deep.is_empty else polygonal(
            _earlier_d.difference(_deep))
        if _vis is None or _vis.is_empty:
            continue
        _reach = _vis.buffer(SEAM_PULL_MM, join_style=2)
        if _reach.is_empty:
            continue
        _out = []
        for cc, g, a in fill_paths:
            if _rank.get(cc, -1) != _k:
                _out.append((cc, g, a))
                continue
            _band = g.intersection(_reach)
            if _band.is_empty:
                _out.append((cc, g, a))
                continue
            g2 = polygonal(g.difference(_band))
            _seam_area += _band.area
            if g2 is None or g2.is_empty:
                # a shape so thin that the pull would erase it keeps its drawn
                # size: a narrow seam is better than a missing detail
                _out.append((cc, g, a))
            else:
                _out.append((cc, g2, a))
        fill_paths = _out
    if _seam_area > 0.5:
        print(f"seam: pulled later colour(s) back {SEAM_PULL_MM} mm off the colour "
              f"edges ({_seam_area:.0f} mm2 of fill) so their thread finishes on "
              f"the drawn edge instead of over the earlier colour")


# ===========================================================================
# 8. build objects, order by colour (document order) with an NN sweep
# ===========================================================================
def centroid_of(geom):
    c = geom.centroid
    return (float(c.x), float(c.y))


objects = []
_color_order = list(authored_colors)
for _it in satin_items:
    if _it is not authored_border and _it["color"] not in _color_order:
        _color_order.append(_it["color"])
for color in _color_order:
    if color.lower() in _SKIP:
        continue
    items = []
    for c, g, a in fill_paths:
        if c != color:
            continue
        pts = geom_points(g)
        items.append(dict(color=color, geom=g, pts=pts, cent=centroid_of(g),
                          satin=False, width_mm=None, attrs=a,
                          group="color:" + color, label=color))
    # satins of this colour are stitched in the same layer, ordered with the
    # fills by the same nearest-neighbour sweep
    for _it in satin_items:
        if _it is authored_border or _it["color"] != color:
            continue
        band = satin_footprint(_it)
        if band is None or band.is_empty:
            print(f"warning: satin in {color} produced no footprint; skipped")
            continue
        if _it.get("lines") is not None:
            centre = (float(_it["lines"].centroid.x), float(_it["lines"].centroid.y))
        else:
            centre = centroid_of(band)
        items.append(dict(color=color, geom=band, pts=geom_points(band),
                          cent=centre, satin=True, width_mm=_it["width_mm"],
                          centreline=_it.get("lines"), rails=_it.get("rails"),
                          attrs=_it["attrs"], group="color:" + color, label=color))
    if not items:
        continue
    # nearest-neighbour sweep, needle carried in from the previous layer
    needle = objects[-1]["cent"] if objects else (0.0, 0.0)
    remaining = list(items)
    while remaining:
        i = min(range(len(remaining)),
                key=lambda k: (remaining[k]["cent"][0] - needle[0]) ** 2 +
                              (remaining[k]["cent"][1] - needle[1]) ** 2)
        nxt = remaining.pop(i)
        objects.append(nxt)
        needle = nxt["cent"]

# border last: the authored outline satin when there is one, else the synthetic band
if authored_border is not None:
    objects.append(dict(color=bcol, geom=border_geom, pts=geom_points(border_geom),
                        cent=centroid_of(border_geom), satin=True,
                        width_mm=authored_border["width_mm"], centreline=None,
                        rails=authored_border["rails"], attrs=authored_border["attrs"],
                        group="border", label="Border"))
elif border_geom is not None:
    objects.append(dict(color=bcol, geom=border_geom, pts=geom_points(border_geom),
                        cent=centroid_of(border_geom), satin=True, width_mm=BORDER_MM,
                        centreline=border_centre, attrs={}, group="border", label="Border"))

if not objects:
    sys.exit("error: no stitchable objects produced (all colours skipped via skip_colors?)")

print(f"objects: {len(objects)}")


# ===========================================================================
# 9. trim: cut a jump that is long OR exposed (not covered by a later object)
# ===========================================================================
def gap_and_segment(a, b):
    """Travel bounds (mm) between two objects, plus the nearest-boundary segment."""
    pa, pb = a["pts"], b["pts"]
    if len(pa) == 0 or len(pb) == 0:
        d = math.hypot(a["cent"][0] - b["cent"][0], a["cent"][1] - b["cent"][1])
        return d, d, np.asarray(a["cent"], float), np.asarray(b["cent"], float)
    dist, idx = cKDTree(pa).query(pb)
    j = int(np.argmin(dist))
    d_min = float(dist[j])
    d_max = max(float(dist.max()), float(cKDTree(pb).query(pa)[0].max()))
    return d_min, d_max, pa[idx[j]], pb[j]


_prepped = [prep(o["geom"]) for o in objects]


def is_hidden(p0, p1, idx):
    """True if every sampled point of the jump after object ``idx`` is covered
    by a later object (a point is in the union iff it is in any member)."""
    later = [g for g in _prepped[idx + 1:]]
    if not later:
        return False
    dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    n = max(8, int(dist * 2))
    for t in np.linspace(0.0, 1.0, n + 2)[1:-1]:
        pt = Point(p0[0] + t * (p1[0] - p0[0]), p0[1] + t * (p1[1] - p0[1]))
        if not any(g.contains(pt) for g in later):
            return False
    return True


trim_after = [False] * len(objects)
n_trims = 0
n_authored = 0
if TRIM:
    for i in range(len(objects)):
        authored = (objects[i].get("attrs") or {}).get("trim_after")
        if authored is not None:
            val = str(authored).strip().lower() in ("true", "1", "yes")
            trim_after[i] = val
            if val:
                n_authored += 1
            continue
        if i >= len(objects) - 1:
            continue
        d_min, d_max, p0, p1 = gap_and_segment(objects[i], objects[i + 1])
        if d_min <= TRIM_MIN_MM:
            continue
        if TRIM_THRESHOLD_MM == 0 or d_max > TRIM_THRESHOLD_MM or not is_hidden(p0, p1, i):
            trim_after[i] = True
    n_trims = sum(trim_after)
    print(f"trim: {n_trims} cut(s) / {len(objects)} objects "
          f"({n_authored} authored, threshold {TRIM_THRESHOLD_MM} mm, min {TRIM_MIN_MM} mm)")


# ===========================================================================
# 10. emit Ink/Stitch SVG
# ===========================================================================
def _esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _ink_attrs(attrs, exclude=()):
    """Serialise authored inkstitch:* attributes, skipping ``exclude`` keys."""
    out = []
    for k, v in (attrs or {}).items():
        if k in exclude:
            continue
        out.append(f'inkstitch:{k}="{_esc(v)}"')
    return (" ".join(out) + " ") if out else ""


def subpaths_to_d(subpaths):
    """Polylines -> path data without ``Z`` (satin rails/rungs must stay open)."""
    return " ".join("M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in sp)
                    for sp in subpaths if len(sp) >= 2)


def mic_diameter_mm(geom):
    """Max inscribed circle diameter; inf when it cannot be measured."""
    try:
        return 2.0 * maximum_inscribed_circle(geom).length
    except Exception:
        return float("inf")


def fill_el(id_, color, d, spacing, trim_after, attrs, small=False, angle=None,
            spacing_override=False):
    a = dict(attrs or {})
    # authored values win; supply defaults only where the artist did not
    if spacing_override:
        # ...unless the operator asked for a density: the artwork ships
        # row_spacing_mm="0.4", which would otherwise silently win over
        # `density: 0.3` and leave the base fabric showing through
        a["row_spacing_mm"] = f"{spacing:g}"
    else:
        a.setdefault("row_spacing_mm", f"{spacing:g}")
    a.setdefault("max_stitch_length_mm", "3")
    if angle is not None:
        a["angle"] = f"{angle:g}"
    if small:
        # A component that small cannot carry a fill underlay plus tie locks
        # without packing the needle; skip both (Ink/Stitch would otherwise
        # stitch them anyway -- there is no automatic small-shape exemption).
        a.setdefault("fill_underlay", "false")
        a.setdefault("ties", "3")
    else:
        a.setdefault("fill_underlay", "true")
    # never emit skip_last (default False); trim is driven by the trim pass
    a.pop("fill_underlay_skip_last", None)
    a.pop("satin_column", None)
    a.pop("trim_after", None)
    passthrough = _ink_attrs(a)
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    return (f'<path id="{id_}" style="fill:{color};stroke:none" fill-rule="evenodd" '
            f'{passthrough}{trim}d="{d}"/>')


def satin_el(id_, color, d, width_mm, trim_after, attrs, pull=True, zigzag=None):
    a = dict(attrs or {})
    a.setdefault("satin_column", "true")
    if pull and SATIN_PULL_MM:
        a.setdefault("pull_compensation_mm", f"{SATIN_PULL_MM} {SATIN_PULL_MM}")
    if zigzag:
        a.setdefault("zigzag_spacing_mm", f"{zigzag:g}")
    a.pop("trim_after", None)
    passthrough = _ink_attrs(a)
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    # round joins: the default miter spikes at sharp centreline corners, the
    # offset self-intersects and Ink/Stitch abandons the rail conversion
    return (f'<path id="{id_}" style="fill:none;stroke:{color};'
            f'stroke-width:{width_mm:.2f};stroke-linejoin:round" '
            f'{passthrough}{trim}d="{d}"/>')


p = []
p.append(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkstitch="http://inkstitch.org/namespace" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
    'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd" '
    f'width="{fit_w:.2f}mm" height="{fit_h:.2f}mm" viewBox="0 0 {fit_w:.2f} {fit_h:.2f}" '
    'inkscape:document-units="mm" sodipodi:docname="design.svg">\n'
)
p.append(
    f'  <sodipodi:namedview id="namedview1" pagecolor="#ffffff" units="mm" '
    f'inkscape:document-units="mm" pagewidth="{fit_w:.2f}" pageheight="{fit_h:.2f}" '
    'inkscape:pageopacity="0.0" inkscape:pagecheckerboard="0" showgrid="false"/>\n'
)
_META_DEFAULTS = [
    ("min_stitch_len_mm", "0.1"),
    ("collapse_len_mm", "3"),
    ("min_satin_stroke_width_mm", "1"),
    ("inkstitch_svg_version", "4"),
]
_meta_items = list(input_metadata if input_metadata else _META_DEFAULTS)
# A satin column narrower than Ink/Stitch's default gate (1 mm) silently
# stitches as running stitch; lower the gate to match the narrowest satin we
# actually emit (stroke-width and the gate are both in mm here).
_narrow = [o["width_mm"] for o in objects if o["satin"] and o.get("width_mm")]
if _narrow and min(_narrow) <= 1.0:
    _gate = min(SATIN_MIN_GATE_MM, round(max(0.1, min(_narrow) - 0.1), 2))
    _meta_items = [(n, (f"{_gate:g}" if n == "min_satin_stroke_width_mm" else v))
                   for n, v in _meta_items]
    if not any(n == "min_satin_stroke_width_mm" for n, _ in _meta_items):
        _meta_items.append(("min_satin_stroke_width_mm", f"{_gate:g}"))
    print(f"note: narrowest satin {min(_narrow):.2f} mm; "
          f"min_satin_stroke_width_mm set to {_gate:g} so it stitches as satin")
_meta_xml = "".join(
    (f'<inkstitch:{_n}>{_esc(_t)}</inkstitch:{_n}>' if _t else f'<inkstitch:{_n}/>')
    for _n, _t in _meta_items)
p.append(f'  <metadata id="metadata1">{_meta_xml}</metadata>\n')

_angle_i = {}   # per-colour component counter for angle_cycle
current_group = None
idx = 0
for o, tm in zip(objects, trim_after):
    if o["group"] != current_group:
        if current_group is not None:
            p.append("  </g>\n")
        gid = "border" if o["group"] == "border" else "color%d" % idx
        p.append(f'  <g inkscape:label="{o["label"]}" inkscape:groupmode="layer" id="{gid}">\n')
        current_group = o["group"]
    if o["satin"]:
        if o.get("rails"):
            d = subpaths_to_d(o["rails"])
        elif o.get("centreline") is not None:
            d = line_geom_to_d(o["centreline"])
        else:
            d = geom_to_d(o["geom"])
        # no pull compensation on an authored rail satin: the reference sews it
        # without one, and widening a rail satin overshoots at sharp corners
        # (measured: radiating cross-stitch spikes at every horn tip).
        # Denser zigzag: where the rails pinch (horn tips) the cross stitches
        # fan out; at the default 0.4 mm the fan leaves 0.5-1.1 mm gaps between
        # the thread ends along the outer rail, which reads as a sawtooth edge.
        # 0.3 mm keeps the ends touching (+1.5k stitches on a 66k design).
        p.append("    " + satin_el(f"s{idx}", o["color"], d, o["width_mm"], tm,
                                   o.get("attrs"), pull=not o.get("rails"),
                                   zigzag=SATIN_ZIGZAG_MM if o.get("rails") else None) + "\n")
    else:
        _cl = o["color"].lower()
        spacing = _DENSITY.get(_cl, ROW_SPACING_MM)
        if FILL_ANGLE is not None:
            angle = FILL_ANGLE
        elif _cl in _ANGLE_CYCLE:
            _i = _angle_i.get(_cl, 0)
            _angle_i[_cl] = _i + 1
            angle = _ANGLE_CYCLE[_cl][_i % len(_ANGLE_CYCLE[_cl])]
        else:
            angle = _ANGLE.get(_cl)
        _small = (o["geom"].area < SMALL_FILL_MM2 or
                  mic_diameter_mm(o["geom"]) < SMALL_FILL_MIC_MM)
        # an explicit density (global or per colour) overrides the row spacing
        # authored on the path; with no density flag the artwork wins
        _override = (DENSITY_MM is not None or isinstance(_dens, (int, float))
                     or _cl in _DENSITY)
        p.append("    " + fill_el(f"f{idx}", o["color"], geom_to_d(o["geom"]), spacing, tm,
                                  o.get("attrs"), small=_small,
                                  angle=angle, spacing_override=_override) + "\n")
    idx += 1
if current_group is not None:
    p.append("  </g>\n")
p.append("</svg>\n")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("".join(p))


# ===========================================================================
# 11. summary
# ===========================================================================
used_colors = []
for o in objects:
    if o["group"] != "border" and o["color"] not in used_colors:
        used_colors.append(o["color"])
n_fill_objs = sum(1 for o in objects if not o["satin"])
n_satin_objs = sum(1 for o in objects if o["satin"])
fill_area = sum(g.area for c, g, _ in fill_paths if c in used_colors)
fill_est = fill_area / ROW_SPACING_MM * 1.25 if ROW_SPACING_MM > 0 else 0.0
_satin_est = 0.0
for o in objects:
    if not o["satin"] or o["group"] == "border":
        continue
    if o.get("centreline") is not None:
        _satin_est += 2.0 * o["centreline"].length / 0.4
    elif o.get("rails"):
        _satin_est += 2.0 * sum(LineString(sp).length for sp in o["rails"][:2]) / 0.4
if authored_border is not None:
    # _rail_len counts both rails, i.e. 2x the centreline; 2 stitches per
    # 0.4 mm zigzag step -> sum(rails)/0.4
    _rail_len = sum(LineString(sp).length for sp in authored_border["rails"][:2])
    border_est = _rail_len / 0.4
elif border_geom is not None and BORDER_MM > 0:
    border_est = 2.0 * border_centre.length / 0.4
else:
    border_est = 0.0
est = int(round(fill_est + _satin_est + border_est))

print(f"thread colours: {len(used_colors)} ({', '.join(used_colors)})")
print(f"objects: {n_fill_objs} fill + {n_satin_objs} satin")
print(f"estimated stitches: ~{est:,} (fills ~{int(fill_est):,} + "
      f"satin ~{int(_satin_est):,} + border ~{int(border_est):,})")
print(f"extent: {fit_w:.1f} x {fit_h:.1f} mm")
print(f"trim: {n_trims} cut(s)")
print(f"\nwrote {OUT}")
