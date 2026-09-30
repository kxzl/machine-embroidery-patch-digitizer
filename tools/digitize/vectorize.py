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
  * the needle position is carried across colour layers and components
    (nearest-neighbour) so travel is minimised globally, not per colour
  * a jump is trimmed when it is long OR exposed (not covered by a later stitch)
  * optional per-image YAML config (--config) for order/skip/density/border/trim

Usage:
  python tools/digitize/vectorize.py [--colors N] [--border-mm W] [--no-border]
                                     [--density MM] [--no-satin-outlines]
                                     [--satin-max-mm W]
                                     [--no-trim] [--trim-mm N] [--config F]
                                     [input.webp] [output.svg]
"""
import os
import sys

import yaml
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.cluster.vq import kmeans2
from scipy.spatial import cKDTree
from skimage import measure, morphology

from skeleton import satin_segments

_VALUE_FLAGS = {"--colors", "--border-mm", "--trim-mm", "--config", "--density", "--satin-max-mm"}
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

SIZE_MM = 100.0            # longer side of finished design (mm)
ROW_SPACING_MM = 0.4       # fill density: 0.35-0.45 standard; <0.3 breaks needles, >0.6 leaves gaps
SATIN_MIN_MM = 0.6         # narrower satin than this is widened to it
SATIN_MAX_MM = 2.5         # thicker than this is kept as a fill, not an outline
SATIN_MIN_LEN_MM = 1.0     # drop satin segments shorter than this
MIN_COMP_MM2 = 0.8         # drop components smaller than this
MIN_HOLE_MM2 = 0.2         # fill in holes smaller than this
OPEN_RADIUS = 1            # morph open (px)
CLOSE_RADIUS = 2           # morph close (px)
TOLERANCE_MM = 0.15        # polygon simplification (mm)
TRIM_MIN_MM = 1.0          # never bother cutting jumps shorter than this

# --- per-image YAML overrides -------------------------------------------------
cfg = load_config(CONFIG)
if flag("trim", False) is True:
    TRIM = True
_trim_cfg = cfg.get("trim") or {}
if "enabled" in _trim_cfg:
    TRIM = bool(_trim_cfg["enabled"])
if cfg.get("satin_outlines") is False:
    NO_SATIN = True
_border_cfg = (cfg.get("border") or {})
_border_mode = _border_cfg.get("mode", "auto")
if _border_cfg.get("thickness_mm") is not None:
    BORDER_MM = float(_border_cfg["thickness_mm"])
if SATIN_MAX_ARG is not None:
    SATIN_MAX_MM = float(SATIN_MAX_ARG)
_extratrim = TRIM_MM if TRIM_MM is not None else (cfg.get("trim") or {}).get("threshold_mm")
TRIM_THRESHOLD_MM = float(_extratrim) if _extratrim is not None else 5.0
if TRIM_THRESHOLD_MM < 0:
    TRIM_THRESHOLD_MM = 0.0
_ORDER = cfg.get("order") or []
_SKIP = {str(s).lower() for s in (cfg.get("skip_colors") or [])}
_dens = cfg.get("density") or {}
if isinstance(_dens, dict):
    _DENSITY = {str(k).lower(): v for k, v in _dens.items()}
elif isinstance(_dens, (int, float)):
    ROW_SPACING_MM = float(_dens)
    _DENSITY = {}
else:
    _DENSITY = {}
if DENSITY_MM is not None:
    ROW_SPACING_MM = float(DENSITY_MM)

if not 0.3 <= ROW_SPACING_MM <= 0.6:
    print(f"warning: density {ROW_SPACING_MM} mm is outside the safe 0.3-0.6 mm range "
          f"(too dense breaks needles, too open leaves gaps)")

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
    cen, _ = kmeans2(pix[idx], k, minit="++", seed=0, iter=30)
    return np.clip(cen.round().astype(int), 0, 255)


def luma(rgb_):
    return 0.2126 * rgb_[0] + 0.7152 * rgb_[1] + 0.0722 * rgb_[2]


# ---------------------------------------------------------------------------
# border detection (transparent-background patches only)
# ---------------------------------------------------------------------------
border_ring = None
border_color = None
border_path_d = None
border_pts = None

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
        border_pts = poly
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
cluster_rgb = centroids

# assign labels for ALL pixels (including transparent) so fills are complete
flat_all = rgb.reshape(-1, 3).astype(float)
d2 = ((flat_all[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
label_all = np.argmin(d2, axis=1).reshape(H, W)

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


def _poly_area(pts):
    ys = pts[:, 0]
    xs = pts[:, 1]
    return 0.5 * np.abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))


def contour_paths(mask, min_area=MIN_COMP_PX, min_hole=MIN_HOLE_PX, tolerance=TOLERANCE):
    """Return (path_d_strings, centroids, outer_point_arrays, dropped).

    Components are NOT ordered here; the global emit pass orders them with the
    needle position carried across colour layers.
    """
    lab, n = ndimage.label(mask)
    paths = []
    cents = []
    pts = []
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
        first = np.asarray(keep[0], dtype=float)
        paths.append(" ".join(sub))
        cents.append((float(first[:, 0].mean()), float(first[:, 1].mean())))
        pts.append(first)
    return paths, cents, pts, dropped


# ---------------------------------------------------------------------------
# outlines -> satin: skeletonize the thin part of the darkest colour
# ---------------------------------------------------------------------------
lw_thin = None
if lw is not None and not NO_SATIN:
    lw_mask = mask_for(lw, use_border_exclusion=has_transparency)
    r = max(1, int(round(SATIN_MAX_MM * px_per_mm / 2)))
    thick = ndimage.binary_opening(lw_mask, structure=morphology.disk(r))
    lw_thin = lw_mask & ~thick
    if not lw_thin.any():
        lw_thin = None

# ---------------------------------------------------------------------------
# collect every stitched object, then order it globally (needle-aware)
# ---------------------------------------------------------------------------
print("fills:")
color_items = {}
for c in fill_colors:
    mask = mask_for(c, use_border_exclusion=has_transparency)
    if c == lw and lw_thin is not None:
        mask = mask & ~lw_thin
    paths, cents, pts, dropped = contour_paths(mask)
    items = [dict(cent=cents[i], pts=pts[i], d=paths[i], satin=False,
                  rgb=cluster_rgb[c], spacing=_DENSITY.get(hexkey(c)), width_px=None)
             for i in range(len(paths))]
    color_items[c] = items
    print(f"  {tuple(cluster_rgb[c])}: {len(paths)} comps (dropped {dropped})")

outline_items = []
if lw_thin is not None:
    for d, poly, w in satin_segments(lw_thin, px_per_mm, SATIN_MIN_LEN_MM,
                                     SATIN_MIN_MM, SATIN_MAX_MM, TOLERANCE):
        outline_items.append(dict(cent=(float(poly[:, 0].mean()), float(poly[:, 1].mean())),
                                  pts=poly, d=d, satin=True, rgb=cluster_rgb[lw],
                                  spacing=None, width_px=w))
    print(f"  satin outlines: {len(outline_items)} segments from {tuple(cluster_rgb[lw])}")


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
color_layer = {}
needle = [0.0, 0.0]
layer_no = 0
for c in fill_colors:
    for o in nn_sort(color_items[c], needle):
        o["group_id"] = "color%d" % layer_no
        o["group_label"] = hexkey(c)
        o["layer"] = layer_no
        objs.append(o)
        needle = o["cent"]
    color_layer[c] = layer_no
    layer_no += 1

if outline_items:
    for o in nn_sort(outline_items, needle):
        o["group_id"] = "outlines"
        o["group_label"] = "Outline"
        o["layer"] = layer_no
        objs.append(o)
        needle = o["cent"]
    layer_no += 1

if border_path_d is not None:
    objs.append(dict(group_id="border", group_label="Border", layer=layer_no,
                     cent=(float(border_pts[:, 0].mean()), float(border_pts[:, 1].mean())) if border_pts is not None else (H / 2, W / 2),
                     pts=border_pts, d=border_path_d, satin=True, rgb=border_color,
                     spacing=None, width_px=BORDER_PX))


# ---------------------------------------------------------------------------
# trim: cut a jump that is long OR exposed (not hidden by a later stitch)
# ---------------------------------------------------------------------------
def gap_and_segment(a, b):
    """Nearest-pair distance (mm) between two objects, plus the connecting segment."""
    pa, pb = a.get("pts"), b.get("pts")
    if pa is None or pb is None:
        d = float(np.hypot(a["cent"][0] - b["cent"][0], a["cent"][1] - b["cent"][1])) / px_per_mm
        return d, np.asarray(a["cent"], float), np.asarray(b["cent"], float)
    d, idx = cKDTree(pa).query(pb)
    j = int(np.argmin(d))
    return float(d[j]) / px_per_mm, pa[idx[j]], pb[j]


def is_hidden(p0, p1, next_layer):
    """True if the straight jump is covered by something stitched at/after next_layer."""
    n = max(8, int(np.hypot(*(p1 - p0)) / px_per_mm * 2))
    for t in np.linspace(0.0, 1.0, n + 2)[1:-1]:
        p = p0 + t * (p1 - p0)
        y, x = int(round(p[0])), int(round(p[1]))
        if not (0 <= y < H and 0 <= x < W) or not silhouette[y, x]:
            return False
        if border_ring is not None and border_ring[y, x]:
            continue
        if lw_thin is not None and lw_thin[y, x]:
            continue
        if color_layer.get(int(label_all[y, x]), -1) < next_layer:
            return False
    return True


trim_after = [False] * len(objs)
n_trims = 0
if TRIM:
    for i in range(len(objs) - 1):
        if TRIM_THRESHOLD_MM == 0:
            trim_after[i] = True
            continue
        d, p0, p1 = gap_and_segment(objs[i], objs[i + 1])
        if d <= TRIM_MIN_MM:
            continue
        if d > TRIM_THRESHOLD_MM or not is_hidden(p0, p1, objs[i + 1]["layer"]):
            trim_after[i] = True
    n_trims = sum(trim_after)
    print(f"trim: {n_trims} cuts / {len(objs)} objects (threshold {TRIM_THRESHOLD_MM} mm)")


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
    if o["group_id"] != current_group:
        if current_group is not None:
            p.append('  </g>\n')
        p.append(f'  <g inkscape:label="{o["group_label"]}" inkscape:groupmode="layer" '
                 f'id="{o["group_id"]}">\n')
        current_group = o["group_id"]
    if o["satin"]:
        p.append("    " + satin_el(f"s{idx}", o["rgb"], o["d"], o["width_px"], trim_after=tm) + "\n")
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
