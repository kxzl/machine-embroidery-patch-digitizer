"""Measure a VP3 with pystitch: stitched extent, stitch count, thread colours in sewing order."""
from __future__ import annotations

from pathlib import Path

from .core import Measure


def measure(path: Path) -> Measure:
    import pystitch

    pattern = pystitch.read(str(path))
    x0, y0, x1, y1 = pattern.bounds()   # units of 0.1 mm
    changes = sum(1 for s in pattern.stitches
                  if len(s) > 2 and (s[2] & pystitch.COMMAND_MASK) == pystitch.COLOR_CHANGE)
    threads = []
    for i in range(changes + 1):
        thread = pattern.get_thread_or_filler(i)
        threads.append(thread.hex_color() if hasattr(thread, "hex_color") else str(thread))
    return Measure(width10=int(round(x1 - x0)), height10=int(round(y1 - y0)),
                   stitches=pattern.count_stitches(), color_changes=changes, threads=threads)
