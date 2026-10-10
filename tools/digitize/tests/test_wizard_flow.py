"""Scripted wizard flows (FakePrompter), picture checks, screens demo.

    python3 -m unittest tools.digitize.tests.test_wizard_flow -v
Needs Pillow for the picture-check tests and rich for the demo; those tests are skipped without them.
"""
from __future__ import annotations

import contextlib
import html
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.digitize.wizard import app, core  # noqa: E402
from tools.digitize.wizard.core import ImageReport, JobResult, JobSpec, Measure  # noqa: E402
from tools.digitize.wizard.prompter import CANCEL, DEFAULT, FakePrompter  # noqa: E402

try:
    from PIL import Image, ImageDraw
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False
try:
    import rich  # noqa: F401
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

TRANSPARENT = ImageReport(width=1000, height=800, design_w=900, design_h=700, kind="transparent")
TALL = ImageReport(width=500, height=1000, design_w=400, design_h=900, kind="transparent")
PLAIN = ImageReport(width=1000, height=800, design_w=900, design_h=700, kind="plain_background",
                    background_hex="#fefffe")


class Env:
    """A temp project folder, a recording runner and a canned picture check."""

    def __init__(self, testcase: unittest.TestCase, report: ImageReport = TRANSPARENT, status: str = "ok"):
        t = tempfile.TemporaryDirectory()
        testcase.addCleanup(t.cleanup)
        self.tmp = Path(t.name)
        self.root = self.tmp / "proj"
        self.root.mkdir()
        self.report, self.status, self.calls = report, status, []

    def picture(self, name: str = "My Patch.png") -> Path:
        p = self.tmp / name
        p.write_bytes(b"x")
        return p

    def inspect(self, _path):
        return self.report

    def runner(self, spec, root, policy=core.KEEP_BOTH, on_stage=None):
        self.calls.append((spec, policy))
        if on_stage:
            on_stage("Making the embroidery file")
        m = Measure(988, 762, 5000, 1, ["#e8590c", "#1a1a1a"])
        r = JobResult(self.status, spec, "My-Patch", root / "output" / "My-Patch", ["a.svg", "summary.txt"],
                      measure=m)
        if self.status == "too_big":
            r.message = "TOO BIG FOR THE HOOP"
        if self.status == "failed":
            r.measure, r.message = None, "The pipeline stopped"
        return r

    def run(self, answers, **kw):
        p = FakePrompter(answers)
        code = app.run_wizard(p, self.root, runner=self.runner, inspect=self.inspect, **kw)
        return p, code


