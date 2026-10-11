"""A small outline loop must not become a satin column (vectorize.py -> SVG, no Ink/Stitch export).

Two offset rails of a loop narrower than the satin cross, and Ink/Stitch then dies in
`flattened_sections` with "tuple index out of range", which aborts the whole VP3 export.

Run: .venv/bin/python -m unittest tools/digitize/tests/test_satin_loops.py -v
"""
import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vectorize  # noqa: E402

CFG = "palette: ['#d8be8e', '#111111']\nborder:\n  mode: force_black\n"


def rings_png(path, r_out, r_in):
    """Disc with two dark rings; the picture is 6 px per mm at --size-mm 60."""
    size = 400
    yy, xx = np.mgrid[0:size, 0:size].astype(float)
    img = np.zeros((size, size, 4), np.uint8)
    inside = np.hypot(xx - 200, yy - 200) < 180
    img[inside] = (0xD8, 0xBE, 0x8E, 255)
    for cx, cy in [(150, 150), (250, 250)]:
        d = np.hypot(xx - cx, yy - cy)
        img[(d < r_out) & (d >= r_in) & inside] = (17, 17, 17, 255)
    Image.fromarray(img, "RGBA").save(path)


def run(r_out, r_in):
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "rings.png"
        rings_png(png, r_out, r_in)
        cfg = Path(tmp) / "cfg.yaml"
        cfg.write_text(CFG)
        out = Path(tmp) / "out.svg"
        with contextlib.redirect_stdout(io.StringIO()) as log:
            vectorize.main(["--size-mm", "60", "--config", str(cfg), str(png), str(out)])
        return out.read_text(), log.getvalue()


def satins(svg):
    return len(re.findall(r'<path id="s\d+"[^>]*inkstitch:satin_column="true"', svg))


class SatinLoopTests(unittest.TestCase):
    def test_small_ring_is_not_a_satin(self):
        svg, log = run(12, 6)
        self.assertIn("2 loop(s)", log)
        self.assertEqual(satins(svg), 1)       # the border only

    def test_larger_ring_keeps_its_satin(self):
        svg, log = run(16, 9)
        self.assertNotIn("loop(s)", log)
        self.assertEqual(satins(svg), 3)       # the border and both rings


if __name__ == "__main__":
    unittest.main()
