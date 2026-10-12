"""Local web server: one picture in, a Slice and a Stitch plan out, driven from a browser page.

One job and one process at a time, always bound to 127.0.0.1. The HTTP shapes are the
contract in docs/design/webui.md (Interfaces, Edge-case rules E5 to E9); the page in
static/ and this file are written against each other. Every pipeline step is the one the
terminal wizard runs, reused from wizard.core, so both routes behave the same.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from tools.digitize.wizard import core, imagecheck, vp3

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]              # tools/digitize/web/server.py -> repo root
DEFAULT_PORT = 8765
LOG_TAIL = 20                            # lines kept for the page
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
PATH_ID_RE = re.compile(r'<path\b[^>]*\bid="([^"]+)"')
HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(?::(\d{1,5}))?$")
RUNNING_STATES = ("slicing", "exporting")  # the job slot is held from start until the write-up
COLOR_CHOICES = (core.COLORS_FEWER, core.COLORS_AUTO, core.COLORS_MORE)
OVERRIDE_TYPES = ("satin", "fill")


# ---- small text helpers ------------------------------------------------------------


def path_ids(svg_text: str) -> List[str]:
    """Every <path id="..."> in an SVG, in document order, without duplicates."""
    out: List[str] = []
    for pid in PATH_ID_RE.findall(svg_text):
        if pid not in out:
            out.append(pid)
    return out


def host_is_local(host: Optional[str], port: Optional[int]) -> bool:
    """True when a Host header names this machine. Port None: any port, and no port at all.

    A Host that is not one of these two names is a page that reached the server by name
    (DNS rebinding) rather than by typing the address; it does not get to drive a job.
    """
    if not host:
        return False
    match = HOST_RE.match(host.strip().lower())
    if match is None:
        return False
    if port is None:
        return True
    return match.group(2) is not None and int(match.group(2)) == port


def origin_is_local(origin: Optional[str], port: Optional[int]) -> bool:
    """True when there is no Origin, or it names this machine's page."""
    if origin is None:
        return True
    rest = origin.strip().lower()
    if not rest.startswith("http://"):
        return False
    return host_is_local(rest[len("http://"):], port)


def yaml_error_text(exc: yaml.YAMLError) -> str:
    """Plain words for a YAML error, with the line number when the parser knows it."""
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    problem = (getattr(exc, "problem", None) or "the YAML could not be read").strip()
    return "line %d: %s" % (mark.line + 1, problem) if mark is not None else problem


def parse_yaml_mapping(text: Any):
    """Text as a YAML mapping ({}, None). Returns (mapping, complaint)."""
    if text is None:
        return {}, None
    if not isinstance(text, str):
        return None, "yaml_text must be text."
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, yaml_error_text(exc)
    if parsed is None:
        return {}, None
    if not isinstance(parsed, dict):
        return None, ("The YAML must be settings written as key: value lines; "
                      "this is a %s." % type(parsed).__name__)
    return parsed, None


def background_for(mapping: Dict[str, Any]) -> str:
    """Preview canvas colour for a job YAML, like run.sh: fabric_color:, else the profile's."""
    bg = str(mapping.get("fabric_color") or "").strip()
    if not bg and str(mapping.get("profile") or "").strip().lower() == "vadmel":
        bg = "#101010"
    return bg


def unlink_quietly(path: Path) -> None:
    """Delete a file if it is there; a missing file is not an error."""
    try:
        path.unlink()
    except OSError:
        pass


