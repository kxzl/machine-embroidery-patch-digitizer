"""Tests for tools/digitize/key_background.py: enclosed pale colours stay opaque.

Run: .venv/bin/python -m unittest tools/digitize/tests/test_key_background.py -v
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "key_background.py"


def key(arr, *extra):
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.png", Path(tmp) / "out.png"
        Image.fromarray(arr.astype(np.uint8), "RGB").save(src)
        subprocess.run([sys.executable, str(SCRIPT), str(src), str(dst), *extra],
                       check=True, capture_output=True)
        return np.asarray(Image.open(dst).convert("RGBA"))


def disc_with_pale_symbol(pale=(238, 236, 228)):
    arr = np.full((200, 200, 3), 254.0)
    yy, xx = np.mgrid[0:200, 0:200]
    arr[np.hypot(yy - 100, xx - 100) < 80] = (20, 20, 20)
    arr[np.hypot(yy - 100, xx - 100) < 45] = pale            # pale symbol, about 30 from the bg
    return arr


class KeyBackgroundTests(unittest.TestCase):
    def test_enclosed_pale_colour_stays_opaque(self):
        out = key(disc_with_pale_symbol(), "--keep-enclosed")
        self.assertEqual(int(out[100, 100, 3]), 255)          # symbol centre
        self.assertEqual(tuple(out[100, 100, :3]), (238, 236, 228))
        self.assertEqual(int(out[5, 5, 3]), 0)                # background corner
        self.assertEqual(int(out[100, 100 - 60, 3]), 255)     # black disc ring

    def test_default_keeps_the_old_behaviour(self):
        out = key(disc_with_pale_symbol())
        self.assertLess(int(out[100, 100, 3]), 255)           # old: pale symbol partly keyed

    def test_background_next_to_the_artwork_is_still_removed(self):
        out = key(disc_with_pale_symbol(), "--keep-enclosed")
        self.assertEqual(int(out[100, 5, 3]), 0)
        self.assertGreater(int((out[..., 3] == 0).mean() * 100), 40)

    def test_pale_colour_touching_the_edge_is_keyed_as_before(self):
        arr = np.full((100, 100, 3), 254.0)
        arr[:, 50:] = (238, 236, 228)                          # pale half reaches the image edge
        arr[40:60, 20:30] = (20, 20, 20)
        out = key(arr, "--keep-enclosed")
        self.assertLess(int(out[10, 80, 3]), 255)


if __name__ == "__main__":
    unittest.main()
