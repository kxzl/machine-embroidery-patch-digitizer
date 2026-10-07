#!/usr/bin/env python3
"""image -> pre-digitized embroidery SVG (Ink/Stitch).

Handles two image classes:
  * transparent-background patch renditions  -> interior fills + a SATIN border
      (the dark outer ring is treated as the satin-stitch edge)
  * opaque flat art (engraving)              -> fills + a SATIN outline layer

Common behaviours:
  * k-means palette (no fixed colors)
  * holes preserved via even-odd fill
  * the darkest colour's thin regions are recognised as OUTLINES and turned into
    simple satin columns (skeleton centerline + local width); its solid regions
    stay fills
  * embroidery-aware cleanup (density 0.4 mm, drop sub-mm detail)
  * fills ordered by perceptual luma (light -> dark), outlines then border topmost
  * the needle position is carried across colour layers, so each layer's
    nearest-neighbour sweep starts where the previous one ended (layer order is
    fixed light -> dark and is not optimised)
  * a jump is trimmed when it is long OR exposed (not covered by a later stitch)
  * optional per-image YAML config (--config) for order/skip/density/border/trim

Usage:
  python tools/digitize/vectorize.py [--colors N] [--border-mm W] [--no-border]
                                     [--density MM] [--no-satin-outlines]
                                     [--satin-max-mm W] [--fill-angle DEG]
                                     [--satinize-colors HEX[,HEX]]
                                     [--trim] [--no-trim] [--trim-mm N] [--config F]
                                     [input.webp] [output.svg]
"""
import os
import sys
import warnings

import yaml
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.cluster.vq import kmeans2
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from skimage import measure, morphology

import satinize
from skeleton import satin_segments

_VALUE_FLAGS = {"--colors", "--border-mm", "--trim-mm", "--config", "--density",
                "--satin-max-mm", "--size-mm", "--fill-angle", "--satinize-colors"}
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

IMG = args[0] if len(args) > 0 else "Scavenger's_Daughter_by_the_dusty_druid.webp"
OUT = args[1] if len(args) > 1 else "work/design.svg"
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)


def flag(name, default):
    return _flags.get(name, default)