def tail_file(path: Path, lines: int = 8) -> List[str]:
    """The last non-empty lines of a file, like core._err_tail for work/<base>.err."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [row for row in text.splitlines() if row.strip()][-lines:]


def replace_job_dir(out_root: Path, slug: str) -> Path:
    """out_root/slug, empty. Only a real folder directly inside out_root is replaced."""
    folder = out_root / slug
    if os.path.lexists(str(folder)):
        if not (folder.is_dir() and not folder.is_symlink()
                and folder.resolve().parent == out_root.resolve()):
            raise OSError("the output folder holds a file or a link named %s, not a folder" % slug)
        shutil.rmtree(str(folder))
    folder.mkdir(parents=True)
    return folder


# ---- the job: everything /api/status reports, plus the one process that may run ----------


class Job:
    """Server state for the current job. One lock guards all of it."""

    def __init__(self, root: Path, out_root: Path):
        self.root = root
        self.out_root = out_root
        self.lock = threading.Lock()
        self.state = "idle"
        self.stage: Optional[str] = None
        self.error: Optional[str] = None
        self.log_tail: List[str] = []
        self.picture: Optional[Dict[str, Any]] = None
        self.slice: Optional[Dict[str, Any]] = None
        self.stitchplan: Optional[Dict[str, Any]] = None
        self.hoop: Tuple[float, float] = core.HOOP_SMALL
        self.dir: Optional[Path] = None
        self.image: Optional[Path] = None
        self.proc: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.reserved = False              # a request is setting a job up, no process yet
        self.cancel_requested = False
        self.started_at = 0.0
        self.ended_at = 0.0
        self.slice_id = 0                  # the id of the last Slice that worked
        self.picture_version = 0           # the ?v= of the current picture

    # -- reading --------------------------------------------------------------

    def busy(self) -> bool:
        with self.lock:
            return self._busy()

    def _busy(self) -> bool:
        """The job slot is taken. Caller holds the lock.

        A running state counts as busy on its own: the worker clears `proc` before it
        moves the files and writes the status, and a request in that window must not
        start a second job on top of it.
        """
        return (self.proc is not None or self.reserved
                or self.state in RUNNING_STATES)

    def elapsed_s(self) -> Optional[float]:
        if not self.started_at:
            return None
        return round((self.ended_at or time.time()) - self.started_at, 1)

    def status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "state": self.state,
                "stage": self.stage,
                "elapsed_s": self.elapsed_s(),
                "log_tail": list(self.log_tail),
                "error": self.error,
                "picture": dict(self.picture) if self.picture else None,
                "slice": dict(self.slice) if self.slice else None,
                "stitchplan": dict(self.stitchplan) if self.stitchplan else None,
            }

    # -- writing --------------------------------------------------------------

    @contextlib.contextmanager
    def claimed(self):
        """The one job slot. Yields self, or None when a job already has it."""
        with self.lock:
            if self._busy():
                yield None
                return
            self.reserved = True
        try:
            yield self
        finally:
            with self.lock:
                self.reserved = False

    def start(self, script: Path, args: Sequence[Any], log_path: Path, state: str, after) -> None:
        """Start one pipeline process and read its output in the background.

        The process is started in the caller's thread, so Cancel and the 409 check see
        it at once; reading its output and the finishing steps run in one thread.
        """
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(["bash", str(script)] + [str(a) for a in args], cwd=str(self.root),
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                errors="replace", bufsize=1, start_new_session=True)

        def worker():
            try:
                rc, lines = self._pump(proc, log_path)
                after(rc, lines)
            finally:
                with self.lock:
                    self.thread = None

        thread = threading.Thread(target=worker, name="digitize-web", daemon=True)
        with self.lock:
            self.proc = proc
            self.thread = thread
            self.reserved = False
            self.state = state
            self.stage = "Starting"
            self.error = None
            self.log_tail = []
            self.cancel_requested = False
            self.started_at = time.time()
            self.ended_at = 0.0
        thread.start()

    def _pump(self, proc: subprocess.Popen, log_path: Path) -> Tuple[int, List[str]]:
        """Every output line goes into log_tail and the job log file. Returns (exit code, lines)."""
        lines: List[str] = []
        try:
            with open(str(log_path), "a", encoding="utf-8") as log:
                with proc.stdout:
                    for raw in proc.stdout:
                        line = raw.rstrip("\n")
                        lines.append(line)
                        log.write(line + "\n")
                        log.flush()
                        with self.lock:
                            self.log_tail.append(line)
                            del self.log_tail[:-LOG_TAIL]
                            label = core.stage_label(line)
                            if label:
                                self.stage = label
            rc = proc.wait()
        except BaseException:
            core._kill_group(proc)
            raise
        finally:
            with self.lock:
                if self.proc is proc:
                    self.proc = None
        return rc, lines

    def done(self, state: str, error: Optional[str] = None, log_tail: Optional[List[str]] = None) -> None:
        """Mark the job finished. `log_tail` replaces the page's tail (a failure shows the run)."""
        with self.lock:
            self.state = state
            self.error = error
            if log_tail is not None:
                self.log_tail = log_tail
            self.ended_at = time.time()


# ---- request body checks ----------------------------------------------------------------------


