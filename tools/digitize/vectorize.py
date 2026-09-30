#!/usr/bin/env python3
"""image -> pre-digitized embroidery SVG (Ink/Stitch).

Handles two image classes:
  * transparent-background patch renditions  -> interior fills + a SATIN border
      (the dark outer ring is treated as the satin-stitch edge)
  * opaque flat art (engraving)              -> fills + darkest cluster as linework

Common behaviours:
  * k-means palette (no fixed colors)
  * holes preserved via even-odd fill
  * embroidery-aware cleanup (density 0.4 mm, drop sub-mm detail)
  * fills ordered by perceptual luma (light -> dark), border topmost
  * within each color, components ordered by nearest-neighbor to minimise travel
  * optional per-image YAML config (--config) for order/skip/density/border/trim

Usage:
  python tools/digitize/vectorize.py [--colors N] [--border-mm W] [--no-border]
                                     [--trim] [--trim-mm N] [--config F]
                                     [input.webp] [output.svg]
"""
import os
import sys

import yaml
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.cluster.vq import kmeans2
from skimage import filters, measure, morphology

_VALUE_FLAGS = {"--colors", "--border-mm", "--trim-mm", "--config"}
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
TRIM = flag("trim", False) is True   # master on/off for trimming (auto-cut)
CONFIG = flag("config", None)
TRIM_MM = flag("trim-mm", None)      # None = unset (fall back to YAML/default)

SIZE_MM = 100.0            # longer side of finished design (mm)
ROW_SPACING_MM = 0.5       # fill line spacing (LIGHT density, avoid fabric ripping)
LINEWORK_ROW_SPACING_MM = 0.6  # linework stand-in fill: even lighter (will be re-traced)
MIN_COMP_MM2 = 0.8         # drop components smaller than this
MIN_HOLE_MM2 = 0.2         # fill in holes smaller than this
OPEN_RADIUS = 1            # morph open (px)
CLOSE_RADIUS = 2           # morph close (px)
TOLERANCE_MM = 0.15        # polygon simplification (mm)

# --- per-image YAML overrides -------------------------------------------------
cfg = load_config(CONFIG)
if (cfg.get("trim") or {}).get("enabled"):
    TRIM = True
_border_cfg = (cfg.get("border") or {})
_border_mode = _border_cfg.get("mode", "auto")
if _border_cfg.get("thickness_mm") is not None:
    BORDER_MM = float(_border_cfg["thickness_mm"])
_extratrim = TRIM_MM if TRIM_MM is not None else (cfg.get("trim") or {}).get("threshold_mm")
TRIM_THRESHOLD_MM = float(_extratrim) if _extratrim is not None else 5.0
if TRIM_THRESHOLD_MM < 0:
    TRIM_THRESHOLD_MM = 0.0
_ORDER = cfg.get("order") or []
_SKIP = {str(s).lower() for s in (cfg.get("skip_colors") or [])}
_DENSITY = {str(k).lower(): v for k, v in (cfg.get("density") or {}).items()}

im = Image.open(IMG).convert("RGBA")
arr = np.array(im)
H, W = arr.shape[:2]
alpha = arr[..., 3]
transparent = alpha < 128
has_transparency = bool(transparent.any())

# px-per-mm based on actual image resolution (longer side -> SIZE_MM)
px_per_mm = max(H, W) / SIZE_MM
scale = 1.0 / px_per_mm
Wmm = W * scale
Hmm = H * scale

MIN_COMP_PX = int(MIN_COMP_MM2 * px_per_mm * px_per_mm)
MIN_HOLE_PX = int(MIN_HOLE_MM2 * px_per_mm * px_per_mm)
TOLERANCE = TOLERANCE_MM * px_per_mm
BORDER_PX = BORDER_MM * px_per_mm

# ---------------------------------------------------------------------------
# silhouette = pixels that are part of the design (opaque, or whole image)
# ---------------------------------------------------------------------------
if has_transparency:
    silhouette = ~transparent
    bg_mask = transparent
else:
    silhouette = np.ones((H, W), dtype=bool)
    bg_mask = None

rgb = arr[..., :3]

# detailed painted renditions dither/speckle; denoise before quantizing so the
# posterization yields clean regions instead of thousands of tiny fragments.
if has_transparency:
    disc = morphology.disk(3)
    rgb = np.stack([ndimage.median_filter(rgb[..., i], footprint=disc) for i in range(3)], axis=-1)


