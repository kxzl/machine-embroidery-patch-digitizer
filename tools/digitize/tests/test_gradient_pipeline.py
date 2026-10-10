"""Pipeline-level tests for `gradients:` (vectorize.py -> SVG, no Ink/Stitch export).

Run: .venv/bin/python -m unittest tools/digitize/tests/test_gradient_pipeline.py -v
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
from gradient import rgb_to_lab  # noqa: E402

STOPS = ["#f8a81f", "#eb6723", "#ab2920"]
PALETTE = STOPS + ["#111111"]


def disc_png(path, theta_deg=30.0, flat=None, size=300):
    """RGBA disc on a transparent background, a linear gradient along theta (or flat)."""
    yy, xx = np.mgrid[0:size, 0:size].astype(float)
    cx = cy = size / 2.0
    r = size * 0.42
    th = math.radians(theta_deg)
    s = np.clip(0.5 + (math.cos(th) * (xx - cx) + math.sin(th) * (yy - cy)) / (2 * r), 0, 1)
    stops = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in STOPS], float)
    img = np.zeros((size, size, 4), np.uint8)
    if flat is not None:
        rgb = np.tile(np.array(flat, float), (size, size, 1))
    else:
        off = np.array([0.0, 0.5, 1.0])
        rgb = np.stack([np.interp(s, off, stops[:, c]) for c in range(3)], axis=-1)
    d = np.hypot(xx - cx, yy - cy)
    inside = d < r
    ring = inside & (d > r - 8)
    img[..., :3] = rgb.astype(np.uint8)
    img[ring, :3] = (17, 17, 17)
    img[inside, 3] = 255
    Image.fromarray(img, "RGBA").save(path)


def run_vectorize(tmp, png, cfg_text):
    cfg = Path(tmp) / "cfg.yaml"
    cfg.write_text(cfg_text)
    out = Path(tmp) / "out.svg"
    with contextlib.redirect_stdout(io.StringIO()) as log:
        vectorize.main(["--size-mm", "60", "--config", str(cfg), str(png), str(out)])
    return out.read_text(), log.getvalue()


BASE_CFG = "palette: %s\nborder:\n  mode: force_black\n" % PALETTE
GRAD_CFG = BASE_CFG + "gradients:\n  - name: test\n    stops: %s\n" % STOPS


class GradientPipelineTests(unittest.TestCase):
    def test_gradient_disc_becomes_one_linear_gradient_fill(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "disc.png"
            disc_png(png, theta_deg=30.0)
            svg, log = run_vectorize(tmp, png, GRAD_CFG)
        self.assertIn("gradient test: region", log)
        self.assertEqual(svg.count("<linearGradient"), 1)
        self.assertIn('inkstitch:fill_method="linear_gradient_fill"', svg)
        self.assertRegex(svg, r'fill:url\(#g\d+\)')
        m = re.search(r'x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', svg)
        x1, y1, x2, y2 = (float(v) for v in m.groups())
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        self.assertLess(abs(angle - 30.0), 5.0)
        stops = re.findall(r'stop offset="([\d.]+)" style="stop-color:(#[0-9a-f]{6})', svg)
        self.assertEqual([c for _, c in stops], STOPS)
        self.assertEqual(float(stops[0][0]), 0.0)
        self.assertAlmostEqual(float(stops[-1][0]), 1.0, places=3)
        self.assertIn('inkstitch:row_spacing_mm="0.3"', svg.split("linear_gradient_fill")[1][:80])

    def test_flat_region_stays_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "flat.png"
            disc_png(png, flat=(0xEB, 0x67, 0x23))
            svg, log = run_vectorize(tmp, png, GRAD_CFG)
        self.assertNotIn("<linearGradient", svg)
        self.assertNotIn("linear_gradient_fill", svg)

    def test_no_gradients_config_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "disc.png"
            disc_png(png, theta_deg=30.0)
            svg_plain, _ = run_vectorize(tmp, png, BASE_CFG)
            svg_empty, _ = run_vectorize(tmp, png, BASE_CFG + "gradients: []\n")
        self.assertEqual(svg_plain, svg_empty)
        self.assertNotIn("<defs>", svg_plain)

    def test_bad_stop_list_is_ignored_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "disc.png"
            disc_png(png)
            cfg = BASE_CFG + "gradients:\n  - name: bad\n    stops: ['#f8a81f']\n"
            svg, log = run_vectorize(tmp, png, cfg)
        self.assertIn("ignoring gradient #1", log)
        self.assertNotIn("<linearGradient", svg)

    def test_gradient_pixels_are_not_also_stitched_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "disc.png"
            disc_png(png, theta_deg=30.0)
            svg_flat, _ = run_vectorize(tmp, png, BASE_CFG)
            svg_grad, _ = run_vectorize(tmp, png, GRAD_CFG)
        n_flat = len(re.findall(r'<path id="f\d+" style="fill:#(?:f8a81f|eb6723|ab2920)', svg_flat))
        n_flat_with_grad = len(re.findall(r'<path id="f\d+" style="fill:#(?:f8a81f|eb6723|ab2920)', svg_grad))
        self.assertGreater(n_flat, 0)
        self.assertLess(n_flat_with_grad, n_flat)


if __name__ == "__main__":
    unittest.main()
