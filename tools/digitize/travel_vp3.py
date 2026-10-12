#!/usr/bin/env python3
"""Replace cut-and-jump travel with a running stitch hidden under later stitching.

Every TRIM costs the machine a cut, a thread tail to catch, lock stitches and a
restart, and each one is a chance for a thread break or a bird's nest.  Where
the next object has the same colour and a later layer (a different-colour fill,
an outline satin or the border) will be sewn over the way between the two, the
needle can run there instead: a chain of short stitches under the later layer.
The thread is never cut and the run is not seen.

Per same-colour TRIM -> STITCH pair in a VP3 the pass:

  0. removes the TRIM outright when E and S are at most ``hop_mm`` apart (the
     never-cut floor, ``trim.min_mm`` in the YAML, default 2 mm); nothing needs
     hiding for a hop that short;
  1. takes the exit point E (stitch before the TRIM) and the entry point S
     (stitch after it) from the file, not from a model of where Ink/Stitch
     leaves a fill;
  2. rasterises everything sewn AFTER the TRIM (0.2 mm cells, thread width
     0.4 mm), closes the gaps between fill rows and keeps only cells at least
     ``margin_mm`` inside that cover.  A single thread, a long travel stitch or
     a thin outline does not count as cover;
  3. counts only cover that is not lighter than the travel thread, so a dark run
     is never put under a light fill it would show through.  With
     ``surface: same_colour`` the stitching of the same colour block sewn
     BEFORE the TRIM counts too (a run lying on satin of its own colour);
  4. finds the shortest route through the cover from E to S (a short straight
     connector of at most ``snap_mm`` joins E and S to it, because E sits on the
     edge of the object just sewn);
  5. replaces the TRIM with stitches of at most ``stitch_mm`` along that route.
     No route, a route longer than ``max_mm`` or an exposed endpoint keeps the
     TRIM.

Ink/Stitch's tie-off and tie-in lock stitches around the old TRIM stay in the
file.  Nothing is added at a colour change; those cuts are the machine's.

Run it before ``trim_vp3.py``: that pass is the safety net for whatever is left.

Usage:
    travel_vp3.py <file.vp3> [--max-mm N] [--snap-mm N] [--margin-mm N]
                  [--stitch-mm N] [--hop-mm N] [--surface later|same_colour]
                  [--config F] [--dry-run]

``--config`` reads the ``travel:`` section of the per-image YAML (``enabled``,
``max_mm``, ``snap_mm``, ``margin_mm``, ``stitch_mm``, ``surface``) and
``trim: min_mm`` for ``--hop-mm``; flags win over it.
Exit status 0 always; prints how many trims it turned into runs and why the
others stayed.
"""
import argparse
import math
import sys
from collections import Counter

import numpy as np
import pystitch
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage import color
from skimage.graph import route_through_array

UNIT_MM = 0.1            # one VP3 coordinate unit
RES_MM = 0.2             # raster cell
THREAD_MM = 0.4          # drawn width of a sewn stitch
COVER_SEG_MAX_MM = 12.0  # longer sewn moves are travel, not cover
LIGHTER_TOL = 15.0       # L* a covering thread may exceed the travel thread by
CHORD_SLACK_MM = 0.15    # a run stitch may cut a corner this far inside the route margin
MIN_STITCH_MM = 0.5      # no run stitch shorter than this

COLOUR_CHANGE = "colour change or end"
SURFACES = ("later", "same_colour")
DEFAULTS = {"max_mm": 60.0, "snap_mm": 1.5, "margin_mm": 0.5, "stitch_mm": 2.5,
            "hop_mm": 2.0, "surface": "later"}
_NUMERIC_KEYS = ("max_mm", "snap_mm", "margin_mm", "stitch_mm", "hop_mm")


def cmd_of(s):
    return s[2] & pystitch.COMMAND_MASK if len(s) > 2 else pystitch.STITCH


def block_lightness(pattern, n_blocks):
    """L* of each colour block's thread (50 when the file has no thread for it)."""
    out = []
    for i in range(n_blocks):
        try:
            c = int(pattern.get_thread_or_filler(i).color)
        except (AttributeError, TypeError, ValueError):
            out.append(50.0)
            continue
        rgb = np.array([[[(c >> 16) & 255, (c >> 8) & 255, c & 255]]], dtype=float) / 255.0
        out.append(float(color.rgb2lab(rgb)[0, 0, 0]))
    return out


def _disc(radius_cells):
    r = int(math.ceil(radius_cells))
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= radius_cells * radius_cells


