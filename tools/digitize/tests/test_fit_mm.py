"""Tests for vectorize.py --fit-mm and its interplay with --size-mm.

Run from the repo root:
    .venv/bin/python -m unittest discover -s tools/digitize/tests -p 'test_fit_mm.py'

Pure-logic tests call ``resolve_px_per_mm`` / ``parse_fit_mm``; the scale tests run
``build_settings`` + ``load_image`` + ``design_scale`` on tiny synthetic images; two
CLI tests check the exit code 2 path and one full run.  No Ink/Stitch needed.
"""
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DIGITIZE = os.path.dirname(HERE)
sys.path.insert(0, DIGITIZE)

from PIL import Image, ImageDraw  # noqa: E402

import vectorize as V  # noqa: E402


def ellipse_png(path, w, h):
    """Transparent canvas w x h, red ellipse filling it, dark inner ellipse."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, w - 1, h - 1], fill=(200, 30, 30, 255))
    d.ellipse([w * 0.3, h * 0.3, w * 0.7, h * 0.7], fill=(20, 20, 120, 255))
    im.save(path)


def scale_for(png, *argv):
    """design_scale() result and its printed text for the given CLI flags."""
    flags, _ = V.parse_args(list(argv))
    settings = V.build_settings(flags, {})
    img = V.load_image(png)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc = V.design_scale(img, settings)
    return sc, buf.getvalue()


class ResolveRule(unittest.TestCase):
    def ppm(self, w, h, size=100.0, given=False, fit=None):
        return V.resolve_px_per_mm(w, h, size, given, fit)

    def test_default_is_longest_side_100(self):
        ppm, rule, note = self.ppm(600, 200)
        self.assertEqual(ppm, 600 / 100.0)      # same expression as before the flag
        self.assertIn("default", rule)
        self.assertIsNone(note)

    def test_size_only(self):
        ppm, rule, note = self.ppm(600, 200, size=60.0, given=True)
        self.assertEqual(ppm, 10.0)
        self.assertIn("--size-mm 60", rule)
        self.assertIsNone(note)

    def test_fit_only_wide_width_limits(self):
        ppm, rule, note = self.ppm(900, 300, fit=(120, 120))
        self.assertAlmostEqual(ppm, 7.5)         # 900 px / 120 mm
        self.assertIn("width limits", rule)
        self.assertIsNone(note)

    def test_fit_only_tall_height_limits(self):
        ppm, rule, _ = self.ppm(300, 900, fit=(260, 200))
        self.assertAlmostEqual(ppm, 4.5)         # 900 px / 200 mm
        self.assertIn("height limits", rule)

    def test_fit_only_nearly_box_shaped_design_width_limits(self):
        # 300 x 200 px design in a 260 x 200 box: 300/260 > 200/200, so width binds
        ppm, rule, _ = self.ppm(300, 200, fit=(260, 200))
        self.assertAlmostEqual(ppm, 300 / 260)
        self.assertIn("width limits", rule)

    def test_fit_only_fills_box_exactly_on_limiting_axis(self):
        for w, h, box in [(900, 300, (120, 120)), (300, 900, (120, 120)),
                          (900, 300, (260, 200)), (300, 900, (260, 200)),
                          (500, 500, (120, 120))]:
            ppm, _, _ = self.ppm(w, h, fit=box)
            mm_w, mm_h = w / ppm, h / ppm
            self.assertLessEqual(mm_w, box[0] + 1e-9)
            self.assertLessEqual(mm_h, box[1] + 1e-9)
            self.assertTrue(abs(mm_w - box[0]) < 1e-9 or abs(mm_h - box[1]) < 1e-9)

    def test_fit_can_scale_up_beyond_100(self):
        ppm, _, _ = self.ppm(500, 500, fit=(260, 200))
        self.assertAlmostEqual(500 / ppm, 200.0)  # larger than the 100 mm default

    def test_both_fit_limits(self):
        # wide 900 x 300; size 150 would be 150 mm wide, box 120 wide wins
        ppm, rule, note = self.ppm(900, 300, size=150.0, given=True, fit=(120, 120))
        self.assertAlmostEqual(900 / ppm, 120.0)
        self.assertIn("--fit-mm 120x120 limited", rule)
        self.assertIn("--fit-mm 120x120 limited", note)

    def test_both_size_limits(self):
        # size 60 is smaller than the 120 mm box
        ppm, rule, note = self.ppm(900, 300, size=60.0, given=True, fit=(120, 120))
        self.assertAlmostEqual(900 / ppm, 60.0)
        self.assertIn("--size-mm 60 limited", rule)
        self.assertIn("--size-mm 60 limited", note)

    def test_both_tall_in_landscape_hoop(self):
        ppm, rule, note = self.ppm(300, 900, size=100.0, given=True, fit=(260, 200))
        self.assertAlmostEqual(900 / ppm, 100.0)  # size 100 < 200 mm box height
        self.assertIn("--size-mm", rule)

    def test_both_equal(self):
        ppm, rule, note = self.ppm(600, 200, size=120.0, given=True, fit=(120, 120))
        self.assertAlmostEqual(600 / ppm, 120.0)
        self.assertIn("same size", note)

    def test_both_never_larger_than_either(self):
        for size in (30.0, 90.0, 120.0, 150.0, 400.0):
            for w, h in [(900, 300), (300, 900), (500, 500)]:
                ppm, _, _ = self.ppm(w, h, size=size, given=True, fit=(120, 120))
                self.assertLessEqual(max(w, h) / ppm, size + 1e-9)
                self.assertLessEqual(w / ppm, 120 + 1e-9)
                self.assertLessEqual(h / ppm, 120 + 1e-9)


class ParseFit(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(V.parse_fit_mm("120x120"), (120.0, 120.0))
        self.assertEqual(V.parse_fit_mm("260X200"), (260.0, 200.0))
        self.assertEqual(V.parse_fit_mm("120.5x80.25"), (120.5, 80.25))
        self.assertEqual(V.parse_fit_mm(" 120 x 120 "), (120.0, 120.0))
        self.assertEqual(V.parse_fit_mm(".5x2"), (0.5, 2.0))

    def test_invalid_exits_2_and_says_what_is_expected(self):
        for bad in ["", "120", "axb", "0x100", "100x0", "-1x5", "120x", "x120", "120*120",
                    "120x120x5", "nanxnan", "infxinf", "1e3x1e3", "120,120", True]:
            err = io.StringIO()
            with self.subTest(bad=bad), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    V.parse_fit_mm(bad)
                self.assertEqual(cm.exception.code, 2)
                self.assertIn("--fit-mm 120x120", err.getvalue())

    def test_flag_forms(self):
        for argv in (["--fit-mm", "120x120"], ["--fit-mm=120x120"]):
            flags, args = V.parse_args(argv + ["in.png", "out.svg"])
            self.assertEqual(flags["fit-mm"], "120x120")
            self.assertEqual(args, ["in.png", "out.svg"])
            st = V.build_settings(flags, {})
            self.assertEqual(st.fit_mm, (120.0, 120.0))
            self.assertFalse(st.size_given)

    def test_missing_value_exits_2(self):
        flags, _ = V.parse_args(["--fit-mm"])
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                V.build_settings(flags, {})
        self.assertEqual(cm.exception.code, 2)


class ScaleOnImages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.wide = os.path.join(cls.tmp.name, "wide.png")     # 400 x 100
        cls.tall = os.path.join(cls.tmp.name, "tall.png")     # 100 x 400
        ellipse_png(cls.wide, 400, 100)
        ellipse_png(cls.tall, 100, 400)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_default_unchanged(self):
        sc, out = scale_for(self.wide)
        self.assertEqual(sc.px_per_mm, 400 / 100.0)
        self.assertIn("design size: 100.0 x 25.0 mm", out)

    def test_size_only_unchanged(self):
        sc, out = scale_for(self.wide, "--size-mm", "60")
        self.assertEqual(sc.px_per_mm, 400 / 60.0)
        self.assertIn("design size: 60.0 x 15.0 mm", out)
        self.assertNotIn("note:", out)

    def test_fit_only_wide(self):
        sc, out = scale_for(self.wide, "--fit-mm", "120x120")
        self.assertAlmostEqual(sc.px_per_mm, 400 / 120)
        self.assertIn("design size: 120.0 x 30.0 mm", out)
        self.assertIn("width limits", out)

    def test_fit_only_tall_in_landscape_hoop(self):
        sc, out = scale_for(self.tall, "--fit-mm=260x200")
        self.assertAlmostEqual(sc.px_per_mm, 2.0)             # 400 px / 200 mm
        self.assertIn("design size: 50.0 x 200.0 mm", out)
        self.assertIn("height limits", out)

    def test_low_resolution_warning_uses_final_size(self):
        _, out = scale_for(self.tall, "--fit-mm", "260x200")   # 2 px/mm
        self.assertIn("warning: source is too coarse", out)
        self.assertIn("at 200 mm", out)

    def test_no_warning_when_resolution_fine(self):
        _, out = scale_for(self.wide, "--fit-mm", "120x120")   # 3.33 px/mm
        self.assertNotIn("too coarse", out)

    def test_both_fit_limits(self):
        sc, out = scale_for(self.wide, "--fit-mm", "120x120", "--size-mm", "150")
        self.assertAlmostEqual(400 / sc.px_per_mm, 120.0)
        self.assertEqual(out.count("note:"), 1)
        self.assertIn("--fit-mm 120x120 limited", out)

    def test_both_size_limits(self):
        sc, out = scale_for(self.wide, "--fit-mm", "120x120", "--size-mm", "100")
        self.assertAlmostEqual(400 / sc.px_per_mm, 100.0)
        self.assertEqual(out.count("note:"), 1)
        self.assertIn("--size-mm 100 limited", out)

    def test_explicit_size_100_is_detected_as_given(self):
        # --size-mm 100 equals the default but is still "given": it caps a larger box
        sc, out = scale_for(self.wide, "--fit-mm", "260x200", "--size-mm", "100")
        self.assertAlmostEqual(400 / sc.px_per_mm, 100.0)
        self.assertIn("--size-mm 100 limited", out)
        sc2, _ = scale_for(self.wide, "--fit-mm", "260x200")   # no --size-mm: fills the box
        self.assertAlmostEqual(400 / sc2.px_per_mm, 260.0)


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, os.path.join(DIGITIZE, "vectorize.py"), *args],
                              capture_output=True, text=True, env=env, timeout=300)

    def test_invalid_exits_2_before_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, "a.png")
            svg = os.path.join(tmp, "out", "a.svg")
            ellipse_png(png, 400, 100)
            r = self.run_cli("--fit-mm", "banana", png, svg)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("--fit-mm 120x120", r.stderr)
            self.assertFalse(os.path.exists(os.path.dirname(svg)), "output dir must not be created")

    def test_full_run_writes_svg_at_fit_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, "a.png")
            svg = os.path.join(tmp, "a.svg")
            ellipse_png(png, 400, 100)
            r = self.run_cli("--fit-mm", "120x120", "--colors", "2", png, svg)
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            with open(svg, encoding="utf-8") as f:
                m = re.search(r'width="([\d.]+)mm" height="([\d.]+)mm"', f.read())
            self.assertEqual((float(m.group(1)), float(m.group(2))), (120.0, 30.0))


if __name__ == "__main__":
    unittest.main()