def load_config(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


N_COLORS = int(flag("colors", "5"))
NO_BORDER = flag("no-border", False) is True
BORDER_MM = float(flag("border-mm", "2.5"))
NO_TRIM = flag("no-trim", False) is True
TRIM = not NO_TRIM                   # cut long/exposed jumps (default on, machine-ready)
CONFIG = flag("config", None)
TRIM_MM = flag("trim-mm", None)      # None = unset (fall back to YAML/default)
DENSITY_MM = flag("density", None)   # None = unset (fall back to YAML/default)
NO_SATIN = flag("no-satin-outlines", False) is True
SATIN_MAX_ARG = flag("satin-max-mm", None)

SIZE_MM = float(flag("size-mm", "100"))   # longer side of finished design (mm)
ROW_SPACING_MM = 0.4       # fill density: 0.35-0.45 standard; <0.3 breaks needles, >0.6 leaves gaps
# narrower satin is widened to this.  Must stay strictly ABOVE Ink/Stitch's
# min_satin_stroke_width_mm = 1 (inkstitch/lib/utils/settings.py): thinner strokes
# silently render as running stitch
SATIN_MIN_MM = 1.2
SATIN_GATE_MM = 1.0       # Ink/Stitch's min_satin_stroke_width_mm; emit-time guard only
SATIN_MAX_MM = 2.5         # thicker than this is kept as a fill, not an outline
SATIN_MIN_LEN_MM = 2.0     # drop satin segments shorter than this (kills micro-segment flood)
SATIN_PULL_MM = 0.2        # satin pull compensation per side (closes the gap at the ends)
MIN_COMP_MM2 = 0.8         # drop components smaller than this
MIN_HOLE_MM2 = 0.2         # fill in holes smaller than this
OPEN_RADIUS = 1            # morph open (px)
CLOSE_RADIUS = 2           # morph close (px)
TOLERANCE_MM = 0.25        # polygon simplification (mm); 0.25 measured 1.5x faster
                           # export vs 0.15 with ~0.8% fewer stitches and no visible
                           # difference (docs/adr/0002-export-performance.md)
TRIM_MIN_MM = 2.0          # never cut jumps shorter than this (Ink/Stitch adds no locks below ~3 mm)

# --- per-image YAML overrides (CLI always wins) -------------------------------
cfg = load_config(CONFIG)
if flag("trim", False) is True:
    TRIM = True
_trim_cfg = cfg.get("trim") or {}
if "enabled" in _trim_cfg and flag("trim", False) is not True and not NO_TRIM:
    TRIM = bool(_trim_cfg["enabled"])
if cfg.get("satin_outlines") is False and not flag("no-satin-outlines", False):
    NO_SATIN = True
_border_cfg = (cfg.get("border") or {})
_border_mode = _border_cfg.get("mode", "auto")
if _border_cfg.get("thickness_mm") is not None and flag("border-mm", None) is None:
    BORDER_MM = float(_border_cfg["thickness_mm"])
if SATIN_MAX_ARG is not None:
    SATIN_MAX_MM = float(SATIN_MAX_ARG)
_extratrim = TRIM_MM if TRIM_MM is not None else (cfg.get("trim") or {}).get("threshold_mm")
TRIM_THRESHOLD_MM = float(_extratrim) if _extratrim is not None else 4.0
if TRIM_THRESHOLD_MM < 0:
    TRIM_THRESHOLD_MM = 0.0
_ORDER = cfg.get("order") or []
_SKIP = {str(s).lower() for s in (cfg.get("skip_colors") or [])}
_dens = cfg.get("density") or {}
if isinstance(_dens, (int, float)):
    ROW_SPACING_MM = float(_dens)
    _DENSITY = {}
elif isinstance(_dens, dict):
    _DENSITY = {}
    for _k, _v in _dens.items():
        try:
            _DENSITY[str(_k).lower()] = float(_v)
        except (TypeError, ValueError):
            print(f"warning: ignoring non-numeric density {_v!r} for {_k}")
elif _dens:
    print(f"warning: ignoring non-numeric density {_dens!r}")
    _DENSITY = {}
else:
    _DENSITY = {}
if DENSITY_MM is not None:
    ROW_SPACING_MM = float(DENSITY_MM)

# --- fill angle: one value for every fill, or a per-colour YAML map ---------
FILL_ANGLE = flag("fill-angle", None)
try:
    FILL_ANGLE = None if FILL_ANGLE is None else float(FILL_ANGLE)
except (TypeError, ValueError):
    print(f"warning: ignoring non-numeric --fill-angle {FILL_ANGLE!r}")
    FILL_ANGLE = None
_ANGLE = {}
for _k, _v in (cfg.get("angle") or {}).items():
    try:
        _ANGLE[str(_k).lower()] = float(_v)
    except (TypeError, ValueError):
        print(f"warning: ignoring non-numeric angle {_v!r} for {_k}")

# --- satinize: thin/elongated fills of the listed colours -> satin columns ---
_sat_cfg = cfg.get("satinize") or {}
if isinstance(_sat_cfg, list):
    _sat_cfg = {"colors": _sat_cfg}
elif not isinstance(_sat_cfg, dict):
    print(f"warning: ignoring non-mapping satinize {_sat_cfg!r}")
    _sat_cfg = {}
SATINIZE_COLORS = {str(c).lower() for c in (_sat_cfg.get("colors") or [])}
for _s in str(flag("satinize-colors", "") or "").split(","):
    if _s.strip():
        SATINIZE_COLORS.add(_s.strip().lower())
if _sat_cfg.get("enabled") is False:
    SATINIZE_COLORS = set()
SAT_MAX_ROW_MM = float(_sat_cfg.get("max_row_mm", 4.5))
SAT_MAX_ROWS = int(_sat_cfg.get("max_rows", 3))
SAT_MIN_COVERAGE = float(_sat_cfg.get("min_coverage", 0.9))
SAT_MAX_OVERHANG = float(_sat_cfg.get("max_overhang", 0.45))

for _name, _val in [("global", ROW_SPACING_MM)] + list(_DENSITY.items()):
    if not 0.3 <= _val <= 0.6:
        print(f"warning: density {_val} mm ({_name}) is outside the safe 0.3-0.6 mm range "
              f"(too dense breaks needles, too open leaves gaps)")

im = Image.open(IMG).convert("RGBA")
arr = np.array(im)
H, W = arr.shape[:2]
alpha = arr[..., 3]
transparent = alpha < 128
has_transparency = bool(transparent.any())

# px-per-mm based on the design's own bounds (longer side -> SIZE_MM).
# For transparent artwork the design is the union of the alpha silhouette's
# real components, not the canvas: scaling the canvas made a patch floating in
# a large canvas come out undersized (Book Burner: 87 mm instead of 100 mm).
# Tiny noise specks are ignored so they cannot inflate the bounds; the design
# may legitimately consist of several disconnected parts (flames + book).
if has_transparency:
    _lbl, _n = ndimage.label(~transparent)
    if _n:
        _sizes = ndimage.sum(np.ones_like(_lbl), _lbl, index=range(1, _n + 1))
        _cut = max(100, int(0.0001 * W * H))  # ignore noise specks
        _keep = [i + 1 for i, s in enumerate(_sizes) if s >= _cut]
        if _keep:
            _ys, _xs = np.where(np.isin(_lbl, _keep))
            design_w = int(_xs.max() - _xs.min() + 1)
            design_h = int(_ys.max() - _ys.min() + 1)
        else:
            design_w, design_h = W, H
    else:
        design_w, design_h = W, H
else:
    # Opaque flat art: the "paper" is usually the border/corner colour.  Use the
    # bbox of pixels that differ from it so a design drawn with a margin still
    # scales to SIZE_MM (Earth patch: globe inscribed in a white canvas came out
    # at 51 mm instead of 60 mm).
    _pad = 8
    _corners = np.concatenate([
        arr[:_pad, :_pad, :3].reshape(-1, 3), arr[:_pad, -_pad:, :3].reshape(-1, 3),
        arr[-_pad:, :_pad, :3].reshape(-1, 3), arr[-_pad:, -_pad:, :3].reshape(-1, 3)])
    _bg = np.median(_corners, axis=0)
    _fg = np.linalg.norm(arr[..., :3].astype(float) - _bg, axis=-1) > 40
    if _fg.any():
        _ys, _xs = np.where(_fg)
        design_w = int(_xs.max() - _xs.min() + 1)
        design_h = int(_ys.max() - _ys.min() + 1)
    else:
        design_w, design_h = W, H
px_per_mm = max(design_w, design_h) / SIZE_MM
scale = 1.0 / px_per_mm
if px_per_mm < 3.0:
    print(f"warning: source is too coarse to stitch well ({1 / px_per_mm:.2f} mm per source pixel at "
          f"{SIZE_MM:.0f} mm; need >= 3 px/mm). Supply a larger source image.")
Wmm = W * scale
Hmm = H * scale

MIN_COMP_PX = max(1, int(MIN_COMP_MM2 * px_per_mm * px_per_mm))
MIN_HOLE_PX = max(1, int(MIN_HOLE_MM2 * px_per_mm * px_per_mm))
TOLERANCE = TOLERANCE_MM * px_per_mm
BORDER_PX = BORDER_MM * px_per_mm

# ---------------------------------------------------------------------------
# silhouette = pixels that are part of the design (opaque, or whole image)
# ---------------------------------------------------------------------------
if has_transparency:
    silhouette = ~transparent
else:
    silhouette = np.ones((H, W), dtype=bool)

rgb = arr[..., :3]

# detailed painted renditions dither/speckle; denoise before quantizing so the
# posterization yields clean regions instead of thousands of tiny fragments.
if has_transparency:
    disc = morphology.disk(3)
    rgb = np.stack([ndimage.median_filter(rgb[..., i], footprint=disc) for i in range(3)], axis=-1)


def kmeans_palette(pixels, k):
    pix = pixels.astype(float)
    idx = np.random.default_rng(0).choice(len(pix), min(len(pix), 200000), replace=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # empty clusters / 0-division are expected on few-colour images
        cen, _ = kmeans2(pix[idx], k, minit="++", seed=0, iter=30)
    return np.clip(cen.round().astype(int), 0, 255)


def _rgb_str(v):
    return "(" + ",".join(str(int(x)) for x in v) + ")"


def luma(rgb_):
    return 0.2126 * rgb_[0] + 0.7152 * rgb_[1] + 0.0722 * rgb_[2]


# ---------------------------------------------------------------------------
# border detection (transparent-background patches only)
# ---------------------------------------------------------------------------
def _poly_area(pts):
    """Absolute polygon area (shoelace) for a (N, 2) array of (y, x) points."""
    ys, xs = pts[:, 0], pts[:, 1]
    return 0.5 * np.abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))