def plan_travel(stitches, lightness, params):
    """Plan a run for every eligible TRIM.

    ``stitches`` is the pystitch list ([x, y, cmd], 0.1 mm); ``lightness`` the L*
    of each colour block.  Returns ``(plans, kept, hops)``: ``plans`` maps the
    index of a TRIM to the run's points (VP3 units, exit connector to entry
    connector; empty for a hop), ``hops`` is the set of TRIMs removed because
    exit and entry are at most ``hop_mm`` apart, and ``kept`` maps the index of
    a TRIM that stays to the reason.
    """
    n = len(stitches)
    p = {**DEFAULTS, **params}
    cmds = [cmd_of(s) for s in stitches]
    block_of, b = [], 0
    for c in cmds:
        if c == pystitch.COLOR_CHANGE:
            b += 1
        block_of.append(b)
    n_blocks = b + 1

    xs = [s[0] for s in stitches]
    ys = [s[1] for s in stitches]
    x0 = min(xs) - 50
    y0 = min(ys) - 50
    cell = RES_MM / UNIT_MM                      # VP3 units per cell
    W = int((max(xs) - x0) / cell) + 52
    H = int((max(ys) - y0) / cell) + 52
    line_w = max(1, int(round(THREAD_MM / RES_MM)))

    def to_cell(x, y):
        return (int(round((x - x0) / cell)), int(round((y - y0) / cell)))

    def sewn_segment(k):
        """The segment k -> k+1 as cell coordinates when it is sewn cover, else None."""
        if cmds[k] != pystitch.STITCH or k + 1 >= n or cmds[k + 1] != pystitch.STITCH:
            return None
        a, bb = stitches[k], stitches[k + 1]
        if math.hypot(bb[0] - a[0], bb[1] - a[1]) * UNIT_MM > COVER_SEG_MAX_MM:
            return None
        return [to_cell(a[0], a[1]), to_cell(bb[0], bb[1])]

    plans, kept, hops = {}, {}, set()
    todo = {}                                    # TRIM index -> crop box
    pad = int(math.ceil((p["max_mm"] / 2 + 2.0) / RES_MM))
    for k in range(n):
        if cmds[k] != pystitch.TRIM:
            continue
        if not (0 < k < n - 1 and cmds[k - 1] == pystitch.STITCH
                and cmds[k + 1] == pystitch.STITCH):
            kept[k] = COLOUR_CHANGE
            continue
        E, S = stitches[k - 1], stitches[k + 1]
        straight = math.hypot(S[0] - E[0], S[1] - E[1]) * UNIT_MM
        if straight <= p["hop_mm"]:
            plans[k] = []
            hops.add(k)
        elif straight > p["max_mm"]:
            kept[k] = "too far"
        else:
            ec, sc = to_cell(E[0], E[1]), to_cell(S[0], S[1])
            todo[k] = (max(min(ec[0], sc[0]) - pad, 0), max(min(ec[1], sc[1]) - pad, 0),
                       min(max(ec[0], sc[0]) + pad + 1, W), min(max(ec[1], sc[1]) + pad + 1, H))

    # same-colour surface: what the TRIM's own colour block has sewn BEFORE it
    earlier = {}
    if p["surface"] == "same_colour" and todo:
        fwd = [Image.new("L", (W, H), 0) for _ in range(n_blocks)]
        fwd_draw = [ImageDraw.Draw(m) for m in fwd]
        for k in range(n):
            if k in todo:
                earlier[k] = np.asarray(fwd[block_of[k]].crop(todo[k]), dtype=bool)
            seg = sewn_segment(k)
            if seg:
                fwd_draw[block_of[k]].line(seg, fill=1, width=line_w)
        del fwd, fwd_draw

    # cover: everything sewn AFTER the TRIM, built by sweeping backwards
    masks = [Image.new("L", (W, H), 0) for _ in range(n_blocks)]
    draws = [ImageDraw.Draw(m) for m in masks]
    snap_cells = p["snap_mm"] / RES_MM
    closing = _disc(1.0)
    for k in range(n - 1, -1, -1):
        seg = sewn_segment(k)
        if seg:
            draws[block_of[k]].line(seg, fill=1, width=line_w)
            continue
        if k not in todo:
            continue
        reason, pts = _route(masks, block_of[k], lightness, stitches[k - 1], stitches[k + 1],
                             to_cell, x0, y0, todo[k], snap_cells, closing, p, earlier.get(k))
        if pts is None:
            kept[k] = reason
        else:
            plans[k] = pts
    return plans, kept, hops


