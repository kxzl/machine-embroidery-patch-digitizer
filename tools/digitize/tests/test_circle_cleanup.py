"""Tests for the circle border, label cleanup, thread map and small-fill rule.

vectorize.py -> SVG only, no Ink/Stitch export.

Run: .venv/bin/python -m unittest tools/digitize/tests/test_circle_cleanup.py -v
"""
import contextlib
import io
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vectorize  # noqa: E402

BLACK, DARK, MID, LIGHT = (0x1A, 0x1B, 0x1C), (0x4A, 0x49, 0x47), (0x93, 0x92, 0x8E), (0xD5, 0xD0, 0xC6)
CX, CY, R = 200, 210, 150          # disc; the silhouette is 330 px tall, so --size-mm 66 = 5 px/mm
SIZE_MM = "66"

BASE_CFG = """palette: ['#1a1b1c', '#4a4947', '#93928e', '#d5d0c6']
skip_colors: ['#1a1b1c']
threads:
  '#4a4947': '#1f5e2b'
  '#93928e': '#6cbf3f'
  '#d5d0c6': '#eeeae0'
border:
  mode: circle
  thickness_mm: 4
  color: '#4a4947'
  order: first
"""
CLEANUP = """cleanup:
  min_width_mm: 1.0
  min_area_mm2: 3.0
  fabric_min_width_mm: 1.2
  fabric_min_area_mm2: 1.0
"""


def patch_png(path, speck=4, chip=False):
    """Black disc, a mid-grey horn leaving it at the top, the art's own light rim
    inside the ring band, a light square split by a 0.6 mm black line, a light and
    a mid square 0.6 mm apart, a light speck ``speck`` px square, and with ``chip``
    a 2 x 2 mm light chip outside the circle, away from the horn."""
    yy, xx = np.mgrid[0:400, 0:400].astype(float)
    img = np.zeros((400, 400, 4), np.uint8)
    rr = np.hypot(xx - CX, yy - CY)
    img[rr < R] = BLACK + (255,)
    img[(rr >= 140) & (rr < 145)] = LIGHT + (255,)            # the art's rim, 1 mm wide
    img[30:140, 190:210] = MID + (255,)                        # horn, 4 mm wide
    img[180:240, 120:200] = LIGHT + (255,)
    img[180:240, 158:161] = BLACK + (255,)                     # splits one colour
    img[180:240, 220:280] = LIGHT + (255,)
    img[180:240, 283:330] = MID + (255,)                       # keyline 280..283 between colours
    img[300:300 + speck, 250:250 + speck] = LIGHT + (255,)
    if chip:
        img[320:330, 330:340] = LIGHT + (255,)                 # 177 px from the centre
    Image.fromarray(img, "RGBA").save(path)


def run(tmp, cfg_text, speck=4, chip=False):
    png = Path(tmp) / f"patch{speck}{'c' if chip else ''}.png"
    if not png.exists():
        patch_png(png, speck, chip)
    cfg = Path(tmp) / "cfg.yaml"
    cfg.write_text(cfg_text)
    out = Path(tmp) / "out.svg"
    with contextlib.redirect_stdout(io.StringIO()) as log:
        vectorize.main(["--size-mm", SIZE_MM, "--config", str(cfg), str(png), str(out)])
    return out.read_text(), log.getvalue()


def fills(svg, hx):
    """Point lists (x, y) of every fill path in colour ``hx``."""
    out = []
    for d in re.findall(r'<path id="f\d+" style="fill:%s;[^"]*"[^>]*?d="([^"]+)"' % hx, svg):
        nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", d)]
        out.append(np.array(list(zip(nums[0::2], nums[1::2]))))
    return out


def border_paths(svg):
    return re.findall(r'<path id="s\d+" style="fill:none;stroke:([^;]+);[^"]*"[^>]*?d="([^"]+)"',
                      re.search(r'<g inkscape:label="Border".*?</g>', svg, re.S).group(0))


class CircleFitTests(unittest.TestCase):
    def test_fit_ignores_the_horn(self):
        yy, xx = np.mgrid[0:400, 0:400]
        sil = np.hypot(xx - CX, yy - CY) < R
        sil[30:140, 190:210] = True
        cy, cx, r = vectorize.fit_circle(sil)
        self.assertAlmostEqual(cx, CX, delta=1.0)
        self.assertAlmostEqual(cy, CY, delta=1.0)
        self.assertAlmostEqual(r, R, delta=1.5)