class Flows(unittest.TestCase):
    def test_happy_path_small_hoop(self):
        env = Env(self)
        p, code = env.run([str(env.picture()), DEFAULT, DEFAULT, DEFAULT, True])
        self.assertEqual(code, 0)
        spec, policy = env.calls[0]
        self.assertEqual((spec.hoop, spec.size_mm, spec.colors, spec.key_background),
                         ((120.0, 120.0), 100.0, 6, False))
        self.assertEqual(policy, core.KEEP_BOTH)
        self.assertEqual([e[1][0] for e in p.events if e[0] == "step"], [1, 2, 3, 4, 5, 6, 7])
        self.assertTrue(p.kinds("progress") and p.kinds("results"))
        self.assertEqual(p.kinds("show_choices")[0][-1], ("Files go to", "output/My-Patch/"))
        self.assertFalse((env.root / "output").exists())            # the wizard itself creates nothing

    def test_large_hoop_fill_more_colours(self):
        env = Env(self, TALL)
        p, code = env.run([str(env.picture()), "large", "fill", 8, True])
        self.assertEqual(code, 0)
        spec, _ = env.calls[0]
        self.assertEqual((spec.hoop, spec.size_mm, spec.colors), ((260.0, 200.0), None, 8))
        self.assertIn("Turning the picture 90 degrees", p.said())    # portrait picture in a landscape hoop

    def test_custom_hoop_and_size_with_rejected_numbers(self):
        env = Env(self)
        p, code = env.run([str(env.picture()), "custom", 500, 90, 70, "custom", 5, 80, 4, True])
        self.assertEqual(code, 0)
        spec, _ = env.calls[0]
        self.assertEqual((spec.hoop, spec.size_mm, spec.colors), ((90.0, 70.0), 80.0, 4))
        self.assertEqual([r[1] for r in p.events if r[0] == "rejected"], [500, 5])

    def test_missing_file_then_valid(self):
        env = Env(self)
        p, code = env.run(["/no/such/file.png", str(env.picture()), DEFAULT, DEFAULT, DEFAULT, True])
        self.assertEqual(code, 0)
        self.assertIn("cannot find", p.said())
        self.assertEqual(len(env.calls), 1)

    def test_missing_file_then_quit(self):
        env = Env(self)
        p, code = env.run(["/no/such/file.png", ""])
        self.assertEqual(code, 130)
        self.assertEqual(env.calls, [])
        self.assertIn("Nothing was written", p.said())
        self.assertFalse((env.root / "output").exists())

    def test_wrong_file_type(self):
        env = Env(self)
        svg = env.picture("art.svg")
        p, code = env.run([str(svg), str(env.picture()), DEFAULT, DEFAULT, DEFAULT, True])
        self.assertEqual(code, 0)
        self.assertIn("SVG pictures are not supported", p.said())

    def test_apostrophe_and_spaces_in_every_input_form(self):
        name = "Scavenger's Daughter test.png"
        for form in (lambda p: str(p), lambda p: "'%s'" % str(p).replace("'", "'\"'\"'"),
                     lambda p: str(p).replace(" ", "\\ ").replace("'", "\\'"), lambda p: '"%s"' % p):
            env = Env(self)
            pic = env.picture(name)
            p, code = env.run([form(pic), DEFAULT, DEFAULT, DEFAULT, True])
            self.assertEqual(code, 0, form(pic))
            self.assertEqual(env.calls[0][0].image, pic)
            self.assertIn(("Files go to", "output/Scavenger-s-Daughter-test/"), p.kinds("show_choices")[0])

    def test_plain_background_offers_key_background(self):
        env = Env(self, PLAIN)
        p, code = env.run([str(env.picture()), True, DEFAULT, DEFAULT, DEFAULT, True])
        self.assertEqual(code, 0)
        self.assertTrue(env.calls[0][0].key_background)
        self.assertIn("Remove the plain background", [c for c in p.kinds("confirm")][0])
        env = Env(self, PLAIN)
        env.run([str(env.picture()), False, DEFAULT, DEFAULT, DEFAULT, True])
        self.assertFalse(env.calls[0][0].key_background)

    def test_transparent_picture_has_no_key_question(self):
        env = Env(self)
        p, _code = env.run([str(env.picture()), DEFAULT, DEFAULT, DEFAULT, True])
        self.assertEqual(len(p.kinds("confirm")), 1)       # only "Start now?"

    def test_low_resolution_advice_never_blocks(self):
        env = Env(self, ImageReport(width=200, height=200, design_w=180, design_h=180))
        p, code = env.run([str(env.picture()), DEFAULT, DEFAULT, DEFAULT, True])
        self.assertEqual(code, 0)
        self.assertIn("only 1.8 pixels per mm", p.said())
        self.assertIn("at least 300 pixels", p.said())
        self.assertEqual(len(env.calls), 1)

    def test_existing_folder_choices(self):
        for pick, policy, runs in (("keep_both", core.KEEP_BOTH, 1), ("overwrite", core.OVERWRITE, 1),
                                   ("cancel", None, 0)):
            env = Env(self)
            (env.root / "output" / "My-Patch").mkdir(parents=True)
            p, code = env.run([str(env.picture()), DEFAULT, DEFAULT, DEFAULT, pick, True])
            self.assertEqual(len(env.calls), runs, pick)
            self.assertEqual(code, 130 if pick == "cancel" else 0, pick)
            if runs:
                self.assertEqual(env.calls[0][1], policy)
            self.assertTrue((env.root / "output" / "My-Patch").is_dir())     # the wizard never touches it

    def test_decline_start_and_ctrl_c(self):
        env = Env(self)
        _p, code = env.run([str(env.picture()), DEFAULT, DEFAULT, DEFAULT, False])
        self.assertEqual((code, env.calls), (130, []))
        env = Env(self)
        p, code = env.run([str(env.picture()), DEFAULT, CANCEL])
        self.assertEqual((code, env.calls), (130, []))
        self.assertIn("Cancelled", p.said())

    def test_failed_and_too_big_results_exit_1(self):
        for status in ("failed", "too_big"):
            env = Env(self, status=status)
            p, code = env.run([str(env.picture()), DEFAULT, DEFAULT, DEFAULT, True])
            self.assertEqual(code, 1, status)
            self.assertEqual(p.kinds("results")[0].status, status)

    def test_runner_crash_is_reported(self):
        env = Env(self)

        def boom(*_a, **_k):
            raise OSError("disk full")

        p = FakePrompter([str(env.picture()), DEFAULT, DEFAULT, DEFAULT, True])
        code = app.run_wizard(p, env.root, runner=boom, inspect=env.inspect)
        self.assertEqual(code, 1)
        self.assertIn("disk full", p.said())

    def test_runner_interrupt_is_cancel(self):
        env = Env(self)

        def stop(*_a, **_k):
            raise KeyboardInterrupt()

        p = FakePrompter([str(env.picture()), DEFAULT, DEFAULT, DEFAULT, True])
        self.assertEqual(app.run_wizard(p, env.root, runner=stop, inspect=env.inspect), 130)


