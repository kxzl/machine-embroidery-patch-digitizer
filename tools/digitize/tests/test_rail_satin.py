"""A solid blob (a star) must not be skeletonized into an asterisk.

``satin_segments`` gives a solid shape one short spoke per limb, so a five-pointed
star is stitched as a snowflake.  With ``rail_satin: true`` such a component is
instead split into rail satin rows whose rails follow its outline, and whatever no
skeleton satin reached becomes a rail row too, so the outline colour stays satin.

Run: .venv/bin/python -m unittest tools/digitize/tests/test_rail_satin.py -v
"""
import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vectorize  # noqa: E402

PPM = 6.0          # source pixels per mm
CFG = ("palette: ['#fcfcfc']\n"
       "border:\n  mode: 'off'\n"
       "rail_satin: {}\n")


def star(r_out=3.2, r_in=1.3):
    """Five-pointed star outline, in mm, as a list of (row, col) points."""
    pts = []
    for k in range(10):
        ang = -np.pi / 2 + k * np.pi / 5
        r = (r_out if k % 2 == 0 else r_in) * PPM
        pts.append((300 + r * np.sin(ang), 300 + r * np.cos(ang)))
    return pts


def art_png(path):
    """White linework plus a star on a keyed (transparent) background."""
    img = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(60, 60), (540, 60)], fill=(252, 252, 252, 255), width=int(3 * PPM))
    d.ellipse([60, 400, 400, 560], outline=(252, 252, 252, 255), width=int(2.5 * PPM))
    d.polygon(star(), fill=(252, 252, 252, 255))
    img.save(path)


def run(rail="true", extra=""):
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "art.png"
        art_png(png)
        cfg = Path(tmp) / "cfg.yaml"
        cfg.write_text(CFG.format(rail) + extra)
        out = Path(tmp) / "out.svg"
        with contextlib.redirect_stdout(io.StringIO()) as log:
            vectorize.main(["--size-mm", "100", "--satin-max-mm", "4.5",
                            "--config", str(cfg), str(png), str(out)])
        return out.read_text(), log.getvalue()


def rail_satins(svg):
    """Satin paths built from authored rails (a satin with 2+ subpaths)."""
    n = 0
    for tag in re.findall(r"<path [^>]*/>", svg):
        if 'inkstitch:satin_column="true"' in tag and re.search(r'd="M [^"]*?M ', tag):
            n += 1
    return n


def fills(svg):
    return len(re.findall(r'<path id="f\d+"', svg))


class RailSatinTests(unittest.TestCase):
    def test_star_becomes_a_rail_satin(self):
        svg, log = run()
        self.assertIn("solid blob", log)
        self.assertGreaterEqual(rail_satins(svg), 1)

    def test_star_is_not_left_as_a_fill(self):
        with_rail, on_log = run()
        without_rail, off_log = run(rail="false")
        # without the flag the star's skeleton becomes spokes and the shape keeps
        # a fill; with it the star is a rail satin and one fill fewer is stitched
        self.assertNotIn("solid blob", off_log)
        self.assertIn("solid blob", on_log)
        self.assertEqual(fills(without_rail), fills(with_rail) + 1)

    def test_leftover_pass_can_be_left_off(self):
        _svg, log = run(extra="rail_satin_leftover: false\n")
        self.assertIn("solid blob", log)
        self.assertNotIn("solid pass", log)


if __name__ == "__main__":
    unittest.main()