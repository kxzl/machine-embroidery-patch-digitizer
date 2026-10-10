#!/usr/bin/env python3
"""Flag spots in a VP3 that are likely to jam a home machine.

Three checks, all on the sewn stitch list (0.1 mm units, converted to mm here):

  A  needle packing: needle points (STITCH records) within 1.5 mm of each
     needle point.  WARN when the maximum exceeds --max-points-15 (default 140,
     docs/EMBROIDERY_QUALITY.md section 4).
  B  thread per cell: length of every sewn segment (STITCH to STITCH, no TRIM,
     JUMP or COLOR_CHANGE between, at most 8 mm) summed into 1 mm cells.  Long
     segments are split into 0.25 mm pieces, each credited to its own cell.
     WARN when the busiest cell exceeds --max-thread-cell-mm (default 20).
  C  trim clusters: each TRIM sits at the last needle point before it.  Trims
     counted within --trim-cluster-mm (default 6) of each trim, the trim itself
     included.  WARN when any count reaches --trim-cluster-n (default 4).

Coordinates in the report are measured from the top-left corner of the design
bounding box (needle points), y downward, the same orientation as the preview.

Usage:
    jam_check.py <file.vp3> [--max-points-15 N] [--max-thread-cell-mm X]
                 [--trim-cluster-n N] [--trim-cluster-mm X] [--strict]

Exit status: 0 normally; 1 with --strict when any check WARNs; 2 when the file
cannot be read.
"""
import argparse
import math
import os
import sys

import numpy as np
import pystitch
from scipy.spatial import cKDTree

PACKING_RADIUS_MM = 1.5
MAX_SEGMENT_MM = 8.0
SPLIT_STEP_MM = 0.25
CELL_MM = 1.0
MAX_SPOTS = 5


def _read_records(path):
    """(x_mm, y_mm, cmd) arrays for every record, cmd masked with COMMAND_MASK."""
    p = pystitch.read(path)
    mask = pystitch.COMMAND_MASK
    n = len(p.stitches)
    xs = np.empty(n)
    ys = np.empty(n)
    cs = np.empty(n, dtype=np.int64)
    for i, s in enumerate(p.stitches):
        xs[i] = s[0] / 10.0
        ys[i] = s[1] / 10.0
        cs[i] = (s[2] & mask) if len(s) > 2 else pystitch.STITCH
    return xs, ys, cs


def _pick_spots(values, xs, ys, limit_radius, n_spots=MAX_SPOTS):
    """Greedy top-N by value; a spot within limit_radius of a chosen one is skipped."""
    order = np.argsort(-values, kind="stable")
    chosen = []
    for i in order:
        if len(chosen) >= n_spots:
            break
        if any(math.hypot(xs[i] - xs[j], ys[i] - ys[j]) < limit_radius
               for j in chosen):
            continue
        chosen.append(i)
    return [{"x": float(xs[i]), "y": float(ys[i]), "value": float(values[i])}
            for i in chosen]