class Main(unittest.TestCase):
    def call(self, argv, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = app.main(argv, **kw)
        return code, out.getvalue(), err.getvalue()

    def test_not_a_tty_does_not_prompt(self):
        with tempfile.TemporaryDirectory() as t:
            p = FakePrompter([])
            code, out, _ = self.call([], root=Path(t), prompter=p, is_tty=False)
            self.assertEqual(code, 2)
            self.assertIn("tools/digitize/run.sh --colors 6 --size-mm 100 --fit-mm 120x120", out)
            self.assertEqual(p.events, [])
            self.assertEqual(list(Path(t).iterdir()), [])

    def test_setup_missing(self):
        with tempfile.TemporaryDirectory() as t:
            p = FakePrompter([])
            code, out, _ = self.call([], root=Path(t), prompter=p, is_tty=True)
            self.assertEqual(code, 2)
            self.assertIn("python3 digitize.py setup", out)
            self.assertIn("no .venv", out.replace("there is no .venv folder", "no .venv"))
            self.assertEqual(p.events, [])
            self.assertEqual(list(Path(t).iterdir()), [])

    def test_unknown_argument_and_help(self):
        self.assertEqual(self.call(["--wat"], is_tty=True)[0], 2)
        code, out, _ = self.call(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("setup", out)


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class ImageCheck(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)

    def save(self, im, name):
        p = self.tmp / name
        im.save(str(p))
        return p

    def test_transparent_patch(self):
        from tools.digitize.wizard.imagecheck import inspect
        im = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((100, 50, 700, 550), fill=(200, 30, 30, 255))
        r = inspect(self.save(im, "a.png"))
        self.assertTrue(r.ok)
        self.assertEqual((r.kind, r.width, r.height), ("transparent", 800, 600))
        self.assertAlmostEqual(r.design_w, 601, delta=2)
        self.assertAlmostEqual(r.design_h, 501, delta=2)

    def test_plain_and_busy_background(self):
        from tools.digitize.wizard.imagecheck import inspect
        im = Image.new("RGB", (800, 600), (254, 255, 254))
        ImageDraw.Draw(im).ellipse((100, 50, 700, 550), fill=(200, 30, 30))
        r = inspect(self.save(im, "plain.png"))
        self.assertEqual((r.kind, r.background_hex), ("plain_background", "#fefffe"))
        self.assertAlmostEqual(r.design_w, 601, delta=3)
        d = ImageDraw.Draw(im)
        for x in range(0, 800, 20):
            d.rectangle((x, 0, x + 9, 599), fill=(30, 60, 200))
        r = inspect(self.save(im, "busy.png"))
        self.assertEqual(r.kind, "busy_background")

    def test_unreadable_files(self):
        from tools.digitize.wizard.imagecheck import inspect
        bad = self.tmp / "notes.png"
        bad.write_text("this is a text file renamed to .png")
        r = inspect(bad)
        self.assertFalse(r.ok)
        self.assertIn("cannot read", r.error)

    def test_transparent_artwork_touching_one_edge(self):
        from tools.digitize.wizard.imagecheck import inspect
        im = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((0, 100, 199, 299), fill=(200, 30, 30, 255))
        r = inspect(self.save(im, "edge.png"))
        self.assertEqual((r.design_x, r.design_y), (0, 100))
        self.assertTrue(core.artwork_touches_edge(r))
        self.assertTrue(any("touches the edge" in a for a in core.image_advice(r)))

    def test_transparent_artwork_with_a_margin(self):
        from tools.digitize.wizard.imagecheck import inspect
        im = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((100, 100, 299, 299), fill=(200, 30, 30, 255))
        r = inspect(self.save(im, "margin.png"))
        self.assertGreaterEqual(r.design_x, 90)
        self.assertFalse(core.artwork_touches_edge(r))
        self.assertFalse(any("touches the edge" in a for a in core.image_advice(r)))

    def test_opaque_plain_background_with_a_margin(self):
        from tools.digitize.wizard.imagecheck import inspect
        im = Image.new("RGB", (400, 400), (254, 255, 254))
        ImageDraw.Draw(im).ellipse((100, 100, 299, 299), fill=(200, 30, 30))
        r = inspect(self.save(im, "plain_margin.png"))
        self.assertEqual(r.kind, "plain_background")
        self.assertFalse(core.artwork_touches_edge(r))
        self.assertFalse(any("touches the edge" in a for a in core.image_advice(r)))

    def test_wizard_rejects_unreadable_then_accepts(self):
        from tools.digitize.wizard.imagecheck import inspect
        bad = self.tmp / "notes.png"
        bad.write_text("this is a text file renamed to .png")
        good = self.save(Image.new("RGBA", (400, 400), (0, 0, 0, 0)), "ok.png")
        im = Image.open(good)
        im.paste((1, 2, 3, 255), (50, 50, 350, 350))
        im.save(str(good))
        env = Env(self)
        p = FakePrompter([str(bad), str(good), DEFAULT, DEFAULT, DEFAULT, True])
        code = app.run_wizard(p, env.root, runner=env.runner, inspect=inspect)
        self.assertEqual(code, 0)
        self.assertIn("cannot read", p.said())
        self.assertEqual(env.calls[0][0].image, good)


@unittest.skipUnless(HAVE_PIL and HAVE_RICH, "Pillow and rich are needed")
class ScreensDemo(unittest.TestCase):
    def test_every_screen_is_rendered(self):
        from tools.digitize.wizard import screens_demo
        with tempfile.TemporaryDirectory() as t:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(screens_demo.main([t]), 0)
            files = sorted(Path(t).glob("*.svg"))
            self.assertEqual(len(files), 9)
            text = html.unescape(re.sub(r"<[^>]+>", "", "\n".join(f.read_text() for f in files))).replace("\xa0", " ")
            for needle in ("Step 1 of 7", "Step 7 of 7", "Which hoop", "Sewing order", "TOO BIG FOR THE HOOP",
                           "Let the program decide"):
                self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