def _route(masks, block, lightness, E, S, to_cell, x0, y0, box, snap_cells, closing, p,
           earlier=None):
    """(reason, None) when no hidden route exists, else (None, run points)."""
    cell = RES_MM / UNIT_MM
    left, top, right, bottom = box
    ec, sc = to_cell(E[0], E[1]), to_cell(S[0], S[1])
    cover = earlier.copy() if earlier is not None else None
    for b, m in enumerate(masks):
        if b < block or lightness[b] > lightness[block] + LIGHTER_TOL:
            continue
        a = np.asarray(m.crop(box), dtype=bool)
        cover = a if cover is None else (cover | a)
    if cover is None or not cover.any():
        return "nothing sewn over it", None
    closed = ndimage.binary_closing(cover, structure=closing)
    dist = ndimage.distance_transform_edt(closed) * RES_MM
    allowed = dist >= p["margin_mm"]
    if not allowed.any():
        return "cover too thin", None

    # nearest allowed cell for every cell: joins E and S to the cover
    gap, idx = ndimage.distance_transform_edt(~allowed, return_indices=True)
    e = (ec[1] - top, ec[0] - left)
    s = (sc[1] - top, sc[0] - left)
    if gap[e] > snap_cells:
        return "exit not under cover", None
    if gap[s] > snap_cells:
        return "entry not under cover", None
    e_cell = (int(idx[0][e]), int(idx[1][e]))
    s_cell = (int(idx[0][s]), int(idx[1][s]))

    cost = np.where(allowed, 1.0 + 2.0 * (dist < 0.8), np.inf)
    try:
        path, _ = route_through_array(cost, e_cell, s_cell, fully_connected=True,
                                      geometric=True)
    except ValueError:
        return "no route under cover", None
    path = np.asarray(path, dtype=float)
    length = float(np.hypot(*np.diff(path, axis=0).T).sum()) * RES_MM
    length += (gap[e] + gap[s]) * RES_MM
    if length > p["max_mm"]:
        return "route too long", None

    run = _resample(path, dist, p["stitch_mm"], max(p["margin_mm"] - CHORD_SLACK_MM, 0.05))
    out = []
    for r, c in run:
        out.append((x0 + (c + left) * cell, y0 + (r + top) * cell))
    return None, _drop_close(out, E, S)


def _resample(path, dist, stitch_mm, chord_margin_mm):
    """Greedy stitches of at most ``stitch_mm`` along ``path``.

    A stitch may cut a corner, but never closer than ``chord_margin_mm`` to the
    uncovered cells, so a larger route margin is not undone by corner cutting.
    """
    max_cells = stitch_mm / RES_MM
    ok = dist >= chord_margin_mm
    out = [tuple(path[0])]
    i, last = 0, len(path) - 1
    while i < last:
        j = i + 1
        for cand in range(min(last, i + int(math.ceil(max_cells * 1.5))), i, -1):
            d = float(np.hypot(*(path[cand] - path[i])))
            if d > max_cells:
                continue
            steps = max(2, int(d * 2))
            t = np.linspace(0.0, 1.0, steps + 1)
            rr = np.rint(path[i, 0] + t * (path[cand, 0] - path[i, 0])).astype(int)
            cc = np.rint(path[i, 1] + t * (path[cand, 1] - path[i, 1])).astype(int)
            if ok[rr, cc].all():
                j = cand
                break
        out.append(tuple(path[j]))
        i = j
    return out


def _drop_close(points, E, S):
    """Drop run points closer than MIN_STITCH_MM to the previous stitch."""
    kept = []
    prev = (E[0], E[1])
    for x, y in points:
        if math.hypot(x - prev[0], y - prev[1]) * UNIT_MM >= MIN_STITCH_MM:
            kept.append((x, y))
            prev = (x, y)
    while kept and math.hypot(S[0] - kept[-1][0], S[1] - kept[-1][1]) * UNIT_MM < MIN_STITCH_MM:
        kept.pop()
    return kept


def apply_plans(stitches, plans):
    """New stitch list: each planned TRIM replaced by its run stitches."""
    out = []
    for k, s in enumerate(stitches):
        if k in plans:
            out.extend([int(round(x)), int(round(y)), pystitch.STITCH] for x, y in plans[k])
            continue
        out.append(s)
    return out


def run_length_mm(points, E, S):
    chain = [(E[0], E[1])] + list(points) + [(S[0], S[1])]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(chain, chain[1:])) * UNIT_MM


def _body(stitches):
    """The stitch list without trailing TRIM/END records (the writer adds its own)."""
    end = len(stitches)
    while end and cmd_of(stitches[end - 1]) != pystitch.STITCH:
        end -= 1
    return stitches[:end]