def _number(value: Any) -> Optional[float]:
    """The value as a number, or None (booleans are not numbers here)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _pixel(value: float) -> Any:
    """A picture pixel coordinate, kept as an int when it is a whole number."""
    return int(value) if float(value).is_integer() else float(value)


def check_hoop(value: Any):
    """[w, h] in mm as floats, or a plain complaint."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return "hoop must be two numbers in mm, like [120, 120]."
    a, b = _number(value[0]), _number(value[1])
    if a is None or b is None or a <= 0 or b <= 0:
        return "hoop must be two numbers in mm, like [120, 120]."
    return (a, b)


def check_size(value: Any):
    """A positive number of mm, or None for "fill the hoop". Or a plain complaint."""
    if value is None:
        return None
    number = _number(value)
    if number is None or number <= 0:
        return "size_mm must be a number of mm, or null to fill the hoop."
    return number


def check_overrides(value: Any):
    """A list of {at_px: [x, y], type: satin|fill} as plain dicts, or a plain complaint."""
    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, "overrides must be a list of entries: {at_px: [x, y], type: satin}."
    out = []
    for entry in value:
        if not isinstance(entry, dict):
            return None, "Every override needs at_px: [x, y] and type: satin or fill."
        point = entry.get("at_px")
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return None, "Every override needs at_px: [x, y] and type: satin or fill."
        x, y = _number(point[0]), _number(point[1])
        if x is None or y is None or entry.get("type") not in OVERRIDE_TYPES:
            return None, "Every override needs at_px: [x, y] and type: satin or fill."
        out.append({"at_px": [_pixel(x), _pixel(y)], "type": entry["type"]})
    return out, None


# ---- the Flask app --------------------------------------------------------------------------


