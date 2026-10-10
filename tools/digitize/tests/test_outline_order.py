"""Tests for `outline_order` and `trim: min_mm` (vectorize.py -> SVG, no Ink/Stitch export).

Run: .venv/bin/python -m unittest tools/digitize/tests/test_outline_order.py -v
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
BASE_CFG = ("palette: %s\nborder:\n  mode: force_black\nthin_lines: run\n" % PALETTE)


def grid_png(path):
    """A disc crossed by a 4 x 4 grid of thin black lines: a connected outline network."""
    size = 400
    yy, xx = np.mgrid[0:size, 0:size].astype(float)
    img = np.zeros((size, size, 4), np.uint8)
    inside = np.hypot(xx - 200, yy - 200) < 180
    img[inside] = (0xD8, 0xBE, 0x8E, 255)
    for c in (95, 150, 205, 260):
        img[c:c + 4, 40:360][inside[c:c + 4, 40:360]] = (17, 17, 17, 255)
        img[40:360, c:c + 4][inside[40:360, c:c + 4]] = (17, 17, 17, 255)
    Image.fromarray(img, "RGBA").save(path)


def run(tmp, extra_cfg=""):
    png = Path(tmp) / "grid.png"
    if not png.exists():
        grid_png(png)
    cfg = Path(tmp) / "cfg.yaml"
    cfg.write_text(BASE_CFG + extra_cfg)
    out = Path(tmp) / "out.svg"
    with contextlib.redirect_stdout(io.StringIO()) as log:
        vectorize.main(["--size-mm", "60", "--config", str(cfg), str(png), str(out)])
    return out.read_text(), log.getvalue()


def outline_trims(svg):
    g = re.search(r'<g inkscape:label="Outline"[^>]*id="outlines">(.*?)</g>', svg, re.S).group(1)
    return len(re.findall(r'trim_after="true"', g)), len(re.findall(r"<path", g))


class OutlineOrderTests(unittest.TestCase):
    def test_default_is_unchanged_by_the_new_keys_being_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, _ = run(tmp)
            b, _ = run(tmp, "outline_order: centroid\ntrim:\n  min_mm: 2.0\n")
        self.assertEqual(a, b)

    def test_endpoint_order_never_adds_trims_and_cuts_fewer_here(self):
        with tempfile.TemporaryDirectory() as tmp:
            c_svg, _ = run(tmp)
            e_svg, _ = run(tmp, "outline_order: endpoint\n")
        (ct, cn), (et, en) = outline_trims(c_svg), outline_trims(e_svg)
        self.assertEqual(cn, en)                 # same segments, only the order and direction differ
        self.assertLess(et, ct)

    def test_endpoint_order_only_reverses_paths_not_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            c_svg, _ = run(tmp)
            e_svg, _ = run(tmp, "outline_order: endpoint\n")
        key = lambda svg: sorted(
            tuple(sorted(re.findall(r"-?\d+\.?\d*,-?\d+\.?\d*", d)))
            for d in re.findall(r'<path id="[sr]\d+"[^>]*? d="([^"]+)"',
                                re.search(r'id="outlines">(.*?)</g>', svg, re.S).group(1)))
        self.assertEqual(key(c_svg), key(e_svg))

    def test_larger_min_jump_cuts_fewer_trims(self):
        with tempfile.TemporaryDirectory() as tmp:
            low, _ = run(tmp, "outline_order: endpoint\ntrim:\n  min_mm: 2.0\n")
            high, _ = run(tmp, "outline_order: endpoint\ntrim:\n  min_mm: 6.0\n")
        self.assertLessEqual(outline_trims(high)[0], outline_trims(low)[0])

    def test_outline_zigzag_spacing_is_written_to_outline_satins_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, _ = run(tmp, "thin_lines: widen\n")
            wide, _ = run(tmp, "thin_lines: widen\noutline_zigzag_spacing_mm: 0.5\n")
        g = lambda svg: re.search(r'id="outlines">(.*?)</g>', svg, re.S).group(1)
        self.assertNotIn("zigzag_spacing_mm", g(plain))
        self.assertGreaterEqual(g(wide).count('zigzag_spacing_mm="0.5"'), 1)
        self.assertEqual(g(wide).count("satin_column"), g(wide).count('zigzag_spacing_mm="0.5"'))

    def test_bad_zigzag_value_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, _ = run(tmp)
            svg, log = run(tmp, "outline_zigzag_spacing_mm: 9\n")
        self.assertIn("ignoring outline_zigzag_spacing_mm", log)
        self.assertEqual(plain, svg)

    def test_bad_values_are_ignored_with_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, _ = run(tmp)
            svg, log = run(tmp, "outline_order: sideways\ntrim:\n  min_mm: lots\n")
        self.assertIn("ignoring outline_order", log)
        self.assertIn("ignoring non-numeric trim.min_mm", log)
        self.assertEqual(plain, svg)


if __name__ == "__main__":
    unittest.main()
