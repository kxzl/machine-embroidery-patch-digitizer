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
import threading
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
# sidecar: the run also writes the two files a real Slice may add (T1's regions.json
# and vectorize's posterized preview).
if [[ "$MODE" == "sidecar" ]]; then
  printf '{"picture_px": [40, 30], "objects": [{"id": "f0", "kind": "fill", "color": "#ddb97f"}], "overrides": []}\n' \
    > "output_inkstitch_svg/$BASE.regions.json"
  printf 'not a real png\n' > "output_inkstitch_svg/${BASE}_posterized.png"
fi
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

    def post(self, url: str, payload=None, headers=None):
        return self.client.post(url, json=payload if payload is not None else {},
                                headers=headers or {})

    def status(self) -> dict:
        resp = self.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def upload(self, name: str = "Skyfowl Patch.PNG", data: bytes = None, headers=None):
        return self.client.post("/api/picture",
                                data={"picture": (io.BytesIO(data if data is not None
                                                             else png_bytes()), name)},
                                content_type="multipart/form-data", headers=headers or {})

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
        with self.client.get("/") as resp:
            self.assertEqual(resp.status_code, 200)
            page = resp.get_data(as_text=True)
        self.assertIn("<html", page)
        self.assertIn("/static/app.js", page)


class Picture(ServerTestCase):
    def test_upload(self):
        resp = self.upload("Skyfowl Patch.PNG")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertEqual(data["slug"], "Skyfowl-Patch")
        self.assertEqual(data["url"], "/files/Skyfowl-Patch/picture.png?v=1")  # suffix lowered
        self.assertEqual((data["width"], data["height"]), (40, 30))
        self.assertEqual(data["kind"], "transparent")
        self.assertEqual(data["background_hex"], "")
        self.assertTrue(any("40 x 30 pixels" in a for a in data["advice"]), data["advice"])
        self.assertTrue((self.job_dir() / "picture.png").is_file())
        st = self.status()
        self.assertEqual(st["picture"], {"slug": "Skyfowl-Patch",
                                         "url": "/files/Skyfowl-Patch/picture.png?v=1",
                                         "width": 40, "height": 30})

    def test_the_picture_url_changes_with_every_picture(self):
        """A page holding the old picture must fetch the new one: the ?v= goes up."""
        first = self.picture_loaded()
        self.do_slice()
        self.wait_state({"idle", "failed"})
        second = self.upload("Skyfowl Patch.PNG")          # same slug, new file
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_json()["url"], "/files/Skyfowl-Patch/picture.png?v=2")
        self.assertEqual(self.status()["picture"]["url"], "/files/Skyfowl-Patch/picture.png?v=2")
        self.do_slice()                                    # slice ids restart with a new picture
        self.wait_state({"idle", "failed"})
        third = self.upload("Skyfowl Patch.PNG")
        self.assertEqual(third.get_json()["url"], "/files/Skyfowl-Patch/picture.png?v=3")
        self.assertNotEqual(first["url"], third.get_json()["url"])
        self.assertEqual(list(self.out_root.glob(".upload-*")), [])

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
        self.assertEqual(list(self.out_root.glob(".upload-*")), [], "no temp file left behind")

    def test_a_rejected_upload_leaves_the_previous_job_alone(self):
        """The picture is checked before anything in the job folder is touched."""
        self.picture_loaded()
        self.do_slice(yaml_text="profile: vadmel\n")
        self.wait_state({"idle", "failed"})
        jobdir = self.job_dir()
        (jobdir / "stale.txt").write_text("from the last job")
        before = self.status()

        resp = self.upload("Skyfowl Patch.PNG", b"this is not a png")   # same name, bad bytes
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(list(self.out_root.glob(".upload-*")), [], "no temp file left behind")

        self.assertTrue((jobdir / "picture.png").is_file(), "the old picture is still there")
        self.assertTrue((jobdir / "slice.svg").is_file(), "the old Slice is still there")
        self.assertTrue((jobdir / "job.yaml").is_file())
        self.assertTrue((jobdir / "stale.txt").is_file(), "the folder was not made fresh")
        self.assertEqual(yaml.safe_load((jobdir / "job.yaml").read_text()), {"profile": "vadmel"})
        st = self.status()
        self.assertEqual(st["picture"], before["picture"])
        self.assertEqual(st["slice"], before["slice"])
        self.assertEqual(st["state"], before["state"])

        resp = self.do_slice()                    # the id of the failed upload is not spent
        self.assertEqual(resp.get_json()["slice_id"], 2)
        self.wait_state({"idle", "failed"})

    def test_a_rejected_picture_names_the_uploaded_file(self):
        resp = self.upload("broken.png", b"this is not a png")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("broken.png", resp.get_json()["error"])
        self.assertNotIn(".upload-", resp.get_json()["error"])
        self.assertEqual(list(self.out_root.glob(".upload-*")), [])


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

    def test_a_successful_slice_saves_the_config_it_ran_with(self):
        self.picture_loaded()
        resp = self.do_slice(yaml_text="fabric_color: '#ffffff'\n", hoop=[260, 200],
                             size_mm=None, overrides=[{"at_px": [4, 5], "type": "satin"}])
        self.assertEqual(resp.status_code, 202)
        st = self.wait_state({"idle", "failed"})
        self.assertEqual(st["state"], "idle", st["error"])
        jobdir = self.job_dir()
        self.assertEqual(yaml.safe_load((jobdir / "job.yaml").read_text()),
                         {"fabric_color": "#ffffff",
                          "stitch_overrides": [{"at_px": [4, 5], "type": "satin"}]})
        self.assertFalse((jobdir / "job.next.yaml").exists(), "the staging name is gone")
        self.assertIn("job.next.yaml", (jobdir / "log.txt").read_text())
        self.assertEqual(self.app.job.hoop, (260.0, 200.0))
        self.assertEqual(st["slice"]["hoop"], [260.0, 200.0])
        self.assertEqual(st["slice"]["background"], "#ffffff")

    def test_a_failed_slice_keeps_the_config_and_the_id_of_the_last_good_one(self):
        self.picture_loaded()
        self.assertEqual(self.do_slice(yaml_text="profile: vadmel\n").get_json()["slice_id"], 1)
        self.wait_state({"idle", "failed"})
        jobdir = self.job_dir()

        self.set_mode("boom")
        resp = self.do_slice(yaml_text="profile: lizard\n", hoop=[260, 200])
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.get_json()["slice_id"], 2, "the id it gets if it succeeds")
        st = self.wait_state({"failed"})
        self.assertEqual(st["state"], "failed")
        self.assertEqual(yaml.safe_load((jobdir / "job.yaml").read_text()), {"profile": "vadmel"},
                         "a failed Slice does not overwrite the last good config")
        self.assertFalse((jobdir / "job.next.yaml").exists())
        self.assertEqual(self.app.job.hoop, (120.0, 120.0), "the stored hoop is the last good one")

        self.set_mode("ok")
        self.assertEqual(self.do_slice().get_json()["slice_id"], 2,
                         "a failed Slice does not spend its id")
        st = self.wait_state({"idle", "failed"})
        self.assertEqual(st["state"], "idle", st["error"])
        self.assertEqual(st["slice"]["slice_id"], 2)
        self.assertEqual(yaml.safe_load((jobdir / "job.yaml").read_text()), {},
                         "this one had no yaml_text of its own")

    def test_a_stale_sidecar_does_not_survive_a_slice_that_wrote_none(self):
        self.picture_loaded()
        self.set_mode("sidecar")
        self.do_slice()
        st = self.wait_state({"idle", "failed"})
        self.assertEqual(st["state"], "idle", st["error"])
        jobdir = self.job_dir()
        self.assertIsNotNone(st["slice"]["regions_url"])
        self.assertIsNotNone(st["slice"]["posterized_url"])
        self.assertTrue((jobdir / "slice.regions.json").is_file())
        self.assertTrue((jobdir / "slice_posterized.png").is_file())

        self.set_mode("ok")                          # the next Slice writes no sidecar
        self.do_slice()
        st = self.wait_state({"idle", "failed"})
        self.assertIsNone(st["slice"]["regions_url"], "the old sidecar is not offered again")
        self.assertIsNone(st["slice"]["posterized_url"])
        self.assertFalse((jobdir / "slice.regions.json").exists())
        self.assertFalse((jobdir / "slice_posterized.png").exists())


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
        self.assertTrue(args.startswith("%s/plan.svg %s/plan " % (jobdir, jobdir)), args)  # the copy
        self.assertIn("--config %s/job.yaml" % jobdir, args)    # travel_vp3.py reads travel:

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

    def test_the_background_comes_from_the_slice_that_made_the_svg(self):
        self.slice_first(yaml_text="fabric_color: '#123456'\n")
        self.set_mode("boom")                      # a Slice that fails writes no config
        self.assertEqual(self.do_slice(yaml_text="fabric_color: '#abcdef'\n").status_code, 202)
        self.wait_state({"failed"})
        self.set_mode("ok")
        with self.measured():
            self.assertEqual(self.post("/api/stitchplan").status_code, 202)
            self.wait_state({"idle", "failed"})
        args = (self.job_dir() / "export_args.txt").read_text()
        self.assertIn("#123456", args)
        self.assertNotIn("#abcdef", args)
        # the --config file is the working Slice's too, so its travel: section matches the SVG
        config = (self.job_dir() / "job.yaml").read_text()
        self.assertIn("#123456", config)
        self.assertNotIn("#abcdef", config)

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
    def test_g4_two_slices_at_the_same_instant_give_one_202_and_one_409(self):
        self.picture_loaded()
        self.set_mode("slow")
        for round_number in range(5):
            barrier = threading.Barrier(2)
            codes: list = []
            lock = threading.Lock()

            def hit():
                client = self.app.test_client()        # one client per thread
                barrier.wait(30)                      # both requests leave at the same moment
                resp = client.post("/api/slice", json={"hoop": [120, 120], "size_mm": 100,
                                                        "colors": 6, "key_background": False,
                                                        "yaml_text": "", "overrides": []})
                with lock:
                    codes.append(resp.status_code)

            threads = [threading.Thread(target=hit) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
                self.assertFalse(thread.is_alive(), "a POST never came back")
            self.assertEqual(sorted(codes), [202, 409], round_number)
            st = self.wait_state({"idle", "failed"})
            self.assertEqual(st["state"], "idle", st["error"])
        self.assertEqual(self.status()["slice"]["slice_id"], 5, "one id per Slice, none lost")

    def test_two_slices_give_one_202_and_one_409(self):
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

    def test_busy_is_409_while_the_state_says_slicing_or_exporting(self):
        """Between the process exiting and the worker's after-steps the slot is still taken."""
        job = self.app.job
        for state in ("slicing", "exporting"):
            with job.lock:
                job.state = state
                job.proc = None
                job.reserved = False
            self.assertTrue(job.busy(), state)
            with job.lock:
                job.state = "idle"
        self.picture_loaded()
        self.set_mode("slow")
        self.assertEqual(self.do_slice().status_code, 202)
        self.assertEqual(self.do_slice().status_code, 409)
        self.assertEqual(self.do_plan().status_code, 409)
        self.assertEqual(self.upload().status_code, 409)
        self.wait_state({"idle", "failed"})

    def test_a_second_slice_is_409_while_the_worker_finishes_up(self):
        """The real window: the pipeline process is gone, the job is not written up yet."""
        self.picture_loaded()
        self.set_mode("slow")
        entered = threading.Event()
        gate = threading.Event()
        real_collect = server.core._collect

        def blocked_collect(root, base, dest):
            entered.set()
            gate.wait(30)
            return real_collect(root, base, dest)

        with mock.patch.object(server.core, "_collect", blocked_collect):
            self.assertEqual(self.do_slice().status_code, 202)
            self.assertTrue(entered.wait(30), "the Slice never reached the after-steps")
            with self.app.job.lock:
                self.assertIsNone(self.app.job.proc, "the process is already gone")
                self.assertEqual(self.app.job.state, "slicing")
            try:
                resp = self.do_slice()
                self.assertEqual(resp.status_code, 409, resp.get_data(as_text=True))
                self.assertEqual(resp.get_json(), {"error": "busy"})
            finally:
                gate.set()
        self.assertEqual(self.wait_state({"idle", "failed"})["state"], "idle")

    def test_busy_is_checked_before_the_body(self):
        """E6 wins over a bad body: the operator gets busy, not a complaint about their JSON."""
        self.picture_loaded()
        self.set_mode("slow")
        self.assertEqual(self.do_slice().status_code, 202)
        cases = [self.post("/api/slice", {"hoop": "rubbish"}),
                 self.post("/api/slice", {"hoop": [120, 120], "size_mm": 100, "colors": 5}),
                 self.post("/api/slice", ["not", "an", "object"]),
                 self.post("/api/stitchplan", {"anything": 1}),
                 self.upload("notes.gif", b"GIF89a"),
                 self.upload("broken.png", b"not a png"),
                 self.client.post("/api/picture", data={}, content_type="multipart/form-data")]
        for resp in cases:
            self.assertEqual(resp.status_code, 409, resp.get_data(as_text=True))
            self.assertEqual(resp.get_json(), {"error": "busy"})
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


# ---- only this machine drives the server (Host and Origin) ---------------------------------


class LocalRequestsOnly(ServerTestCase):
    """A page on another site, or a name that resolves to this machine, must not drive the server."""

    def test_an_origin_from_another_page_is_403(self):
        for origin in ("http://evil.example", "https://localhost:8765", "null",
                       "http://127.0.0.1.evil.example", "http://192.168.1.10:8765",
                       "http://[::1]:8765", "file:///home/someone/page.html"):
            resp = self.post("/api/yaml", {"yaml_text": ""}, headers={"Origin": origin})
            self.assertEqual(resp.status_code, 403, origin)
            self.assertIn("error", resp.get_json(), origin)
            resp = self.upload(headers={"Origin": origin})
            self.assertEqual(resp.status_code, 403, origin)

    def test_a_host_that_is_not_this_machine_is_403(self):
        for host in ("evil.example", "192.168.1.10:8765", "localhost.evil.example",
                     "digitize-patch.attacker.test", "127.0.0.1.evil.example"):
            for url in ("/api/status", "/", "/api/options"):
                resp = self.client.get(url, headers={"Host": host})
                self.assertEqual(resp.status_code, 403, "%s %s" % (host, url))
                self.assertIn("error", resp.get_json())
            resp = self.post("/api/yaml", {"yaml_text": ""}, headers={"Host": host})
            self.assertEqual(resp.status_code, 403, host)

    def test_this_machine_is_allowed(self):
        with self.client.get("/") as resp:                       # Flask's default Host: localhost
            self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.get("/api/status").status_code, 200)
        self.assertEqual(self.post("/api/yaml", {"yaml_text": ""}).status_code, 200)
        for host in ("localhost", "127.0.0.1", "127.0.0.1:8765", "localhost:1234", "LOCALHOST:8765"):
            self.assertEqual(self.client.get("/api/status",
                                             headers={"Host": host}).status_code, 200, host)
        for origin in ("http://localhost:8765", "http://127.0.0.1:8765", "http://localhost:9999"):
            self.assertEqual(self.post("/api/yaml", {"yaml_text": ""},
                                       headers={"Origin": origin}).status_code, 200, origin)

    def test_a_known_port_is_the_only_one_accepted(self):
        out_root = self.root / "output" / "web2"
        app = server.create_app(self.root, run_sh=self.run_sh, export_sh=self.export_sh,
                                out_root=out_root, port=8765)
        client = app.test_client()
        good = {"Host": "localhost:8765"}
        self.assertEqual(client.post("/api/yaml", json={"yaml_text": ""}, headers=good).status_code, 200)
        self.assertEqual(client.get("/api/status", headers=good).status_code, 200)
        with client.get("/", headers=good) as resp:
            self.assertEqual(resp.status_code, 200)
        for headers in ({"Host": "localhost:9999"}, {"Host": "127.0.0.1:80"}, {"Host": "localhost"},
                        {"Host": "127.0.0.1:8765", "Origin": "http://localhost:9999"},
                        {"Host": "127.0.0.1:8765", "Origin": "https://127.0.0.1:8765"}):
            resp = client.post("/api/yaml", json={"yaml_text": ""}, headers=headers)
            self.assertEqual(resp.status_code, 403, headers)
        resp = client.post("/api/yaml", json={"yaml_text": ""},
                           headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"})
        self.assertEqual(resp.status_code, 200)


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