border_ring = None
border_color = None
border_paths = []          # one "M ... Z" per connected part of the patch
border_pts_list = []       # matching polygons, for centroids + trim tests
border_polys = []

border_off = NO_BORDER or _border_mode == "off"

if has_transparency and not border_off:
    dt = ndimage.distance_transform_edt(silhouette)
    force_black = _border_mode == "force_black"

    # the satin stroke (BORDER_PX wide) must be centred on the ring midline, so
    # trace the silhouette eroded by half the ring width: a stroke centred at
    # dt = BORDER_PX/2 covers exactly dt in 0..BORDER_PX, the carved ring
    half = int(round(BORDER_PX / 2))
    eroded = silhouette & (dt > half) if half > 0 else silhouette
    if not eroded.any():
        eroded = silhouette        # thinner than the border: nothing left to erode

    # Erosion can SPLIT one connected patch into several parts (a patch with a
    # thin arm or neck survives the ring carve but not the midline trace).  Take
    # one border per part: the fills have the whole ring carved out of them, so a
    # part we skipped would be left with an unstitched band around it.
    parts, n_parts = ndimage.label(eroded)
    n_tiny_parts = 0
    n_thin_parts = 0
    for i in range(1, n_parts + 1):
        cnts = measure.find_contours(np.pad(parts == i, 1), 0.5)
        if not cnts:
            continue
        # widest-area contour, not the longest: a wiggly hole can have more
        # boundary points than the patch edge and would otherwise win
        outer = max(cnts, key=_poly_area) - 1
        poly = measure.approximate_polygon(outer, tolerance=TOLERANCE)
        if len(poly) < 3:
            continue
        # A border loop must be long enough for the satin to stitch sensibly.
        # A part only a few mm across survives the erosion but its 4 mm satin
        # would be a solid knot of thread, so it keeps its plain fill instead.
        perim = float(np.hypot(*np.diff(np.vstack([poly, poly[:1]]), axis=0).T).sum())
        if perim < 3.0 * BORDER_PX:
            n_tiny_parts += 1
            continue
        # A thin part traced at border width makes its offset rails cross, and
        # Ink/Stitch then dies building sections ("tuple index out of range" in
        # flattened_sections).  Compare the part's thickness against the border:
        # a part whose inscribed radius is under ~1x the border cannot carry a
        # clean band, so it keeps its plain fill.
        _inscribed = float(ndimage.distance_transform_edt(parts == i).max())
        if _inscribed < 1.0 * BORDER_PX:
            n_thin_parts += 1
            continue
        border_polys.append(poly)

    # the digital border sits just inside the silhouette edge
    ring = silhouette & (dt > 0) & (dt <= max(2, BORDER_PX))
    if force_black:
        border_color = np.array([0, 0, 0])
    elif ring.any():
        border_color = kmeans_palette(rgb[ring], 1)[0]
    else:
        # fallback: no dark ring -> black border
        border_color = np.array([0, 0, 0])

    if border_polys:
        border_color_str = _rgb_str(border_color)
        for poly in border_polys:
            border_paths.append("M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in poly) + " Z")
            border_pts_list.append(poly)
        # Carve out ONLY what the emitted satin actually covers.  A blanket
        # distance ring erases every part thinner than the border width -- the
        # detached ember specks in a flame patch are all under 4 mm -- and a
        # part that vanishes under erosion gets no border path, so those pixels
        # would end up stitched nowhere.  Stroking the same midlines we emit as
        # satin guarantees carve area == covered area.
        stroke_img = Image.new("L", (W, H), 0)
        sdraw = ImageDraw.Draw(stroke_img)
        for poly in border_polys:
            pts_px = [(float(x), float(y)) for y, x in poly]
            sdraw.line(pts_px + pts_px[:1], fill=255,
                       width=max(1, int(round(BORDER_PX))), joint="curve")
        border_ring = (np.array(stroke_img) > 0) & silhouette
        print(f"border: color {border_color_str} width {BORDER_MM} mm "
              f"({len(border_polys)} path{'s' if len(border_polys) > 1 else ''}, "
              f"{sum(len(p) for p in border_polys)} pts"
              + (f", {n_tiny_parts} part(s) too small to border"
                 if n_tiny_parts else "")
              + (f", {n_thin_parts} part(s) too thin for the border width"
                 if n_thin_parts else "") + ")")
    else:
        border_ring = None


# ---------------------------------------------------------------------------
# interior palette (exclude the border ring so it doesn't pollute fills)
# ---------------------------------------------------------------------------
interior_mask = silhouette & (~border_ring if border_ring is not None else silhouette)
if not interior_mask.any():
    # very thin patch: the border ring swallowed the whole silhouette -> keep the
    # interior as fills and drop the ring exclusion, otherwise everything vanishes
    print("warning: border ring covers the whole silhouette; keeping interior as fills")
    border_ring = None
    interior_mask = silhouette
if has_transparency:
    interior_pix = rgb[interior_mask]
else:
    # opaque image: background handled by dropping the lightest cluster below
    interior_pix = rgb[silhouette]

if len(interior_pix) == 0:
    sys.exit("error: no opaque pixels to digitize (image is fully transparent?)")

centroids = kmeans_palette(interior_pix, N_COLORS)

# assign every pixel to its nearest centroid.  Transparent pixels are labelled
# too, but both consumers intersect `silhouette` first, so those labels are
# simply discarded -- there is no need to keep them for any other reason.
flat_all = rgb.reshape(-1, 3).astype(float)
d2 = ((flat_all[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
label_all = np.argmin(d2, axis=1).reshape(H, W)
del d2, flat_all

# k-means returns duplicate and empty clusters when the image has fewer distinct
# colours than --colors, which leaves `order`/`skip_colors` unable to address
# every colour (hex_to_idx can only map a hex to one index).  Collapse duplicate
# centroids, then drop clusters nothing inside the silhouette was assigned to,
# remapping the labels so every index below stays addressable.
_uniq, _inv = np.unique(centroids, axis=0, return_inverse=True)
centroids = _uniq
label_all = _inv[label_all]
_used = np.bincount(label_all[silhouette].ravel(), minlength=len(centroids))
if not _used.all():
    _keep = _used > 0
    _remap = np.full(len(centroids), -1, dtype=np.int32)
    _remap[_keep] = np.arange(int(_keep.sum()), dtype=np.int32)
    label_all = _remap[label_all]
    centroids = centroids[_keep]
if len(centroids) < N_COLORS:
    print(f"note: image has {len(centroids)} distinct colours, fewer than --colors {N_COLORS}")

# merge visually identical clusters (k-means splits near-black pixels into e.g.
# (0,1,1) and (2,2,2)) so the design doesn't stitch two indistinguishable
# threads and waste a colour change
_MERGE_DIST = 20.0
_keep = []
for i in range(len(centroids)):
    for j in _keep:
        if np.linalg.norm(centroids[i].astype(float) - centroids[j].astype(float)) < _MERGE_DIST:
            label_all[label_all == i] = j
            break
    else:
        _keep.append(i)
if len(_keep) < len(centroids):
    _remap = np.full(len(centroids), -1, dtype=np.int32)
    for _new, _old in enumerate(_keep):
        _remap[_old] = _new
    label_all = _remap[label_all]
    centroids = centroids[_keep]

cluster_rgb = centroids

# snap the detected border colour to the nearest palette colour when they are
# visually the same, so the border shares the fill's thread
if border_color is not None:
    _bd = np.linalg.norm(cluster_rgb.astype(float) - np.asarray(border_color, float), axis=1)
    _bj = int(np.argmin(_bd))
    if _bd[_bj] <= 40:
        border_color = cluster_rgb[_bj].astype(float)

# background cluster handling
if not has_transparency:
    lum = cluster_rgb.sum(axis=1)
    bg = int(np.argmax(lum))     # lightest = paper
else:
    bg = None                    # transparent = background (no cluster)

print(f"image {W}x{H} -> {Wmm:.0f}x{Hmm:.0f} mm ({px_per_mm:.1f} px/mm), palette k={len(centroids)}")
if bg is not None:
    print(f"  background (skip) = {_rgb_str(cluster_rgb[bg])}")


def hexkey(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in cluster_rgb[c])


hex_to_idx = {hexkey(c).lower(): c for c in range(len(centroids))}

# default: all non-background colors sorted light->dark (bottom->top)
_default_colors = sorted(
    [c for c in range(len(centroids)) if c != bg],
    key=lambda c: luma(cluster_rgb[c]),
    reverse=True,
)

# apply explicit order: listed colors first (in list order), then unlisted by luma
listed = [c for c in
          (hex_to_idx[h.lower()] for h in _ORDER if h.lower() in hex_to_idx)
          if c != bg]
fill_colors = listed + [c for c in _default_colors if c not in listed]

# skip colors
fill_colors = [c for c in fill_colors if hexkey(c).lower() not in _SKIP]

# outline colour = darkest remaining fill; its thin parts become satin
lw = min(fill_colors, key=lambda c: luma(cluster_rgb[c])) if fill_colors else None

print("order:", [hexkey(c) for c in fill_colors])


def mask_for(c, use_border_exclusion=False):
    m = (label_all == c) & silhouette
    if use_border_exclusion and border_ring is not None:
        m = m & (~border_ring)
    if OPEN_RADIUS:
        m = ndimage.binary_opening(m, structure=morphology.disk(OPEN_RADIUS))
    if CLOSE_RADIUS:
        m = ndimage.binary_closing(m, structure=morphology.disk(CLOSE_RADIUS))
    return m


def contour_paths(mask, min_area=MIN_COMP_PX, min_hole=MIN_HOLE_PX, tolerance=TOLERANCE):
    """Return (path_d_strings, centroids, outer_point_arrays, keep_lab, dropped, polys).

    Components are NOT ordered here; the global emit pass orders them with the
    needle position carried across colour layers.  ``keep_lab`` marks each kept
    component with a 1-based id (parallel to the returned paths) so the emitted
    coverage can be rasterised for the trim test.  ``polys`` is the matching
    shapely geometry per component (px space, holes attached), used by satinize.
    """
    lab, n = ndimage.label(mask)
    paths = []
    cents = []
    pts = []
    polys_out = []
    keep_lab = np.zeros(mask.shape, dtype=np.int32)
    dropped = 0
    for c in range(1, n + 1):
        comp = (lab == c)
        if int(comp.sum()) < min_area:
            dropped += 1
            continue
        padded = np.pad(comp, 1)
        polys = []
        for cnt in measure.find_contours(padded, 0.5):
            if len(cnt) < 4:
                continue
            cnt = cnt - 1
            poly = measure.approximate_polygon(cnt, tolerance=tolerance)
            if len(poly) >= 3:
                polys.append(poly)
        if not polys:
            dropped += 1
            continue
        areas = [float(_poly_area(np.asarray(p))) for p in polys]
        order = sorted(range(len(polys)), key=lambda i: -areas[i])
        keep, seen = [], False
        for i in order:
            if not seen:
                keep.append(polys[i]); seen = True; continue
            if areas[i] >= min_hole:
                keep.append(polys[i])
        sub = ["M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in p) + " Z" for p in keep]
        first = np.asarray(keep[0], dtype=float)
        keep_lab[comp] = len(paths) + 1
        paths.append(" ".join(sub))
        cents.append((float(first[:, 0].mean()), float(first[:, 1].mean())))
        pts.append(np.vstack([np.asarray(k, dtype=float) for k in keep]))
        # shapely geometry in px space, for satinize; contours come back as
        # (y, x), so flip each ring to (x, y)
        rings = [[(float(x), float(y)) for y, x in np.asarray(k, dtype=float)] for k in keep]
        geom = None
        try:
            geom = Polygon(rings[0], rings[1:]).buffer(0)
        except (ValueError, TypeError):
            geom = None
        polys_out.append(geom)
    return paths, cents, pts, keep_lab, dropped, polys_out


# ---------------------------------------------------------------------------
# outlines -> satin: skeletonize the darkest colour, classify each segment by its
# own width, and carve the satin bands out of that colour's fill
# ---------------------------------------------------------------------------
outline_items = []
lw_cover = None
if lw is not None and not NO_SATIN:
    lw_mask = mask_for(lw, use_border_exclusion=has_transparency)
    segs = satin_segments(lw_mask, px_per_mm, SATIN_MIN_LEN_MM,
                          SATIN_MIN_MM, SATIN_MAX_MM, TOLERANCE)
    # A satin shorter than it is wide is not stitchable: its rails are shorter
    # than the zigzag travel, and Ink/Stitch then builds a section with no
    # points and dies with "tuple index out of range" in flattened_sections.
    # Polygonal simplification can shorten a run below the SATIN_MIN_LEN_MM
    # gate, so re-test on the emitted polyline.
    _segs = []
    for d, poly, w in segs:
        _len = float(np.hypot(*np.diff(poly, axis=0).T).sum()) / px_per_mm
        if _len < max(2.5, 1.5 * w / px_per_mm):
            continue
        _segs.append((d, poly, w))
    if len(_segs) != len(segs):
        print(f"note: dropped {len(segs) - len(_segs)} outline satin(s) shorter than "
              f"their own width ({len(segs)} -> {len(_segs)})")
    segs = _segs
    if segs:
        cover_img = Image.new("L", (W, H), 0)
        cover_draw = ImageDraw.Draw(cover_img)
        for d, poly, w in segs:
            outline_items.append(dict(cent=(float(poly[:, 0].mean()), float(poly[:, 1].mean())),
                                      pts=poly, d=d, satin=True, lab_id=None,
                                      rgb=cluster_rgb[lw], spacing=None, width_px=w))
            cover_draw.line([(float(x), float(y)) for y, x in poly], fill=255,
                            width=max(1, int(round(w))), joint="curve")
        # dilate the band a couple of px before carving the fill: otherwise the
        # band-edge mismatch with the simplified skeleton leaves sub-mm slivers
        lw_cover = ndimage.binary_dilation((np.array(cover_img) > 0) & lw_mask,
                                           structure=morphology.disk(2))
        print(f"satin outlines: {len(outline_items)} segments from {_rgb_str(cluster_rgb[lw])}")

# ---------------------------------------------------------------------------
# collect every stitched object, then order it globally (needle-aware)
# ---------------------------------------------------------------------------
print("fills:")
color_items = {}
color_keep_lab = {}
satinized_satins = []      # (cluster, d, pts, width_px)
satinized_polys = []       # px-space shapely geoms removed from their fill
for c in fill_colors:
    mask = mask_for(c, use_border_exclusion=has_transparency)
    if c == lw and lw_cover is not None:
        mask = mask & ~lw_cover
    paths, cents, pts, keep_lab, dropped, geoms = contour_paths(mask)
    hx = hexkey(c).lower()
    angle = FILL_ANGLE if FILL_ANGLE is not None else _ANGLE.get(hx)
    items = []
    n_sat = 0
    for i in range(len(paths)):
        geom = geoms[i] if hx in SATINIZE_COLORS else None
        if geom is not None and not geom.is_empty:
            # satinize works in mm (its own pixel grid is 0.1 mm), so hand it
            # fitted mm geometry and scale the resulting centrelines back to px
            from shapely import affinity
            # origin=(0, 0) is essential: affinity.scale defaults to
            # origin='center', which would scale about each component's own
            # centroid and leave it sitting near its original pixel position
            res = satinize.component_to_satins(
                affinity.scale(geom, scale, scale, origin=(0, 0)),
                max_row_mm=SAT_MAX_ROW_MM, max_rows=SAT_MAX_ROWS,
                min_coverage=SAT_MIN_COVERAGE, max_overhang=SAT_MAX_OVERHANG)
            if res and all(satinize.centreline_ok(r["centreline"], r["width_mm"])
                           for r in res):
                n_sat += 1
                satinized_polys.append(geom)
                for r in res:
                    line = np.asarray(r["centreline"], float) / scale
                    satinized_satins.append(dict(
                        cluster=c, rgb=cluster_rgb[c], lab_id=None, satin=True,
                        cent=(float(line[:, 1].mean()), float(line[:, 0].mean())),
                        pts=np.vstack([line[:, ::-1], line[-1::-1, ::-1]]),
                        d="M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in line),
                        width_px=r["width_mm"] / scale))
                continue        # the satin replaces this fill component
        items.append(dict(cent=cents[i], pts=pts[i], d=paths[i], satin=False,
                          lab_id=i + 1, rgb=cluster_rgb[c],
                          spacing=_DENSITY.get(hx), width_px=None, angle=angle))
    color_items[c] = items
    color_keep_lab[c] = keep_lab
    _sat_note = f", {n_sat} -> satin" if n_sat else ""
    print(f"  {_rgb_str(cluster_rgb[c])}: {len(items)} comps (dropped {dropped}){_sat_note}")

if satinized_satins:
    # each fill component is its own object, so dropping the item removes the
    # fill entirely -- the satin replaces it, with no fill sliver left behind
    _w_min = min(s["width_px"] / px_per_mm for s in satinized_satins)
    print(f"satinize: {len(satinized_satins)} satin column(s) from "
          f"{len(satinized_polys)} component(s), narrowest {_w_min:.2f} mm")


def nn_sort(items, needle):
    """Nearest-neighbour order of items (by centroid) from the current needle."""
    remaining = list(items)
    out = []
    cur = np.asarray(needle, dtype=float)
    while remaining:
        i = min(range(len(remaining)),
                key=lambda k: (remaining[k]["cent"][0] - cur[0]) ** 2 +
                              (remaining[k]["cent"][1] - cur[1]) ** 2)
        nxt = remaining.pop(i)
        out.append(nxt)
        cur = np.asarray(nxt["cent"], dtype=float)
    return out


objs = []
needle = [0.0, 0.0]
layer_no = 0

# stitch_index[y, x] = emit index of the last object covering that pixel (-1 =
# nothing).  A jump after object i is hidden iff every sampled pixel has
# stitch_index > i: something stitched later lies over the thread.
stitch_index = np.full((H, W), -1, dtype=np.int32)

color_satins = {}
for s in satinized_satins:
    color_satins.setdefault(s["cluster"], []).append(s)

for c in fill_colors:
    for o in nn_sort(color_items[c], needle):
        o["group_id"] = "color%d" % layer_no
        o["group_label"] = hexkey(c)
        o["index"] = len(objs)
        stitch_index[color_keep_lab[c] == o["lab_id"]] = o["index"]
        objs.append(o)
        needle = o["cent"]
    # this colour's satinized columns go last inside the same layer, so the
    # satin is stitched on top of the fills around it
    for o in nn_sort(color_satins.get(c, []), needle):
        o["group_id"] = "color%d" % layer_no
        o["group_label"] = hexkey(c)
        o["satin"] = True
        o["index"] = len(objs)
        _si = Image.new("I", (W, H), -1)
        ImageDraw.Draw(_si).line([(float(x), float(y)) for y, x in o["pts"]],
                                 fill=o["index"],
                                 width=max(1, int(round(o["width_px"]))), joint="curve")
        stitch_index = np.maximum(stitch_index, np.array(_si, dtype=np.int32))
        objs.append(o)
        needle = o["cent"]
    layer_no += 1
color_keep_lab.clear()

if outline_items:
    satin_img = Image.new("I", (W, H), -1)
    satin_draw = ImageDraw.Draw(satin_img)
    for o in nn_sort(outline_items, needle):
        o["group_id"] = "outlines"
        o["group_label"] = "Outline"
        o["index"] = len(objs)
        satin_draw.line([(float(x), float(y)) for y, x in o["pts"]], fill=o["index"],
                        width=max(1, int(round(o["width_px"]))), joint="curve")
        objs.append(o)
        needle = o["cent"]
    stitch_index = np.maximum(stitch_index, np.array(satin_img, dtype=np.int32))
    layer_no += 1

for d_path, poly in zip(border_paths, border_pts_list):
    o = dict(group_id="border", group_label="Border",
             cent=(float(poly[:, 0].mean()), float(poly[:, 1].mean())),
             pts=poly, d=d_path, satin=True, rgb=border_color,
             spacing=None, width_px=BORDER_PX)
    o["index"] = len(objs)
    # model the border as its actual stroke (BORDER_PX wide, centred on the
    # ring midline contour, so it covers the carved ring)
    bim = Image.new("I", (W, H), -1)
    ring_pts = [(float(x), float(y)) for y, x in poly]
    ImageDraw.Draw(bim).line(ring_pts + ring_pts[:1], fill=o["index"],
                             width=max(1, int(round(BORDER_PX))), joint="curve")
    stitch_index = np.maximum(stitch_index, np.array(bim, dtype=np.int32))
    objs.append(o)

if not objs:
    sys.exit("error: no stitchable objects produced (single-colour image, or every colour skipped via skip_colors?)")


# ---------------------------------------------------------------------------
# trim: cut a jump that is long OR exposed (not hidden by a later stitch)
# ---------------------------------------------------------------------------
def gap_and_segment(a, b):
    """Travel bounds (mm) between two objects, plus the nearest-boundary segment.

    Returns ``(d_min, d_max, p0, p1)``.

    Ink/Stitch stitches every fill in its own scanline order, so where the needle
    actually leaves object ``i`` and enters object ``i+1`` is not known here.
    ``d_min`` (nearest boundary pair) is a lower bound on the thread travelled and
    ``d_max`` (the larger one-sided Hausdorff distance) is a deliberately
    conservative estimate of it -- not a strict upper bound, since the true
    exit/entry pair can exceed it, but far less optimistic than ``d_min``.  The
    caller uses ``d_min`` to decide whether a jump is too short to bother cutting
    and ``d_max`` to decide whether it may be too long to leave sewn.
    """
    pa, pb = a.get("pts"), b.get("pts")
    if pa is None or pb is None:
        d = float(np.hypot(a["cent"][0] - b["cent"][0], a["cent"][1] - b["cent"][1])) / px_per_mm
        return d, d, np.asarray(a["cent"], float), np.asarray(b["cent"], float)
    d, idx = cKDTree(pa).query(pb)
    j = int(np.argmin(d))
    d_min = float(d[j]) / px_per_mm
    d_max = max(float(d.max()), float(cKDTree(pb).query(pa)[0].max())) / px_per_mm
    return d_min, d_max, pa[idx[j]], pb[j]


def is_hidden(p0, p1, idx):
    """True if the straight jump after object ``idx`` is covered by a later stitch."""
    n = max(8, int(np.hypot(*(p1 - p0)) / px_per_mm * 2))
    for t in np.linspace(0.0, 1.0, n + 2)[1:-1]:
        p = p0 + t * (p1 - p0)
        y, x = int(round(p[0])), int(round(p[1]))
        if not (0 <= y < H and 0 <= x < W) or stitch_index[y, x] <= idx:
            return False
    return True


trim_after = [False] * len(objs)
n_trims = 0
if TRIM:
    for i in range(len(objs) - 1):
        d_min, d_max, p0, p1 = gap_and_segment(objs[i], objs[i + 1])
        if d_min <= TRIM_MIN_MM:
            continue
        if TRIM_THRESHOLD_MM == 0 or d_max > TRIM_THRESHOLD_MM or not is_hidden(p0, p1, i):
            trim_after[i] = True
    n_trims = sum(trim_after)
    print(f"trim: {n_trims} cuts / {len(objs)} objects (threshold {TRIM_THRESHOLD_MM} mm)")


def el(id_, fill_rgb, d, spacing=None, trim_after=False, angle=None):
    hx = "#%02x%02x%02x" % tuple(int(v) for v in fill_rgb)
    rs = spacing if spacing is not None else ROW_SPACING_MM
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    ang = f'inkstitch:angle="{angle:g}" ' if angle is not None else ""
    return (f'<path id="{id_}" style="fill:{hx};stroke:none" fill-rule="evenodd" '
            f'inkstitch:row_spacing_mm="{rs}" {ang}'
            f'inkstitch:fill_underlay_skip_last="true" {trim}d="{d}"/>')


def satin_el(id_, stroke_rgb, d, width_px, trim_after=False):
    w_mm = width_px / px_per_mm
    if w_mm <= SATIN_GATE_MM:      # Ink/Stitch's test is strictly `>`
        # would be emitted as satin_column and then silently stitched as running
        print(f"warning: satin {id_} is {w_mm:.2f} mm wide, below Ink/Stitch's "
              f"{SATIN_GATE_MM:.1f} mm gate -- it will stitch as running stitch")
    hx = "#%02x%02x%02x" % tuple(int(v) for v in stroke_rgb)
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    pull = f'inkstitch:pull_compensation_mm="{SATIN_PULL_MM} {SATIN_PULL_MM}" ' if SATIN_PULL_MM else ""
    return (f'<path id="{id_}" style="fill:none;stroke:{hx};stroke-width:{width_px:.2f}" '
            f'inkstitch:satin_column="true" {pull}{trim}d="{d}"/>')


p = []
p.append(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkstitch="http://inkstitch.org/namespace" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
    'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd" '
    f'width="{Wmm:.2f}mm" height="{Hmm:.2f}mm" viewBox="0 0 {W} {H}" '
    'inkscape:document-units="mm" sodipodi:docname="design.svg">\n'
)
p.append(
    f'  <sodipodi:namedview id="namedview1" pagecolor="#ffffff" units="mm" '
    f'inkscape:document-units="mm" pagewidth="{Wmm:.2f}" pageheight="{Hmm:.2f}" '
    'inkscape:pageopacity="0.0" inkscape:pagecheckerboard="0" showgrid="false"/>\n'
)
idx = 0
current_group = None
for o, tm in zip(objs, trim_after):
    if o["group_id"] != current_group:
        if current_group is not None:
            p.append('  </g>\n')
        p.append(f'  <g inkscape:label="{o["group_label"]}" inkscape:groupmode="layer" '
                 f'id="{o["group_id"]}">\n')
        current_group = o["group_id"]
    if o["satin"]:
        p.append("    " + satin_el(f"s{idx}", o["rgb"], o["d"], o["width_px"], trim_after=tm) + "\n")
    else:
        p.append("    " + el(f"f{idx}", o["rgb"], o["d"], spacing=o["spacing"],
                              trim_after=tm, angle=o.get("angle")) + "\n")
    idx += 1
if current_group is not None:
    p.append('  </g>\n')
p.append('</svg>\n')

with open(OUT, "w", encoding="utf-8") as f:
    f.write("".join(p))

# posterized preview (for review)
preview = np.full((H, W, 3), 255, dtype=np.uint8)
view = label_all[silhouette]
preview[silhouette] = cluster_rgb[view]
if has_transparency:
    alpha8 = np.where(silhouette, 255, 0).astype(np.uint8)
    prev = np.dstack([preview, alpha8])
else:
    prev = preview
Image.fromarray(prev).save(OUT.rsplit(".", 1)[0] + "_posterized.png")

print(f"\nwrote {OUT}")