def matches(expected, actual):
    """True when two stitch lists have the same commands and positions within 0.2 mm.

    pystitch moves a colour-block-start JUMP by one unit on write, so exact
    equality would reject every file.
    """
    expected, actual = _body(expected), _body(actual)
    if len(expected) != len(actual):
        return False
    return all(cmd_of(a) == cmd_of(b) and abs(a[0] - b[0]) <= 2 and abs(a[1] - b[1]) <= 2
               for a, b in zip(expected, actual))


def load_config(path):
    """``(travel section, trim.min_mm)`` from a per-image YAML ({}, None when absent)."""
    if not path:
        return {}, None
    import yaml
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"travel_vp3: cannot read config {path}: {exc}")
        return {}, None
    if not isinstance(cfg, dict):
        return {}, None
    section = cfg.get("travel") or {}
    if not isinstance(section, dict):
        print("travel_vp3: ignoring non-mapping 'travel:' in config")
        section = {}
    trim = cfg.get("trim")
    return section, (trim.get("min_mm") if isinstance(trim, dict) else None)


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vp3")
    ap.add_argument("--max-mm", type=float, dest="max_mm")
    ap.add_argument("--snap-mm", type=float, dest="snap_mm")
    ap.add_argument("--margin-mm", type=float, dest="margin_mm")
    ap.add_argument("--stitch-mm", type=float, dest="stitch_mm")
    ap.add_argument("--hop-mm", type=float, dest="hop_mm",
                    help="remove a trim whose exit and entry are this close (default: "
                         "trim.min_mm of --config, else 2)")
    ap.add_argument("--surface", dest="surface",
                    help="'later' (default): only stitching sewn after the trim hides a run; "
                         "'same_colour': earlier stitching of the same colour block counts too")
    ap.add_argument("--config")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, do not write the file")
    return ap.parse_args(argv)


def build_params(args, section, trim_min_mm=None):
    params = dict(DEFAULTS)
    for key in _NUMERIC_KEYS:
        val = getattr(args, key)
        if val is None:
            val = section.get(key)
        if val is None and key == "hop_mm":
            val = trim_min_mm
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            print(f"travel_vp3: ignoring non-numeric {key}")
            continue
        if val < 0 or (val == 0 and key != "hop_mm"):
            print(f"travel_vp3: ignoring non-positive {key}")
            continue
        params[key] = val
    surface = args.surface if args.surface is not None else section.get("surface")
    if surface is not None:
        if surface in SURFACES:
            params["surface"] = surface
        else:
            print(f"travel_vp3: ignoring unknown surface {surface!r} (use {' or '.join(SURFACES)})")
    return params


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    section, trim_min_mm = load_config(args.config)
    if section.get("enabled") is False:
        print("travel_vp3: disabled by config (travel.enabled: false)")
        return 0
    params = build_params(args, section, trim_min_mm)

    pattern = pystitch.read(args.vp3)
    stitches = pattern.stitches
    n_trims = sum(1 for s in stitches if cmd_of(s) == pystitch.TRIM)
    if not n_trims:
        print("travel_vp3: no trims, nothing to do")
        return 0
    n_blocks = 1 + sum(1 for s in stitches if cmd_of(s) == pystitch.COLOR_CHANGE)
    plans, kept, hops = plan_travel(stitches, block_lightness(pattern, n_blocks), params)

    machine = sum(1 for why in kept.values() if why == COLOUR_CHANGE)
    eligible = n_trims - machine
    runs = {k: v for k, v in plans.items() if k not in hops}
    added = sum(len(v) for v in runs.values())
    run_mm = sum(run_length_mm(v, stitches[k - 1], stitches[k + 1]) for k, v in runs.items())
    print(f"travel_vp3: {len(runs)} of {eligible} same-colour trim(s) turned into a run under "
          f"later stitching (+{added} stitches, {run_mm:.0f} mm of run)")
    if hops:
        print(f"  {len(hops)} trim(s) between points at most {params['hop_mm']:g} mm apart "
              f"dropped, no run needed")
    why = Counter(v for v in kept.values() if v != COLOUR_CHANGE)
    if why:
        print("  kept: " + ", ".join(f"{v} {k}" for k, v in why.most_common()))
    if machine:
        print(f"  {machine} trim(s) at colour changes or the end are the machine's and stay")
    if plans and not args.dry_run:
        with open(args.vp3, "rb") as fh:
            original = fh.read()
        new = apply_plans(stitches, plans)
        pattern.stitches = new
        pystitch.write(pattern, args.vp3)
        if not matches(new, pystitch.read(args.vp3).stitches):
            with open(args.vp3, "wb") as fh:
                fh.write(original)
            print("travel_vp3: WARNING the rewritten file did not read back the same; "
                  "original restored, trims left as they were")
    return 0


if __name__ == "__main__":
    sys.exit(main())
