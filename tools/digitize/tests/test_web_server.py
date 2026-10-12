"""Tests for the local web server: every route against stand-in run.sh and export_svg.sh.

No real pipeline, no Ink/Stitch, no image export: the two scripts are bash stubs that
write the files the server looks for. The picture check and Flask are the real ones.

    python3 -m unittest tools.digitize.tests.test_web_server -v
"""
from __future__ import annotations

import io
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.digitize.web import server  # noqa: E402
from tools.digitize.wizard.core import Measure  # noqa: E402

# Stands in for tools/digitize/run.sh: the last argument is the picture, the base name of
# the picture is the base of the run, and one SVG comes out of output_inkstitch_svg/.
RUN_STUB = r'''#!/usr/bin/env bash
set -euo pipefail
HERE="$(dirname "$0")"
MODE="$(cat "$HERE/mode" 2>/dev/null || echo ok)"
IMG=""
for a in "$@"; do IMG="$a"; done
BASE="$(basename "$IMG")"; BASE="${BASE%.*}"
ROOT="$(cd "$HERE/../.." && pwd)"; cd "$ROOT"
mkdir -p output_inkstitch_svg
echo "== digitizing $IMG -> output_inkstitch_svg/$BASE.svg  (flags: $*)"
case "$MODE" in
  slow) sleep 2 ;;
  boom) echo "boom" >&2; exit 3 ;;
esac
cat > "output_inkstitch_svg/$BASE.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 40 30">
<path id="f0" d="M4 4h10v8h-10z" style="fill:#ddb97f"/>
<path id="s1" d="M20 4h4v20h-4z" style="fill:#bc7d28"/>
</svg>
SVG
echo "warning: satin s1 is 0.80 mm wide, below Ink/Stitch's 1.0 mm gate -- it will run as a running stitch"
echo "== done: output_inkstitch_svg/$BASE.svg"
'''

# Stands in for tools/digitize/export_svg.sh. It drops the satin path from the SVG it is
# given (what satin_precheck.py --fix does) and writes the files the server reads.
EXPORT_STUB = r'''#!/usr/bin/env bash
set -euo pipefail
HERE="$(dirname "$0")"
MODE="$(cat "$HERE/mode" 2>/dev/null || echo ok)"
SVG="$1"; OUT="$2"
DIR="$(dirname "$OUT")"
echo "$@" > "$DIR/export_args.txt"
if [[ "$MODE" == "fail" ]]; then echo "boom" >&2; exit 3; fi
if [[ "$MODE" == "hang" ]]; then
  echo "== exporting VP3"
  echo $$ > "$DIR/pgid"
  sleep 300 &
  echo $! > "$DIR/grandchild.pid"
  wait
fi
echo "== satin precheck"
if [[ "$MODE" == "nope" ]]; then echo "== done: nothing at all"; exit 0; fi
grep -v 'id="s1"' "$SVG" > "$SVG.fixed" || true
mv "$SVG.fixed" "$SVG"
echo "== exporting VP3"
echo "warning: satin s1 was removed before the export"
printf 'not a real vp3\n' > "$OUT.vp3"
printf 'not a real png\n' > "${OUT}_stitchplan.png"
printf 'not a real png\n' > "${OUT}_coverage.png"
printf 'not a real zip\n' > "${OUT}.zip"
printf 'no inkstitch here\n' > "${OUT}.err"
echo "== stitch plan"
echo "== jam check"
echo "== done: $OUT.vp3"
'''


