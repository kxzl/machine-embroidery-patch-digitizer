"""Unit tests for tools/digitize/gradient.py.

Run: .venv/bin/python -m unittest tools/digitize/tests/test_gradient.py -v
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gradient import fit_region, regions, resolve_stops, rgb_to_lab  # noqa: E402

STOPS3 = rgb_to_lab([(0xF8, 0xA8, 0x1F), (0xEB, 0x67, 0x23), (0xAB, 0x29, 0x20)])
STOPS2 = STOPS3[[0, 2]]


def colour_at(s, stops_lab):
    seglen = np.linalg.norm(np.diff(stops_lab, axis=0), axis=1)
    off = np.concatenate([[0.0], np.cumsum(seglen)]) / seglen.sum()
    return np.column_stack([np.interp(s, off, stops_lab[:, c]) for c in range(3)])


def true_s(x, y, th, cx=60.0, cy=45.0, length=200.0):
    return 0.5 + (math.cos(th) * (x - cx) + math.sin(th) * (y - cy)) / length


def region(th_deg, stops_lab, noise=0.0, length=200.0, seed=0):
    yy, xx = np.mgrid[0:90, 0:120]
    xy = np.column_stack([xx.ravel(), yy.ravel()]).astype(float)
    s = true_s(xy[:, 0], xy[:, 1], math.radians(th_deg), length=length)
    lab = colour_at(s, stops_lab)
    if noise:
        lab = lab + np.random.default_rng(seed).normal(0.0, noise, lab.shape)
    return lab, xy


def angle_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


class FitRegionTests(unittest.TestCase):
    def check(self, th_deg, stops, tol=3.0, noise=0.0):
        lab, xy = region(th_deg, stops, noise=noise)
        fit = fit_region(lab, xy, stops)
        self.assertIsNotNone(fit)
        self.assertLess(angle_diff(fit["angle_deg"], th_deg), tol)
        th = math.radians(th_deg)
        self.assertAlmostEqual(true_s(*fit["p1"], th), 0.0, delta=0.03)
        self.assertAlmostEqual(true_s(*fit["p2"], th), 1.0, delta=0.03)
        self.assertEqual(len(fit["offsets"]), len(stops))
        self.assertEqual(fit["offsets"][0], 0.0)
        self.assertAlmostEqual(fit["offsets"][-1], 1.0)

    def test_three_stops_30_degrees(self):
        self.check(30, STOPS3)

    def test_three_stops_minus_75_degrees(self):
        self.check(-75, STOPS3)

    def test_three_stops_180_degrees(self):
        self.check(180, STOPS3)

    def test_two_stops(self):
        self.check(30, STOPS2)

    def test_noise_still_recovers_direction(self):
        self.check(30, STOPS3, tol=6.0, noise=3.0)

    def test_constant_colour_is_not_a_gradient(self):
        xy = np.column_stack([np.arange(500) % 25, np.arange(500) // 25]).astype(float)
        lab = np.tile(STOPS3[1], (500, 1))
        self.assertIsNone(fit_region(lab, xy, STOPS3))

    def test_random_colours_are_not_a_gradient(self):
        rng = np.random.default_rng(0)
        xy = np.column_stack([np.arange(2000) % 50, np.arange(2000) // 50]).astype(float)
        lab = rng.uniform([20, -40, -40], [90, 60, 80], (2000, 3))
        self.assertIsNone(fit_region(lab, xy, STOPS3))

    def test_tiny_ramp_is_rejected_by_min_span(self):
        lab, xy = region(0, STOPS3, length=1200.0)
        self.assertIsNone(fit_region(lab, xy, STOPS3))

    def test_hard_edge_does_not_raise(self):
        yy, xx = np.mgrid[0:60, 0:80]
        xy = np.column_stack([xx.ravel(), yy.ravel()]).astype(float)
        lab = np.where((xy[:, 0] < 40)[:, None], STOPS3[0], STOPS3[2])
        fit_region(lab, xy, STOPS3)      # result may be a fit or None; must not raise


class RegionsTests(unittest.TestCase):
    def test_min_area_and_order(self):
        m = np.zeros((100, 100), bool)
        m[0:5, 0:10] = True       # 50 px
        m[30:50, 30:50] = True    # 400 px
        m[80:85, 80:86] = True    # 30 px
        out = regions(m, 40)
        self.assertEqual([int(r.sum()) for r in out], [400, 50])
        self.assertEqual(out[0].shape, m.shape)

    def test_diagonal_touch_is_one_region(self):
        m = np.zeros((30, 30), bool)
        m[10:15, 10:15] = True
        m[15:20, 15:20] = True
        self.assertEqual([int(r.sum()) for r in regions(m, 40)], [50])

    def test_empty_mask(self):
        self.assertEqual(regions(np.zeros((5, 5), bool), 1), [])


class ResolveStopsTests(unittest.TestCase):
    CENTS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]

    def test_nearest(self):
        self.assertEqual(resolve_stops(["#f00000", "#00ff10"], self.CENTS), [0, 1])

    def test_far_stop_raises(self):
        with self.assertRaises(ValueError):
            resolve_stops(["#808000"], self.CENTS)

    def test_duplicate_raises(self):
        with self.assertRaises(ValueError):
            resolve_stops(["#ff0000", "#fe0000"], self.CENTS)


if __name__ == "__main__":
    unittest.main()
