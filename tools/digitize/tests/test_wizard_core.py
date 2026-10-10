"""Tests for the wizard core: slug rule, path parsing, fit correction, output folder, and the
pipeline run against a stand-in run.sh (no export needed, stdlib only).

    python3 -m unittest tools.digitize.tests.test_wizard_core -v
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.digitize.wizard import core  # noqa: E402
from tools.digitize.wizard.core import ImageReport, JobSpec, Measure  # noqa: E402

STUB = r'''#!/usr/bin/env bash
set -e
LOG="$(dirname "$0")/args.log"
IMG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --colors|--size-mm|--fit-mm) echo "$1 $2" >> "$LOG"; shift 2 ;;
    --key-background) echo "--key-background" >> "$LOG"; shift ;;
    *) IMG="$1"; shift ;;
  esac
done
BASE="$(basename "$IMG")"; BASE="${BASE%.*}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
MODE="$(cat "$ROOT/mode" 2>/dev/null || echo ok)"
mkdir -p work output_inkstitch_svg output_vp3
echo "== digitizing $IMG"
echo "warning: source is too coarse"
echo svg > "output_inkstitch_svg/$BASE.svg"
echo zip > "work/$BASE.zip"; echo "stderr text" > "work/$BASE.err"
case "$MODE" in
  fail) echo "boom"; exit 1 ;;
  fail_second) if [[ $(grep -c -- '--fit-mm' "$LOG") -ge 2 ]]; then echo "boom"; exit 1; fi ;;
  hang) sleep 300 & echo $! > "$ROOT/childpid"; echo $$ > "$ROOT/started"; wait ;;
esac
echo "== exporting VP3"; echo vp3 > "output_vp3/$BASE.vp3"
echo "== stitch plan"
echo png > "output_vp3/${BASE}_stitchplan.png"; echo png > "output_vp3/${BASE}_coverage.png"
echo "== done"
'''


def make_root(tmp: Path, mode: str = "ok") -> Path:
    root = tmp / "proj"
    (root / "tools" / "digitize").mkdir(parents=True)
    (root / "tools" / "digitize" / "run.sh").write_text(STUB)
    (root / "mode").write_text(mode)
    return root


def picture(tmp: Path, name: str = "My Patch.png") -> Path:
    p = tmp / name
    p.write_bytes(b"not really a png, the stand-in run.sh never opens it")
    return p


class Seq:
    """measure() stand-in: returns the given Measures in order, remembers the paths."""

    def __init__(self, *measures: Measure):
        self.measures, self.paths = list(measures), []

    def __call__(self, path):
        self.paths.append(Path(path))
        return self.measures[len(self.paths) - 1]


def meas(w10: int, h10: int) -> Measure:
    return Measure(w10, h10, stitches=1000, color_changes=1, threads=["#112233", "#445566"])


def leftovers(root: Path):
    out = []
    for d in ("output_inkstitch_svg", "output_vp3", "work"):
        if (root / d).is_dir():
            out += [str(p) for p in (root / d).iterdir() if p.name.startswith("wiz-")]
    return out


class SlugAndPath(unittest.TestCase):
    def test_slug_rule(self):
        self.assertEqual(core.slugify("Scavenger's Daughter test"), "Scavenger-s-Daughter-test")
        self.assertEqual(core.slugify("a  b///c"), "a-b-c")
        self.assertEqual(core.slugify("ok_name-1.2"), "ok_name-1.2")
        self.assertEqual(core.slugify(""), "design")
        self.assertEqual(core.slugify("..."), "design")
        self.assertEqual(core.slugify(".."), "design")   # stem of '...png': must never name output/..
        self.assertEqual(core.slugify("---"), "design")
        self.assertEqual(core.slugify("ñandú"), "and")
        self.assertEqual(core.slugify(".hidden"), "hidden")
        self.assertLessEqual(len(core.slugify("x" * 500)), core.SLUG_MAX)

    def test_parse_path_forms(self):
        with tempfile.TemporaryDirectory() as t:
            p = picture(Path(t), "Scavenger's Daughter test.png")
            q = picture(Path(t), "plain name.png")
            forms = [str(p), " %s " % p, "'%s'" % p, '"%s"' % p, str(p).replace(" ", "\\ ").replace("'", "\\'"),
                     "file://" + str(p).replace(" ", "%20")]
            for raw in forms:
                self.assertEqual(core.parse_picture_path(raw), p, raw)
            for raw in (str(q), "'%s'" % q, str(q).replace(" ", "\\ ")):
                self.assertEqual(core.parse_picture_path(raw), q, raw)

    def test_parse_path_tilde(self):
        with tempfile.TemporaryDirectory() as t:
            home = Path(t)
            picture(home, "pic.png")
            old = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            try:
                self.assertEqual(core.parse_picture_path("~/pic.png"), home / "pic.png")
            finally:
                if old is None:
                    del os.environ["HOME"]
                else:
                    os.environ["HOME"] = old

    def test_file_checks(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            self.assertIn("cannot find", core.check_picture_file(t / "nope.png"))
            self.assertIn("folder", core.check_picture_file(t))
            for name in ("a.svg", "a.pdf", "a"):
                f = t / name
                f.write_text("x")
                self.assertTrue(core.check_picture_file(f), name)
            for name in ("a.png", "a.JPG", "a.jpeg", "a.webp"):
                f = t / name
                f.write_text("x")
                self.assertEqual(core.check_picture_file(f), "", name)


class FitMath(unittest.TestCase):
    def test_overshoot_in_tenths(self):
        box = (120.0, 120.0)
        self.assertEqual(core.overshoot(meas(1200, 1200), box), (0.0, 0.0))
        self.assertEqual(core.overshoot(meas(1199, 1000), box), (0.0, 0.0))
        self.assertEqual(core.overshoot(meas(1229, 1000), box), (2.9, 0.0))
        self.assertEqual(core.overshoot(meas(1201, 1205), box), (0.1, 0.5))

    def test_corrected_box(self):
        self.assertEqual(core.corrected_box((120.0, 120.0), (2.9, 0.0)), (117.1, 120.0))
        self.assertEqual(core.corrected_box((260.0, 200.0), (0.3, 0.8)), (259.7, 199.2))
        self.assertIsNone(core.corrected_box((20.0, 20.0), (20.0, 0.0)))

    def test_edge_warning_within_two_mm(self):
        box = (120.0, 120.0)
        self.assertEqual(core.edge_warnings(meas(1000, 1000), box), [])
        self.assertEqual(len(core.edge_warnings(meas(1181, 1000), box)), 1)     # 1.9 mm gap
        self.assertEqual(core.edge_warnings(meas(1180, 1000), box), [])         # exactly 2.0 mm: fine
        self.assertEqual(len(core.edge_warnings(meas(1200, 1199), box)), 2)     # touching both
        self.assertEqual(core.edge_warnings(meas(1201, 1000), box), [])         # over: reported as too big instead

    def test_pipeline_args(self):
        spec = JobSpec(Path("a.png"), hoop=(120.0, 120.0), size_mm=100.0, colors=6)
        self.assertEqual(core.pipeline_args(spec, spec.hoop),
                         ["--colors", "6", "--fit-mm", "120x120", "--size-mm", "100"])
        fill = JobSpec(Path("a.png"), key_background=True, hoop=(260.0, 200.0), size_mm=None, colors=4)
        self.assertEqual(core.pipeline_args(fill, (259.7, 199.2)),
                         ["--colors", "4", "--fit-mm", "259.7x199.2", "--key-background"])


class ThreadCount(unittest.TestCase):
    def test_a_colour_sewn_twice_is_one_thread_colour(self):
        m = Measure(1000, 800, 5000, 3, ["#f1c40f", "#c0392b", "#1a1a1a", "#c0392b"])
        self.assertEqual(m.thread_colours, 3)
        spec = JobSpec(Path("a.png"))
        text = core.summary_text(core.JobResult("ok", spec, "a", Path("output/a"), measure=m))
        self.assertIn("3 (3 thread colours)", text)
        self.assertIn("4. #c0392b", text)                    # the sewing order keeps the repeat


class Advice(unittest.TestCase):
    def test_resolution(self):
        rep = ImageReport(width=1000, height=800, design_w=1000, design_h=800)
        self.assertIn("enough detail", core.resolution_advice(rep, 100)[0])
        low = core.resolution_advice(rep, 500)[0]
        self.assertIn("only 2.0 pixels per mm", low)
        self.assertIn("at least 1500 pixels", low)

    def test_rotation_advice(self):
        tall = ImageReport(design_w=400, design_h=800)
        self.assertEqual(core.rotation_advice(tall, (120.0, 120.0), None), [])
        adv = core.rotation_advice(tall, (260.0, 200.0), None)
        self.assertEqual(len(adv), 1)
        self.assertIn("200 mm", adv[0])        # tall now fills the 200 mm height
        self.assertIn("260 mm", adv[0])        # turned, the long side can be 260 mm
        wide = ImageReport(design_w=800, design_h=400)
        self.assertEqual(core.rotation_advice(wide, (260.0, 200.0), None), [])
        self.assertEqual(core.rotation_advice(tall, (260.0, 200.0), 100.0), [])   # 100 mm fits already

    def test_edge_advice_when_artwork_touches_the_picture_edge(self):
        # artwork flush with the left edge, margins elsewhere
        rep = ImageReport(width=800, height=600, design_w=500, design_h=400, design_x=0, design_y=100)
        adv = core.image_advice(rep)
        self.assertTrue(any("touches the edge" in a for a in adv))
        line = [a for a in adv if "touches the edge" in a][0]
        self.assertIn("%s mm" % core.fmt_mm(core.SATIN_BORDER_MM), line)
        self.assertTrue(core.artwork_touches_edge(rep))
        # one pixel from the edge still counts
        near = ImageReport(width=800, height=600, design_w=500, design_h=400, design_x=1, design_y=100)
        self.assertTrue(core.artwork_touches_edge(near))

    def test_no_edge_advice_with_a_margin(self):
        rep = ImageReport(width=800, height=600, design_w=500, design_h=400, design_x=100, design_y=100)
        self.assertFalse(core.artwork_touches_edge(rep))
        self.assertFalse(any("touches the edge" in a for a in core.image_advice(rep)))

    def test_no_edge_advice_when_bounds_position_was_not_measured(self):
        rep = ImageReport(width=800, height=600, design_w=800, design_h=600)
        self.assertFalse(core.artwork_touches_edge(rep))
        self.assertFalse(any("touches the edge" in a for a in core.image_advice(rep)))


class PipelineWarnings(unittest.TestCase):
    SATIN = ("warning: satin %s is %s mm wide, below Ink/Stitch's 1.0 mm gate "
             "-- it will stitch as running stitch")

    def test_satin_warnings_collapse_to_one_line(self):
        lines = ["== digitizing x",
                 self.SATIN % ("sat-1", "0.80"),
                 self.SATIN % ("sat-2", "0.62"),
                 self.SATIN % ("s_3", "0.95"),
                 "warning: source is too coarse"]
        out = core._pipeline_warnings(lines)
        satin = [w for w in out if "thin line" in w]
        self.assertEqual(len(satin), 1)
        self.assertIn("3 thin lines", satin[0])
        self.assertIn("the 1.0 mm", satin[0])
        self.assertIn("the narrowest is 0.62 mm", satin[0])
        self.assertIn("Source is too coarse", out)          # other warnings kept
        self.assertNotIn("warning: satin", "\n".join(out))  # the raw lines are gone

    def test_satin_warnings_dedupe_across_passes(self):
        line = self.SATIN % ("sat-1", "0.80")
        out = core._pipeline_warnings([line, line])
        self.assertEqual(len(out), 1)
        self.assertIn("1 thin line is narrower", out[0])
        self.assertIn("it is 0.80 mm", out[0])

    def test_dropped_outline_note_becomes_one_plain_line(self):
        note = "note: dropped 3 outline satin(s) shorter than their own width (5 -> 2)"
        out = core._pipeline_warnings([note, "note: pinned colour(s) with no pixels dropped: #000000"])
        self.assertEqual(out, ["3 very short pieces of outline were left out because they were "
                               "shorter than they are wide."])

    def test_dropped_outline_note_dedupes_across_passes(self):
        note = "note: dropped 2 outline satin(s) shorter than their own width (4 -> 2)"
        out = core._pipeline_warnings([note, note])
        self.assertEqual(len(out), 1)
        self.assertIn("2 very short pieces of outline", out[0])

    def test_satin_and_dropped_keep_their_place_between_other_warnings(self):
        lines = ["warning: first",
                 self.SATIN % ("a", "0.70"),
                 "warning: middle",
                 "note: dropped 1 outline satin(s) shorter than their own width (3 -> 2)",
                 "warning: last"]
        out = core._pipeline_warnings(lines)
        self.assertEqual(len(out), 5)
        self.assertIn("First", out[0])
        self.assertIn("thin line", out[1])
        self.assertIn("Middle", out[2])
        self.assertIn("very short pieces", out[3])
        self.assertIn("Last", out[4])


class PickName(unittest.TestCase):
    def test_numbering_and_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            self.assertEqual(core.pick_name(out, "x", core.KEEP_BOTH), "x")
            (out / "x").mkdir()
            self.assertEqual(core.pick_name(out, "x", core.KEEP_BOTH), "x-2")
            (out / "x-2").mkdir()
            self.assertEqual(core.pick_name(out, "x", core.KEEP_BOTH), "x-3")
            self.assertEqual(core.pick_name(out, "x", core.OVERWRITE), "x")
            (out / "f").write_text("a file")
            self.assertEqual(core.pick_name(out, "f", core.OVERWRITE), "f-2")   # never replace a plain file


class RunJob(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.addCleanup(self._t.cleanup)

    def job(self, mode="ok", measure=None, **kw):
        root = make_root(self.tmp, mode)
        spec = JobSpec(picture(self.tmp), colors=6, size_mm=100.0)
        res = core.run_job(spec, root, measure=measure or Seq(meas(1000, 800)), **kw)
        return root, spec, res

    def test_happy_path_files_and_cleanup(self):
        stages = []
        root, spec, res = self.job(on_stage=stages.append)
        self.assertEqual(res.status, "ok")
        self.assertEqual(res.folder, root / "output" / "My-Patch")
        names = sorted(p.name for p in res.folder.iterdir())
        self.assertEqual(names, ["My-Patch.svg", "My-Patch.vp3", "My-Patch_coverage.png",
                                 "My-Patch_stitchplan.png", "summary.txt"])
        self.assertEqual(sorted(res.files), names)
        self.assertEqual(leftovers(root), [])
        self.assertEqual([p.name for p in (root / "output").iterdir()], ["My-Patch"])     # no stage folder left
        self.assertEqual(list((root / "work").iterdir()), [])                              # zip and err gone
        self.assertEqual(list((root / "output_vp3").iterdir()), [])
        self.assertIn("Making the embroidery file", stages)
        text = (res.folder / "summary.txt").read_text()
        self.assertIn("Stitched size:   100 x 80 mm", text)
        self.assertIn("1. #112233", text)
        self.assertIn("Source is too coarse", text)           # pipeline warning carried over
        self.assertNotIn("—", text)
        args = (root / "tools/digitize/args.log").read_text().split("\n")
        self.assertIn("--fit-mm 120x120", args)
        self.assertIn("--size-mm 100", args)

    def test_unique_base_never_touches_existing_files(self):
        root = make_root(self.tmp)
        for d, n in (("output_inkstitch_svg", "My-Patch.svg"), ("output_vp3", "My-Patch.vp3"),
                     ("output_vp3", "My-Patch_stitchplan.png")):
            (root / d).mkdir(exist_ok=True)
            (root / d / n).write_text("precious")
        core.run_job(JobSpec(picture(self.tmp)), root, measure=Seq(meas(1000, 800)))
        for d, n in (("output_inkstitch_svg", "My-Patch.svg"), ("output_vp3", "My-Patch.vp3"),
                     ("output_vp3", "My-Patch_stitchplan.png")):
            self.assertEqual((root / d / n).read_text(), "precious")

    def test_T4_no_silent_overwrite(self):
        root = make_root(self.tmp)
        old = root / "output" / "My-Patch"
        old.mkdir(parents=True)
        (old / "sentinel.txt").write_text("keep me")
        spec = JobSpec(picture(self.tmp))
        r1 = core.run_job(spec, root, measure=Seq(meas(1000, 800)))
        self.assertEqual((old / "sentinel.txt").read_text(), "keep me")
        self.assertEqual(sorted(p.name for p in old.iterdir()), ["sentinel.txt"])
        self.assertEqual(r1.folder, root / "output" / "My-Patch-2")
        self.assertTrue((r1.folder / "My-Patch.vp3").is_file())
        self.assertIn("My-Patch-2", (r1.folder / "summary.txt").read_text())
        r2 = core.run_job(spec, root, measure=Seq(meas(1000, 800)))
        self.assertEqual(r2.folder, root / "output" / "My-Patch-3")

    def test_overwrite_only_when_asked(self):
        root = make_root(self.tmp)
        old = root / "output" / "My-Patch"
        old.mkdir(parents=True)
        (old / "sentinel.txt").write_text("old")
        res = core.run_job(JobSpec(picture(self.tmp)), root, policy=core.OVERWRITE, measure=Seq(meas(1000, 800)))
        self.assertEqual(res.folder, old)
        self.assertFalse((old / "sentinel.txt").exists())
        self.assertTrue((old / "My-Patch.vp3").is_file())
        self.assertEqual(sorted(p.name for p in (root / "output").iterdir()), ["My-Patch"])

    def test_T5_forced_pipeline_failure_leaves_nothing(self):
        root, _spec, res = self.job("fail")
        self.assertEqual(res.status, "failed")
        self.assertEqual(res.exit_code, 1)
        self.assertIsNone(res.folder)
        self.assertIn("boom", "\n".join(res.log_tail))
        self.assertIn("stderr text", "\n".join(res.log_tail))      # the .err tail is kept for the message
        self.assertEqual(list((root / "output").iterdir()), [])
        self.assertEqual(leftovers(root), [])

    def test_measure_error_leaves_nothing(self):
        root = make_root(self.tmp)

        def broken(_path):
            raise RuntimeError("corrupt vp3")

        with self.assertRaises(RuntimeError):
            core.run_job(JobSpec(picture(self.tmp)), root, measure=broken)
        self.assertEqual(list((root / "output").iterdir()), [])
        self.assertEqual(leftovers(root), [])

    def test_T5_sigint_leaves_nothing(self):
        root = make_root(self.tmp, "hang")
        pic = picture(self.tmp)
        harness = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            from pathlib import Path
            from tools.digitize.wizard import core
            core.run_job(core.JobSpec(Path(%r)), Path(%r), measure=lambda p: None)
        """) % (str(REPO), str(pic), str(root))
        proc = subprocess.Popen([sys.executable, "-c", harness], stderr=subprocess.PIPE, universal_newlines=True)
        try:
            deadline = time.time() + 20
            while not (root / "started").exists() and time.time() < deadline:
                time.sleep(0.05)
            self.assertTrue((root / "started").exists(), "the stand-in pipeline never started")
            self.assertTrue(any((root / "output").iterdir()), "the stage folder should exist mid-run")
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
        err = proc.stderr.read()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("KeyboardInterrupt", err)
        self.assertEqual(list((root / "output").iterdir()), [], "no output/<slug> and no stage folder")
        self.assertEqual(leftovers(root), [])
        child = int((root / "childpid").read_text())
        for _ in range(50):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(child, signal.SIGKILL)
            self.fail("the pipeline's child process was left running")

    def test_second_pass_corrects_overshoot(self):
        seq = Seq(meas(1229, 1000), meas(1198, 980))
        root, _spec, res = self.job(measure=seq)
        self.assertEqual(res.status, "ok")
        self.assertEqual([p.number for p in res.passes], [1, 2])
        self.assertEqual(res.passes[1].box, (117.1, 120.0))
        log = (root / "tools/digitize/args.log").read_text().split("\n")
        self.assertIn("--fit-mm 120x120", log)
        self.assertIn("--fit-mm 117.1x120", log)
        self.assertEqual(log.count("--size-mm 100"), 2)                 # the size cap stays
        self.assertEqual(res.measure.width10, 1198)
        self.assertEqual(len(seq.paths), 2)
        text = (res.folder / "summary.txt").read_text()
        self.assertIn("Fit correction", text)
        self.assertIn("117.1 x 120 mm", text)
        self.assertEqual(leftovers(root), [])
        self.assertEqual(sorted(p.name for p in res.folder.iterdir()),
                         ["My-Patch.svg", "My-Patch.vp3", "My-Patch_coverage.png", "My-Patch_stitchplan.png",
                          "summary.txt"])

    def test_no_second_pass_when_inside(self):
        seq = Seq(meas(1000, 800))
        _root, _spec, res = self.job(measure=seq)
        self.assertEqual(len(seq.paths), 1)
        self.assertEqual(len(res.passes), 1)

    def test_still_too_big_after_second_pass_is_a_failure(self):
        seq = Seq(meas(1229, 1000), meas(1215, 990))
        root, _spec, res = self.job(measure=seq)
        self.assertEqual(res.status, "too_big")
        self.assertEqual(res.exit_code, 1)
        self.assertTrue(res.folder.is_dir())                              # the files stay
        text = (res.folder / "summary.txt").read_text()
        self.assertIn("TOO BIG FOR THE HOOP", text)
        self.assertIn("121.5 x 99 mm", text)
        self.assertEqual(leftovers(root), [])

    def test_second_pass_pipeline_failure_keeps_first_result_as_too_big(self):
        seq = Seq(meas(1229, 1000))
        root, _spec, res = self.job("fail_second", measure=seq)
        self.assertEqual(res.status, "too_big")
        self.assertTrue((res.folder / "My-Patch.vp3").is_file())
        self.assertTrue(any("second run" in w for w in res.warnings))
        self.assertEqual(leftovers(root), [])

    def test_edge_warning_reaches_the_summary(self):
        _root, _spec, res = self.job(measure=Seq(meas(1195, 900)))
        self.assertEqual(res.status, "ok")
        self.assertTrue(any("0.5 mm from the edge" in w for w in res.warnings))
        self.assertIn("0.5 mm from the edge", (res.folder / "summary.txt").read_text())

    def test_jpg_extension_is_kept_lowercase(self):
        root = make_root(self.tmp)
        pic = picture(self.tmp, "Photo.JPG")
        res = core.run_job(JobSpec(pic), root, measure=Seq(meas(1000, 800)))
        self.assertEqual(res.status, "ok")
        self.assertEqual(res.folder.name, "Photo")


if __name__ == "__main__":
    unittest.main()
