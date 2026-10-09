#!/usr/bin/env python3
"""Insert TRIM commands before long un-trimmed travel moves in a VP3.

Ink/Stitch writes jumps as long stitches and only cuts where the SVG asked.
It does add tie-off/tie-in lock stitches around any gap longer than
``collapse_len`` (3 mm), so a long move is already secured at both ends -- it
just needs the trim.  This pass inserts a TRIM at the stitch before any move
longer than ``threshold_mm`` that is not already preceded by a trim.

A satin column's cross-stitches are not travel.  Where a rail satin turns a
tight tip the two rails pinch, Ink/Stitch fans the cross-stitches and they get
long: on the Scavenger's Daughter artwork 393 of them exceed 8 mm and reach
15.2 mm, every one with both ends still on the 3.3 mm border band.  Cutting
there converted each into a trim plus an unsewn jump and left the horns, claws
and spikes bare.  The fan is an alternating run, so a long move whose
neighbour is comparably long and doubles back (angle > 120 deg) is a satin
cross-stitch and is left alone; a travel move goes somewhere new and is cut.

Usage:
    trim_vp3.py <file.vp3> [threshold_mm]

Exit status 0 always; prints how many trims it inserted.

Do not rewrite colour-block starts here.  pystitch reads every VP3 block start
back as a JUMP at the previous block's end followed by a long STITCH to the new
block's first point; that is how the format stores the block header, not sewn
thread.  Moving the JUMP/COLOR_CHANGE was tried and displaced whole blocks by
up to 11 mm on read-back (the goat's amber eyes landed on its cheek).
"""
import math
import sys

import pystitch

path = sys.argv[1]
threshold_mm = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
# a satin cross-stitch is only ever as long as the band it crosses, so its
# partner in the zigzag is at least half the threshold long
SATIN_PAIR_MM = threshold_mm * 0.5
SATIN_TURN_DEG = 120.0

pattern = pystitch.read(path)
stitches = pattern.stitches


def cmd_of(s):
    return s[2] & pystitch.COMMAND_MASK if len(s) > 2 else pystitch.STITCH


def move(k):
    """(dx, dy, length_mm) of the stitch run from k to k+1, or None."""
    if k < 0 or k + 1 >= len(stitches):
        return None
    if cmd_of(stitches[k]) != pystitch.STITCH or cmd_of(stitches[k + 1]) != pystitch.STITCH:
        return None
    a, b = stitches[k], stitches[k + 1]
    dx = (b[0] - a[0]) / 10.0
    dy = (b[1] - a[1]) / 10.0
    return dx, dy, math.hypot(dx, dy)


def doubles_back(k):
    """True when move k continues a satin zigzag instead of travelling."""
    here = move(k)
    if here is None or here[2] < SATIN_PAIR_MM:
        return False
    hx, hy, hl = here
    for j in (k - 1, k + 1):
        nb = move(j)
        if nb is None or nb[2] < SATIN_PAIR_MM:
            continue
        nx, ny, nl = nb
        cos = (hx * nx + hy * ny) / (hl * nl)
        if cos < math.cos(math.radians(SATIN_TURN_DEG)):
            return True
    return False


out = []
inserted = 0
skipped = 0

for k, stitch in enumerate(stitches):
    cmd = cmd_of(stitch)
    if cmd == pystitch.STITCH and out and not doubles_back(k - 1):
        prev = out[-1]
        if cmd_of(prev) != pystitch.TRIM:
            length = ((stitch[0] - prev[0]) ** 2 + (stitch[1] - prev[1]) ** 2) ** 0.5 / 10.0
            if length > threshold_mm:
                out.append([prev[0], prev[1], pystitch.TRIM])
                inserted += 1
    out.append(stitch)

# count how many over-threshold moves the satin rule protected
for k in range(len(stitches) - 1):
    m = move(k)
    if m and m[2] > threshold_mm and doubles_back(k):
        skipped += 1

if inserted:
    pattern.stitches = out
    pystitch.write(pattern, path)
print(f"trim_vp3: inserted {inserted} trim(s) (untrimmed travel > {threshold_mm:g} mm; "
      f"{skipped} satin cross-stitch(es) of that length left intact)")