def analyze(path, max_points_15=140, max_thread_cell_mm=20.0,
            trim_cluster_n=4, trim_cluster_mm=6.0):
    """Run the three jam checks on a VP3 file and return a dict of results.

    Never raises on empty designs or designs without trims.
    """
    rx, ry, rc = _read_records(path)
    stitch = rc == pystitch.STITCH
    trim = rc == pystitch.TRIM

    nx, ny = rx[stitch], ry[stitch]
    n_stitch = int(stitch.sum())
    n_trim = int(trim.sum())

    if n_stitch:
        min_x, min_y = float(nx.min()), float(ny.min())
        width = float(nx.max()) - min_x
        height = float(ny.max()) - min_y
    else:
        min_x = min_y = 0.0
        width = height = 0.0

    def top_left(x, y):
        return x - min_x, y - min_y

    # A: needle packing
    packing = {"ok": True, "max": 0, "limit": max_points_15, "spots": []}
    if n_stitch:
        pts = np.column_stack([nx, ny])
        tree = cKDTree(pts)
        counts = np.asarray(tree.query_ball_point(
            pts, r=PACKING_RADIUS_MM, return_length=True)) - 1
        worst = int(counts.max())
        packing["max"] = worst
        packing["ok"] = worst <= max_points_15
        if not packing["ok"]:
            spots = _pick_spots(counts.astype(float), nx, ny, PACKING_RADIUS_MM)
            packing["spots"] = [
                {"x": s["x"] - min_x, "y": s["y"] - min_y, "value": s["value"]}
                for s in spots]

    # B: thread per 1 mm cell
    thread = {"ok": True, "max_mm": 0.0, "limit": max_thread_cell_mm, "spots": []}
    if n_stitch >= 2:
        both = stitch[:-1] & stitch[1:]
        x0, y0 = rx[:-1][both], ry[:-1][both]
        x1, y1 = rx[1:][both], ry[1:][both]
        seg = np.hypot(x1 - x0, y1 - y0)
        keep = seg <= MAX_SEGMENT_MM
        x0, y0, x1, y1, seg = x0[keep], y0[keep], x1[keep], y1[keep], seg[keep]
        if seg.size:
            pieces = np.maximum(1, np.ceil(seg / SPLIT_STEP_MM).astype(np.int64))
            total = int(pieces.sum())
            idx = np.repeat(np.arange(seg.size), pieces)
            starts = np.cumsum(pieces) - pieces
            j = np.arange(total) - starts[idx]
            t = (j + 0.5) / pieces[idx]
            mx = x0[idx] + t * (x1 - x0)[idx]
            my = y0[idx] + t * (y1 - y0)[idx]
            piece_len = (seg / pieces)[idx]
            cx = np.floor((mx - min_x) / CELL_MM).astype(np.int64)
            cy = np.floor((my - min_y) / CELL_MM).astype(np.int64)
            n_cy = int(cy.max()) + 1
            key = cx * n_cy + cy
            uniq, inv = np.unique(key, return_inverse=True)
            sums = np.bincount(inv, weights=piece_len)
            worst = float(sums.max())
            thread["max_mm"] = worst
            thread["ok"] = worst <= max_thread_cell_mm
            if not thread["ok"]:
                cell_x = (uniq // n_cy) * CELL_MM + CELL_MM / 2.0
                cell_y = (uniq % n_cy) * CELL_MM + CELL_MM / 2.0
                spots = _pick_spots(sums, cell_x, cell_y, 2.0)
                thread["spots"] = spots

    # C: trim clusters
    trims = {"ok": True, "max": 0, "limit_n": trim_cluster_n,
             "radius_mm": trim_cluster_mm, "spots": [], "cuts": 0}
    if n_trim:
        last_needle = np.full(len(rc), -1, dtype=np.int64)
        cur = -1
        for i in range(len(rc)):
            last_needle[i] = cur
            if rc[i] == pystitch.STITCH:
                cur = i
        # consecutive TRIMs with no needle point between them are one cut:
        # several records share one last-needle index, so count each index once
        src = []
        for i in np.nonzero(trim)[0]:
            k = last_needle[i]
            src.append(k if k >= 0 else i)
        src = sorted(set(src))
        tpts = np.column_stack([rx[src], ry[src]])
        ttree = cKDTree(tpts)
        tcounts = np.asarray(ttree.query_ball_point(
            tpts, r=trim_cluster_mm, return_length=True))
        worst = int(tcounts.max())
        trims["max"] = worst
        trims["cuts"] = len(src)
        trims["ok"] = worst < trim_cluster_n
        if not trims["ok"]:
            spots = _pick_spots(tcounts.astype(float), tpts[:, 0], tpts[:, 1],
                                trim_cluster_mm)
            trims["spots"] = [
                {"x": s["x"] - min_x, "y": s["y"] - min_y, "value": s["value"]}
                for s in spots]

    warn = not (packing["ok"] and thread["ok"] and trims["ok"])
    return {
        "file": os.path.basename(path),
        "design_mm": [width, height],
        "stitches": n_stitch,
        "trims": n_trim,
        "packing": packing,
        "thread": thread,
        "trim_clusters": trims,
        "warn": warn,
    }


def _spot_lines(spots, unit, digits=1):
    out = []
    for s in spots:
        out.append(f"      {s['x']:.1f}, {s['y']:.1f} mm: "
                   f"{s['value']:.{digits}f} {unit}")
    return out


def format_report(res):
    w, h = res["design_mm"]
    lines = [f"{res['file']}: {w:.1f} x {h:.1f} mm, "
             f"{res['stitches']} stitches, {res['trims']} trims"]
    pk = res["packing"]
    lines.append(
        f"A needle packing: {'OK' if pk['ok'] else 'WARN'} "
        f"max {pk['max']} points within {PACKING_RADIUS_MM:g} mm "
        f"(limit {pk['limit']})")
    if not pk["ok"]:
        lines += _spot_lines(pk["spots"], "points", digits=0)
    th = res["thread"]
    lines.append(
        f"B thread per cell: {'OK' if th['ok'] else 'WARN'} "
        f"max {th['max_mm']:.1f} mm in a {CELL_MM:g} mm cell "
        f"(limit {th['limit']:g} mm)")
    if not th["ok"]:
        lines += _spot_lines(th["spots"], "mm of thread")
    tc = res["trim_clusters"]
    lines.append(
        f"C trim clusters: {'OK' if tc['ok'] else 'WARN'} "
        f"max {tc['max']} cuts within {tc['radius_mm']:g} mm "
        f"(WARN at {tc['limit_n']}; {tc['cuts']} cut points)")
    if not tc["ok"]:
        lines += _spot_lines(tc["spots"], "trims", digits=0)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vp3", help="machine file to check")
    ap.add_argument("--max-points-15", type=int, default=140, dest="max_points_15",
                    help="WARN above this many needle points in 1.5 mm (default 140)")
    ap.add_argument("--max-thread-cell-mm", type=float, default=20.0,
                    dest="max_thread_cell_mm",
                    help="WARN above this thread length in one 1 mm cell (default 20)")
    ap.add_argument("--trim-cluster-n", type=int, default=4, dest="trim_cluster_n",
                    help="WARN when this many trims lie in one radius (default 4)")
    ap.add_argument("--trim-cluster-mm", type=float, default=6.0,
                    dest="trim_cluster_mm",
                    help="trim cluster radius in mm (default 6)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any check WARNs")
    a = ap.parse_args(argv)

    try:
        res = analyze(a.vp3, max_points_15=a.max_points_15,
                      max_thread_cell_mm=a.max_thread_cell_mm,
                      trim_cluster_n=a.trim_cluster_n,
                      trim_cluster_mm=a.trim_cluster_mm)
    except Exception as e:  # unreadable file: report, do not traceback
        print(f"jam_check: cannot read {a.vp3}: {e}", file=sys.stderr)
        return 2
    print(format_report(res))
    if a.strict and res["warn"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