def kmeans_palette(pixels, k):
    pix = pixels.astype(float)
    idx = np.random.default_rng(0).choice(len(pix), min(len(pix), 200000), replace=False)
    cen, _ = kmeans2(pix[idx], k, minit="++", seed=0, iter=30)
    return np.clip(cen.round().astype(int), 0, 255)


def classify(pixels, centroids):
    flat = pixels.reshape(-1, 3).astype(float)
    d2 = ((flat[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
    return np.argmin(d2, axis=1)


def luma(rgb_):
    return 0.2126 * rgb_[0] + 0.7152 * rgb_[1] + 0.0722 * rgb_[2]


# ---------------------------------------------------------------------------
# border detection (transparent-background patches only)
# ---------------------------------------------------------------------------
border_ring = None
border_color = None
border_path_d = None
border_centroid = None

border_off = NO_BORDER or _border_mode == "off"

if has_transparency and not border_off:
    dt = ndimage.distance_transform_edt(silhouette)
    force_black = _border_mode == "force_black"

    padded = np.pad(silhouette, 1)
    contours = measure.find_contours(padded, 0.5)
    outer = (max(contours, key=lambda c: len(c)) - 1) if contours else None

    # the digital border sits just inside the silhouette edge
    ring = silhouette & (dt > 0) & (dt <= max(2, BORDER_PX))
    if force_black:
        border_color = np.array([0, 0, 0])
    elif ring.any():
        border_color = kmeans_palette(rgb[ring], 1)[0]
    else:
        # fallback: no dark ring -> black border
        border_color = np.array([0, 0, 0])
    # exclude the ring band from the interior palette whenever it exists
    border_ring = silhouette & (dt > 0) & (dt <= BORDER_PX) if ring.any() else None

    if outer is not None:
        poly = measure.approximate_polygon(outer, tolerance=TOLERANCE)
        border_path_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in poly) + " Z"
        border_centroid = (float(poly[:, 0].mean()), float(poly[:, 1].mean()))
        print(f"border: color {tuple(border_color)} width {BORDER_MM} mm ({len(poly)} pts)")


# ---------------------------------------------------------------------------
# interior palette (exclude the border ring so it doesn't pollute fills)
# ---------------------------------------------------------------------------
interior_mask = silhouette & (~border_ring if border_ring is not None else silhouette)
if has_transparency:
    interior_pix = rgb[interior_mask]
else:
    # opaque image: background handled by dropping the lightest cluster below
    interior_pix = rgb[silhouette]

centroids = kmeans_palette(interior_pix, N_COLORS)
nz = len(centroids)


def mask_of(i, rgb_im):
    lab = classify(rgb_im, centroids)  # works on full flat; rebuild below
    return None


# assign labels for ALL pixels (including transparent) so fills are complete
flat_all = rgb.reshape(-1, 3).astype(float)
d2 = ((flat_all[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
label_all = np.argmin(d2, axis=1).reshape(H, W)

cluster_rgb = centros = centroids
counts = np.bincount(label_all[silhouette].ravel(), minlength=len(centroids))

# background cluster handling
if not has_transparency:
    lum = cluster_rgb.sum(axis=1)
    bg = int(np.argmax(lum))     # lightest = paper
else:
    bg = None                    # transparent = background (no cluster)

print(f"image {W}x{H} -> {Wmm:.0f}x{Hmm:.0f} mm ({px_per_mm:.1f} px/mm), palette k={len(centroids)}")
if bg is not None:
    print(f"  background (skip) = {tuple(cluster_rgb[bg])}")


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

# linework = darkest remaining fill (opaque/engraving images only)
lw = None
if not has_transparency:
    cands = [c for c in fill_colors]
    if cands:
        lw = min(cands, key=lambda c: luma(cluster_rgb[c]))

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


def _poly_area(pts):
    ys = pts[:, 0]
    xs = pts[:, 1]
    return 0.5 * np.abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))


def contour_paths(mask, min_area=MIN_COMP_PX, min_hole=MIN_HOLE_PX, tolerance=TOLERANCE):
    lab, n = ndimage.label(mask)
    paths = []
    cents = []
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
        first = np.asarray(keep[0])
        cent = (float(first[:, 0].mean()), float(first[:, 1].mean()))
        paths.append(" ".join(sub))
        cents.append(cent)

    # nearest-neighbor TSP (minimise needle travel), start nearest the origin
    if cents:
        pts = cents
        ordr = []
        cur = min(range(len(pts)), key=lambda i: pts[i][0] ** 2 + pts[i][1] ** 2)
        ordr.append(cur)
        used = {cur}
        while len(ordr) < len(pts):
            last = pts[ordr[-1]]
            best, bd = None, None
            for i in range(len(pts)):
                if i in used:
                    continue
                d = (pts[i][0] - last[0]) ** 2 + (pts[i][1] - last[1]) ** 2
                if bd is None or d < bd:
                    best, bd = i, d
            ordr.append(best)
            used.add(best)
        paths = [paths[i] for i in ordr]
        cents = [cents[i] for i in ordr]
    return paths, cents, dropped


print("fills:")
groups = {}
cent = {}
for c in fill_colors:
    paths, cents, dropped = contour_paths(mask_for(c, use_border_exclusion=has_transparency))
    groups[c] = paths
    cent[c] = cents
    print(f"  {tuple(cluster_rgb[c])}: {len(paths)} comps (dropped {dropped})")

linework = []
lw_cents = []
if not has_transparency and lw is not None:
    linework, lw_cents, _ = contour_paths(mask_for(lw))
    cent[lw] = lw_cents
    print(f"  linework {tuple(cluster_rgb[lw])}: {len(linework)} comps")


# ---------------------------------------------------------------------------
# build global stitch order (fills light->dark, linework, border topmost)
# ---------------------------------------------------------------------------
def _cent(i, cents_list):
    if isinstance(cents_list, list) and i < len(cents_list):
        return cents_list[i]
    return (H / 2, W / 2)


objs = []  # ordered list of dicts: group, cent, satin, rgb, d, spacing, width_px
for c in fill_colors:
    if lw is not None and c == lw:
        continue
    sd = _DENSITY.get(hexkey(c))
    for i, d in enumerate(groups[c]):
        objs.append(dict(group="fills", cent=_cent(i, cent.get(c, [])), satin=False,
                         rgb=cluster_rgb[c], d=d, spacing=sd, width_px=None))
if linework:
    for i, d in enumerate(linework):
        objs.append(dict(group="linework", cent=_cent(i, lw_cents), satin=False,
                         rgb=cluster_rgb[lw], d=d, spacing=LINEWORK_ROW_SPACING_MM, width_px=None))
if border_path_d is not None:
    objs.append(dict(group="border", cent=border_centroid or (H / 2, W / 2), satin=True,
                     rgb=border_color, d=border_path_d, spacing=None, width_px=BORDER_PX))


def dist_mm(a, b):
    return float(np.hypot(a[0] - b[0], a[1] - b[1])) / px_per_mm


# threshold-based trim: cut only when the jump between consecutive targets is long
trim_after = [False] * len(objs)
if TRIM:
    for i in range(1, len(objs)):
        if TRIM_THRESHOLD_MM == 0 or dist_mm(objs[i - 1]["cent"], objs[i]["cent"]) > TRIM_THRESHOLD_MM:
            trim_after[i - 1] = True


def el(id_, fill_rgb, d, spacing=None, trim_after=False):
    hx = "#%02x%02x%02x" % tuple(int(v) for v in fill_rgb)
    rs = spacing if spacing is not None else ROW_SPACING_MM
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    return (f'<path id="{id_}" style="fill:{hx};stroke:none" fill-rule="evenodd" '
            f'inkstitch:row_spacing_mm="{rs}" '
            f'inkstitch:fill_underlay_skip_last="true" {trim}d="{d}"/>')


def satin_el(id_, stroke_rgb, d, width_px, trim_after=False):
    hx = "#%02x%02x%02x" % tuple(int(v) for v in stroke_rgb)
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    return (f'<path id="{id_}" style="fill:none;stroke:{hx};stroke-width:{width_px:.2f}" '
            f'inkstitch:satin_column="true" {trim}d="{d}"/>')


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
    if o["group"] != current_group:
        if current_group is not None:
            p.append('  </g>\n')
        p.append(f'  <g inkscape:label="{o["group"]}" inkscape:groupmode="layer" id="{o["group"]}">\n')
        current_group = o["group"]
    if o["satin"]:
        p.append("    " + satin_el(f"b{idx}", o["rgb"], o["d"], o["width_px"], trim_after=tm) + "\n")
    else:
        p.append("    " + el(f"f{idx}", o["rgb"], o["d"], spacing=o["spacing"], trim_after=tm) + "\n")
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
