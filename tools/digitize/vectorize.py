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
                                     [--palette HEX[,HEX]] [--palette-mode auto|kmeans]
                                     [--size-mm N] [--fit-mm WxH]
                                     [--trim] [--no-trim] [--trim-mm N] [--config F]
                                     [input.webp] [output.svg]
"""
import math
import os
import re
import sys
import warnings
from dataclasses import dataclass, field

import yaml
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.cluster.vq import kmeans2
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from skimage import color, measure, morphology

import gradient as gradfit
import satinize
from skeleton import satin_segments, trace_skeleton

_VALUE_FLAGS = {"--colors", "--border-mm", "--trim-mm", "--config", "--density",
                "--satin-max-mm", "--size-mm", "--fill-angle", "--satinize-colors",
                "--palette", "--palette-mode", "--underlap-mm", "--raster-pull-mm",
                "--profile", "--fit-mm", "--satin-taper"}

# module-level defaults (docs reference these names); build_settings resolves the
# per-run values into a Settings instance.
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
SMALL_FILL_MM2 = 2.5       # ADR 0003, as in svg_digitize.py: fills smaller than this get no
                           # underlay and no ties (each tiny element otherwise packs
                           # underlay + lock stitches into a few mm2)
SMALL_FILL_MIC_MM = 1.0    # ... same for any component thinner than this even if it is long
CIRCLE_GAP_MM = 1.0        # border.mode circle with gaps: the ring stops this far from a
                           # shape that crosses it (the art's keyline width)
CROSS_REACH_DEG = 15.0     # border.mode circle: a crossing shape may enter the ring band
                           # this many degrees away from where it leaves the circle

# A solid shape (a star, a pommel) has no skeleton stroke: its skeleton is a
# handful of short spokes, so satin along it stitches an asterisk instead of the
# shape.  Such a component is stitched as a rail satin instead, but only when
# asked for (``--rail-satin``), because rails cost a denser stitch than skeleton
# bands.  BLOB_WIDTH_RATIO is the test: the widest band the component's own
# skeleton carries, as a fraction of the component's thickest point.  A stroke
# sits at 0.8-1.0 (its skeleton is as wide as the shape), a star at 0.45.
BLOB_WIDTH_RATIO = 0.55
RAIL_MIN_GAP_MM = 0.25     # rails may come this close before the row packs thread
RAIL_MAX_OVERHANG = 0.2     # a rail row may leave at most this much of its band
                            # outside the shape, or the shape is left a fill
RAIL_ZIGZAG_MM = 0.35       # zigzag on a rail satin row (same as the authored border satin)

# Named fabric profiles (review.md section 2.5): reviewed starting values for one
# fabric type.  YAML ``profile:`` / ``--profile`` selects one; an explicit CLI
# flag or YAML key always wins over the profile, which wins over the built-in
# default.  Only values that differ from the defaults need to be listed.
PROFILES = {
    "vadmel": {
        "density": 0.35,              # black felted wool: tighter rows to close the pile
        "underlap_mm": 0.6,
        "raster_pull_mm": 0.25,
        "fill_underlay_skip_last": False,   # full second underlay pass, no skipped rows
        "fill_underlay_double_light": True,  # perpendicular second underlay for light thread
        "satin_underlay": True,              # centre-walk + contour on border/outline satins
        "border_zigzag_spacing_mm": 0.35,
        "fabric_color": "#101010",           # preview canvas for run.sh
    },
}
# profile values with no matching user-facing key (tunable in code only)
PROFILE_CONSTANTS = {
    "fill_underlay_light_l": 70.0,   # double-underlay fills whose Lab L* exceeds this
    "satin_underlay_inset_mm": 0.4,  # contour underlay inset (mm)
}


@dataclass
class Settings:
    """Every constant and YAML/CLI-resolved value for one run."""
    n_colors: int = 5
    colors_given: bool = False
    size_mm: float = 100.0     # longer side of finished design (mm)
    size_given: bool = False   # --size-mm was passed (else size_mm is just the default)
    fit_mm: tuple | None = None  # (W, H) Fit box in mm from --fit-mm, or None
    no_border: bool = False
    border_mm: float = 2.5
    border_mode: str = "auto"
    trim: bool = True          # cut long/exposed jumps (default on, machine-ready)
    trim_threshold_mm: float = 4.0
    row_spacing_mm: float = ROW_SPACING_MM
    no_satin: bool = False
    satin_extend: bool = True    # outline ends tuck under the line they meet
    fill_angle: float | None = None
    angle_map: dict = field(default_factory=dict)
    density_map: dict = field(default_factory=dict)
    satinize_colors: set = field(default_factory=set)
    sat_max_row_mm: float = 4.5
    sat_max_rows: int = 3
    sat_min_coverage: float = 0.9
    sat_max_overhang: float = 0.45
    order: list = field(default_factory=list)
    skip: set = field(default_factory=set)
    palette: list = field(default_factory=list)   # pinned thread hexes, [] = auto
    palette_mode: str = "auto"    # "auto" = S3 Lab palette, "kmeans" = legacy RGB
    profile: str = ""             # named fabric profile, "" = none
    underlap_mm: float = 0.6      # grow each fill under later layers (0 disables)
    raster_pull_mm: float = 0.0   # stretch each fill along its row angle (0 disables)
    fill_underlay_skip_last: bool = True
    fill_underlay_double_light: bool = False
    fill_underlay_light_l: float = 70.0
    satin_underlay: bool = False
    satin_underlay_inset_mm: float = 0.4
    border_zigzag_spacing_mm: float | None = None
    fabric_color: str = ""
    gradients: list = field(default_factory=list)   # [{name, stops, min_area_mm2, min_r2, row_spacing_mm}]
    thin_lines: str = "widen"     # outline runs under the satin gate: "widen" to satin, or "run" = bean stitch
    satin_taper_mm: float = 0.0   # >0: split each satin run into pieces this long, each
                                  # with the width its own stretch of line measures
    rail_satin: bool = False      # solid outline blobs and the parts no skeleton satin reached
                                  # become rail satin rows instead of fills
    rail_satin_leftover: bool = True   # ... including the parts no skeleton satin reached
    outline_order: str = "centroid"   # outline stitch order: by "centroid" (default) or by path "endpoint"
    outline_zigzag_spacing_mm: float | None = None   # satin zigzag spacing on outline satins (None = Ink/Stitch 0.4)
    cleanup_min_width_mm: float = 0.0   # >0: parts of any colour thinner than this join the nearest colour
    cleanup_min_area_mm2: float = 0.0   # >0: islands smaller than this join the nearest colour
    cleanup_fabric_min_width_mm: float | None = None   # the same for skipped colours (fabric
    cleanup_fabric_min_area_mm2: float | None = None   # showing through); None = as above
    thread_map: dict = field(default_factory=dict)   # source hex -> thread hex written to the SVG
    border_color: str = ""        # border colour as a source hex ("" = mode default)
    border_order: str = "last"    # circle border: "last" (on top) or "first" (art sewn over it)
    border_gaps: bool = True      # circle border sewn last: leave a gap where the art crosses it
    border_underlay: bool = False  # centre-walk + contour underlay on the border satin
    # algorithm constants (module-level defaults, overridable per class later)
    satin_min_mm: float = SATIN_MIN_MM
    satin_gate_mm: float = SATIN_GATE_MM
    satin_max_mm: float = SATIN_MAX_MM
    satin_min_len_mm: float = SATIN_MIN_LEN_MM
    satin_pull_mm: float = SATIN_PULL_MM
    min_comp_mm2: float = MIN_COMP_MM2
    min_hole_mm2: float = MIN_HOLE_MM2
    open_radius: int = OPEN_RADIUS
    close_radius: int = CLOSE_RADIUS
    tolerance_mm: float = TOLERANCE_MM
    trim_min_mm: float = TRIM_MIN_MM


@dataclass
class ImageData:
    H: int
    W: int
    arr: np.ndarray
    transparent: np.ndarray
    has_transparency: bool
    silhouette: np.ndarray
    rgb: np.ndarray


@dataclass
class Scale:
    design_w: int
    design_h: int
    px_per_mm: float
    scale: float
    Wmm: float
    Hmm: float
    min_comp_px: int
    min_hole_px: int
    tolerance: float
    border_px: float


@dataclass
class Border:
    off: bool = False
    ring: object = None        # bool mask of the carved ring, or None
    color: object = None       # np.array RGB, or None
    force_black: bool = False  # border.mode=force_black: snap to the darkest thread (see build_palette)
    paths: list = field(default_factory=list)      # one "M ... Z" per satin part
    pts_list: list = field(default_factory=list)   # matching polygons (centroids + trim)
    polys: list = field(default_factory=list)
    widths: list = field(default_factory=list)     # px satin width per path (narrow parts differ)
    closed: list = field(default_factory=list)     # True when a path is a closed ring (normal border)
    outline_paths: list = field(default_factory=list)   # running-stitch outlines for tiny/thin parts
    outline_pts: list = field(default_factory=list)
    circle: tuple | None = None   # border.mode circle: fitted (cy, cx, R) in px, ring paths
                                  # built later by circle_ring once the labels are known
    first: bool = False           # sew the border before the fills (art crosses over it)


@dataclass
class Palette:
    centroids: np.ndarray      # cluster_rgb
    label_all: np.ndarray
    bg: object                 # background cluster index, or None
    hex_to_idx: dict


def parse_args(argv):
    """Split ``argv`` into ``(flags, positional)`` (flags keyed without ``--``)."""
    flags = {}
    args = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if "=" in a:
                name, val = a[2:].split("=", 1)
                flags[name] = val
            elif a in _VALUE_FLAGS and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                flags[a[2:]] = argv[i + 1]
                i += 1
            else:
                flags[a[2:]] = True
        elif a.startswith("-") and a != "-":
            pass  # ignore short flags
        else:
            args.append(a)
        i += 1
    return flags, args


def load_config(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_palette(value):
    """Normalise a palette given as a comma/semicolon string or a YAML list of hexes.

    Returns lowercase ``#rrggbb`` strings.  Invalid entries are reported and
    skipped; an empty result keeps the automatic palette.
    """
    if value is None:
        return []
    if isinstance(value, str):
        items = value.replace(";", ",").split(",")
    else:
        items = value
    out = []
    for it in items:
        s = str(it).strip().strip("'\"")
        if not s:
            continue
        if not s.startswith("#"):
            s = "#" + s
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", s):
            print(f"warning: ignoring invalid palette entry {it!r} (need #rrggbb)")
            continue
        out.append(s.lower())
    return out


def parse_fit_mm(value):
    """Parse ``--fit-mm WxH`` (``x`` or ``X``) into ``(W, H)`` mm; exit 2 if invalid."""
    m = None
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(\d+(?:\.\d*)?|\.\d+)\s*[xX]\s*(\d+(?:\.\d*)?|\.\d+)\s*", value)
    if m:
        w, h = float(m.group(1)), float(m.group(2))
        if w > 0 and h > 0:
            return w, h
    sys.stderr.write(f"error: --fit-mm needs two positive numbers as WIDTHxHEIGHT in mm "
                     f"(for example --fit-mm 120x120), got {value!r}\n")
    sys.exit(2)


def build_settings(flags, cfg):
    """Resolve CLI flags and YAML config into a Settings instance.

    Precedence for every value: CLI flag > explicit YAML key > named profile >
    built-in default.  ``--profile`` / YAML ``profile:`` selects a fabric profile
    from ``PROFILES`` (currently ``vadmel``); see review.md section 2.5.
    """
    def flag(name, default):
        return flags.get(name, default)

    # --- fabric profile (lowest precedence, overridden key by key below) ------
    _prof_arg = flag("profile", None)
    profile = str(_prof_arg if _prof_arg is not None else cfg.get("profile") or "").strip().lower()
    if profile and profile not in PROFILES:
        print(f"warning: unknown profile {profile!r}; ignoring (known: {', '.join(PROFILES)})")
        profile = ""
    prof = PROFILES.get(profile, {})

    def profile_value(key, default):
        """Profile value if the profile sets it, else the built-in default."""
        return prof.get(key, default)

    n_colors = int(flag("colors", "5"))
    colors_given = flag("colors", None) is not None
    no_border = flag("no-border", False) is True
    border_mm = float(flag("border-mm", "2.5"))
    no_trim = flag("no-trim", False) is True
    trim = not no_trim
    trim_mm = flag("trim-mm", None)      # None = unset (fall back to YAML/default)
    density_mm = flag("density", None)   # None = unset (fall back to YAML/default)
    no_satin = flag("no-satin-outlines", False) is True
    satin_extend = flag("no-satin-extend", False) is not True
    satin_max_arg = flag("satin-max-mm", None)
    size_mm = float(flag("size-mm", "100"))
    size_given = flag("size-mm", None) is not None
    fit_arg = flag("fit-mm", None)
    fit_mm = None if fit_arg is None else parse_fit_mm(fit_arg)
    row_spacing_mm = float(profile_value("density", ROW_SPACING_MM))
    satin_max_mm = SATIN_MAX_MM

    # --- mask compensation (underlap default on; raster pull profile-only) ----
    _ul_arg = flag("underlap-mm", None)
    if _ul_arg is not None:
        underlap_mm = float(_ul_arg)
    elif cfg.get("underlap_mm") is not None:
        underlap_mm = float(cfg["underlap_mm"])
    else:
        underlap_mm = float(profile_value("underlap_mm", 0.6))
    _rp_arg = flag("raster-pull-mm", None)
    if _rp_arg is not None:
        raster_pull_mm = float(_rp_arg)
    elif cfg.get("raster_pull_mm") is not None:
        raster_pull_mm = float(cfg["raster_pull_mm"])
    else:
        raster_pull_mm = float(profile_value("raster_pull_mm", 0.0))

    # --- underlay options (profile turns the vadmel ones on) ------------------
    if flag("no-skip-last", False) is True:
        skip_last = False
    elif cfg.get("fill_underlay_skip_last") is not None:
        skip_last = bool(cfg["fill_underlay_skip_last"])
    elif cfg.get("no_skip_last") is not None:
        skip_last = not bool(cfg["no_skip_last"])
    else:
        skip_last = bool(profile_value("fill_underlay_skip_last", True))
    if cfg.get("fill_underlay_double") is not None:
        double_light = bool(cfg["fill_underlay_double"])
    else:
        double_light = bool(profile_value("fill_underlay_double_light", False))
    if cfg.get("satin_underlay") is not None:
        satin_underlay = bool(cfg["satin_underlay"])
    else:
        satin_underlay = bool(profile_value("satin_underlay", False))
    _bz_cfg = cfg.get("border_zigzag_spacing_mm")
    border_zigzag = float(_bz_cfg) if _bz_cfg is not None else prof.get("border_zigzag_spacing_mm")
    fabric_color = str(cfg.get("fabric_color") or profile_value("fabric_color", ""))
    fill_underlay_light_l = float(profile_value("fill_underlay_light_l",
                                                PROFILE_CONSTANTS["fill_underlay_light_l"]))
    satin_underlay_inset_mm = float(profile_value("satin_underlay_inset_mm",
                                                  PROFILE_CONSTANTS["satin_underlay_inset_mm"]))

    # --- per-image YAML overrides (CLI always wins) ---------------------------
    if flag("trim", False) is True:
        trim = True
    _trim_cfg = cfg.get("trim") or {}
    if "enabled" in _trim_cfg and flag("trim", False) is not True and not no_trim:
        trim = bool(_trim_cfg["enabled"])
    if cfg.get("satin_outlines") is False and not flag("no-satin-outlines", False):
        no_satin = True
    _border_cfg = (cfg.get("border") or {})
    _border_mode = _border_cfg.get("mode", "auto")
    if _border_cfg.get("thickness_mm") is not None and flag("border-mm", None) is None:
        border_mm = float(_border_cfg["thickness_mm"])
    if satin_max_arg is not None:
        satin_max_mm = float(satin_max_arg)
    _extratrim = trim_mm if trim_mm is not None else (cfg.get("trim") or {}).get("threshold_mm")
    trim_threshold_mm = float(_extratrim) if _extratrim is not None else 4.0
    if trim_threshold_mm < 0:
        trim_threshold_mm = 0.0
    order = cfg.get("order") or []
    skip = {str(s).lower() for s in (cfg.get("skip_colors") or [])}
    # pinned palette: CLI --palette wins over YAML palette:, which wins over auto.
    _pal_arg = flag("palette", None)
    palette = _parse_palette(_pal_arg if _pal_arg is not None else cfg.get("palette"))
    _mode_arg = flag("palette-mode", None)
    palette_mode = str(_mode_arg if _mode_arg is not None else cfg.get("palette_mode", "auto")).lower()
    if palette_mode not in ("auto", "kmeans"):
        print(f"warning: unknown palette_mode {palette_mode!r}; using 'auto'")
        palette_mode = "auto"
    _dens = cfg.get("density") or {}
    if isinstance(_dens, (int, float)):
        row_spacing_mm = float(_dens)
        _density = {}
    elif isinstance(_dens, dict):
        _density = {}
        for _k, _v in _dens.items():
            try:
                _density[str(_k).lower()] = float(_v)
            except (TypeError, ValueError):
                print(f"warning: ignoring non-numeric density {_v!r} for {_k}")
    elif _dens:
        print(f"warning: ignoring non-numeric density {_dens!r}")
        _density = {}
    else:
        _density = {}
    if density_mm is not None:
        row_spacing_mm = float(density_mm)

    # --- fill angle: one value for every fill, or a per-colour YAML map -------
    fill_angle = flag("fill-angle", None)
    try:
        fill_angle = None if fill_angle is None else float(fill_angle)
    except (TypeError, ValueError):
        print(f"warning: ignoring non-numeric --fill-angle {fill_angle!r}")
        fill_angle = None
    _angle = {}
    for _k, _v in (cfg.get("angle") or {}).items():
        try:
            _angle[str(_k).lower()] = float(_v)
        except (TypeError, ValueError):
            print(f"warning: ignoring non-numeric angle {_v!r} for {_k}")

    # --- satinize: thin/elongated fills of the listed colours -> satin columns -
    _sat_cfg = cfg.get("satinize") or {}
    if isinstance(_sat_cfg, list):
        _sat_cfg = {"colors": _sat_cfg}
    elif not isinstance(_sat_cfg, dict):
        print(f"warning: ignoring non-mapping satinize {_sat_cfg!r}")
        _sat_cfg = {}
    satinize_colors = {str(c).lower() for c in (_sat_cfg.get("colors") or [])}
    for _s in str(flag("satinize-colors", "") or "").split(","):
        if _s.strip():
            satinize_colors.add(_s.strip().lower())
    if _sat_cfg.get("enabled") is False:
        satinize_colors = set()
    sat_max_row_mm = float(_sat_cfg.get("max_row_mm", 4.5))
    sat_max_rows = int(_sat_cfg.get("max_rows", 3))
    sat_min_coverage = float(_sat_cfg.get("min_coverage", 0.9))
    sat_max_overhang = float(_sat_cfg.get("max_overhang", 0.45))

    # --- thin_lines: what to do with outline runs thinner than the satin gate -----
    _thin = str(cfg.get("thin_lines", "widen")).strip().lower()
    if _thin not in ("widen", "run"):
        print(f"warning: ignoring thin_lines {_thin!r} (use widen or run)")
        _thin = "widen"

    # --- satin_taper: one satin width per run, or one per stretch of line -------
    _taper = flag("satin-taper", None)
    _taper_mm = cfg.get("satin_taper_mm")
    satin_taper_mm = float(_taper if _taper is not None else
                           (_taper_mm if _taper_mm is not None else 0.0))
    if satin_taper_mm < 0:
        print(f"warning: ignoring satin_taper {satin_taper_mm} (use 0 or a length in mm)")
        satin_taper_mm = 0.0

    # --- rail_satin: stitch solid outline blobs as rail satin rows, not fills ----
    _rail = flag("rail-satin", None)
    rail_satin = bool(cfg.get("rail_satin", False)) if _rail is None else (_rail is True)
    _rail_left = cfg.get("rail_satin_leftover", True)
    rail_satin_leftover = bool(_rail_left)

    # --- trim.min_mm: jumps up to this length are never cut (Ink/Stitch adds no
    # lock stitches for gaps under its 3 mm collapse length) ----------------------
    try:
        _trim_min = float((cfg.get("trim") or {}).get("min_mm", TRIM_MIN_MM))
    except (TypeError, ValueError):
        print("warning: ignoring non-numeric trim.min_mm")
        _trim_min = TRIM_MIN_MM

    # --- outline_zigzag_spacing_mm: wider zigzag on outline satins = less thread ----
    _ozz = cfg.get("outline_zigzag_spacing_mm")
    try:
        _ozz = float(_ozz) if _ozz is not None else None
        if _ozz is not None and not 0.3 <= _ozz <= 0.8:
            print(f"warning: ignoring outline_zigzag_spacing_mm {_ozz} (use 0.3 to 0.8)")
            _ozz = None
    except (TypeError, ValueError):
        print("warning: ignoring non-numeric outline_zigzag_spacing_mm")
        _ozz = None

    # --- outline_order: how the outline segments are sequenced -------------------
    _oo = str(cfg.get("outline_order", "centroid")).strip().lower()
    if _oo not in ("centroid", "endpoint"):
        print(f"warning: ignoring outline_order {_oo!r} (use centroid or endpoint)")
        _oo = "centroid"

    # --- gradients: regions stitched as one Ink/Stitch linear gradient fill -----
    _gradients = []
    _grad_cfg = cfg.get("gradients") or []
    if not isinstance(_grad_cfg, list):
        print(f"warning: ignoring non-list gradients {_grad_cfg!r}")
        _grad_cfg = []
    for _i, _g in enumerate(_grad_cfg):
        _stops = [str(h).strip().lower() for h in ((_g or {}).get("stops") or [])] if isinstance(_g, dict) else []
        if not 2 <= len(_stops) <= 4 or not all(re.fullmatch(r"#[0-9a-f]{6}", h) for h in _stops):
            print(f"warning: ignoring gradient #{_i + 1}: needs 2 to 4 '#rrggbb' stops, light to dark")
            continue
        _gradients.append(dict(name=str(_g.get("name") or f"gradient{_i + 1}"), stops=_stops,
                               min_area_mm2=float(_g.get("min_area_mm2", 20.0)),
                               min_r2=float(_g.get("min_r2", 0.5)),
                               # interleaved rows leave small gaps at 0.4 mm (measured:
                               # 2.9 % uncovered on a flame lobe vs 0.05 % at 0.3 mm)
                               row_spacing_mm=float(_g.get("row_spacing_mm", 0.3))))

    # --- cleanup: merge parts below the art's detail limit into their neighbour ---
    _clean = cfg.get("cleanup") or {}
    if not isinstance(_clean, dict):
        print(f"warning: ignoring non-mapping cleanup {_clean!r}")
        _clean = {}
    try:
        cleanup_min_width_mm = float(_clean.get("min_width_mm", 0.0) or 0.0)
        cleanup_min_area_mm2 = float(_clean.get("min_area_mm2", 0.0) or 0.0)
        _fw, _fa = _clean.get("fabric_min_width_mm"), _clean.get("fabric_min_area_mm2")
        cleanup_fabric_min_width_mm = None if _fw is None else float(_fw)
        cleanup_fabric_min_area_mm2 = None if _fa is None else float(_fa)
    except (TypeError, ValueError):
        print("warning: ignoring non-numeric cleanup values")
        cleanup_min_width_mm = cleanup_min_area_mm2 = 0.0
        cleanup_fabric_min_width_mm = cleanup_fabric_min_area_mm2 = None

    # --- threads: stitch a source colour in a different thread colour ----------
    thread_map = {}
    for _k, _v in (cfg.get("threads") or {}).items():
        _src, _dst = _parse_palette([_k]), _parse_palette([_v])
        if _src and _dst:
            thread_map[_src[0]] = _dst[0]

    # --- circle border options ---------------------------------------------------
    _bcol = _parse_palette([_border_cfg["color"]]) if _border_cfg.get("color") else []
    border_color = _bcol[0] if _bcol else ""
    border_order = str(_border_cfg.get("order", "last")).strip().lower()
    if border_order not in ("first", "last"):
        print(f"warning: ignoring border.order {border_order!r} (use first or last)")
        border_order = "last"
    border_gaps = bool(_border_cfg.get("gaps", True))
    border_underlay = bool(_border_cfg.get("underlay", False))

    for _name, _val in [("global", row_spacing_mm)] + list(_density.items()):
        if not 0.3 <= _val <= 0.6:
            print(f"warning: density {_val} mm ({_name}) is outside the safe 0.3-0.6 mm range "
                  f"(too dense breaks needles, too open leaves gaps)")

    if profile:
        print(f"profile: {profile} (density={row_spacing_mm} mm, underlap_mm={underlap_mm}, "
              f"raster_pull_mm={raster_pull_mm}, fill_underlay_skip_last={skip_last}, "
              f"fill_underlay_double_light={double_light} (L*>{fill_underlay_light_l:g}), "
              f"satin_underlay={satin_underlay} (inset {satin_underlay_inset_mm} mm), "
              f"border_zigzag_spacing_mm={border_zigzag}, fabric_color={fabric_color or 'unset'})")

    return Settings(
        n_colors=n_colors, colors_given=colors_given, size_mm=size_mm, size_given=size_given,
        fit_mm=fit_mm, no_border=no_border, border_mm=border_mm,
        border_mode=_border_mode, trim=trim, trim_threshold_mm=trim_threshold_mm,
        row_spacing_mm=row_spacing_mm, no_satin=no_satin, satin_extend=satin_extend, fill_angle=fill_angle,
        angle_map=_angle, density_map=_density, satinize_colors=satinize_colors,
        sat_max_row_mm=sat_max_row_mm, sat_max_rows=sat_max_rows,
        sat_min_coverage=sat_min_coverage, sat_max_overhang=sat_max_overhang,
        order=order, skip=skip, satin_max_mm=satin_max_mm,
        palette=palette, palette_mode=palette_mode, profile=profile,
        underlap_mm=underlap_mm, raster_pull_mm=raster_pull_mm,
        fill_underlay_skip_last=skip_last, fill_underlay_double_light=double_light,
        fill_underlay_light_l=fill_underlay_light_l, satin_underlay=satin_underlay,
        satin_underlay_inset_mm=satin_underlay_inset_mm,
        border_zigzag_spacing_mm=border_zigzag, fabric_color=fabric_color,
        gradients=_gradients, thin_lines=_thin, outline_order=_oo, rail_satin=rail_satin,
        rail_satin_leftover=rail_satin_leftover, satin_taper_mm=satin_taper_mm,
        trim_min_mm=_trim_min, outline_zigzag_spacing_mm=_ozz,
        cleanup_min_width_mm=cleanup_min_width_mm, cleanup_min_area_mm2=cleanup_min_area_mm2,
        cleanup_fabric_min_width_mm=cleanup_fabric_min_width_mm,
        cleanup_fabric_min_area_mm2=cleanup_fabric_min_area_mm2,
        thread_map=thread_map, border_color=border_color, border_order=border_order,
        border_gaps=border_gaps, border_underlay=border_underlay,
    )


def load_image(path):
    """Open the source image and derive the silhouette and denoised RGB."""
    im = Image.open(path).convert("RGBA")
    arr = np.array(im)
    H, W = arr.shape[:2]
    alpha = arr[..., 3]
    transparent = alpha < 128
    has_transparency = bool(transparent.any())

    # silhouette = pixels that are part of the design (opaque, or whole image)
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

    return ImageData(H=H, W=W, arr=arr, transparent=transparent,
                     has_transparency=has_transparency, silhouette=silhouette, rgb=rgb)


def resolve_px_per_mm(design_w, design_h, size_mm, size_given, fit_mm):
    """Source pixels per mm for a design of ``design_w`` x ``design_h`` px.

    ``--size-mm`` alone (or neither flag): the longest side is ``size_mm``.
    ``--fit-mm`` alone: the design fills the box, whichever axis hits it first.
    Both: the smaller design wins, i.e. the larger px/mm.
    Returns ``(px_per_mm, rule, note)``; ``note`` is None unless both were given.
    """
    size_ppm = max(design_w, design_h) / size_mm
    if fit_mm is None:
        rule = f"--size-mm {size_mm:g}, longest side" if size_given else f"default {size_mm:g} mm longest side"
        return size_ppm, rule, None
    fw, fh = fit_mm
    fit_ppm = max(design_w / fw, design_h / fh)
    limit = "width" if design_w / fw >= design_h / fh else "height"
    box = f"{fw:g}x{fh:g}"
    if not size_given:
        return fit_ppm, f"fills --fit-mm {box}, {limit} limits", None
    if fit_ppm > size_ppm:
        return fit_ppm, f"--fit-mm {box} limited it, {limit} limits", (
            f"note: --fit-mm {box} limited the size; --size-mm {size_mm:g} alone would give a "
            f"longest side of {max(design_w, design_h) / size_ppm:.1f} mm, larger than the box")
    if size_ppm > fit_ppm:
        return size_ppm, f"--size-mm {size_mm:g} limited it, longest side", (
            f"note: --size-mm {size_mm:g} limited the size; --fit-mm {box} alone would allow a "
            f"longest side of {max(design_w, design_h) / fit_ppm:.1f} mm")
    return size_ppm, f"--size-mm {size_mm:g} and --fit-mm {box} give the same size", (
        f"note: --size-mm {size_mm:g} and --fit-mm {box} give the same size")


def design_scale(img, settings):
    """Scale so the design's own bounds (longer side) map to ``size_mm``.

    For transparent artwork the design is the union of the alpha silhouette's
    real components, not the canvas: scaling the canvas made a patch floating in
    a large canvas come out undersized (Book Burner: 87 mm instead of 100 mm).
    Tiny noise specks are ignored so they cannot inflate the bounds; the design
    may legitimately consist of several disconnected parts (flames + book).
    """
    arr = img.arr
    H, W = img.H, img.W
    if img.has_transparency:
        _lbl, _n = ndimage.label(~img.transparent)
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

    px_per_mm, rule, note = resolve_px_per_mm(
        design_w, design_h, settings.size_mm, settings.size_given, settings.fit_mm)
    scale = 1.0 / px_per_mm
    print(f"design size: {design_w / px_per_mm:.1f} x {design_h / px_per_mm:.1f} mm ({rule})")
    if note:
        print(note)
    if px_per_mm < 3.0:
        print(f"warning: source is too coarse to stitch well ({1 / px_per_mm:.2f} mm per source pixel at "
              f"{max(design_w, design_h) / px_per_mm:.0f} mm; need >= 3 px/mm). Supply a larger source image.")
    Wmm = W * scale
    Hmm = H * scale

    return Scale(
        design_w=design_w, design_h=design_h, px_per_mm=px_per_mm, scale=scale,
        Wmm=Wmm, Hmm=Hmm,
        min_comp_px=max(1, int(settings.min_comp_mm2 * px_per_mm * px_per_mm)),
        min_hole_px=max(1, int(settings.min_hole_mm2 * px_per_mm * px_per_mm)),
        tolerance=settings.tolerance_mm * px_per_mm,
        border_px=settings.border_mm * px_per_mm,
    )


def kmeans_palette(pixels, k):
    pix = pixels.astype(float)
    idx = np.random.default_rng(0).choice(len(pix), min(len(pix), 200000), replace=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # empty clusters / 0-division are expected on few-colour images
        cen, _ = kmeans2(pix[idx], k, minit="++", seed=0, iter=30)
    return np.clip(cen.round().astype(int), 0, 255)


def auto_palette(pixels, k, seed=0):
    """S3 palette: Lab over-cluster, protected merge, blend absorption, Lloyd.

    Over-clusters in CIELAB (k = max(2N, 16)), agglomeratively merges the closest
    pair, never merges a saturated (chroma > 25) cluster into a neutral one,
    absorbs small (< 2 %) clusters lying within ``dE 6`` of the segment between
    two others (anti-alias blends), then polishes with Lloyd iterations that
    leave saturated, tiny clusters pinned.  Returns ``N <= k`` uint8 centroids.
    """
    lab = color.rgb2lab(np.asarray(pixels, float).reshape(1, -1, 3) / 255.0).reshape(-1, 3)
    if len(lab) > 200000:
        lab = lab[np.random.default_rng(seed).choice(len(lab), 200000, replace=False)]
    with warnings.catch_warnings():                       # empty clusters expected
        warnings.simplefilter("ignore")
        cen = list(kmeans2(lab, max(2 * k, 16), minit="++", seed=seed, iter=30)[0])
    share = np.bincount(((lab[:, None] - np.array(cen)) ** 2).sum(2).argmin(1),
                        minlength=len(cen)).astype(float)
    share = list(share / share.sum())

    def chroma(c):
        return float(np.hypot(c[1], c[2]))

    def hue(c):
        return float(np.degrees(np.arctan2(c[2], c[1])))

    def saturated(c):
        """Most saturated cluster of its hue: never averaged away."""
        return chroma(c) > 25 and not any(
            chroma(o) > chroma(c) + 10 and abs((hue(c) - hue(o) + 180) % 360 - 180) < 40
            for o in cen)

    def mergeable(a, b):
        # a saturated and a neutral cluster are different threads: never merge
        return not (chroma(a) > 25 > chroma(b) or chroma(b) > 25 > chroma(a))

    def point_seg_dist(p, a, b):
        d = b - a
        t = 0.0 if d @ d < 1e-9 else float(np.clip((p - a) @ d / (d @ d), 0, 1))
        return float(np.linalg.norm(p - (a + t * d)))

    def merge(i, j):
        total = share[i] + share[j]
        cen[i] = (cen[i] * share[i] + cen[j] * share[j]) / total
        share[i] = total
        del cen[j], share[j]

    def blend():
        """Small non-saturated cluster lying on the segment of two others."""
        best = None
        for i in range(len(cen)):
            if share[i] >= 0.02 or saturated(cen[i]):
                continue
            for j in range(len(cen)):
                for m in range(j + 1, len(cen)):
                    if i in (j, m):
                        continue
                    d = point_seg_dist(cen[i], cen[j], cen[m])
                    if d <= 6 and (best is None or d < best[0]):
                        near = (j if np.linalg.norm(cen[i] - cen[j]) <= np.linalg.norm(cen[i] - cen[m])
                                else m)
                        best = (d, i, near)
        return best

    def closest_pair():
        cand = [(float(np.linalg.norm(cen[i] - cen[j])), i, j)
                for i in range(len(cen)) for j in range(i + 1, len(cen))
                if mergeable(cen[i], cen[j])]
        if not cand:                                      # all pairs forbidden
            cand = [(float(np.linalg.norm(cen[i] - cen[j])), i, j)
                    for i in range(len(cen)) for j in range(i + 1, len(cen))]
        return min(cand)[1:]

    while True:                                           # merge, drop final blends
        n, b = len(cen), blend()
        if b is not None and n > 3:
            merge(b[1], b[2])
        elif n > k:
            merge(*closest_pair())
        else:
            break
    while len(cen) > 2:                                   # drop fuzz below target
        bad = next((i for i in range(len(cen)) if share[i] < 0.02 and not saturated(cen[i])), None)
        if bad is not None:
            near = min((q for q in range(len(cen)) if q != bad),
                       key=lambda q: np.linalg.norm(cen[bad] - cen[q]))
            merge(bad, near)
        else:
            break

    pin, cents = [saturated(c) for c in cen], np.array(cen)
    for _ in range(20):                                   # Lloyd polish in Lab
        cl = ((lab[:, None] - cents) ** 2).sum(2).argmin(1)
        new = cents.copy()
        for c in range(len(cents)):
            m = cl == c
            if m.any() and not (pin[c] and m.sum() < 0.001 * len(lab)):
                new[c] = lab[m].mean(0)
        if np.allclose(new, cents, atol=1e-4):
            break
        cents = new
    rgb = color.lab2rgb(cents.reshape(1, -1, 3)).reshape(-1, 3) * 255
    return np.clip(rgb.round(), 0, 255).astype(np.uint8)


def _rgb_str(v):
    return "(" + ",".join(str(int(x)) for x in v) + ")"


def luma(rgb_):
    return 0.2126 * rgb_[0] + 0.7152 * rgb_[1] + 0.0722 * rgb_[2]


def hexkey(rgb_):
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb_)


def _poly_area(pts):
    """Absolute polygon area (shoelace) for a (N, 2) array of (y, x) points."""
    ys, xs = pts[:, 0], pts[:, 1]
    return 0.5 * np.abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))


def _original_part(sil_lab, part):
    """Silhouette connected component that contains ``part`` (for a part outline)."""
    vals = sil_lab[part]
    if vals.size == 0:
        return part
    counts = np.bincount(vals.ravel())
    counts[0] = 0                       # label 0 is background
    return sil_lab == int(counts.argmax())


def fit_circle(sil, step_deg=1.0, tol=0.04):
    """Circle ``(cy, cx, R)`` in px through the outer edge of a round patch.

    One ray per ``step_deg`` from the centre takes the outermost silhouette
    pixel.  Rays more than ``tol`` off the median radius (a horn, a beard, a
    chip in a rough edge) stay out of the least-squares fit.  Two rounds, so the
    second casts from the fitted centre instead of the silhouette centroid.
    """
    H, W = sil.shape
    ys, xs = np.nonzero(sil)
    cy, cx = float(ys.mean()), float(xs.mean())
    r = np.arange(int(np.hypot(H, W)))
    R = 0.0
    for _ in range(2):
        pts = []
        for th in np.radians(np.arange(0.0, 360.0, step_deg)):
            y = np.round(cy - r * np.sin(th)).astype(int)
            x = np.round(cx + r * np.cos(th)).astype(int)
            ok = (y >= 0) & (y < H) & (x >= 0) & (x < W)
            hit = np.nonzero(sil[y[ok], x[ok]])[0]
            if len(hit):
                k = hit.max()
                pts.append((y[ok][k], x[ok][k], r[ok][k]))
        pts = np.asarray(pts, float)
        med = np.median(pts[:, 2])
        inl = np.abs(pts[:, 2] - med) <= tol * med
        Y, X = pts[inl, 0], pts[inl, 1]
        A = np.c_[2 * X, 2 * Y, np.ones_like(X)]
        (a, b, c), *_ = np.linalg.lstsq(A, X ** 2 + Y ** 2, rcond=None)
        cy, cx, R = float(b), float(a), float(np.sqrt(c + a * a + b * b))
    return cy, cx, R


def clean_labels(img, scale, palette, settings):
    """Merge parts below the art's detail limit into the nearest colour (YAML ``cleanup:``).

    Every colour takes part, skipped colours included, inside the silhouette.
    First the parts thinner than ``min_width_mm`` (what an opening with a disc
    that wide removes), then connected islands smaller than ``min_area_mm2``.
    The freed pixels take the colour of the nearest pixel that stays, so a
    sliver between two shades joins them and a speck inside a fill closes the
    hole, instead of each becoming its own object with its own locks and cuts.

    Skipped colours are the fabric showing through and take ``fabric_min_*``
    when set: a spot of fabric inside a fill is only a hole and costs no cut.
    A thin fabric part is filled in only when one stitched colour alone lies
    next to it: a line that splits one colour into two islands (a cut each)
    closes, a keyline between two different colours or along the patch edge
    stays (it separates the tones or outlines the patch, and costs nothing).
    """
    fw, fa = settings.cleanup_fabric_min_width_mm, settings.cleanup_fabric_min_area_mm2
    if (settings.cleanup_min_width_mm <= 0 and settings.cleanup_min_area_mm2 <= 0
            and not fw and not fa):
        return
    sil = img.silhouette
    L = palette.label_all.copy()
    ppm = scale.px_per_mm
    labels = [int(c) for c in np.unique(L[sil])]
    skipped = {c for c in labels if hexkey(palette.centroids[c]).lower() in settings.skip}

    def width_mm(c):
        return fw if c in skipped and fw is not None else settings.cleanup_min_width_mm

    def area_mm2(c):
        return fa if c in skipped and fa is not None else settings.cleanup_min_area_mm2

    def islands():
        return {c: ndimage.label((L == c) & sil)[1] for c in labels}

    def refill(free):
        keep = sil & ~free
        if free.any() and keep.any():
            iy, ix = ndimage.distance_transform_edt(~keep, return_distances=False,
                                                    return_indices=True)
            L[free] = L[iy[free], ix[free]]

    def thin(c):
        r = width_mm(c) * ppm / 2.0
        m = (L == c) & sil
        if r <= 0:
            return np.zeros_like(sil), r
        core = ndimage.distance_transform_edt(m) > r                  # erosion by a disc
        return m & ~(ndimage.distance_transform_edt(~core) <= r), r   # minus the opening

    before = islands()
    stitched = [c for c in labels if c not in skipped]
    joins = []
    for c in skipped:
        part, r = thin(c)
        if part.any() and stitched:
            near = [ndimage.distance_transform_edt(~((L == s) & sil)) <= r + 1.5 for s in stitched]
            # the patch edge counts as a neighbour too: a fabric line along the
            # edge is an outline, not a split
            n_near = np.sum(near, axis=0) + (ndimage.distance_transform_edt(sil) <= r + 1.5)
            for s, nr in zip(stitched, near):
                joins.append((part & nr & (n_near == 1), s))
    free = np.zeros_like(sil)
    for c in stitched:
        free |= thin(c)[0]
    for m, s in joins:
        L[m] = s
    refill(free)
    for _ in range(3):
        free = np.zeros_like(sil)
        for c in labels:
            a_px = area_mm2(c) * ppm * ppm
            lab, n = ndimage.label((L == c) & sil)
            if n and a_px > 0:
                small = np.nonzero(np.bincount(lab.ravel()) < a_px)[0]
                small = small[small > 0]
                if len(small):
                    free |= np.isin(lab, small)
        if not free.any():
            break
        refill(free)
    after = islands()
    palette.label_all = L
    print("cleanup: islands per colour " + ", ".join(
        f"{hexkey(palette.centroids[c])} {before[c]} -> {after[c]}" for c in labels)
        + f" (thinner than {settings.cleanup_min_width_mm:g} mm or smaller than "
          f"{settings.cleanup_min_area_mm2:g} mm2 joins its neighbour"
        + (f"; fabric {width_mm(min(skipped)):g} mm, {area_mm2(min(skipped)):g} mm2" if skipped else "")
        + ")")


def _arc_sector(ang):
    """Smallest angular interval ``(lo, width)`` in degrees holding every angle in ``ang``."""
    a = np.sort(np.mod(ang, 360.0))
    gaps = np.diff(np.r_[a, a[0] + 360.0])
    k = int(np.argmax(gaps))
    lo = a[(k + 1) % len(a)]
    return lo, 360.0 - float(gaps[k])


def circle_ring(img, scale, palette, border, fill_colors, settings):
    """Build the circle border once the labels are known (``border: mode: circle``).

    The ring is a satin ``border_mm`` wide whose outer edge is the fitted
    circle.  Art that crosses the circle (horns, a beard) is found by angle,
    not by connectivity, because keylines cut a horn into separate stripes:
    stitched pixels just outside the circle, grouped into angular clusters,
    each widened to the stitched pixels at the band's inner edge within
    ``CROSS_REACH_DEG`` (an oblique horn enters the band at another angle than
    it leaves).  Stitched art outside the circle is kept, and in the band only
    inside those sectors, so the art's own thin rim is removed everywhere
    else: the ring is the only thing sewn there.

    Sewn last with ``gaps``, the ring stops ``CIRCLE_GAP_MM`` short of each
    crossing shape, so the shape reads as lying over it.  Sewn first, the ring
    is one closed satin and the crossing shapes are sewn over it.
    """
    cy, cx, R = border.circle
    ppm = scale.px_per_mm
    t = scale.border_px
    H, W = img.H, img.W
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.hypot(yy - cy, xx - cx)
    ang = np.degrees(np.arctan2(cy - yy, xx - cx))
    stitched = img.silhouette & np.isin(palette.label_all, fill_colors)
    out_ang = np.sort(np.mod(ang[stitched & (rr > R + 0.3 * ppm) & (rr <= R + 2.0 * ppm)], 360.0))
    in_ang = np.mod(ang[stitched & (rr > R - t - 2.0 * ppm) & (rr <= R - t)], 360.0)
    clusters = []
    if len(out_ang):
        # split the sorted angles wherever two neighbours are more than 3 degrees apart
        cut = np.nonzero(np.diff(np.r_[out_ang, out_ang[0] + 360.0]) > 3.0)[0]
        if len(cut) == 0:
            clusters = [out_ang]
        else:
            start = (cut[-1] + 1) % len(out_ang)
            ring_order = np.r_[out_ang[start:], out_ang[:start] + 360.0]
            bounds = np.nonzero(np.diff(ring_order) > 3.0)[0]
            clusters = np.split(ring_order, bounds + 1)
    in_sector = np.zeros((H, W), dtype=bool)       # where a crossing shape passes the band
    out_sector = np.zeros((H, W), dtype=bool)      # ... and where its tip may curve outside
    for cl in clusters:
        lo, width = _arc_sector(cl)
        d = np.mod(in_ang - (lo - CROSS_REACH_DEG), 360.0)
        entering = in_ang[d <= width + 2 * CROSS_REACH_DEG]
        lo, width = _arc_sector(np.r_[cl, entering])
        in_sector |= np.mod(ang - lo, 360.0) <= width
        out_sector |= np.mod(ang - (lo - CROSS_REACH_DEG), 360.0) <= width + 2 * CROSS_REACH_DEG
    n_cross = len(clusters)
    keep = stitched & (((rr > R) & out_sector) | ((rr > R - t) & (rr <= R) & in_sector))

    # the ring band and the outside belong to the ring now, except where art crosses
    removed = stitched & (rr > R - t) & ~keep
    img.silhouette = img.silhouette & ~((rr > R - t) & ~keep)
    band = (rr > R - t) & (rr <= R)

    if settings.border_color:
        h = settings.border_color
        border.color = np.array([int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)])
    else:
        border.color = palette.centroids[min(fill_colors, key=lambda c: luma(palette.centroids[c]))]

    Rm = R - t / 2.0
    step = np.degrees(1.0 * ppm / Rm)                 # a path point every ~1 mm
    gaps = settings.border_gaps and not border.first and n_cross > 0
    if gaps:
        gap_px = CIRCLE_GAP_MM * ppm + settings.satin_pull_mm * ppm
        near = ndimage.distance_transform_edt(~keep) <= gap_px
        fine = np.arange(0.0, 360.0, 0.25)
        blocked = np.zeros(len(fine), dtype=bool)
        for i, a in enumerate(np.radians(fine)):
            for rad in np.linspace(R - t, R, 9):
                y, x = int(round(cy - rad * np.sin(a))), int(round(cx + rad * np.cos(a)))
                if 0 <= y < H and 0 <= x < W and near[y, x]:
                    blocked[i] = True
                    break
        # rotate so the list starts inside a gap, then cut it into open runs
        s = int(np.argmax(blocked))
        order = np.r_[np.arange(s, len(fine)), np.arange(0, s)]
        arcs, cur = [], []
        for i in order:
            if blocked[i]:
                if cur:
                    arcs.append(cur)
                cur = []
            else:
                cur.append(fine[i])
        if cur:
            arcs.append(cur)
        for arc in arcs:
            a0, a1 = arc[0], arc[0] + (len(arc) - 1) * 0.25
            if np.radians(a1 - a0) * Rm < 3.0 * t:
                continue                      # a stub shorter than 3 widths packs, skip it
            th = np.radians(np.linspace(a0, a1, max(2, int((a1 - a0) / step) + 1)))
            poly = np.c_[cy - Rm * np.sin(th), cx + Rm * np.cos(th)]
            border.polys.append(poly)
            border.pts_list.append(poly)
            border.widths.append(t)
            border.closed.append(False)
            border.paths.append("M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in poly))
        border.ring = band & ~near
    else:
        th = np.radians(np.arange(0.0, 360.0, step))
        poly = np.c_[cy - Rm * np.sin(th), cx + Rm * np.cos(th)]
        border.polys.append(poly)
        border.pts_list.append(poly)
        border.widths.append(t)
        border.closed.append(True)
        border.paths.append("M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in poly) + " Z")
        border.ring = band & ~keep
    print(f"border: circle ring {settings.border_mm} mm, colour {hexkey(border.color)}, "
          f"{len(border.paths)} satin path(s), {n_cross} crossing shape(s) kept over it, "
          f"{removed.sum() / ppm ** 2:.1f} mm2 of art in the band or outside the circle removed")


def detect_border(img, scale, settings):
    """Detect the satin border ring / colour (transparent-background patches only)."""
    W, H = img.W, img.H
    border_off = settings.no_border or settings.border_mode == "off"
    border = Border(off=border_off)
    if not (img.has_transparency and not border_off):
        return border

    if settings.border_mode == "circle":
        border.circle = fit_circle(img.silhouette)
        border.first = settings.border_order == "first"
        cy, cx, R = border.circle
        print(f"border: circle fitted, centre ({cx / scale.px_per_mm:.1f}, {cy / scale.px_per_mm:.1f}) mm, "
              f"diameter {2 * R / scale.px_per_mm:.1f} mm, ring {settings.border_mm} mm, "
              f"sewn {settings.border_order}")
        return border

    dt = ndimage.distance_transform_edt(img.silhouette)
    force_black = settings.border_mode == "force_black"

    # the satin stroke (BORDER_PX wide) must be centred on the ring midline, so
    # trace the silhouette eroded by half the ring width: a stroke centred at
    # dt = BORDER_PX/2 covers exactly dt in 0..BORDER_PX, the carved ring
    half = int(round(scale.border_px / 2))
    eroded = img.silhouette & (dt > half) if half > 0 else img.silhouette
    if not eroded.any():
        eroded = img.silhouette        # thinner than the border: nothing left to erode

    # Erosion can SPLIT one connected patch into several parts (a patch with a
    # thin arm or neck survives the ring carve but not the midline trace).  Take
    # one border per part: the fills have the whole ring carved out of them, so a
    # part we skipped would be left with an unstitched band around it.
    parts, n_parts = ndimage.label(eroded)
    sil_lab = None                               # lazily labelled, only for a part outline
    n_tiny_parts = 0
    n_thin_parts = 0
    n_runout = 0       # parts given a running-stitch outline
    runout_seen = set()   # silhouette components whose outline is already emitted
    for i in range(1, n_parts + 1):
        part = (parts == i)
        cnts = measure.find_contours(np.pad(part, 1), 0.5)
        if not cnts:
            continue
        # widest-area contour, not the longest: a wiggly hole can have more
        # boundary points than the patch edge and would otherwise win
        outer = max(cnts, key=_poly_area) - 1
        poly = measure.approximate_polygon(outer, tolerance=scale.tolerance)
        if len(poly) < 3:
            continue
        # A border loop must be long enough for the satin to stitch sensibly,
        # and a part thinner than the border makes its offset rails cross (which
        # dies in Ink/Stitch's flattened_sections).  Instead of skipping such a
        # part, give it a
        # running-stitch outline along its edge (review.md 2.6.4).  A narrower
        # centreline satin was tried and dropped: on blob-shaped embers it lays a
        # bar across the middle instead of edging the part.
        perim = float(np.hypot(*np.diff(np.vstack([poly, poly[:1]]), axis=0).T).sum())
        r_eroded = float(ndimage.distance_transform_edt(part).max())
        too_small = perim < 3.0 * scale.border_px
        too_thin = r_eroded < 1.0 * scale.border_px
        if too_small or too_thin:
            if too_small:
                n_tiny_parts += 1
            elif too_thin:
                n_thin_parts += 1
            # running-stitch outline along the part's own edge
            n_runout += 1
            if sil_lab is None:
                sil_lab, _ = ndimage.label(img.silhouette)
            comp = _original_part(sil_lab, part)
            # several thin parts of one silhouette component all trace that
            # component's whole outline: emit it once, or the same line is
            # stitched (and bean-stitched) twice over the border
            comp_key = (int(comp.sum()), int(comp.argmax()))
            if comp_key in runout_seen:
                continue
            runout_seen.add(comp_key)
            ocnts = measure.find_contours(np.pad(comp, 1), 0.5)
            if ocnts:
                opoly = measure.approximate_polygon(max(ocnts, key=_poly_area) - 1,
                                                    tolerance=scale.tolerance)
                if len(opoly) >= 3:
                    border.outline_paths.append("M " + " L ".join(
                        f"{x:.1f},{y:.1f}" for y, x in opoly) + " Z")
                    border.outline_pts.append(opoly)
            continue
        border.polys.append(poly)
        border.widths.append(scale.border_px)
        border.closed.append(True)
        border.paths.append("M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in poly) + " Z")
        border.pts_list.append(poly)

    # the digital border sits just inside the silhouette edge
    ring = img.silhouette & (dt > 0) & (dt <= max(2, scale.border_px))
    if force_black:
        border.color = np.array([0, 0, 0])
        border.force_black = True
    elif ring.any():
        border.color = kmeans_palette(img.rgb[ring], 1)[0]
    else:
        # fallback: no dark ring -> black border
        border.color = np.array([0, 0, 0])

    if border.paths:
        border_color_str = _rgb_str(border.color)
        # Carve out ONLY what the emitted satin actually covers.  A blanket
        # distance ring erases every part thinner than the border width -- the
        # detached ember specks in a flame patch are all under 4 mm -- and a
        # part that vanishes under erosion gets no border path, so those pixels
        # would end up stitched nowhere.  Stroking the same midlines we emit as
        # satin guarantees carve area == covered area.
        stroke_img = Image.new("L", (W, H), 0)
        sdraw = ImageDraw.Draw(stroke_img)
        for spoly, wpx, closed in zip(border.polys, border.widths, border.closed):
            pts_px = [(float(x), float(y)) for y, x in spoly]
            if closed:
                pts_px = pts_px + pts_px[:1]
            sdraw.line(pts_px, fill=255, width=max(1, int(round(wpx))), joint="curve")
        border.ring = (np.array(stroke_img) > 0) & img.silhouette
        print(f"border: color {border_color_str} width {settings.border_mm} mm "
              f"({len(border.paths)} path{'s' if len(border.paths) > 1 else ''}, "
              f"{sum(len(p) for p in border.polys)} pts"
              + (f", {n_runout} part(s) given a running-stitch outline" if n_runout else "")
              + (f", {n_tiny_parts} part(s) too small to border" if n_tiny_parts else "")
              + (f", {n_thin_parts} part(s) too thin for the border width" if n_thin_parts else "")
              + ")")

    return border


def build_palette(img, scale, border, settings):
    """Interior k-means palette: dedupe, merge, background pick, border-colour snap."""
    # interior palette (exclude the border ring so it doesn't pollute fills)
    interior_mask = img.silhouette & (~border.ring if border.ring is not None else img.silhouette)
    if not interior_mask.any():
        # very thin patch: the border ring swallowed the whole silhouette -> keep the
        # interior as fills and drop the ring exclusion, otherwise everything vanishes
        print("warning: border ring covers the whole silhouette; keeping interior as fills")
        border.ring = None
        interior_mask = img.silhouette
    if img.has_transparency:
        interior_pix = img.rgb[interior_mask]
    else:
        # opaque image: background handled by dropping the lightest cluster below
        interior_pix = img.rgb[img.silhouette]

    if len(interior_pix) == 0:
        sys.exit("error: no opaque pixels to digitize (image is fully transparent?)")

    # Palette source: a pinned list, the S3 Lab palette (default), or legacy RGB k-means.
    mode = "pinned" if settings.palette else settings.palette_mode
    H, W = img.H, img.W
    if mode == "pinned":
        centroids = np.array(
            [[int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)] for h in settings.palette],
            dtype=int)
        if settings.colors_given and settings.n_colors != len(centroids):
            print(f"note: --colors {settings.n_colors} ignored; palette pinned to "
                  f"{len(centroids)} colour(s)")
        # assign every pixel to the nearest pinned colour in CIELAB
        lab_all = color.rgb2lab(img.rgb.astype(float) / 255.0).reshape(-1, 3)
        lab_cen = color.rgb2lab(
            centroids.reshape(1, -1, 3).astype(float) / 255.0).reshape(-1, 3)
        label_all = ((lab_all[:, None, :] - lab_cen[None, :, :]) ** 2).sum(axis=2) \
            .argmin(axis=1).reshape(H, W)
        del lab_all, lab_cen
    else:
        if mode == "kmeans":
            centroids = kmeans_palette(interior_pix, settings.n_colors)
        else:
            # S3's blend absorption was verified on the whole opaque silhouette
            # (RESULTS_palette.md); the ring-excluded interior can still leave a
            # 0-component anti-alias cluster (Book Burner tan), so cluster on the
            # full silhouette for S3.  Legacy k-means keeps the interior it always
            # used, to stay byte-identical.
            auto_pix = img.rgb[img.silhouette] if img.has_transparency else interior_pix
            centroids = auto_palette(auto_pix, settings.n_colors)

        # assign every pixel to its nearest centroid.  Transparent pixels are labelled
        # too, but both consumers intersect `silhouette` first, so those labels are
        # simply discarded -- there is no need to keep them for any other reason.
        flat_all = img.rgb.reshape(-1, 3).astype(float)
        d2 = ((flat_all[:, None, :] - centroids.astype(float)[None, :, :]) ** 2).sum(axis=2)
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
    _used = np.bincount(label_all[img.silhouette].ravel(), minlength=len(centroids))
    if not _used.all():
        _dropped = [hexkey(centroids[i]) for i in range(len(centroids)) if not _used[i]]
        _keep = _used > 0
        _remap = np.full(len(centroids), -1, dtype=np.int32)
        _remap[_keep] = np.arange(int(_keep.sum()), dtype=np.int32)
        label_all = _remap[label_all]
        centroids = centroids[_keep]
        if mode == "pinned":
            print("note: pinned colour(s) with no pixels dropped: " + ", ".join(_dropped))
    if mode != "pinned" and len(centroids) < settings.n_colors:
        print(f"note: image has {len(centroids)} distinct colours, fewer than --colors {settings.n_colors}")

    # Legacy RGB k-means splits near-black pixels into e.g. (0,1,1) and (2,2,2);
    # merge those so the design doesn't stitch two indistinguishable threads.  The
    # pinned palette is explicit and the S3 palette already merges in Lab, so both
    # skip this RGB-distance pass.
    if mode == "kmeans":
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
    if border.color is not None:
        if border.force_black:
            # force_black: use the darkest palette thread when it is genuinely
            # dark (L* < 25), so the border joins that thread's colour block
            # instead of adding a 7th (#000000) thread (review.md 2.6.1)
            _L = color.rgb2lab(
                np.asarray(cluster_rgb, float).reshape(1, -1, 3) / 255.0).reshape(-1, 3)[:, 0]
            _j = int(np.argmin(_L))
            if _L[_j] < 25.0:
                border.color = cluster_rgb[_j].astype(float)
                print(f"border: force_black snaps to darkest thread "
                      f"{hexkey(cluster_rgb[_j])} (L* {_L[_j]:.1f} < 25)")
            else:
                border.color = np.array([0, 0, 0])
                print(f"border: force_black keeps #000000 "
                      f"(darkest thread {hexkey(cluster_rgb[_j])} L* {_L[_j]:.1f} >= 25)")
        else:
            _bd = np.linalg.norm(cluster_rgb.astype(float) - np.asarray(border.color, float), axis=1)
            _bj = int(np.argmin(_bd))
            if _bd[_bj] <= 40:
                border.color = cluster_rgb[_bj].astype(float)

    # background cluster handling
    if not img.has_transparency:
        lum = cluster_rgb.sum(axis=1)
        bg = int(np.argmax(lum))     # lightest = paper
    else:
        bg = None                    # transparent = background (no cluster)

    print(f"image {W}x{H} -> {scale.Wmm:.0f}x{scale.Hmm:.0f} mm "
          f"({scale.px_per_mm:.1f} px/mm), palette k={len(centroids)}")
    if bg is not None:
        print(f"  background (skip) = {_rgb_str(cluster_rgb[bg])}")

    hex_to_idx = {hexkey(centroids[c]).lower(): c for c in range(len(centroids))}
    return Palette(centroids=cluster_rgb, label_all=label_all, bg=bg, hex_to_idx=hex_to_idx)


def order_colors(palette, settings):
    """Return (fill_colors light->dark with explicit order applied, outline colour)."""
    cluster_rgb = palette.centroids
    bg = palette.bg

    # default: all non-background colors sorted light->dark (bottom->top)
    _default_colors = sorted(
        [c for c in range(len(cluster_rgb)) if c != bg],
        key=lambda c: luma(cluster_rgb[c]),
        reverse=True,
    )

    # apply explicit order: listed colors first (in list order), then unlisted by luma
    listed = [c for c in
              (palette.hex_to_idx[h.lower()] for h in settings.order if h.lower() in palette.hex_to_idx)
              if c != bg]
    fill_colors = listed + [c for c in _default_colors if c not in listed]

    # skip colors
    fill_colors = [c for c in fill_colors if hexkey(cluster_rgb[c]).lower() not in settings.skip]

    # outline colour = darkest remaining fill; its thin parts become satin
    lw = min(fill_colors, key=lambda c: luma(cluster_rgb[c])) if fill_colors else None

    print("order:", [hexkey(cluster_rgb[c]) for c in fill_colors])
    return fill_colors, lw


def mask_for(c, palette, img, border, settings, use_border_exclusion=False):
    m = (palette.label_all == c) & img.silhouette
    if use_border_exclusion and border.ring is not None:
        m = m & (~border.ring)
    if settings.open_radius:
        m = ndimage.binary_opening(m, structure=morphology.disk(settings.open_radius))
    if settings.close_radius:
        m = ndimage.binary_closing(m, structure=morphology.disk(settings.close_radius))
    return m


def build_masks(img, border, palette, fill_colors, lw, settings):
    """Base per-colour cleaned masks, with the border ring excluded before filling.

    Fabric compensation (underlap + raster pull) is applied on top by
    ``compensate_masks`` once the satin-outline cover is known.
    """
    masks = {}
    for c in fill_colors:
        masks[c] = mask_for(c, palette, img, border, settings,
                            use_border_exclusion=img.has_transparency)
    if lw is not None and lw not in masks:
        masks[lw] = mask_for(lw, palette, img, border, settings,
                             use_border_exclusion=img.has_transparency)
    return masks


def _line_struct(angle_deg, r):
    """Boolean (2r+1)^2 structuring element: a 1-px line at ``angle_deg``."""
    st = np.zeros((2 * r + 1, 2 * r + 1), dtype=bool)
    t = math.radians(angle_deg)
    for k in range(-r, r + 1):
        st[int(round(r - k * math.sin(t))), int(round(r + k * math.cos(t)))] = True
    return st


def compensate_masks(masks, img, scale, border, palette, fill_colors, lw_cover, settings):
    """Fabric compensation on the cleaned masks (review.md 2.1, 2.3).

    Must run after the satin-outline cover is known (``lw_cover``) and before the
    masks are contoured, so the trim hidden-test and ``stitch_index`` see exactly
    the stitched shapes.

    * **Underlap** grows each fill up to ``underlap_mm`` under everything that
      stitches after it (later fills, the satin-outline cover, the border ring),
      clipped to the silhouette, walking from the top layer down.
    * **Raster pull** stretches each fill by ``raster_pull_mm`` along its
      stitch-row angle (FILL_ANGLE / YAML angle / 0), clipped to the silhouette
      grown by the same amount -- overshooting the outer edge is intended.
    """
    if settings.underlap_mm <= 0 and settings.raster_pull_mm <= 0:
        return masks

    H, W = img.H, img.W
    px_per_mm = scale.px_per_mm

    ul_px = int(round(settings.underlap_mm * px_per_mm))
    if ul_px > 0:
        later = np.zeros((H, W), dtype=bool)
        if lw_cover is not None:
            later |= lw_cover
        if border.ring is not None and not border.first:   # a ring sewn first is not later
            later |= border.ring
        for c in reversed(fill_colors):     # walk from the top layer down
            m0 = masks[c]                   # base mask: later fills stay un-grown
            masks[c] = m0 | (ndimage.binary_dilation(m0, structure=morphology.disk(ul_px))
                             & later & img.silhouette)
            later |= m0
        print(f"underlap: each fill grows up to {settings.underlap_mm} mm under "
              f"later fills / satin outlines / border")

    rp_px = int(round(settings.raster_pull_mm * px_per_mm))
    if rp_px > 0:
        sil_grow = ndimage.binary_dilation(img.silhouette, structure=morphology.disk(rp_px))
        for c in fill_colors:
            angle = settings.fill_angle
            if angle is None:
                angle = settings.angle_map.get(hexkey(palette.centroids[c]).lower(), 0.0)
            masks[c] = masks[c] | (ndimage.binary_dilation(
                masks[c], structure=_line_struct(angle or 0.0, rp_px)) & sil_grow)
        print(f"raster pull compensation: fills stretched {settings.raster_pull_mm} mm "
              f"along their stitch rows")
    return masks


def contour_paths(mask, min_area, min_hole, tolerance):
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


def blob_mask(lw_mask):
    """Outline components whose skeleton does not describe their own shape.

    ``satin_segments`` gives a solid shape (a star, a pommel) one short spoke per
    limb, so the star is stitched as an asterisk.  A component qualifies as a blob
    when its widest skeleton band is under ``BLOB_WIDTH_RATIO`` of its thickest
    point: the skeleton is too thin to be a stroke through the shape.  A shape
    with a hole is never a blob: its skeleton is the ring around the hole, which
    is exactly the satin you want.
    """
    blobs = np.zeros_like(lw_mask)
    dist = ndimage.distance_transform_edt(lw_mask)
    lab, n = ndimage.label(lw_mask)
    for i in range(1, n + 1):
        comp = lab == i
        thick = 2.0 * float(dist[comp].max())
        if thick <= 0:
            continue
        skel_w = 0.0
        for chain in trace_skeleton(morphology.skeletonize(comp)):
            if len(chain) < 2:
                continue
            arr = np.asarray(chain, float)
            skel_w = max(skel_w, 2.0 * float(np.median(
                dist[arr[:, 0].astype(int), arr[:, 1].astype(int)])))
        if ndimage.binary_fill_holes(comp).sum() == comp.sum() and skel_w < BLOB_WIDTH_RATIO * thick:
            blobs |= comp
    return blobs


def _rail_band(rail_pairs, n=48):
    """Area covered by the satin between each pair of rails, unioned.

    Each pair is sampled to ``n`` points along its length, which is how Ink/Stitch
    pairs the rails, so the polygon is what the zigzag actually spans.
    """
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    ts = np.linspace(0.0, 1.0, n)
    quads = []
    for rail_a, rail_b in rail_pairs:
        a = LineString(rail_a).interpolate(ts, normalized=True)
        b = LineString(rail_b).interpolate(ts, normalized=True)
        for i in range(n - 1):
            q = Polygon([(a[i].x, a[i].y), (a[i + 1].x, a[i + 1].y),
                         (b[i + 1].x, b[i + 1].y), (b[i].x, b[i].y)])
            if not q.is_valid:
                q = q.buffer(0)
            if not q.is_empty:
                quads.append(q)
    return unary_union(quads) if quads else None


def blob_rail_satins(mask, scale, rgb, min_area_px):
    """Solid components -> rail satin rows. Returns (handled_mask, items).

    The rails are the component's own outline, split along its long axis into
    1-3 rows, so the satin follows the shape instead of crossing it: that is the
    only way to stitch a star or a pommel as satin.  The builder is
    ``invert_ink.try_plate_satin``, the one the Scavenger's Daughter plates use
    (imported here so the rail geometry lives in one place).  A component whose
    rows would spill outside it is left alone: it stays a fill rather than growing
    satin over the bare fabric.
    """
    import invert_ink
    from shapely.affinity import scale as shp_scale

    handled = np.zeros_like(mask)
    items = []
    lab, n = ndimage.label(mask)
    for i in range(1, n + 1):
        comp = lab == i
        if comp.sum() < min_area_px:
            continue
        if ndimage.binary_fill_holes(comp).sum() != comp.sum():
            continue        # a hole wants the skeleton: rails would stitch over it
        cnts = measure.find_contours(np.pad(comp, 1), 0.5)
        if not cnts:
            continue
        # find_contours gives (row, col); shapely wants (x, y)
        outer = max(cnts, key=_poly_area)[:, ::-1] - 1
        poly = Polygon(outer).simplify(scale.tolerance)
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        poly_mm = shp_scale(poly, scale.scale, scale.scale, origin=(0, 0))
        rows, _stats = invert_ink.try_plate_satin(poly_mm, zigzag=RAIL_ZIGZAG_MM,
                                                  min_gap=RAIL_MIN_GAP_MM)
        if rows is None:
            continue
        band = _rail_band([(sub[0], sub[1]) for sub, _ in rows])
        if band is None or band.is_empty:
            continue
        if band.difference(poly_mm).area > RAIL_MAX_OVERHANG * band.area:
            continue        # the rows would grow outside the shape: leave it a fill
        for subpaths, st in rows:
            rails = [np.asarray(r, float) / scale.scale for r in subpaths]
            pts = np.vstack(rails)
            d = " ".join("M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in r) for r in rails)
            items.append(dict(cent=(float(pts[:, 0].mean()), float(pts[:, 1].mean())),
                              pts=pts, d=d, satin=True, stroke=False, lab_id=None,
                              rgb=rgb, spacing=None,
                              # decorative: a rail satin takes its width from the
                              # rails, but it must clear Ink/Stitch's 1 mm gate
                              width_px=max(SATIN_MIN_MM, st["sep_max"]) * scale.px_per_mm))
        handled |= comp
    return handled, items


def outline_satins(img, scale, masks, palette, lw, settings):
    """Skeletonize the darkest colour's thin parts into satin segments.

    Later changes land here: satin end extension at junctions (E3) modifies the
    emitted segments before they are covered/carved.
    """
    W, H = img.W, img.H
    outline_items = []
    lw_cover = None
    if lw is None or settings.no_satin:
        return outline_items, lw_cover

    lw_mask = masks[lw]
    rail_done = np.zeros_like(lw_mask)
    if settings.rail_satin:
        # solid blobs first: their skeleton is an asterisk, not a satin band
        blobs = blob_mask(lw_mask)
        rail_done, items = blob_rail_satins(blobs, scale, palette.centroids[lw],
                                            scale.min_comp_px)
        lw_mask = lw_mask & ~rail_done
        if items:
            outline_items += items
            print(f"rail satin: {len(items)} row(s) on "
                  f"{blobs.sum() / scale.px_per_mm ** 2:.1f} mm2 of solid blob(s) "
                  f"(skeleton under {BLOB_WIDTH_RATIO:g} of the shape's thickness)")
    thin_run = settings.thin_lines == "run"
    seg_items, lw_cover = _skeleton_satins(img, lw_mask, masks[lw], scale,
                                           palette.centroids[lw], settings, thin_run)
    outline_items += seg_items
    n_sat = sum(1 for i in seg_items if i["satin"])
    if lw_cover is None:
        if not rail_done.any():
            return outline_items, lw_cover
        lw_cover = np.zeros_like(lw_mask)
    lw_cover = lw_cover | rail_done
    _extra = f" + {len(seg_items) - n_sat} thin running lines" if thin_run else ""
    print(f"satin outlines: {n_sat} segments{_extra} from {_rgb_str(palette.centroids[lw])}")
    if settings.rail_satin and settings.rail_satin_leftover:
        # Whatever no skeleton satin reached is solid: a rail satin row, not a
        # tatami fill, so the whole outline colour stays satin.  A leftover whose
        # rails would pack or spill is left as fill -- a satin widened to reach it
        # would leave its mask and notch the edge.
        leftover = masks[lw] & ~lw_cover
        done, items2 = blob_rail_satins(leftover, scale, palette.centroids[lw],
                                        scale.min_comp_px)
        if items2:
            outline_items += items2
            lw_cover = lw_cover | ndimage.binary_dilation(done, morphology.disk(2))
            left = float((leftover & ~done).sum()) / scale.px_per_mm ** 2
            print(f"solid pass: {len(items2)} rail row(s) on the "
                  f"{leftover.sum() / scale.px_per_mm ** 2:.1f} mm2 the skeleton satin "
                  f"did not reach" + (f", {left:.1f} mm2 left as fill" if left else ""))
    return outline_items, lw_cover


def _skeleton_satins(img, mask, clip, scale, rgb, settings, thin_run):
    """Satin runs (and the area they cover) for one mask. Returns (items, cover).

    A satin shorter than it is wide is not stitchable: its rails are shorter than
    the zigzag travel, and Ink/Stitch then builds a section with no points and
    dies with "tuple index out of range" in flattened_sections.  Polygonal
    simplification can shorten a run below the satin_min_len_mm gate, so the
    emitted polyline is re-tested.  A short run that closes on itself (its ends
    closer than half its width) is the outline of a blob smaller than the satin
    is wide: the two offset rails cross and Ink/Stitch dies in the same place.
    """
    W, H = img.W, img.H
    items = []
    raw_segs = satin_segments(mask, scale.px_per_mm, settings.satin_min_len_mm,
                              settings.satin_min_mm, settings.satin_max_mm, scale.tolerance,
                              extend_ends=settings.satin_extend, raw_widths=thin_run,
                              taper_mm=settings.satin_taper_mm)
    runs = []
    if thin_run:
        # runs thinner than the satin gate stitch as a bean-stitch line along the
        # centre line instead of a satin widened to satin_min_mm
        gate_px = settings.satin_gate_mm * scale.px_per_mm
        runs = [(d, poly, w_raw) for d, poly, w, w_raw in raw_segs if w_raw < gate_px]
        raw_segs = [(d, poly, w) for d, poly, w, w_raw in raw_segs if w_raw >= gate_px]
    segs = []
    n_loops = 0
    for d, poly, w in raw_segs:
        _px = float(np.hypot(*np.diff(poly, axis=0).T).sum())
        if _px / scale.px_per_mm < max(2.5, 1.5 * w / scale.px_per_mm):
            continue
        if _px < 10.0 * w and float(np.hypot(*(poly[0] - poly[-1]))) < 0.5 * w:
            n_loops += 1
            continue
        segs.append((d, poly, w))
    if len(segs) != len(raw_segs):
        print(f"note: dropped {len(raw_segs) - len(segs)} outline satin(s) shorter than "
              f"their own width or closed on themselves ({len(raw_segs)} -> {len(segs)}"
              + (f", {n_loops} loop(s)" if n_loops else "") + ")")
    if not (segs or runs):
        return items, None
    cover_img = Image.new("L", (W, H), 0)
    cover_draw = ImageDraw.Draw(cover_img)
    for d, poly, w_raw in runs:
        items.append(dict(cent=(float(poly[:, 0].mean()), float(poly[:, 1].mean())),
                          pts=poly, d=d, satin=False, stroke=True, lab_id=None,
                          rgb=rgb, spacing=None, width_px=w_raw))
        cover_draw.line([(float(x), float(y)) for y, x in poly], fill=255,
                        width=max(1, int(round(w_raw))), joint="curve")
    for d, poly, w in segs:
        items.append(dict(cent=(float(poly[:, 0].mean()), float(poly[:, 1].mean())),
                          pts=poly, d=d, satin=True, lab_id=None,
                          rgb=rgb, spacing=None, width_px=w))
        cover_draw.line([(float(x), float(y)) for y, x in poly], fill=255,
                        width=max(1, int(round(w))), joint="curve")
    # dilate the band a couple of px before carving the fill: otherwise the
    # band-edge mismatch with the simplified skeleton leaves sub-mm slivers
    cover = ndimage.binary_dilation((np.array(cover_img) > 0) & clip,
                                    structure=morphology.disk(2))
    return items, cover


def gradient_regions(img, scale, palette, masks, fill_colors, lw, settings):
    """Find the regions to stitch as one linear gradient (config ``gradients:``).

    A region is a connected component of the union of a gradient's stop colours
    whose original pixels follow a straight colour ramp (gradient.fit_region).
    Its pixels are removed from the flat masks so no flat fill stitches under it.
    A region that does not fit stays flat. Returns dicts: mask, stops (palette
    indices in offset order), fit, name.
    """
    out = []
    for g in settings.gradients:
        try:
            stops = gradfit.resolve_stops(g["stops"], palette.centroids)
        except ValueError as e:
            print(f"gradient {g['name']}: skipped, {e}")
            continue
        if any(c not in masks or c == lw for c in stops):
            print(f"gradient {g['name']}: skipped, a stop colour is skipped or is the outline colour")
            continue
        union = np.zeros_like(masks[stops[0]])
        base = np.zeros_like(union)
        for c in stops:
            union |= masks[c]
            base |= (palette.label_all == c) & img.silhouette
        stops_lab = gradfit.rgb_to_lab(palette.centroids[stops])
        min_px = max(1, int(g["min_area_mm2"] * scale.px_per_mm ** 2))
        for comp in gradfit.regions(union, min_px):
            fitpix = comp & base
            n_fit = int(fitpix.sum())
            share = [int(((palette.label_all == c) & fitpix).sum()) / max(1, n_fit) for c in stops]
            area = float(comp.sum()) / scale.px_per_mm ** 2
            if sum(1 for f in share if f >= 0.08) < 2:
                print(f"gradient {g['name']}: region {area:.0f} mm2 stays flat (under two stop colours)")
                continue
            ys, xs = np.nonzero(fitpix)
            fit = gradfit.fit_region(gradfit.rgb_to_lab(img.rgb[ys, xs]),
                                     np.column_stack([xs, ys]), stops_lab, min_r2=g["min_r2"])
            if fit is None:
                print(f"gradient {g['name']}: region {area:.0f} mm2 stays flat (no straight colour ramp)")
                continue
            out.append(dict(mask=comp, stops=stops, fit=fit, name=g["name"],
                            spacing=g["row_spacing_mm"]))
            for c in stops:
                masks[c] = masks[c] & ~comp
            print(f"gradient {g['name']}: region {area:.0f} mm2, ramp at {fit['angle_deg']:.0f} deg, "
                  f"R2 {fit['r2']:.2f}, stops {[_rgb_str(palette.centroids[c]) for c in stops]}")
    return out


def _is_small_fill(geom, px_per_mm):
    """ADR 0003: smaller than SMALL_FILL_MM2 or thinner than SMALL_FILL_MIC_MM."""
    from shapely import maximum_inscribed_circle
    if geom is None or geom.is_empty:
        return False
    if geom.area / px_per_mm ** 2 < SMALL_FILL_MM2:
        return True
    try:
        return 2.0 * maximum_inscribed_circle(geom).length / px_per_mm < SMALL_FILL_MIC_MM
    except Exception:
        return False


def fill_components(img, scale, border, palette, masks, fill_colors, lw, lw_cover, settings):
    """Contour every fill colour; satinize the components listed in satinize.colors."""
    from shapely import affinity

    color_items = {}
    color_keep_lab = {}
    satinized_satins = []      # (cluster, d, pts, width_px)
    satinized_polys = []       # px-space shapely geoms removed from their fill
    grad_regions = gradient_regions(img, scale, palette, masks, fill_colors, lw, settings)
    print("fills:")
    for c in fill_colors:
        mask = masks[c]
        if c == lw and lw_cover is not None:
            mask = mask & ~lw_cover
        paths, cents, pts, keep_lab, dropped, geoms = contour_paths(
            mask, scale.min_comp_px, scale.min_hole_px, scale.tolerance)
        hx = hexkey(palette.centroids[c]).lower()
        angle = settings.fill_angle if settings.fill_angle is not None else settings.angle_map.get(hx)
        items = []
        n_sat = 0
        for i in range(len(paths)):
            geom = geoms[i] if hx in settings.satinize_colors else None
            if geom is not None and not geom.is_empty:
                # satinize works in mm (its own pixel grid is 0.1 mm), so hand it
                # fitted mm geometry and scale the resulting centrelines back to px
                # origin=(0, 0) is essential: affinity.scale defaults to
                # origin='center', which would scale about each component's own
                # centroid and leave it sitting near its original pixel position
                res = satinize.component_to_satins(
                    affinity.scale(geom, scale.scale, scale.scale, origin=(0, 0)),
                    max_row_mm=settings.sat_max_row_mm, max_rows=settings.sat_max_rows,
                    min_coverage=settings.sat_min_coverage, max_overhang=settings.sat_max_overhang)
                if res and all(satinize.centreline_ok(r["centreline"], r["width_mm"])
                               for r in res):
                    n_sat += 1
                    satinized_polys.append(geom)
                    for r in res:
                        line = np.asarray(r["centreline"], float) / scale.scale
                        satinized_satins.append(dict(
                            cluster=c, rgb=palette.centroids[c], lab_id=None, satin=True,
                            cent=(float(line[:, 1].mean()), float(line[:, 0].mean())),
                            pts=np.vstack([line[:, ::-1], line[-1::-1, ::-1]]),
                            d="M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in line),
                            width_px=r["width_mm"] / scale.scale))
                    continue        # the satin replaces this fill component
            items.append(dict(cent=cents[i], pts=pts[i], d=paths[i], satin=False,
                              lab_id=i + 1, rgb=palette.centroids[c],
                              spacing=settings.density_map.get(hx), width_px=None, angle=angle,
                              small=_is_small_fill(geoms[i], scale.px_per_mm)))
        color_items[c] = items
        color_keep_lab[c] = keep_lab
        _sat_note = f", {n_sat} -> satin" if n_sat else ""
        print(f"  {_rgb_str(palette.centroids[c])}: {len(items)} comps (dropped {dropped}){_sat_note}")

    # Gradient regions join the layer of their first stop colour in stitch order.
    for gr in grad_regions:
        c0 = next(c for c in fill_colors if c in gr["stops"])
        g_paths, g_cents, g_pts, g_keep, _drop, _geoms = contour_paths(
            gr["mask"], scale.min_comp_px, scale.min_hole_px, scale.tolerance)
        kl = color_keep_lab[c0]
        base_id = int(kl.max())
        hx0 = hexkey(palette.centroids[c0]).lower()
        for i in range(len(g_paths)):
            kl[g_keep == i + 1] = base_id + i + 1
            color_items[c0].append(dict(
                cent=g_cents[i], pts=g_pts[i], d=g_paths[i], satin=False,
                lab_id=base_id + i + 1, rgb=palette.centroids[c0],
                spacing=gr["spacing"], width_px=None, angle=None,
                gradient=dict(
                    stops=[tuple(int(v) for v in palette.centroids[c]) for c in gr["stops"]],
                    offsets=gr["fit"]["offsets"], p1=gr["fit"]["p1"], p2=gr["fit"]["p2"])))

    if satinized_satins:
        # each fill component is its own object, so dropping the item removes the
        # fill entirely -- the satin replaces it, with no fill sliver left behind
        _w_min = min(s["width_px"] / scale.px_per_mm for s in satinized_satins)
        print(f"satinize: {len(satinized_satins)} satin column(s) from "
              f"{len(satinized_polys)} component(s), narrowest {_w_min:.2f} mm")

    return color_items, color_keep_lab, satinized_satins, satinized_polys


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


def nn_sort_ends(items, needle):
    """Nearest-neighbour order of path items by ENDPOINT, reversing a path when its far end is nearer.

    Outline segments meet at junctions, so the next segment usually starts where the
    previous one ended: no jump, no trim. Each item gets ``ends`` = (start, end) in
    path order, which plan_trims uses as the exact jump instead of its geometric guess.
    """
    remaining = list(items)
    out = []
    cur = np.asarray(needle, dtype=float)
    while remaining:
        best = None
        for k, o in enumerate(remaining):
            pts = np.asarray(o["pts"], dtype=float)
            da = float(np.hypot(*(pts[0] - cur)))
            db = float(np.hypot(*(pts[-1] - cur)))
            cand = (da, k, False) if da <= db else (db, k, True)
            if best is None or cand[0] < best[0]:
                best = cand
        _, k, rev = best
        o = remaining.pop(k)
        pts = np.asarray(o["pts"], dtype=float)
        if rev:
            pts = pts[::-1]
            o["pts"] = pts
            o["d"] = "M " + " L ".join(f"{x:.1f},{y:.1f}" for y, x in pts)
        o["ends"] = (pts[0], pts[-1])
        out.append(o)
        cur = pts[-1]
    return out


def order_objects(img, scale, palette, fill_colors, color_items, color_keep_lab,
                  satinized_satins, outline_items, border, settings):
    """Global needle-aware ordering; builds stitch_index for the trim test."""
    W, H = img.W, img.H
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

    def add_border_satins():
        nonlocal stitch_index, needle
        for d_path, poly, wpx, closed in zip(border.paths, border.pts_list,
                                              border.widths, border.closed):
            o = dict(group_id="border", group_label="Border",
                     cent=(float(poly[:, 0].mean()), float(poly[:, 1].mean())),
                     pts=poly, d=d_path, satin=True, rgb=border.color,
                     spacing=None, width_px=wpx, closed=closed)
            o["index"] = len(objs)
            # model the border as its actual stroke (wpx wide, centred on the ring
            # midline contour, so it covers the carved ring)
            bim = Image.new("I", (W, H), -1)
            ring_pts = [(float(x), float(y)) for y, x in poly]
            if closed:
                ring_pts = ring_pts + ring_pts[:1]
            ImageDraw.Draw(bim).line(ring_pts, fill=o["index"],
                                     width=max(1, int(round(wpx))), joint="curve")
            stitch_index = np.maximum(stitch_index, np.array(bim, dtype=np.int32))
            objs.append(o)
            needle = (float(poly[-1, 0]), float(poly[-1, 1]))

    if border.first:            # circle ring sewn first: the art crosses over it
        add_border_satins()

    for c in fill_colors:
        for o in nn_sort(color_items[c], needle):
            o["group_id"] = "color%d" % layer_no
            o["group_label"] = hexkey(palette.centroids[c])
            o["index"] = len(objs)
            stitch_index[color_keep_lab[c] == o["lab_id"]] = o["index"]
            objs.append(o)
            needle = o["cent"]
        # this colour's satinized columns go last inside the same layer, so the
        # satin is stitched on top of the fills around it
        for o in nn_sort(color_satins.get(c, []), needle):
            o["group_id"] = "color%d" % layer_no
            o["group_label"] = hexkey(palette.centroids[c])
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
        _outline_sort = nn_sort_ends if settings.outline_order == "endpoint" else nn_sort
        for o in _outline_sort(outline_items, needle):
            o["group_id"] = "outlines"
            o["group_label"] = "Outline"
            o["index"] = len(objs)
            satin_draw.line([(float(x), float(y)) for y, x in o["pts"]], fill=o["index"],
                            width=max(1, int(round(o["width_px"]))), joint="curve")
            objs.append(o)
            needle = o["cent"]
        stitch_index = np.maximum(stitch_index, np.array(satin_img, dtype=np.int32))
        layer_no += 1

    if not border.first:
        add_border_satins()

    # running-stitch outlines along tiny/thin parts (review.md 2.6.4b): same
    # border colour, same layer, stitched after the border satins
    for opoly, d_path in zip(border.outline_pts, border.outline_paths):
        o = dict(group_id="border", group_label="Border",
                 cent=(float(opoly[:, 0].mean()), float(opoly[:, 1].mean())),
                 pts=opoly, d=d_path, satin=False, stroke=True, rgb=border.color,
                 spacing=None, width_px=None)
        o["index"] = len(objs)
        bim = Image.new("I", (W, H), -1)
        rp = [(float(x), float(y)) for y, x in opoly]
        ImageDraw.Draw(bim).line(rp, fill=o["index"], width=1, joint="curve")
        stitch_index = np.maximum(stitch_index, np.array(bim, dtype=np.int32))
        objs.append(o)

    return objs, stitch_index


def gap_and_segment(a, b, px_per_mm):
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


def is_hidden(p0, p1, idx, stitch_index, H, W, px_per_mm):
    """True if the straight jump after object ``idx`` is covered by a later stitch."""
    n = max(8, int(np.hypot(*(p1 - p0)) / px_per_mm * 2))
    for t in np.linspace(0.0, 1.0, n + 2)[1:-1]:
        p = p0 + t * (p1 - p0)
        y, x = int(round(p[0])), int(round(p[1]))
        if not (0 <= y < H and 0 <= x < W) or stitch_index[y, x] <= idx:
            return False
    return True


def plan_trims(img, scale, objs, stitch_index, settings):
    """Trim: cut a jump that is long OR exposed (not hidden by a later stitch).

    A jump is skipped only when it is genuinely short on both measures: the
    nearest-boundary distance AND the worst one-sided travel are under the
    threshold.  Using ``d_min`` alone skipped the Book Burner jump where
    Ink/Stitch leaves a fill at a row end 0.74 mm from the next shape but enters
    it 59.7 mm away -- the 58 mm sewn jump (review.md 2.8).  A jump at a layer
    boundary is always cut when the next object's nearest boundary is farther
    than ``TRIM_MIN_MM``, so no colour change or outline->border move is left
    sewn and the trim_vp3 safety net has nothing to add.
    """
    H, W = img.H, img.W
    trim_after = [False] * len(objs)
    n_trims = 0
    if settings.trim:
        for i in range(len(objs) - 1):
            d_min, d_max, p0, p1 = gap_and_segment(objs[i], objs[i + 1], scale.px_per_mm)
            _ea, _eb = objs[i].get("ends"), objs[i + 1].get("ends")
            if (_ea is not None and _eb is not None
                    and float(np.hypot(*(_ea[1] - _eb[0]))) / scale.px_per_mm <= settings.trim_min_mm):
                continue        # the next path starts where this one ended: no jump to cut
            if settings.trim_threshold_mm == 0:
                short = d_min <= settings.trim_min_mm
            else:
                short = (d_min <= settings.trim_min_mm
                         and d_max <= settings.trim_threshold_mm)
            if short:
                continue
            if (settings.trim_threshold_mm == 0 or d_max > settings.trim_threshold_mm
                    or not is_hidden(p0, p1, i, stitch_index, H, W, scale.px_per_mm)):
                trim_after[i] = True
        for i in range(len(objs) - 1):
            if (not trim_after[i]
                    and objs[i]["group_id"] != objs[i + 1]["group_id"]):
                d_min = gap_and_segment(objs[i], objs[i + 1], scale.px_per_mm)[0]
                if d_min > settings.trim_min_mm:
                    trim_after[i] = True
        n_trims = sum(trim_after)
        print(f"trim: {n_trims} cuts / {len(objs)} objects (threshold {settings.trim_threshold_mm} mm)")
    return trim_after, n_trims


def el(id_, fill_rgb, d, settings, spacing=None, trim_after=False, angle=None,
       gradient_id=None, small=False, cut=False):
    hx = "#%02x%02x%02x" % tuple(int(v) for v in fill_rgb)
    fill_css = f"url(#{gradient_id})" if gradient_id else hx
    method = 'inkstitch:fill_method="linear_gradient_fill" ' if gradient_id else ""
    rs = spacing if spacing is not None else settings.row_spacing_mm
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    ang = f'inkstitch:angle="{angle:g}" ' if angle is not None else ""
    # Underlay: default skips the last row (density on stable twill).  The vadmel
    # profile keeps every row and adds a perpendicular second pass on light thread
    # (L* above the threshold), which the research says stops the pile showing.
    underlay = ('inkstitch:fill_underlay_skip_last="true" '
                if settings.fill_underlay_skip_last else "")
    if settings.fill_underlay_double_light:
        _l = float(color.rgb2lab(np.asarray(fill_rgb, float).reshape(1, 1, 3) / 255.0)[0, 0, 0])
        if _l > settings.fill_underlay_light_l:
            _a = angle if angle is not None else 0.0
            underlay += f'inkstitch:fill_underlay_angle="{_a + 90:g} {_a:g}" '
    if small:
        # ADR 0003: a component this small cannot carry an underlay plus tie locks
        # without packing the needle; Ink/Stitch has no small-shape exemption.
        # The ties stay when a cut touches the fill: Ink/Stitch adds locks only
        # after a trim or a long jump, and ties="3" removes even those, which
        # leaves the cut tail unlocked (lib/elements/element.py lock_stitches)
        underlay = 'inkstitch:fill_underlay="false" ' + ("" if cut else 'inkstitch:ties="3" ')
    # Pin the params the legacy version-0 update used to inject, so a version-4
    # file stitches the same tatami rows: 3 mm max stitch (samples sew 3.0 mm)
    # and 1.5 mm travel between fill rows.
    return (f'<path id="{id_}" style="fill:{fill_css};stroke:none" fill-rule="evenodd" '
            f'{method}inkstitch:row_spacing_mm="{rs}" {ang}'
            f'inkstitch:max_stitch_length_mm="3" inkstitch:running_stitch_length_mm="1.5" '
            f'{underlay}{trim}d="{d}"/>')


def satin_el(id_, stroke_rgb, d, width_px, scale, settings, trim_after=False,
             underlay=False, zigzag_mm=None, border=False):
    w_mm = width_px / scale.px_per_mm
    if w_mm <= settings.satin_gate_mm:      # Ink/Stitch's test is strictly `>`
        # would be emitted as satin_column and then silently stitched as running
        print(f"warning: satin {id_} is {w_mm:.2f} mm wide, below Ink/Stitch's "
              f"{settings.satin_gate_mm:.1f} mm gate -- it will stitch as running stitch")
    hx = "#%02x%02x%02x" % tuple(int(v) for v in stroke_rgb)
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    pull = (f'inkstitch:pull_compensation_mm="{settings.satin_pull_mm} {settings.satin_pull_mm}" '
            if settings.satin_pull_mm else "")
    u = ""
    if underlay:
        u = ('inkstitch:center_walk_underlay="true" inkstitch:contour_underlay="true" '
             f'inkstitch:contour_underlay_inset_mm="{settings.satin_underlay_inset_mm:g}" ')
    zz = f'inkstitch:zigzag_spacing_mm="{zigzag_mm:g}" ' if zigzag_mm else ""
    # The border fans at tight tips (goat horn); inset the crossing stitches and
    # split any satin stitch longer than 7 mm so the fan does not leave a long
    # bar of thread (review.md 2.6.6)
    bp = ('inkstitch:short_stitch_inset="20" inkstitch:max_stitch_length_mm="7" '
          if border else "")
    return (f'<path id="{id_}" style="fill:none;stroke:{hx};stroke-width:{width_px:.2f}" '
            f'inkstitch:satin_column="true" {pull}{u}{zz}{bp}{trim}d="{d}"/>')


def run_el(id_, stroke_rgb, d, trim_after=False):
    """Running-stitch outline in the border colour (review.md 2.6.4b)."""
    hx = "#%02x%02x%02x" % tuple(int(v) for v in stroke_rgb)
    trim = 'inkstitch:trim_after="true" ' if trim_after else ""
    return (f'<path id="{id_}" style="fill:none;stroke:{hx};stroke-width:0.3" '
            f'inkstitch:bean_stitch_repeats="1" inkstitch:running_stitch_length_mm="1.5" '
            f'{trim}d="{d}"/>')


def _thread(rgb, settings):
    """The thread colour a source colour is stitched in (YAML ``threads:``)."""
    hx = settings.thread_map.get(hexkey(rgb).lower())
    return (int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)) if hx else rgb


def emit_svg(out, objs, trim_after, img, scale, settings):
    """Write the Ink/Stitch SVG.

    Emits version-4 metadata so Ink/Stitch does not run its legacy updates, and
    pins the fill stitch params the update used to inject (see ``el``).
    """
    W, H = img.W, img.H
    p = []
    p.append(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkstitch="http://inkstitch.org/namespace" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd" '
        f'width="{scale.Wmm:.2f}mm" height="{scale.Hmm:.2f}mm" viewBox="0 0 {W} {H}" '
        'inkscape:document-units="mm" sodipodi:docname="design.svg">\n'
    )
    p.append(
        f'  <sodipodi:namedview id="namedview1" pagecolor="#ffffff" units="mm" '
        f'inkscape:document-units="mm" pagewidth="{scale.Wmm:.2f}" pageheight="{scale.Hmm:.2f}" '
        'inkscape:pageopacity="0.0" inkscape:pagecheckerboard="0" showgrid="false"/>\n'
    )
    # Version-4 metadata stops Ink/Stitch treating the file as unversioned (which
    # pops the "Unversioned Ink/Stitch SVG file detected" dialog and runs the
    # legacy updates).  collapse_len_mm=3 matches what svg_digitize.py writes.
    p.append(
        '  <metadata id="metadata1">'
        '<inkstitch:inkstitch_svg_version>4</inkstitch:inkstitch_svg_version>'
        '<inkstitch:collapse_len_mm>3</inkstitch:collapse_len_mm>'
        '</metadata>\n'
    )
    grads = [(i, o["gradient"]) for i, o in enumerate(objs) if o.get("gradient")]
    if grads:
        p.append("  <defs>\n")
        for i, gr in grads:
            p.append(f'    <linearGradient id="g{i}" gradientUnits="userSpaceOnUse" '
                     f'x1="{gr["p1"][0]:.2f}" y1="{gr["p1"][1]:.2f}" '
                     f'x2="{gr["p2"][0]:.2f}" y2="{gr["p2"][1]:.2f}">\n')
            for off, rgb in zip(gr["offsets"], gr["stops"]):
                rgb = _thread(rgb, settings)
                p.append(f'      <stop offset="{off:.4f}" style="stop-color:'
                         f'#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x};stop-opacity:1"/>\n')
            p.append("    </linearGradient>\n")
        p.append("  </defs>\n")
    idx = 0
    current_group = None
    prev_tm, prev_rgb = True, None          # the first object starts after a cut
    for o, tm in zip(objs, trim_after):
        # a cut or a colour change on either side: the fill's locks hold the thread
        cut = tm or prev_tm or prev_rgb is None or hexkey(o["rgb"]) != hexkey(prev_rgb)
        prev_tm, prev_rgb = tm, o["rgb"]
        if o["group_id"] != current_group:
            if current_group is not None:
                p.append('  </g>\n')
            p.append(f'  <g inkscape:label="{o["group_label"]}" inkscape:groupmode="layer" '
                     f'id="{o["group_id"]}">\n')
            current_group = o["group_id"]
        rgb = _thread(o["rgb"], settings)
        if o["satin"]:
            gid = o["group_id"]
            underlay = ((settings.satin_underlay and gid in ("outlines", "border"))
                        or (settings.border_underlay and gid == "border"))
            zigzag = (settings.border_zigzag_spacing_mm if gid == "border"
                      else settings.outline_zigzag_spacing_mm if gid == "outlines" else None)
            p.append("    " + satin_el(f"s{idx}", rgb, o["d"], o["width_px"],
                                       scale, settings, trim_after=tm,
                                       underlay=underlay, zigzag_mm=zigzag,
                                       border=(gid == "border")) + "\n")
        elif o.get("stroke"):
            p.append("    " + run_el(f"r{idx}", rgb, o["d"], trim_after=tm) + "\n")
        else:
            p.append("    " + el(f"f{idx}", rgb, o["d"], settings, spacing=o["spacing"],
                                  trim_after=tm, angle=o.get("angle"),
                                  gradient_id=f"g{idx}" if o.get("gradient") else None,
                                  small=o.get("small", False), cut=cut) + "\n")
        idx += 1
    if current_group is not None:
        p.append('  </g>\n')
    p.append('</svg>\n')

    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(p))


def write_preview(out, img, palette, settings=None):
    """Posterized preview PNG next to the SVG (for review), in thread colours."""
    preview = np.full((img.H, img.W, 3), 255, dtype=np.uint8)
    view = palette.label_all[img.silhouette]
    cen = palette.centroids
    if settings is not None and settings.thread_map:
        cen = np.array([_thread(c, settings) for c in cen], dtype=np.uint8)
    preview[img.silhouette] = cen[view]
    if img.has_transparency:
        alpha8 = np.where(img.silhouette, 255, 0).astype(np.uint8)
        prev = np.dstack([preview, alpha8])
    else:
        prev = preview
    Image.fromarray(prev).save(out.rsplit(".", 1)[0] + "_posterized.png")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    flags, args = parse_args(argv)
    cfg = load_config(flags.get("config"))
    settings = build_settings(flags, cfg)

    out = args[1] if len(args) > 1 else "work/design.svg"
    img_path = args[0] if len(args) > 0 else "Scavenger's_Daughter_by_the_dusty_druid.webp"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    img = load_image(img_path)
    scale = design_scale(img, settings)
    border = detect_border(img, scale, settings)
    palette = build_palette(img, scale, border, settings)
    clean_labels(img, scale, palette, settings)
    fill_colors, lw = order_colors(palette, settings)
    if border.circle is not None:
        circle_ring(img, scale, palette, border, fill_colors, settings)
    masks = build_masks(img, border, palette, fill_colors, lw, settings)
    outline_items, lw_cover = outline_satins(img, scale, masks, palette, lw, settings)
    masks = compensate_masks(masks, img, scale, border, palette, fill_colors,
                             lw_cover, settings)
    color_items, color_keep_lab, satinized_satins, satinized_polys = fill_components(
        img, scale, border, palette, masks, fill_colors, lw, lw_cover, settings)
    objs, stitch_index = order_objects(
        img, scale, palette, fill_colors, color_items, color_keep_lab,
        satinized_satins, outline_items, border, settings)

    if not objs:
        sys.exit("error: no stitchable objects produced (single-colour image, or every colour skipped via skip_colors?)")

    trim_after, n_trims = plan_trims(img, scale, objs, stitch_index, settings)
    emit_svg(out, objs, trim_after, img, scale, settings)
    write_preview(out, img, palette, settings)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