def png_bytes(width: int = 40, height: int = 30) -> bytes:
    """A small picture with a transparent background and an opaque blob in the middle."""
    from PIL import Image

    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for x in range(10, 30):
        for y in range(8, 22):
            im.putpixel((x, y), (221, 185, 127, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class ServerTestCase(unittest.TestCase):
    """A temp repo with the two stand-in scripts, one app and one test client."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proj"
        tools = self.root / "tools" / "digitize"
        tools.mkdir(parents=True)
        self.run_sh = tools / "run.sh"
        self.export_sh = tools / "export_svg.sh"
        self.mode_file = tools / "mode"
        for script, text in ((self.run_sh, RUN_STUB), (self.export_sh, EXPORT_STUB)):
            script.write_text(text)
            script.chmod(0o755)
        self.set_mode("ok")
        self.out_root = self.root / "output" / "web"
        self.app = server.create_app(self.root, run_sh=self.run_sh, export_sh=self.export_sh,
                                     out_root=self.out_root)
        self.client = self.app.test_client()
        self.addCleanup(self.settle)          # never leave a pipeline writing into a removed folder

    # ---- helpers ------------------------------------------------------------

    def set_mode(self, mode: str):
        self.mode_file.write_text(mode)

    def settle(self, seconds: float = 20.0):
        """Wait until the job is done, so teardown never races a background thread."""
        job = self.app.job
        end = time.time() + seconds
        while time.time() < end:
            with job.lock:
                if job.proc is None and job.thread is None and not job.reserved:
                    return
            time.sleep(0.02)

    def get(self, url: str):
        return self.client.get(url)

    def get_json(self, url: str):
        resp = self.get(url)
        return resp, resp.get_json()

    def post(self, url: str, payload=None):
        return self.client.post(url, json=payload if payload is not None else {})

    def status(self) -> dict:
        resp = self.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def upload(self, name: str = "Skyfowl Patch.PNG", data: bytes = None):
        return self.client.post("/api/picture",
                                data={"picture": (io.BytesIO(data if data is not None
                                                             else png_bytes()), name)},
                                content_type="multipart/form-data")

    def wait_state(self, want, seconds: float = 20.0) -> dict:
        """Poll /api/status until the state is one of `want`."""
        end = time.time() + seconds
        st = {}
        while time.time() < end:
            st = self.status()
            if st["state"] in want:
                return st
            time.sleep(0.05)
        self.fail("state stayed %r, wanted %r; log: %r" % (st.get("state"), want, st.get("log_tail")))
        return st

    def do_slice(self, **extra):
        body = {"hoop": [120, 120], "size_mm": 100, "colors": 6, "key_background": False,
                "yaml_text": "", "overrides": []}
        body.update(extra)
        return self.post("/api/slice", body)

    def do_plan(self):
        return self.post("/api/stitchplan")

    def picture_loaded(self):
        resp = self.upload()
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return resp.get_json()

    def job_dir(self) -> Path:
        return self.out_root / self.app.job.picture["slug"]

    def measured(self, m=None):
        """Patch vp3.measure: reading a real VP3 needs Ink/Stitch, which the tests do not run."""
        return mock.patch.object(server.vp3, "measure",
                                 return_value=m or Measure(1185, 1190, stitches=17065, color_changes=1,
                                                          threads=["#ddb97f", "#bc7d28"]))


# ---- options, picture, yaml ------------------------------------------------------------


class Options(ServerTestCase):
    def test_options(self):
        resp, data = self.get_json("/api/options")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data, {"hoops": [[120.0, 120.0], [260.0, 200.0]], "default_hoop": 0,
                                "default_size_mm": 100.0, "colors": [4, 6, 8], "default_colors": 6})

    def test_page_or_json_error(self):
        page = server.HERE / "static" / "index.html"
        resp = self.get("/")
        if page.is_file():
            self.assertEqual(resp.status_code, 200)
        else:
            self.assertEqual(resp.status_code, 404)
            self.assertIn("error", resp.get_json())


class Picture(ServerTestCase):
    def test_upload(self):
        resp = self.upload("Skyfowl Patch.PNG")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertEqual(data["slug"], "Skyfowl-Patch")
        self.assertEqual(data["url"], "/files/Skyfowl-Patch/picture.png")     # suffix lowered
        self.assertEqual((data["width"], data["height"]), (40, 30))
        self.assertEqual(data["kind"], "transparent")
        self.assertEqual(data["background_hex"], "")
        self.assertTrue(any("40 x 30 pixels" in a for a in data["advice"]), data["advice"])
        self.assertTrue((self.job_dir() / "picture.png").is_file())
        st = self.status()
        self.assertEqual(st["picture"], {"slug": "Skyfowl-Patch",
                                         "url": "/files/Skyfowl-Patch/picture.png",
                                         "width": 40, "height": 30})

    def test_bad_suffix(self):
        resp = self.upload("notes.gif", b"GIF89a")
        self.assertEqual(resp.status_code, 400)
        self.assertIn(".gif", resp.get_json()["error"])
        self.assertIsNone(self.status()["picture"])

    def test_no_file(self):
        resp = self.client.post("/api/picture", data={}, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_unreadable_picture(self):
        resp = self.upload("broken.png", b"this is not a png")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())
        self.assertIsNone(self.status()["picture"])

    def test_new_picture_replaces_the_folder_and_forgets_the_slice(self):
        self.picture_loaded()
        self.do_slice()
        st = self.wait_state({"idle"})
        self.assertIsNotNone(st["slice"])
        (self.job_dir() / "stale.txt").write_text("left over from the last job")
        with self.measured():
            self.do_plan()
            self.wait_state({"idle"})
        self.assertIsNotNone(self.status()["stitchplan"])
        resp = self.upload("Skyfowl Patch.PNG")          # same name again: E5
        self.assertEqual(resp.status_code, 200)
        st = self.status()
        self.assertIsNone(st["slice"], "a new picture clears the Slice")
        self.assertIsNone(st["stitchplan"], "a new picture clears the Stitch plan")
        self.assertFalse((self.job_dir() / "stale.txt").exists(), "the folder is made fresh")

    def test_only_a_real_folder_with_that_name_is_replaced(self):
        self.out_root.mkdir(parents=True, exist_ok=True)
        link = self.out_root / "linked"
        link.symlink_to(self.root)                       # a link out of the output folder
        resp = self.upload("linked.PNG")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())
        self.assertTrue(link.is_symlink())


class YamlCheck(ServerTestCase):
    def test_valid(self):
        text = "profile: vadmel\npalette:\n  - '#ddb97f'\n"
        r = self.post("/api/yaml", {"yaml_text": text}).get_json()
        self.assertEqual(r, {"ok": True, "has_palette": True, "stitch_overrides": []})

    def test_no_palette_and_overrides(self):
        r = self.post("/api/yaml", {"yaml_text": "stitch_overrides:\n  - at_px: [4, 5]\n"
                                                    "    type: satin\n"}).get_json()
        self.assertTrue(r["ok"])
        self.assertFalse(r["has_palette"])
        self.assertEqual(r["stitch_overrides"], [{"at_px": [4, 5], "type": "satin"}])

    def test_empty_text(self):
        self.assertEqual(self.post("/api/yaml", {"yaml_text": ""}).get_json(),
                         {"ok": True, "has_palette": False, "stitch_overrides": []})
        self.assertEqual(self.post("/api/yaml", {}).get_json(),
                         {"ok": True, "has_palette": False, "stitch_overrides": []})

    def test_broken_yaml_gives_the_line(self):
        r = self.post("/api/yaml", {"yaml_text": "a: 1\n  b: 2\n"}).get_json()
        self.assertFalse(r["ok"])
        self.assertTrue(r["error"].startswith("line 2: "), r["error"])

    def test_yaml_that_is_not_settings(self):
        r = self.post("/api/yaml", {"yaml_text": "- one\n- two\n"}).get_json()
        self.assertFalse(r["ok"])
        self.assertIn("list", r["error"])


# ---- slice ------------------------------------------------------------------------------


class Slice(ServerTestCase):
    def test_happy_path(self):
        self.picture_loaded()
        resp = self.do_slice()
        self.assertEqual(resp.status_code, 202, resp.get_data(as_text=True))
        slice_id = resp.get_json()["slice_id"]
        st = self.wait_state({"idle", "failed"})
        self.assertEqual(st["state"], "idle", st["error"])
        jobdir = self.job_dir()
        self.assertTrue((jobdir / "slice.svg").is_file())
        self.assertFalse((jobdir / "_in").exists(), "the staged copy is cleaned up")
        self.assertFalse((jobdir / "_slice").exists())
        self.assertEqual(list(self.root.glob("output_inkstitch_svg/*")), [])
        self.assertEqual(st["slice"]["slice_id"], slice_id)
        self.assertEqual(st["slice"]["svg_url"],
                         "/files/Skyfowl-Patch/slice.svg?v=%d" % slice_id)
        self.assertIsNone(st["slice"]["regions_url"])       # the stand-in writes no sidecar
        self.assertEqual(st["slice"]["overrides"], [])
        self.assertEqual(st["stage"], "Reading the picture and planning the stitches")
        self.assertIn("== digitizing", "\n".join(st["log_tail"]))
        self.assertIn("== digitizing", (jobdir / "log.txt").read_text())
        self.assertGreaterEqual(st["elapsed_s"], 0.0)

    def test_status_shape(self):
        self.picture_loaded()
        st = self.status()
        self.assertEqual(sorted(st), ["elapsed_s", "error", "log_tail", "picture", "slice",
                                      "stage", "state", "stitchplan"])
        self.assertEqual(st["state"], "idle")
        self.assertIsNone(st["stage"])
        self.assertIsNone(st["elapsed_s"])
        self.assertEqual(st["log_tail"], [])
        self.assertIsNone(st["error"])
        self.do_slice()
        st = self.wait_state({"idle", "failed"})
        self.assertIsNotNone(st["elapsed_s"])
        self.assertIsInstance(st["stage"], str)
        first = st["elapsed_s"]
        time.sleep(0.3)
        self.assertEqual(self.status()["elapsed_s"], first, "elapsed stops when the job ends")

    def test_stage_while_running(self):
        self.picture_loaded()
        self.set_mode("slow")
        self.assertEqual(self.do_slice().status_code, 202)
        self.assertEqual(self.status()["state"], "slicing")
        self.assertEqual(self.wait_state({"idle", "failed"})["state"], "idle")

    def test_job_yaml_holds_the_overrides(self):
        self.picture_loaded()
        overrides = [{"at_px": [412, 310], "type": "satin"}, {"at_px": [128.5, 95], "type": "fill"}]
        self.do_slice(yaml_text="profile: vadmel\n", overrides=overrides)
        self.wait_state({"idle", "failed"})
        written = yaml.safe_load((self.job_dir() / "job.yaml").read_text())
        self.assertEqual(written["profile"], "vadmel")
        self.assertEqual(written["stitch_overrides"], overrides)
        self.assertEqual(self.status()["slice"]["overrides"], overrides)
        flags = (self.job_dir() / "log.txt").read_text()
        self.assertIn("--no-export", flags)
        self.assertIn("--colors 6 --fit-mm 120x120 --size-mm 100 --no-export --config", flags)

    def test_empty_overrides_leave_the_key_out(self):
        self.picture_loaded()
        self.do_slice(yaml_text="profile: vadmel\nstitch_overrides:\n  - at_px: [1, 2]\n"
                                "    type: satin\n", overrides=[])
        self.wait_state({"idle", "failed"})
        written = yaml.safe_load((self.job_dir() / "job.yaml").read_text())
        self.assertNotIn("stitch_overrides", written, "G1: absent means today's behaviour")
        self.assertEqual(written, {"profile": "vadmel"})

    def test_bad_bodies(self):
        self.picture_loaded()
        cases = [{"hoop": [120]}, {"hoop": "120x120"}, {"hoop": [0, 120]},
                 {"hoop": [120, 120], "size_mm": 0, "colors": 6},
                 {"hoop": [120, 120], "size_mm": "big", "colors": 6},
                 {"hoop": [120, 120], "size_mm": None, "colors": 5},
                 {"hoop": [120, 120], "size_mm": None, "colors": 6, "overrides": [{"at_px": [1]}]},
                 {"hoop": [120, 120], "size_mm": None, "colors": 6,
                  "overrides": [{"at_px": [1, 2], "type": "outline"}]},
                 {"hoop": [120, 120], "size_mm": None, "colors": 6, "overrides": {"at_px": [1, 2]}},
                 {"hoop": [120, 120], "size_mm": None, "colors": 6, "yaml_text": "- a\n- b\n"},
                 {"hoop": [120, 120], "size_mm": None, "colors": 6, "yaml_text": "a: 1\n  b: 2\n"}]
        for body in cases:
            resp = self.post("/api/slice", body)
            self.assertEqual(resp.status_code, 400, body)
            self.assertIn("error", resp.get_json(), body)
        self.assertIsNone(self.status()["slice"])

    def test_no_picture(self):
        resp = self.do_slice()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("picture", resp.get_json()["error"].lower())

    def test_failed_run(self):
        self.set_mode("boom")
        self.picture_loaded()
        self.do_slice()
        st = self.wait_state({"idle", "failed"})
        self.assertEqual(st["state"], "failed")
        self.assertIn("exit code 3", st["error"])
        self.assertIn("boom", st["log_tail"])
        self.assertIsNone(st["slice"])
        self.assertFalse((self.job_dir() / "slice.svg").exists())


# ---- stitch plan ------------------------------------------------------------------------


class StitchPlan(ServerTestCase):
    def slice_first(self, **extra):
        self.picture_loaded()
        resp = self.do_slice(**extra)
        self.assertEqual(resp.status_code, 202)
        self.wait_state({"idle", "failed"})
        return resp.get_json()["slice_id"]

    def test_without_a_slice(self):
        resp = self.post("/api/stitchplan")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json(), {"error": "no Slice yet"})
        self.picture_loaded()                       # a picture alone is not a Slice
        resp = self.post("/api/stitchplan")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json(), {"error": "no Slice yet"})

    def test_happy_path(self):
        slice_id = self.slice_first()
        with self.measured():
            resp = self.post("/api/stitchplan")
            self.assertEqual(resp.status_code, 202)
            self.assertEqual(resp.get_json(), {"slice_id": slice_id})
            st = self.wait_state({"idle", "failed"})
        self.assertEqual(st["state"], "idle", st["error"])
        plan = st["stitchplan"]
        self.assertEqual(sorted(plan), ["coverage_url", "height_mm", "removed_by_precheck",
                                        "slice_id", "stitches", "stitchplan_url", "threads",
                                        "vp3_url", "warnings", "width_mm"])
        self.assertEqual(plan["slice_id"], slice_id)
        self.assertEqual(plan["stitches"], 17065)
        self.assertEqual((plan["width_mm"], plan["height_mm"]), (118.5, 119.0))
        self.assertEqual(plan["threads"], ["#ddb97f", "#bc7d28"])
        self.assertEqual(plan["vp3_url"], "/files/Skyfowl-Patch/plan.vp3?v=%d" % slice_id)
        self.assertEqual(plan["stitchplan_url"],
                         "/files/Skyfowl-Patch/plan_stitchplan.png?v=%d" % slice_id)
        self.assertEqual(plan["coverage_url"],
                         "/files/Skyfowl-Patch/plan_coverage.png?v=%d" % slice_id)
        self.assertEqual(plan["removed_by_precheck"], ["s1"])
        self.assertTrue(any("mm from the edge" in w for w in plan["warnings"]), plan["warnings"])
        self.assertTrue(any(w.startswith("warning:") for w in plan["warnings"]), plan["warnings"])
        jobdir = self.job_dir()
        for name in ("plan.svg", "plan.vp3", "plan_stitchplan.png", "plan_coverage.png",
                     "plan.zip", "plan.err"):
            self.assertTrue((jobdir / name).is_file(), name)
        self.assertNotIn('id="s1"', (jobdir / "plan.svg").read_text())
        self.assertIn('id="s1"', (jobdir / "slice.svg").read_text())
        args = (jobdir / "export_args.txt").read_text().strip()
        self.assertTrue(args.endswith("plan.svg %s/plan" % jobdir), args)   # the copy, not slice.svg

    def test_background_flag_from_the_job_yaml(self):
        cases = [("", None), ("profile: vadmel\n", "#101010"), ("profile: VadMel\n", "#101010"),
                 ("fabric_color: '#ffffff'\nprofile: vadmel\n", "#ffffff")]
        for yaml_text, wanted in cases:
            self.slice_first(yaml_text=yaml_text)
            with self.measured():
                self.post("/api/stitchplan")
                self.wait_state({"idle", "failed"})
            args = (self.job_dir() / "export_args.txt").read_text()
            self.assertEqual("--background" in args, wanted is not None, yaml_text)
            if wanted:
                self.assertIn(wanted, args, yaml_text)

    def test_no_machine_file(self):
        self.slice_first()
        self.set_mode("nope")                          # the export finishes and writes nothing
        with mock.patch.object(server.vp3, "measure",
                               side_effect=AssertionError("must not be called")):
            self.post("/api/stitchplan")
            st = self.wait_state({"idle", "failed"})
        self.assertEqual(st["state"], "failed")
        self.assertIn("machine file", st["error"])
        self.assertIsNone(st["stitchplan"])

    def test_failed_export(self):
        self.slice_first()
        self.set_mode("fail")
        with mock.patch.object(server.vp3, "measure",
                               side_effect=AssertionError("must not be called")):
            self.post("/api/stitchplan")
            st = self.wait_state({"idle", "failed"})
        self.assertEqual(st["state"], "failed")
        self.assertIn("exit code 3", st["error"])
        self.assertIn("boom", st["log_tail"])          # stderr comes back on the same pipe
        self.assertIsNone(st["stitchplan"])


# ---- one job at a time, cancel, files ------------------------------------------------------


class OneJobAtATime(ServerTestCase):
    def test_g4_two_slices_give_one_202_and_one_409(self):
        self.picture_loaded()
        self.set_mode("slow")
        first = self.do_slice()
        second = self.do_slice()
        codes = sorted([first.status_code, second.status_code])
        self.assertEqual(codes, [202, 409])
        self.assertEqual((first if first.status_code == 409 else second).get_json(),
                         {"error": "busy"})
        self.assertEqual(self.post("/api/picture", {}).status_code, 409)
        self.wait_state({"idle", "failed"})
        self.assertEqual(self.status()["slice"]["slice_id"], 1)

    def test_stitchplan_is_409_while_a_slice_runs(self):
        self.picture_loaded()
        self.set_mode("slow")
        self.do_slice()
        self.assertEqual(self.do_plan().status_code, 409)
        self.wait_state({"idle", "failed"})
        with self.measured():
            self.assertEqual(self.do_plan().status_code, 202)
            self.wait_state({"idle", "failed"})


class Cancel(ServerTestCase):
    def test_g5_cancel_kills_the_whole_process_group(self):
        self.picture_loaded()
        self.do_slice()
        self.wait_state({"idle", "failed"})
        self.set_mode("hang")
        with self.measured():
            self.assertEqual(self.post("/api/stitchplan").status_code, 202)
            jobdir = self.job_dir()
            end = time.time() + 20
            while time.time() < end and not (jobdir / "grandchild.pid").is_file():
                self.assertEqual(self.status()["state"], "exporting")
                time.sleep(0.05)
            self.assertTrue((jobdir / "grandchild.pid").is_file(), "the export never started")
            pgid = int((jobdir / "pgid").read_text())
            child = int((jobdir / "grandchild.pid").read_text())
            resp = self.post("/api/cancel")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json(), {"cancelled": True})
        self.wait_state({"cancelled", "failed"})
        self.assertEqual(self.status()["state"], "cancelled")
        self.assertIsNone(self.status()["stitchplan"])
        end = time.time() + 15
        while time.time() < end:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.killpg(pgid, 9)
            self.fail("the export process group is still alive after Cancel")
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_cancel_without_a_job(self):
        resp = self.post("/api/cancel")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"cancelled": False})


class Files(ServerTestCase):
    def test_serves_a_job_file(self):
        self.picture_loaded()
        self.do_slice()
        self.wait_state({"idle", "failed"})
        with self.client.get("/files/Skyfowl-Patch/slice.svg") as resp:
            self.assertEqual(resp.status_code, 200)
            self.assertIn('id="f0"', resp.get_data(as_text=True))

    def test_refuses_paths_outside_the_job_folder(self):
        self.picture_loaded()
        self.do_slice()
        self.wait_state({"idle", "failed"})
        for url in ("/files/Skyfowl-Patch/..%2Fjob.yaml",
                    "/files/..%2F..%2Fetc/passwd",
                    "/files/Skyfowl-Patch/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
                    "/files/Skyfowl-Patch/a%20b.svg",
                    "/files/Skyfowl-Patch/../job.yaml",
                    "/files/no-such-slug/slice.svg"):
            resp = self.get(url)
            self.assertEqual(resp.status_code, 404, url)
            self.assertIn("error", resp.get_json(), url)


# ---- G3: bound to 127.0.0.1 only -------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def lan_address() -> str:
    """This machine's non-loopback IPv4 address, or '' when there is none."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("192.0.2.1", 9))          # TEST-NET-1: no packet is sent
        return s.getsockname()[0]


class LoopbackOnly(unittest.TestCase):
    def test_g3_not_reachable_from_the_lan(self):
        port = free_port()
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
        script = textwrap.dedent("""
            import sys
            from tools.digitize.web.server import main
            raise SystemExit(main(["--port", "%d"]))
        """) % port
        proc = subprocess.Popen([sys.executable, "-c", script], cwd=str(REPO), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            end = time.time() + 30
            while time.time() < end:
                with socket.socket() as probe:
                    probe.settimeout(0.5)
                    if probe.connect_ex(("127.0.0.1", port)) == 0:
                        break
                if proc.poll() is not None:
                    self.fail("the server stopped: %s" % proc.stdout.read())
                time.sleep(0.1)
            else:
                self.fail("the server never answered on 127.0.0.1:%d" % port)
            address = lan_address()
            if not address or address.startswith("127.") or address == "0.0.0.0":
                self.skipTest("this machine has no non-loopback IPv4 address to try")
            with socket.socket() as probe:
                probe.settimeout(5)
                self.assertNotEqual(probe.connect_ex((address, port)), 0,
                                    "the server answered on the LAN address %s" % address)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
            proc.stdout.close()


if __name__ == "__main__":
    unittest.main()