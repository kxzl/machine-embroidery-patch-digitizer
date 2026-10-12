"""Tests for travel_vp3.py on tiny synthetic VP3 files.

Run from the repo root:
    .venv/bin/python -m unittest tools/digitize/tests/test_travel_vp3.py -v

Layout used throughout (mm): object A at x 0..10, object B at x 30..40, both in
the first colour block and joined by a TRIM.  A cover bar (dense horizontal
rows, y 4..6, x 5..35) is sewn after them, in block 2 unless a test says
otherwise.  Patterns go through pystitch's VP3 writer and reader, so the tests
exercise the same path as the CLI.
"""
import contextlib
import io
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pystitch  # noqa: E402
import travel_vp3 as tv  # noqa: E402

LIGHT, DARK = 0xDDDDDD, 0x202020
S, T, CC = pystitch.STITCH, pystitch.TRIM, pystitch.COLOR_CHANGE


def u(mm):
    return round(mm * 10)


def fill(x0, x1, y0, y1, step=0.4):
    """Horizontal boustrophedon rows, ``step`` mm apart, 2.5 mm stitches."""
    recs, y, left_to_right = [], y0, True
    while y <= y1 + 1e-9:
        n = max(1, int(abs(x1 - x0) / 2.5))
        xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
        for x in (xs if left_to_right else xs[::-1]):
            recs.append((x, y, S))
        left_to_right = not left_to_right
        y += step
    return recs


def pattern(blocks):
    """blocks: list of (colour, records[(x_mm, y_mm, cmd)]).  A COLOR_CHANGE
    record joins consecutive blocks, as in Ink/Stitch output."""
    p = pystitch.EmbPattern()
    for i, (rgb, recs) in enumerate(blocks):
        th = pystitch.EmbThread()
        th.color = rgb
        p.add_thread(th)
        if i:
            p.add_stitch_absolute(CC, u(recs[0][0]), u(recs[0][1]))
        for x, y, c in recs:
            p.add_stitch_absolute(c, u(x), u(y))
    p.add_stitch_absolute(pystitch.END, 0, 0)
    return p


def two_objects(first=LIGHT):
    """A, TRIM, B in one block.  A ends at (10, 5), B starts at (30, 5)."""
    a = fill(0, 10, 0, 10, 0.5)
    a += [(10, 5, S)]
    b = [(30, 5, S)] + fill(30, 40, 0, 10, 0.5)
    return (first, a + [(10, 5, T)] + b)


def bar(rgb=DARK):
    return (rgb, fill(5, 35, 4, 6))


def write(path, p):
    with open(path, "wb") as fh:
        pystitch.write_vp3(p, fh)
    return path


class TravelTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def vp3(self, blocks, name="t.vp3"):
        return write(os.path.join(self.dir, name), pattern(blocks))

    def run_cli(self, path, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = tv.main([path, *args])
        return rc, buf.getvalue()

    @staticmethod
    def trims(path, before=S):
        """TRIMs followed by ``before`` (the writer adds its own TRIM at the very end)."""
        st = pystitch.read(path).stitches
        return sum(1 for k in range(len(st) - 1)
                   if tv.cmd_of(st[k]) == T and tv.cmd_of(st[k + 1]) == before)

    def test_trim_under_later_dark_cover_becomes_a_run(self):
        path = self.vp3([two_objects(), bar()])
        before = tv._body(pystitch.read(path).stitches)
        rc, out = self.run_cli(path)
        after = tv._body(pystitch.read(path).stitches)
        self.assertEqual(rc, 0)
        self.assertIn("1 of 1 same-colour trim(s)", out)
        self.assertEqual(self.trims(path), 0)

        # everything that was there is still there, in order and in place; only the
        # TRIM is replaced by the run
        t = next(k for k, s in enumerate(before) if tv.cmd_of(s) == T)
        tail = len(before) - t - 1
        key = lambda seq: [(s[0], s[1], tv.cmd_of(s)) for s in seq]  # noqa: E731
        self.assertEqual(key(after[:t]), key(before[:t]))
        self.assertEqual(key(after[len(after) - tail:]), key(before[t + 1:]))

        # the run sits between E=(10,5) and S=(30,5), inside the bar, in short stitches
        run = after[t - 1:len(after) - tail + 1]
        self.assertEqual((run[0][0], run[0][1]), (u(10), u(5)))
        self.assertEqual((run[-1][0], run[-1][1]), (u(30), u(5)))
        self.assertGreater(len(run), 6)
        for x, y, c in run:
            self.assertEqual(tv.cmd_of((x, y, c)), S)
            self.assertTrue(u(3.5) <= y <= u(6.5), (x, y))
        for a, b in zip(run, run[1:]):
            self.assertLessEqual(math.hypot(b[0] - a[0], b[1] - a[1]) / 10.0, 3.6)

    def test_nothing_sewn_later_keeps_the_trim(self):
        path = self.vp3([two_objects()])
        rc, out = self.run_cli(path)
        self.assertEqual(self.trims(path), 1)
        self.assertIn("kept: 1 exit not under cover", out)

    def test_lighter_cover_keeps_the_trim(self):
        """A dark run would show through a light fill sewn over it."""
        path = self.vp3([two_objects(first=DARK), bar(LIGHT)])
        rc, out = self.run_cli(path)
        self.assertEqual(self.trims(path), 1)
        self.assertIn("exit not under cover", out)

    def test_cover_of_the_same_darkness_counts(self):
        path = self.vp3([two_objects(first=DARK), bar(DARK)])
        self.run_cli(path)
        self.assertEqual(self.trims(path), 0)

    def test_cover_missing_at_the_exit_keeps_the_trim(self):
        """The bar starts 3 mm past where the needle leaves A: no connector reaches it."""
        far_bar = (DARK, fill(14, 35, 4, 6))
        path = self.vp3([two_objects(), far_bar])
        self.run_cli(path)
        self.assertEqual(self.trims(path), 1)

    def test_route_longer_than_max_keeps_the_trim(self):
        path = self.vp3([two_objects(), bar()])
        rc, out = self.run_cli(path, "--max-mm", "15")
        self.assertEqual(self.trims(path), 1)
        self.assertIn("too far", out)

    def test_single_thread_is_not_cover(self):
        """One travel-length stitch over the way hides nothing."""
        thread = (DARK, [(5, 5, S), (35, 5, S)])
        path = self.vp3([two_objects(), thread])
        self.run_cli(path)
        self.assertEqual(self.trims(path), 1)

    def run_stitches(self, path, before):
        """The stitches the pass inserted: those between the exit E and the entry S."""
        after = tv._body(pystitch.read(path).stitches)
        t = next(k for k, s in enumerate(before) if tv.cmd_of(s) == T)
        tail = len(before) - t - 1
        return after[t - 1:len(after) - tail + 1]

    def test_thin_cover_needs_the_margin(self):
        """Two rows 0.4 mm apart are 0.8 mm of cover: enough at 0.3 mm, not at 0.5 mm."""
        thin = (DARK, fill(5, 35, 4.8, 5.2, 0.4))
        path = self.vp3([two_objects(), thin])
        self.run_cli(path)
        self.assertEqual(self.trims(path), 1)
        self.run_cli(path, "--margin-mm", "0.3")
        self.assertEqual(self.trims(path), 0)

    def test_run_stitches_keep_the_margin_round_a_bend(self):
        """An L-shaped cover with long run stitches allowed: no stitch may cut the inner
        corner closer than margin - 0.15 mm (0.35 mm) to uncovered cloth."""
        import numpy as np
        from scipy import ndimage
        horizontal = fill(5, 21, 4, 6, 0.4)                        # y 4..6, x 5..21
        # columns x 19..21 from y 4 to 26: the same rows as fill(), turned on their side
        vertical = [(x, y, c) for y, x, c in fill(4, 26, 19, 21, 0.4)]
        a = fill(0, 6, 0, 10, 0.5) + [(6, 5, S)]
        b = [(20, 25.5, S)] + fill(15, 25, 25.5, 30, 0.5)
        path = self.vp3([(LIGHT, a + [(6, 5, T)] + b), (DARK, horizontal + vertical)])
        before = tv._body(pystitch.read(path).stitches)
        self.run_cli(path, "--stitch-mm", "6")
        run = self.run_stitches(path, before)
        self.assertGreater(len(run), 5)
        # distance to cloth that neither bar covers, on a 0.05 mm grid
        res = 0.05
        xs = np.arange(0, 40, res)
        ys = np.arange(0, 40, res)
        gx, gy = np.meshgrid(xs, ys)
        covered = (((gx >= 4.8) & (gx <= 21.2) & (gy >= 3.8) & (gy <= 6.2)) |
                   ((gx >= 18.8) & (gx <= 21.2) & (gy >= 3.8) & (gy <= 26.2)))
        dist = ndimage.distance_transform_edt(covered) * res
        worst = 9.0
        for (x0, y0, _), (x1, y1, _) in zip(run[1:-1], run[2:-1]):
            for t in np.linspace(0, 1, 40):
                px, py = (x0 + t * (x1 - x0)) / 10.0, (y0 + t * (y1 - y0)) / 10.0
                worst = min(worst, dist[int(round(py / res)), int(round(px / res))])
        self.assertGreaterEqual(worst, 0.25, f"a run stitch comes within {worst:.2f} mm of bare cloth")

    def test_short_hop_loses_its_trim_without_any_cover(self):
        a = fill(0, 10, 0, 10, 0.5) + [(10, 5, S), (10, 5, T)]
        b = [(11.5, 5, S)] + fill(11.5, 20, 0, 10, 0.5)
        path = self.vp3([(LIGHT, a + b)])
        rc, out = self.run_cli(path)
        self.assertEqual(self.trims(path), 0)
        self.assertIn("1 trim(s) between points at most 2 mm apart dropped", out)
        self.assertIn("0 of 1 same-colour trim(s)", out)

    def test_hop_just_over_the_floor_keeps_its_trim(self):
        a = fill(0, 10, 0, 10, 0.5) + [(10, 5, S), (10, 5, T)]
        b = [(12.2, 5, S)] + fill(12.2, 20, 0, 10, 0.5)
        path = self.vp3([(LIGHT, a + b)])
        self.run_cli(path)
        self.assertEqual(self.trims(path), 1)

    def test_hop_floor_comes_from_trim_min_mm_in_the_config(self):
        a = fill(0, 10, 0, 10, 0.5) + [(10, 5, S), (10, 5, T)]
        b = [(12.2, 5, S)] + fill(12.2, 20, 0, 10, 0.5)
        path = self.vp3([(LIGHT, a + b)])
        cfg = os.path.join(self.dir, "c.yaml")
        with open(cfg, "w") as fh:
            fh.write("trim:\n  min_mm: 3\n")
        self.run_cli(path, "--config", cfg)
        self.assertEqual(self.trims(path), 0)

    def earlier_surface(self):
        """Exit on dense satin of the SAME colour sewn before the trim; nothing later."""
        bar = fill(5, 35, 4, 6, 0.4) + [(10, 5, S)]
        b = [(30, 5, S)] + fill(30, 40, 0, 10, 0.5)
        return self.vp3([(LIGHT, bar + [(10, 5, T)] + b)])

    def test_earlier_same_colour_stitching_is_not_cover_by_default(self):
        path = self.earlier_surface()
        rc, out = self.run_cli(path)
        self.assertEqual(self.trims(path), 1)
        self.assertIn("exit not under cover", out)

    def test_same_colour_surface_is_opt_in(self):
        path = self.earlier_surface()
        before = tv._body(pystitch.read(path).stitches)
        self.run_cli(path, "--surface", "same_colour")
        self.assertEqual(self.trims(path), 0)
        run = self.run_stitches(path, before)
        self.assertGreater(len(run), 4)
        for x, y, c in run:
            self.assertTrue(u(4.3) <= y <= u(5.7), (x, y))

    def test_surface_from_config_and_bad_value(self):
        path = self.earlier_surface()
        cfg = os.path.join(self.dir, "c.yaml")
        with open(cfg, "w") as fh:
            fh.write("travel:\n  surface: sideways\n")
        rc, out = self.run_cli(path, "--config", cfg)
        self.assertIn("unknown surface 'sideways'", out)
        self.assertEqual(self.trims(path), 1)
        with open(cfg, "w") as fh:
            fh.write("travel:\n  surface: same_colour\n")
        self.run_cli(path, "--config", cfg)
        self.assertEqual(self.trims(path), 0)

    def test_trim_before_a_colour_change_is_the_machines(self):
        a = fill(0, 10, 0, 10, 0.5) + [(10, 5, T)]
        path = self.vp3([(LIGHT, a), bar()])
        rc, out = self.run_cli(path)
        self.assertEqual(self.trims(path, before=CC), 1)
        self.assertIn("0 of 0 same-colour trim(s)", out)
        self.assertIn("colour changes or the end are the machine's", out)

    def test_dry_run_leaves_the_file_alone(self):
        path = self.vp3([two_objects(), bar()])
        with open(path, "rb") as fh:
            before = fh.read()
        rc, out = self.run_cli(path, "--dry-run")
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), before)
        self.assertIn("1 of 1 same-colour trim(s)", out)

    def test_config_can_switch_it_off_and_flags_win_over_config(self):
        path = self.vp3([two_objects(), bar()])
        cfg = os.path.join(self.dir, "c.yaml")
        with open(cfg, "w") as fh:
            fh.write("travel:\n  enabled: false\n")
        rc, out = self.run_cli(path, "--config", cfg)
        self.assertIn("disabled by config", out)
        self.assertEqual(self.trims(path), 1)

        with open(cfg, "w") as fh:
            fh.write("travel:\n  max_mm: 15\n")
        self.run_cli(path, "--config", cfg)
        self.assertEqual(self.trims(path), 1)
        self.run_cli(path, "--config", cfg, "--max-mm", "40")
        self.assertEqual(self.trims(path), 0)

    def test_bad_numbers_fall_back_to_defaults(self):
        path = self.vp3([two_objects(), bar()])
        cfg = os.path.join(self.dir, "c.yaml")
        with open(cfg, "w") as fh:
            fh.write("travel:\n  max_mm: lots\n  snap_mm: -1\n")
        rc, out = self.run_cli(path, "--config", cfg)
        self.assertIn("ignoring non-numeric max_mm", out)
        self.assertIn("ignoring non-positive snap_mm", out)
        self.assertEqual(self.trims(path), 0)

    def test_file_without_trims_is_untouched(self):
        path = self.vp3([(LIGHT, fill(0, 10, 0, 10))])
        with open(path, "rb") as fh:
            before = fh.read()
        rc, out = self.run_cli(path)
        self.assertIn("0 of 0 same-colour trim(s)", out)
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), before)


if __name__ == "__main__":
    unittest.main()
