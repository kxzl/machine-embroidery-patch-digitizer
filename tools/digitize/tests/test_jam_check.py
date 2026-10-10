"""Tests for qa/jam_check.py on tiny synthetic VP3 files.

Run from the repo root:
    .venv/bin/python -m unittest tools/digitize/tests/test_jam_check.py -v

Patterns are written with pystitch's own VP3 writer and read back through
``analyze`` / ``main``, so the tests exercise the same path as the CLI.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest.mock
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
QA = os.path.join(os.path.dirname(HERE), "qa")
sys.path.insert(0, QA)

import pystitch  # noqa: E402
import jam_check as jc  # noqa: E402


def write_vp3(path, records):
    """records: list of (x_mm, y_mm, cmd) with cmd in pystitch.STITCH/TRIM."""
    p = pystitch.EmbPattern()
    for x, y, c in records:
        p.add_stitch_absolute(c, round(x * 10), round(y * 10))
    with open(path, "wb") as f:
        pystitch.write_vp3(p, f)
    return path


def quiet_main(argv):
    with contextlib.redirect_stdout(io.StringIO()):
        return jc.main(argv)


class JamCheckTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def sparse(self, name="sparse.vp3"):
        """Ten stitches 5 mm apart on a line, two trims 25 mm apart."""
        recs = []
        for i in range(10):
            recs.append((i * 5.0, 0.0, pystitch.STITCH))
            if i in (4, 9):
                recs.append((i * 5.0, 0.0, pystitch.TRIM))
        return write_vp3(self.path(name), recs)

    def test_sparse_is_ok_on_all_checks(self):
        res = jc.analyze(self.sparse())
        self.assertTrue(res["packing"]["ok"])
        self.assertTrue(res["thread"]["ok"])
        self.assertTrue(res["trim_clusters"]["ok"])
        self.assertFalse(res["warn"])
        self.assertEqual(quiet_main([self.sparse(), "--strict"]), 0)

    def test_six_trims_two_mm_apart_warn_trim_cluster(self):
        # 2 mm grid inside a 5 mm square: every trim sees the other five
        spots = [(0, 0), (2, 0), (4, 0), (0, 2), (2, 2), (4, 2)]
        recs = []
        for x, y in spots:
            recs.append((x, y, pystitch.STITCH))
            recs.append((x, y, pystitch.TRIM))
        res = jc.analyze(write_vp3(self.path("cluster.vp3"), recs))
        self.assertFalse(res["trim_clusters"]["ok"])
        self.assertGreaterEqual(res["trim_clusters"]["max"], 6)
        self.assertTrue(res["trim_clusters"]["spots"])
        self.assertEqual(quiet_main([self.path("cluster.vp3"), "--strict"]), 1)

    def test_six_trims_30_mm_apart_do_not_warn(self):
        recs = []
        for i in range(6):
            x = i * 30.0
            recs.append((x, 0.0, pystitch.STITCH))
            recs.append((x, 0.0, pystitch.TRIM))
        # the writer appends a TRIM before END at the last point; park it
        # away from the six so it cannot pair with the sixth trim
        recs.append((300.0, 0.0, pystitch.STITCH))
        res = jc.analyze(write_vp3(self.path("spread.vp3"), recs))
        self.assertTrue(res["trim_clusters"]["ok"])
        self.assertEqual(res["trim_clusters"]["max"], 1)

    def test_consecutive_trims_at_one_point_count_once(self):
        # the writer collapses repeated TRIMs, so feed the reader's output
        # directly: six spread points, each with two TRIM records (one cut each)
        class FakePattern:
            def __init__(self, stitches):
                self.stitches = stitches

        stitches = []
        for i in range(6):
            x = i * 300
            stitches.append([x, 0, pystitch.STITCH])
            stitches.append([x, 0, pystitch.TRIM])
            stitches.append([x, 0, pystitch.TRIM])
        stitches.append([3000, 0, pystitch.STITCH])
        with unittest.mock.patch.object(
                jc.pystitch, "read", return_value=FakePattern(stitches)):
            res = jc.analyze("unused.vp3")
        self.assertEqual(res["trims"], 12)
        self.assertEqual(res["trim_clusters"]["cuts"], 6)
        self.assertEqual(res["trim_clusters"]["max"], 1)

    def test_200_needle_points_in_small_disk_warn_packing(self):
        # 200 points on the 0.1 mm grid, all within 0.9 mm of the centre,
        # so the centre point sees the other 199 inside 1.5 mm
        pts = [(i, j) for i in range(-9, 10) for j in range(-9, 10)
               if i * i + j * j <= 81]
        pts.sort(key=lambda p: p[0] * p[0] + p[1] * p[1])
        self.assertGreaterEqual(len(pts), 200)
        recs = [(i / 10.0, j / 10.0, pystitch.STITCH) for i, j in pts[:200]]
        res = jc.analyze(write_vp3(self.path("pile.vp3"), recs))
        self.assertFalse(res["packing"]["ok"])
        self.assertGreaterEqual(res["packing"]["max"], 199)
        self.assertEqual(quiet_main([self.path("pile.vp3"), "--strict"]), 1)

    def test_long_travel_over_8_mm_is_not_thread(self):
        # 9 mm moves between two points, back and forth: no sewn thread
        recs = []
        for _ in range(60):
            recs.append((0.0, 0.0, pystitch.STITCH))
            recs.append((9.0, 0.0, pystitch.STITCH))
        res = jc.analyze(write_vp3(self.path("travel.vp3"), recs))
        self.assertEqual(res["thread"]["max_mm"], 0.0)
        self.assertTrue(res["thread"]["ok"])

    def test_same_moves_at_7_mm_are_thread(self):
        # control for the test above: 7 mm moves count and pile up
        recs = []
        for _ in range(60):
            recs.append((0.0, 0.0, pystitch.STITCH))
            recs.append((7.0, 0.0, pystitch.STITCH))
        res = jc.analyze(write_vp3(self.path("sewn.vp3"), recs))
        self.assertGreater(res["thread"]["max_mm"], 20.0)
        self.assertFalse(res["thread"]["ok"])

    def test_strict_exit_codes(self):
        self.assertEqual(quiet_main([self.sparse("s2.vp3"), "--strict"]), 0)
        self.assertEqual(quiet_main([self.sparse("s3.vp3")]), 0)

    def test_empty_file_does_not_crash(self):
        empty = write_vp3(self.path("empty.vp3"), [])
        res = jc.analyze(empty)
        self.assertEqual(res["stitches"], 0)
        self.assertFalse(res["warn"])
        self.assertEqual(quiet_main([empty, "--strict"]), 0)

    def test_no_trim_and_no_stitch_records_do_not_crash(self):
        # pystitch's writer always adds a TRIM before END, so mock the read
        class FakePattern:
            def __init__(self, stitches):
                self.stitches = stitches

        for stitches in ([], [[0, 0, pystitch.STITCH], [30, 0, pystitch.STITCH]]):
            with unittest.mock.patch.object(
                    jc.pystitch, "read", return_value=FakePattern(stitches)):
                res = jc.analyze("unused.vp3")
                self.assertEqual(res["trims"], 0)
                self.assertEqual(res["trim_clusters"]["max"], 0)
                self.assertFalse(res["warn"])
                self.assertEqual(quiet_main(["unused.vp3", "--strict"]), 0)


if __name__ == "__main__":
    unittest.main()
