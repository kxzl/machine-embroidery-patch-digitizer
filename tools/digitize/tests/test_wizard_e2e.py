"""End to end: a real synthetic patch through run.sh, the Ink/Stitch export and the fit check.

Slow (about a minute), needs the venv. Skipped unless DIGITIZE_SLOW=1:

    DIGITIZE_SLOW=1 .venv/bin/python -m unittest tools.digitize.tests.test_wizard_e2e -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.digitize.wizard import core  # noqa: E402

try:
    from PIL import Image, ImageDraw
    import pystitch  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False

RED, YEL, DRK = (192, 57, 43, 255), (241, 196, 15, 255), (26, 26, 26, 255)


def edge_ring_patch(path: Path) -> None:
    """Transparent patch whose own border ring touches the canvas edge (the case that overshoots most)."""
    im = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 999, 999), radius=60, fill=RED)
    d.rounded_rectangle((60, 60, 939, 939), radius=40, outline=DRK, width=40)
    d.ellipse((350, 350, 650, 650), fill=YEL)
    im.save(str(path))


@unittest.skipUnless(os.environ.get("DIGITIZE_SLOW") == "1", "slow: set DIGITIZE_SLOW=1")
@unittest.skipUnless(HAVE and (REPO / ".venv" / "bin" / "python").exists() and (REPO / "inkstitch").exists(),
                     "needs Pillow, pystitch, .venv and inkstitch")
class EndToEnd(unittest.TestCase):
    def test_edge_ring_patch_fits_the_hoop(self):
        from tools.digitize.wizard.vp3 import measure
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            pic = t / "Edge Ring's patch.png"
            edge_ring_patch(pic)
            spec = core.JobSpec(pic, hoop=core.HOOP_SMALL, size_mm=None, colors=4)
            res = core.run_job(spec, REPO, measure=measure, out_root=t / "output")
            for p in res.passes:
                print("pass %d: fit box %s -> stitched %s x %s mm" % (
                    p.number, core.fmt_box(p.box), p.measure.width_mm, p.measure.height_mm))
            self.assertEqual(res.status, "ok", res.message)
            m = measure(res.folder / (res.slug + ".vp3"))                 # read the delivered file again
            self.assertLessEqual(m.width10, 1200)
            self.assertLessEqual(m.height10, 1200)
            self.assertEqual(res.folder.name, "Edge-Ring-s-patch")
            self.assertTrue((res.folder / "summary.txt").is_file())
            self.assertEqual([p.name for p in (t / "output").iterdir()], ["Edge-Ring-s-patch"])


if __name__ == "__main__":
    unittest.main()