class CircleRingTests(unittest.TestCase):
    def test_ring_first_is_one_closed_satin_before_the_fills(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, _ = run(tmp, BASE_CFG + CLEANUP)
        groups = re.findall(r'<g inkscape:label="([^"]+)"', svg)
        self.assertEqual(groups[0], "Border")
        paths = border_paths(svg)
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0][1].rstrip().endswith("Z"))
        self.assertEqual(paths[0][0], "#1f5e2b")              # thread map applies to the ring

    def test_rim_is_removed_and_the_horn_kept_over_the_ring(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, log = run(tmp, BASE_CFG + CLEANUP)
        self.assertIn("1 crossing shape(s)", log)
        for pts in fills(svg, "#eeeae0"):
            r = np.hypot(pts[:, 0] - CX, pts[:, 1] - CY)
            a = np.degrees(np.arctan2(CY - pts[:, 1], pts[:, 0] - CX))
            in_band = r > R - 20 - 1
            self.assertFalse((in_band & (np.abs(a - 90) > 15)).any(),
                             "a light fill is left in the ring band away from the horn")
        horn = [p for p in fills(svg, "#6cbf3f") if p[:, 1].min() < 60]
        self.assertEqual(len(horn), 1)
        self.assertLess(horn[0][:, 1].min(), 35)               # the tip outside the circle survives

    def test_chip_outside_the_circle_away_from_a_crossing_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, log = run(tmp, BASE_CFG + CLEANUP, chip=True)
        self.assertIn("1 crossing shape(s)", log)
        for pts in fills(svg, "#eeeae0"):
            self.assertLess(np.hypot(pts[:, 0] - CX, pts[:, 1] - CY).max(), R,
                            "a light fill is left outside the circle")

    def test_ring_last_leaves_a_gap_at_the_horn(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, _ = run(tmp, BASE_CFG.replace("order: first", "order: last") + CLEANUP)
        groups = re.findall(r'<g inkscape:label="([^"]+)"', svg)
        self.assertEqual(groups[-1], "Border")
        paths = border_paths(svg)
        self.assertEqual(len(paths), 1)                        # one arc, open at the horn
        d = paths[0][1]
        self.assertFalse(d.rstrip().endswith("Z"))
        nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", d)]
        ends = [(nums[0], nums[1]), (nums[-2], nums[-1])]
        for x, y in ends:                                      # both ends sit near the top
            self.assertGreater(CY - y, 100)


class CleanupTests(unittest.TestCase):
    def test_thin_fabric_line_inside_one_colour_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, _ = run(tmp, BASE_CFG + CLEANUP)
        split = [p for p in fills(svg, "#eeeae0") if p[:, 0].min() < 130 and p[:, 0].max() > 190]
        self.assertEqual(len(split), 1, "the split square should be one fill")

    def test_keyline_between_two_colours_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, _ = run(tmp, BASE_CFG + CLEANUP)
        mid = [p for p in fills(svg, "#6cbf3f") if p[:, 1].min() > 170]
        light = [p for p in fills(svg, "#eeeae0") if p[:, 0].min() > 210]
        self.assertEqual(len(mid), 1)
        self.assertEqual(len(light), 1)
        self.assertGreater(mid[0][:, 0].min(), light[0][:, 0].max())

    def test_speck_joins_its_neighbour(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, _ = run(tmp, BASE_CFG + CLEANUP, speck=7)        # 1.96 mm2 < 3 mm2
        near = [p for p in fills(svg, "#eeeae0")
                if abs(p[:, 0].mean() - 253) < 10 and abs(p[:, 1].mean() - 303) < 10]
        self.assertEqual(near, [])

    def test_no_cleanup_key_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, _ = run(tmp, BASE_CFG)
            empty, _ = run(tmp, BASE_CFG + "cleanup: {}\n")
        self.assertEqual(plain, empty)


class SmallFillTests(unittest.TestCase):
    def test_small_fill_gets_no_underlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg, _ = run(tmp, BASE_CFG, speck=7)                 # 1.96 mm2 < 2.5 mm2
        paths = re.findall(r'<path id="f\d+"[^>]*>', svg)
        small = [p for p in paths if 'fill_underlay="false"' in p]
        self.assertEqual(len(small), 1)
        self.assertGreater(len(paths), 1)

    def test_small_fill_next_to_a_cut_keeps_its_ties(self):
        # ties="3" drops the lock stitches Ink/Stitch adds around a trim: the cut
        # tail would be unlocked.  The speck is an island, so a cut touches it.
        with tempfile.TemporaryDirectory() as tmp:
            svg, _ = run(tmp, BASE_CFG, speck=7)
        paths = re.findall(r'<path id="f\d+"[^>]*>', svg)
        small = [p for p in paths if 'fill_underlay="false"' in p]
        self.assertEqual(len(small), 1)
        self.assertNotIn('ties="3"', small[0])
        self.assertFalse(any('ties="3"' in p and 'trim_after="true"' in p for p in paths))


if __name__ == "__main__":
    unittest.main()
