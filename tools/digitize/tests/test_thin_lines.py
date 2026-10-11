"""Tests for the `thin_lines` option (vectorize.py -> SVG, no Ink/Stitch export).

Run: .venv/bin/python -m unittest tools/digitize/tests/test_thin_lines.py -v
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

PALETTE = ["#d8be8e", "#111111"]
BASE_CFG = "palette: %s\nborder:\n  mode: force_black\n" % PALETTE
# the disc is 360 px across at --size-mm 60, so 6 px per mm: 3 px = 0.5 mm, 4 px = 0.67 mm, 9 px = 1.5 mm
LINES = [(100, 3), (200, 4), (300, 9)]


def lines_png(path):
    size = 400
    yy, xx = np.mgrid[0:size, 0:size].astype(float)
    img = np.zeros((size, size, 4), np.uint8)
    inside = np.hypot(xx - 200, yy - 200) < 180
    img[inside] = (0xD8, 0xBE, 0x8E, 255)
    for y, w in LINES:
        img[y - w // 2:y - w // 2 + w, 60:340][inside[y - w // 2:y - w // 2 + w, 60:340]] = (17, 17, 17, 255)
    Image.fromarray(img, "RGBA").save(path)


def outlines_group(svg):
    m = re.search(r'<g inkscape:label="Outline"[^>]*id="outlines">(.*?)</g>', svg, re.S)
    return m.group(1) if m else ""


def run(tmp, cfg_text):
    png = Path(tmp) / "lines.png"
    if not png.exists():
        lines_png(png)
    cfg = Path(tmp) / "cfg.yaml"
    cfg.write_text(cfg_text)
    out = Path(tmp) / "out.svg"
    with contextlib.redirect_stdout(io.StringIO()) as log:
        vectorize.main(["--size-mm", "60", "--config", str(cfg), str(png), str(out)])
    return out.read_text(), log.getvalue()


class ThinLinesTests(unittest.TestCase):
    def test_default_widens_every_line_to_satin(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, _ = run(tmp, BASE_CFG)
        og = outlines_group(svg)
        self.assertEqual(len(re.findall(r"satin_column", og)), len(re.findall(r"<path", og)))
        self.assertGreaterEqual(len(re.findall(r"satin_column", og)), 3)
        self.assertNotIn("bean_stitch_repeats", og)

    def test_widen_is_identical_to_no_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, _ = run(tmp, BASE_CFG)
            widen, _ = run(tmp, BASE_CFG + "thin_lines: widen\n")
        self.assertEqual(plain, widen)

    def test_run_mode_stitches_thin_lines_as_running_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, log = run(tmp, BASE_CFG + "thin_lines: run\n")
        og = outlines_group(svg)
        self.assertEqual(len(re.findall(r"bean_stitch_repeats", og)), 2)     # 0.5 mm and 0.67 mm
        self.assertEqual(len(re.findall(r"satin_column", og)), 1)            # the 1.5 mm line
        self.assertIn("2 thin running lines", log)

    def test_run_mode_leaves_no_fill_under_the_thin_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, _ = run(tmp, BASE_CFG)
            run_svg, _ = run(tmp, BASE_CFG + "thin_lines: run\n")
        n = lambda s: len(re.findall(r'<path id="f\d+" style="fill:#111111', s))
        self.assertLessEqual(n(run_svg), n(plain))

    def test_bad_value_is_ignored_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, _ = run(tmp, BASE_CFG)
            svg, log = run(tmp, BASE_CFG + "thin_lines: banana\n")
        self.assertIn("ignoring thin_lines", log)
        self.assertEqual(plain, svg)


if __name__ == "__main__":
    unittest.main()
