#!/usr/bin/env python3
"""Draw the travel of a machine file so exposed jumps are obvious.

Cyan = trimmed travel (a cut, then a move somewhere new).  Red = untrimmed moves
longer than ``--red-mm`` (default 5 mm).  In VP3 there is no jump command, so a
red move is thread that is actually *sewn* on top of the design.

Satin fans are red legitimately: where a rail satin turns a tip the cross-stitches
get long and look like travel.  A move counts as a satin cross-stitch when a
neighbouring move at least 0.4x its length doubles back (cos < -0.5); the report
prints the count of red moves that are **not** satin cross-stitches -- that is
"exposed travel", the number the regression gate cares about.

Usage:
    travelmap.py <file.vp3> <out.png> [--red-mm 5] [--trim-mm 2] [--width 1600]
"""
import argparse
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vp3", help="machine file to inspect")
    ap.add_argument("out", help="output travel map PNG")
    ap.add_argument("--red-mm", type=float, default=5.0, dest="red_mm",
                    help="untrimmed move length that is drawn red (default 5)")
    ap.add_argument("--trim-mm", type=float, default=2.0, dest="trim_mm",
                    help="trimmed travel shorter than this is not drawn cyan (default 2)")
    ap.add_argument("--width", type=int, default=1600, help="image width in px (default 1600)")
    a = ap.parse_args()

    import pystitch
    from PIL import Image, ImageDraw

    p = pystitch.read(a.vp3)
    M = pystitch.COMMAND_MASK
    recs = [(s[0], s[1], s[2] & M if len(s) > 2 else pystitch.STITCH)
            for s in p.stitches]

    # contiguous STITCH->STITCH moves, indexed by the start record
    moves = {}
    for k in range(len(recs) - 1):
        if recs[k][2] == pystitch.STITCH and recs[k + 1][2] == pystitch.STITCH:
            dx = (recs[k + 1][0] - recs[k][0]) / 10.0
            dy = (recs[k + 1][1] - recs[k][1]) / 10.0
            moves[k] = (dx, dy, math.hypot(dx, dy))

    def doubles_back(k):
        """True when move k continues a satin zigzag instead of travelling."""
        here = moves.get(k)
        if here is None or here[2] <= 0:
            return False
        hx, hy, hl = here
        for j in (k - 1, k + 1):
            nb = moves.get(j)
            if nb is None:
                continue
            nx, ny, nl = nb
            if nl < 0.4 * hl:
                continue
            if (hx * nx + hy * ny) / (hl * nl) < -0.5:
                return True
        return False

    xs = [r[0] for r in recs]
    ys = [r[1] for r in recs]
    x0, y0 = min(xs), min(ys)
    sc = a.width / (max(xs) - x0) if max(xs) > x0 else 1.0
    im = Image.new("RGB", (a.width, int((max(ys) - y0) * sc) + 1), "black")
    d = ImageDraw.Draw(im)
    prev = None
    prev_idx = None
    after_trim = False
    nt = nl = 0
    lens = []
    red_starts = []
    for k, (x, y, c) in enumerate(recs):
        if c == pystitch.TRIM:
            after_trim = True
            continue
        if c == pystitch.COLOR_CHANGE:
            after_trim = True
            continue
        if c not in (pystitch.STITCH, pystitch.JUMP):
            continue
        if prev is not None:
            L = math.hypot(x - prev[0], y - prev[1]) / 10
            q = [((prev[0] - x0) * sc, (prev[1] - y0) * sc),
                 ((x - x0) * sc, (y - y0) * sc)]
            if after_trim and L > a.trim_mm:
                d.line(q, fill=(0, 220, 255), width=2)
                nt += 1
                lens.append(L)
            elif L > a.red_mm:
                d.line(q, fill=(255, 60, 60), width=2)
                nl += 1
                red_starts.append(prev_idx)
            else:
                d.line(q, fill=(80, 80, 80), width=1)
        prev = (x, y)
        prev_idx = k
        after_trim = False
    im.save(a.out)
    lens.sort()
    exposed = sum(1 for k in red_starts if not doubles_back(k))
    print(f"{a.vp3}: {nt} trimmed travel moves (cyan) "
          f"median {lens[len(lens) // 2] if lens else 0:.1f} "
          f"max {lens[-1] if lens else 0:.1f} mm; "
          f"{nl} untrimmed moves >{a.red_mm:g}mm (red); "
          f"exposed travel >{a.red_mm:g}mm (red, not satin): {exposed}")


if __name__ == "__main__":
    main()