def create_app(root, run_sh=None, export_sh=None, out_root=None, port=None) -> Flask:
    """Build the app. Tests inject fake scripts and a temporary output folder.

    `port` is the port the app serves; the Host and Origin check is as strict as it can
    be with it, and relaxed to any port on 127.0.0.1/localhost when it is not known
    (the Flask test client).
    """
    root = Path(root).resolve()
    run_sh = Path(run_sh) if run_sh else root / "tools" / "digitize" / "run.sh"
    export_sh = Path(export_sh) if export_sh else root / "tools" / "digitize" / "export_svg.sh"
    out_root = Path(out_root) if out_root else root / "output" / "web"
    out_root.mkdir(parents=True, exist_ok=True)
    serve_port = int(port) if port else None
    job = Job(root, out_root)

    app = Flask(__name__, static_folder=str(HERE / "static"), static_url_path="/static")
    app.job = job            # the one Job; tests wait on it instead of sleeping blind

    def fail(message: str, code: int):
        return jsonify({"error": message}), code

    def busy():
        return fail("busy", 409)

    def body() -> Optional[Dict[str, Any]]:
        """The request body as a mapping, {} for an empty one, None when it is not one."""
        data = request.get_json(silent=True)
        if data is None:
            return {}
        return data if isinstance(data, dict) else None

    @app.before_request
    def only_this_machine():
        """403 unless the request came from a page on this machine at this port (G3)."""
        if host_is_local(request.headers.get("Host"), serve_port) and \
                origin_is_local(request.headers.get("Origin"), serve_port):
            return None
        return fail("This server only answers pages opened on this machine, at 127.0.0.1:%d "
                    "or localhost:%d." % (serve_port or DEFAULT_PORT, serve_port or DEFAULT_PORT),
                    403)

    # ---- finishing a Slice ---------------------------------------------------

    def finish_slice(base: str, overrides: List[Dict[str, Any]], slice_id: int, jobdir: Path,
                     next_yaml: Path, hoop: Tuple[float, float], background: str):
        """Move the pipeline's files into the job folder, or say why nothing was kept."""

        def after(rc: int, lines: List[str]):
            try:
                with job.lock:
                    job.proc = None
                    job.ended_at = time.time()
                    cancelled = job.cancel_requested
                if cancelled:
                    shutil.rmtree(str(jobdir / "_slice"), ignore_errors=True)
                    job.done("cancelled", "Cancelled.")
                    return
                if rc != 0:
                    tail = (lines + core._err_tail(root, base))[-12:]
                    job.done("failed", "The pipeline stopped before the files were ready "
                                       "(exit code %s). Nothing was saved." % rc, tail)
                    return
                try:
                    core._collect(root, base, jobdir / "_slice")
                    # A Slice that writes no sidecar must not leave the previous one's behind.
                    for stale in ("slice.regions.json", "slice_posterized.png"):
                        unlink_quietly(jobdir / stale)
                    for src, dst in ((base + ".svg", "slice.svg"),
                                     (base + "_posterized.png", "slice_posterized.png"),
                                     (base + ".regions.json", "slice.regions.json")):
                        got = jobdir / "_slice" / src
                        if got.is_file():
                            os.replace(str(got), str(jobdir / dst))
                except OSError as exc:
                    job.done("failed", "The files from the pipeline could not be moved into the "
                                       "job folder (%s)." % exc)
                    return
                if not (jobdir / "slice.svg").is_file():
                    job.done("failed", "The pipeline finished but produced no embroidery drawing.")
                    return
                try:                                  # job.yaml only ever names a Slice that worked
                    os.replace(str(next_yaml), str(jobdir / "job.yaml"))
                except OSError as exc:
                    job.done("failed", "The job settings could not be saved (%s)." % exc)
                    return
                shutil.rmtree(str(jobdir / "_slice"), ignore_errors=True)
                with job.lock:
                    job.slice_id = slice_id            # the id is spent only now
                    job.hoop = hoop
                    job.slice = {
                        "slice_id": slice_id,
                        "svg_url": "/files/%s/slice.svg?v=%d" % (jobdir.name, slice_id),
                        "regions_url": ("/files/%s/slice.regions.json?v=%d"
                                        % (jobdir.name, slice_id)
                                        if (jobdir / "slice.regions.json").is_file() else None),
                        "posterized_url": ("/files/%s/slice_posterized.png?v=%d"
                                           % (jobdir.name, slice_id)
                                           if (jobdir / "slice_posterized.png").is_file() else None),
                        "overrides": overrides,
                        "hoop": [hoop[0], hoop[1]],
                        "background": background,
                    }
                job.done("idle")
            finally:
                shutil.rmtree(str(jobdir / "_in"), ignore_errors=True)
                core._purge(root, base)
                unlink_quietly(next_yaml)             # gone after the rename, cleaned up otherwise
        return after

    # ---- finishing a Stitch plan ----------------------------------------------

    def finish_plan(slice_id: int, jobdir: Path, source_svg: Path, hoop: Tuple[float, float]):
        """Measure the exported VP3: the plan, its warnings and what the precheck removed."""

        def after(rc: int, lines: List[str]):
            with job.lock:
                job.proc = None
                job.ended_at = time.time()
                cancelled = job.cancel_requested
            if cancelled:
                job.done("cancelled", "Cancelled.")
                return
            plan = jobdir / "plan"
            if rc != 0:
                tail = (lines + tail_file(plan.with_suffix(".err")))[-12:]
                job.done("failed", "The export stopped before the files were ready "
                                   "(exit code %s)." % rc, tail)
                return
            if not plan.with_suffix(".vp3").is_file():
                job.done("failed", "The export finished but produced no machine file.")
                return
            try:
                m = vp3.measure(plan.with_suffix(".vp3"))
            except Exception as exc:                     # pystitch, or a broken file
                job.done("failed", "The machine file could not be read (%s)." % exc)
                return
            warnings = core.edge_warnings(m, hoop)
            warnings += [ln for ln in lines if ln.lstrip().startswith("warning:")]
            try:
                kept = set(path_ids((jobdir / "plan.svg").read_text(encoding="utf-8", errors="replace")))
                removed = [pid for pid in path_ids(source_svg.read_text(encoding="utf-8",
                                                                       errors="replace"))
                           if pid not in kept]
            except OSError:
                removed = []
            with job.lock:
                job.stitchplan = {
                    "slice_id": slice_id,
                    "stitchplan_url": "/files/%s/plan_stitchplan.png?v=%d" % (jobdir.name, slice_id),
                    "coverage_url": "/files/%s/plan_coverage.png?v=%d" % (jobdir.name, slice_id),
                    "vp3_url": "/files/%s/plan.vp3?v=%d" % (jobdir.name, slice_id),
                    "stitches": m.stitches,
                    "width_mm": round(m.width_mm, 1),
                    "height_mm": round(m.height_mm, 1),
                    "threads": list(m.threads),
                    "warnings": warnings,
                    "removed_by_precheck": removed,
                }
            job.done("idle")
        return after

    # ---- routes --------------------------------------------------------------

    @app.get("/")
    def index():
        page = HERE / "static" / "index.html"
        if not page.is_file():
            return fail("The page is not built yet: static/index.html is missing.", 404)
        return send_from_directory(str(page.parent), "index.html")

    @app.get("/api/options")
    def api_options():
        return jsonify({"hoops": [list(core.HOOP_SMALL), list(core.HOOP_LARGE)],
                        "default_hoop": 0,
                        "default_size_mm": core.DEFAULT_SIZE_MM,
                        "colors": list(COLOR_CHOICES),
                        "default_colors": core.COLORS_AUTO})

    @app.post("/api/picture")
    def api_picture():
        with job.claimed() as slot:
            if slot is None:
                return busy()
            upload = request.files.get("picture")
            if upload is None or not upload.filename:
                return fail("No picture file came with the upload. "
                            "Choose a png, jpg, jpeg or webp file.", 400)
            suffix = Path(upload.filename).suffix.lower()
            if suffix not in core.PICTURE_SUFFIXES:
                return fail("%s files are not supported. Use a png, jpg, jpeg or webp picture."
                            % (suffix or "These"), 400)
            # The upload is checked as a file first. Nothing in the job folder is touched
            # until the picture is accepted, so a bad upload leaves the last job alone.
            temp: Optional[Path] = None
            try:
                handle, temp_name = tempfile.mkstemp(prefix=".upload-", suffix=suffix,
                                                     dir=str(out_root))
                os.close(handle)
                temp = Path(temp_name)
                upload.save(str(temp))
                problem = core.check_picture_file(temp)
                if problem:
                    return fail(problem, 400)
                report = imagecheck.inspect(temp)
                if not report.ok:
                    return fail(report.error.replace(temp.name, Path(upload.filename).name), 400)
                slug = core.slugify(Path(upload.filename).stem)
                try:
                    jobdir = replace_job_dir(out_root, slug)
                except OSError as exc:
                    return fail("The job folder could not be made: %s" % exc, 400)
                picture = jobdir / ("picture" + suffix)
                os.replace(str(temp), str(picture))
                temp = None
                with job.lock:                       # the folder is made fresh, so E5 drops the
                    job.slice = None                 # old Slice and Stitch plan whatever the check
                    job.stitchplan = None            # below says about the new picture
                    job.slice_id = 0
                    job.picture_version += 1
                    url = "/files/%s/picture%s?v=%d" % (slug, suffix, job.picture_version)
                    job.dir = jobdir
                    job.image = picture
                    job.picture = {"slug": slug, "url": url,
                                   "width": report.width, "height": report.height}
                    job.state = "idle"
                    job.stage = None
                    job.error = None
                    job.log_tail = []
            finally:
                if temp is not None:
                    unlink_quietly(temp)
            return jsonify({"slug": slug, "url": url, "width": report.width,
                            "height": report.height, "kind": report.kind,
                            "background_hex": report.background_hex,
                            "advice": core.image_advice(report)})

    @app.post("/api/yaml")
    def api_yaml():
        data = body()
        if data is None:
            return fail("The request body must be a JSON object with a yaml_text field.", 400)
        mapping, complaint = parse_yaml_mapping(data.get("yaml_text", ""))
        if complaint:
            return jsonify({"ok": False, "error": complaint})
        overrides = mapping.get("stitch_overrides") or []
        if not isinstance(overrides, list):
            return jsonify({"ok": False, "error": "stitch_overrides must be a list of entries, "
                                                   "each with at_px: [x, y] and type: satin or fill"})
        return jsonify({"ok": True, "has_palette": bool(mapping.get("palette")),
                        "stitch_overrides": overrides})

    @app.post("/api/slice")
    def api_slice():
        with job.claimed() as slot:
            if slot is None:
                return busy()
            data = body()
            if data is None:
                return fail("The request body must be a JSON object.", 400)
            hoop = check_hoop(data.get("hoop"))
            if isinstance(hoop, str):
                return fail(hoop, 400)
            size_mm = check_size(data.get("size_mm"))
            if isinstance(size_mm, str):
                return fail(size_mm, 400)
            if data.get("colors") not in COLOR_CHOICES:
                return fail("colors must be 4, 6 or 8.", 400)
            overrides, complaint = check_overrides(data.get("overrides"))
            if complaint:
                return fail(complaint, 400)
            mapping, complaint = parse_yaml_mapping(data.get("yaml_text"))
            if complaint:
                return fail(complaint, 400)

            with job.lock:
                if job.image is None or job.dir is None:
                    return fail("Load a picture first.", 400)
                jobdir, image = job.dir, job.image
            spec = core.JobSpec(image=image, key_background=bool(data.get("key_background")),
                                hoop=hoop, size_mm=size_mm, colors=data["colors"])
            settings = dict(mapping)
            if overrides:
                settings["stitch_overrides"] = overrides
            else:
                settings.pop("stitch_overrides", None)      # G1: absent = today's behaviour
            # job.yaml keeps the last Slice that worked; this run reads job.next.yaml.
            next_yaml = jobdir / "job.next.yaml"
            try:
                next_yaml.write_text(yaml.safe_dump(settings, sort_keys=False, allow_unicode=True),
                                     encoding="utf-8")
                base = core._make_base(jobdir.name)
                staged = jobdir / "_in" / (base + image.suffix)
                staged.parent.mkdir(exist_ok=True)
                shutil.copyfile(str(image), str(staged))
            except OSError as exc:
                shutil.rmtree(str(jobdir / "_in"), ignore_errors=True)
                unlink_quietly(next_yaml)
                return fail("The job could not be set up on disk (%s)." % exc, 400)
            args = core.pipeline_args(spec, spec.hoop) + ["--no-export", "--config", str(next_yaml)]
            with job.lock:
                # The id the Slice gets if it works. A failed one does not spend it.
                slice_id = job.slice_id + 1
            job.start(run_sh, list(args) + [staged], jobdir / "log.txt", "slicing",
                      finish_slice(base, overrides, slice_id, jobdir, next_yaml, hoop,
                                   background_for(settings)))
        return jsonify({"slice_id": slice_id}), 202

    @app.post("/api/stitchplan")
    def api_stitchplan():
        with job.claimed() as slot:
            if slot is None:
                return busy()
            with job.lock:
                if job.slice is None or job.dir is None:
                    return fail("no Slice yet", 400)
                jobdir, slice_id = job.dir, job.slice["slice_id"]
                # The Slice's own values, not whatever job.yaml says now (D11).
                hoop = tuple(job.slice.get("hoop") or job.hoop)
                background = job.slice.get("background") or ""
            source = jobdir / "slice.svg"
            try:
                # D11: export the exact SVG the Slice made; the precheck may edit this copy
                shutil.copyfile(str(source), str(jobdir / "plan.svg"))
            except OSError as exc:
                return fail("plan.svg could not be written (%s)." % exc, 400)
            args = [jobdir / "plan.svg", jobdir / "plan"] + (["--background", background]
                                                            if background else [])
            job.start(export_sh, args, jobdir / "log.txt", "exporting",
                      finish_plan(slice_id, jobdir, source, hoop))
        return jsonify({"slice_id": slice_id}), 202

    @app.post("/api/cancel")
    def api_cancel():
        with job.lock:
            proc = job.proc
            if proc is None:
                return jsonify({"cancelled": False})
            job.cancel_requested = True
        core._kill_group(proc)
        with job.lock:
            job.state = "cancelled"
            job.error = "Cancelled."
            if not job.ended_at:
                job.ended_at = time.time()
        return jsonify({"cancelled": True})

    @app.get("/api/status")
    def api_status():
        return jsonify(job.status())

    @app.get("/files/<slug>/<name>")
    def api_file(slug: str, name: str):
        if not NAME_RE.match(name):
            return fail("That file name is not allowed.", 404)
        folder = out_root / slug
        if slug != (job.dir.name if job.dir else None) and not (
                folder.is_dir() and not folder.is_symlink()
                and folder.resolve().parent == out_root.resolve()):
            return fail("There is no job folder called %s." % slug, 404)
        return send_from_directory(str(out_root), "%s/%s" % (slug, name))

    @app.errorhandler(HTTPException)
    def http_error(exc: HTTPException):
        return jsonify({"error": exc.description}), exc.code

    return app


# ---- start ----------------------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="digitize.py web",
                                 description="Start the local picture-to-patch web page.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help="port on 127.0.0.1 (default %d)" % DEFAULT_PORT)
    ns = ap.parse_args(args)
    app = create_app(REPO_ROOT, port=ns.port)
    print("Digitize Patches: http://127.0.0.1:%d/  (this machine only, Ctrl-C to stop)" % ns.port)
    sys.stdout.flush()
    app.run(host="127.0.0.1", port=ns.port, threaded=True, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())