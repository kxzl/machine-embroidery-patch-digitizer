"""Tests for digitize.py, bootstrap.py (setup, doctor) and requirements.lock.

Standard library unittest. Every test runs in a fake environment: a temp project
folder, a PATH that holds only fake `uv` and `git` scripts (they exit 99, so a call
that slips past the fake fails the test), and a FakeWorld that stands in for uv,
git, the venv Python and Ink/Stitch.

Run from the project root, with the system Python and with Python 3.13:

    python3 -m unittest tools.digitize.tests.test_bootstrap -v
    python3 tools/digitize/tests/test_bootstrap.py
"""
from __future__ import annotations

import collections
import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = _load("digitize_bootstrap_under_test", REPO / "tools" / "digitize" / "bootstrap.py")
entry = _load("digitize_entry_under_test", REPO / "digitize.py")

PIN = bootstrap.INKSTITCH_COMMIT
DiskUsage = collections.namedtuple("DiskUsage", "total used free")
FAKE_LOCK = "# fake lock\nalpha==1.0\nBeta_Pkg==2.5.1\ngamma==3.0\n"


class FakeWorld:
    """Stands in for bootstrap._run: uv, git, the venv Python and the Ink/Stitch export."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.calls = []
        self.venv_version = None  # "3.13.15" once .venv exists
        self.installed = {}
        self.import_errors = {}  # name -> message
        self.fetch_fails = False
        self.export_rc = 0
        self.export_stdout = None  # bytes; None means a good zip with a VP3
        self.stitches = "4321"

    # -- building blocks
    def make_venv(self, version="3.13.15"):
        py = bootstrap.venv_python(self.root)
        py.parent.mkdir(parents=True, exist_ok=True)
        py.write_text("#!fake\n")
        self.venv_version = version

    def make_inkstitch(self, commit=PIN):
        d = self.root / "inkstitch"
        (d / ".git").mkdir(parents=True, exist_ok=True)
        (d / "inkstitch.py").write_text("# fake\n")
        self.set_head(d, commit)

    def set_head(self, d, commit):
        (Path(d) / ".git" / "fakehead").write_text(commit)

    def make_ready(self):
        self.make_venv()
        self.installed = dict(bootstrap.parse_lock(bootstrap.lock_path(self.root)))
        self.make_inkstitch()

    def ran(self, *words):
        return [c for c in self.calls if all(w in c for w in words)]

    # -- the seam
    def run(self, cmd, cwd=None, env=None, text=True, timeout=None):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        ok = lambda out="", err="": subprocess.CompletedProcess(cmd, 0, out if text else out.encode(), err)
        bad = lambda err, rc=1: subprocess.CompletedProcess(cmd, rc, "" if text else b"", err if text else err.encode())
        if cmd[:2] == ["uv", "--version"]:
            return ok("uv 9.9.9 (fake)\n")
        if cmd[:3] == ["uv", "python", "install"]:
            return ok()
        if cmd[:2] == ["uv", "venv"]:
            self.make_venv()
            return ok()
        if cmd[:3] == ["uv", "pip", "install"]:
            self.installed = dict(bootstrap.parse_lock(cmd[-1]))
            return ok()
        if cmd[0] == "git":
            return self._git(cmd, ok, bad)
        py = str(bootstrap.venv_python(self.root))
        if cmd[0] == py and len(cmd) > 3 and cmd[1] == "-I":
            return self._venv_python(cmd, ok, bad)
        if cmd[0] == py and cmd[1].endswith("inkstitch.py"):
            if self.export_rc != 0:
                return bad("Traceback: fake export error", self.export_rc)
            if self.export_stdout is not None:
                return subprocess.CompletedProcess(cmd, 0, self.export_stdout, b"")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("selftest.vp3", b"VP3DATA")
            return subprocess.CompletedProcess(cmd, 0, buf.getvalue(), b"")
        raise AssertionError("unexpected command: %r" % (cmd,))

    def _git(self, cmd, ok, bad):
        if cmd[1] == "init":
            d = Path(cmd[-1])
            (d / ".git").mkdir(parents=True)
            return ok()
        d = Path(cmd[2])
        sub = cmd[3]
        if sub == "remote":
            return ok()
        if sub == "fetch":
            return bad("fatal: unable to access (fake)") if self.fetch_fails else ok()
        if sub == "checkout":
            (d / "inkstitch.py").write_text("# fake\n")
            self.set_head(d, PIN)
            return ok()
        if sub == "rev-parse":
            f = d / ".git" / "fakehead"
            return ok(f.read_text() + "\n") if f.exists() else bad("fatal: no head")
        raise AssertionError("unexpected git command: %r" % (cmd,))

    def _venv_python(self, cmd, ok, bad):
        script = cmd[3]
        if script == bootstrap._PKG_SCRIPT:
            do_import = cmd[4] == "1"
            with open(cmd[5], encoding="utf-8") as fh:
                want = json.load(fh)
            res = {}
            for name, ver in want.items():
                if name not in self.installed:
                    res[name] = ["missing", ""]
                elif self.installed[name] != ver:
                    res[name] = ["version", self.installed[name]]
                elif do_import and name in self.import_errors:
                    res[name] = ["import", self.import_errors[name]]
            return ok(json.dumps(res) + "\n")
        if "sys.version_info" in script:
            return ok(self.venv_version + "\n") if self.venv_version else bad("cannot start")
        if "pystitch" in script:
            return ok(self.stitches + "\n")
        raise AssertionError("unexpected venv python command: %r" % (cmd,))


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="digitize-test-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "project"
        (self.root / "tools" / "wxstub" / "wx").mkdir(parents=True)
        (self.root / "tools" / "wxstub" / "wx" / "__init__.py").write_text("")
        (self.root / "requirements.lock").write_text(FAKE_LOCK)
        # PATH holds only fake uv and git that fail loudly if they are ever really run
        self.bin = Path(self._tmp.name) / "bin"
        self.bin.mkdir()
        for tool in ("uv", "git"):
            f = self.bin / tool
            f.write_text("#!/bin/sh\necho 'FAKE %s CALLED FOR REAL' >&2\nexit 99\n" % tool)
            f.chmod(f.stat().st_mode | stat.S_IXUSR)
        env = mock.patch.dict(os.environ, {"PATH": str(self.bin)})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("DIGITIZE_REEXEC", None)
        self.world = FakeWorld(self.root)
        patch = mock.patch.object(bootstrap, "_run", self.world.run)
        patch.start()
        self.addCleanup(patch.stop)

    def call(self, fn, *args, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = fn(*args, **kw)
        return code, buf.getvalue()

    def tree(self):
        return sorted(
            (str(p.relative_to(self.root)), p.stat().st_mtime_ns)
            for p in self.root.rglob("*")
            if "__pycache__" not in p.parts
        )


class LockFileTests(unittest.TestCase):
    def test_parse_skips_comments_and_blank_lines(self):
        with tempfile.NamedTemporaryFile("w", suffix=".lock", delete=False) as f:
            f.write("# c\n\nalpha==1.0  # trailing\nBeta_Pkg==2.5.1 ; python_version>'3'\n")
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(bootstrap.parse_lock(f.name), [("alpha", "1.0"), ("Beta_Pkg", "2.5.1")])

    def test_parse_rejects_editable_and_unpinned_lines(self):
        for bad in ("-e /home/me/pkg\n", "alpha>=1.0\n", "alpha @ file:///x\n", "alpha\n"):
            with tempfile.NamedTemporaryFile("w", suffix=".lock", delete=False) as f:
                f.write(bad)
            self.addCleanup(os.unlink, f.name)
            with self.assertRaises(ValueError, msg=bad):
                bootstrap.parse_lock(f.name)

    def test_real_lock_is_complete_and_pinned(self):
        pins = bootstrap.parse_lock(REPO / "requirements.lock")
        names = [n.lower().replace("_", "-") for n, _ in pins]
        self.assertEqual(len(names), len(set(names)), "duplicate package in the lock")
        self.assertGreaterEqual(len(pins), 55)
        locked = dict((n.lower().replace("_", "-"), v) for n, v in pins)
        self.assertEqual(locked["inkex"], "1.4.1")
        for needed in ("rich", "questionary", "numpy", "pystitch", "lxml", "shapely", "pillow", "pyyaml",
                       "markdown-it-py", "mdurl", "pygments", "prompt-toolkit", "wcwidth"):
            self.assertIn(needed, locked)
        text = (REPO / "requirements.lock").read_text(encoding="utf-8")
        self.assertNotIn("—", text)
        self.assertNotIn("file://", text)


class ChecksTests(Base):
    def test_old_bootstrap_python_fails(self):
        c = bootstrap.check_python((3, 8, 18))
        self.assertEqual(c.status, "FAIL")
        self.assertIn("3.8.18", c.detail)
        self.assertIn("3.9", c.detail)
        self.assertEqual(bootstrap.check_python((3, 9, 0)).status, "ok")
        self.assertEqual(bootstrap.check_python((3, 14, 7)).status, "ok")

    def test_windows_is_not_supported_natively(self):
        c = bootstrap.check_platform("win32")
        self.assertEqual(c.status, "FAIL")
        self.assertIn("WSL2", c.fix)
        self.assertEqual(bootstrap.check_platform("linux").status, "ok")
        self.assertEqual(bootstrap.check_platform("darwin").status, "ok")

    def test_venv_with_wrong_python_version(self):
        self.world.make_venv("3.12.4")
        c = bootstrap.check_venv(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("3.12.4", c.detail)
        self.assertIn("3.13", c.detail)
        self.assertIn("rm -rf .venv", c.fix)

    def test_venv_that_does_not_start(self):
        self.world.make_venv()
        self.world.venv_version = None
        c = bootstrap.check_venv(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("does not start", c.detail)

    def test_missing_package_is_named(self):
        self.world.make_ready()
        del self.world.installed["Beta_Pkg"]
        c = bootstrap.check_packages(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("Beta_Pkg is missing", c.detail)
        self.assertIn("2.5.1", c.detail)
        self.assertIn("python3 digitize.py setup", c.fix)

    def test_wrong_version_and_broken_import_are_named(self):
        self.world.make_ready()
        self.world.installed["alpha"] = "0.9"
        self.world.import_errors["gamma"] = "gamma: libfoo.so not found"
        c = bootstrap.check_packages(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("alpha is 0.9, the lock says 1.0", c.detail)
        self.assertIn("gamma is installed but cannot be imported", c.detail)
        self.assertIn("libfoo.so", c.detail)

    def test_unreadable_lock_is_reported(self):
        self.world.make_ready()
        (self.root / "requirements.lock").write_text("-e /home/me/pkg\n")
        c = bootstrap.check_packages(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("line 1", c.detail)

    def test_low_disk_space_fails(self):
        usage = DiskUsage(10 * 1024 ** 3, 9 * 1024 ** 3, 1 * 1024 ** 3)
        with mock.patch.object(bootstrap.shutil, "disk_usage", return_value=usage):
            c = bootstrap.check_disk(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("1.0 GB", c.detail)
        usage = DiskUsage(100 * 1024 ** 3, 10 * 1024 ** 3, 90 * 1024 ** 3)
        with mock.patch.object(bootstrap.shutil, "disk_usage", return_value=usage):
            self.assertEqual(bootstrap.check_disk(self.root).status, "ok")

    def test_output_folder_check_leaves_nothing_behind(self):
        c = bootstrap.check_output(self.root)
        self.assertEqual(c.status, "ok")
        self.assertFalse((self.root / "output").exists())
        (self.root / "output").mkdir()
        (self.root / "output" / "keep.txt").write_text("x")
        self.assertEqual(bootstrap.check_output(self.root).status, "ok")
        self.assertEqual([p.name for p in (self.root / "output").iterdir()], ["keep.txt"])

    @unittest.skipIf(not hasattr(os, "geteuid") or os.geteuid() == 0, "root ignores permissions")
    def test_unwritable_project_folder_fails_output_check(self):
        self.root.chmod(0o555)
        self.addCleanup(self.root.chmod, 0o755)
        c = bootstrap.check_output(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("output", c.detail)

    def test_missing_wxstub(self):
        shutil.rmtree(str(self.root / "tools" / "wxstub"))
        self.assertEqual(bootstrap.check_wxstub(self.root).status, "FAIL")

    def test_selftest_failures_are_explained(self):
        self.world.make_ready()
        self.world.export_rc = 1
        c = bootstrap.check_selftest(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("fake export error", c.detail)
        self.world.export_rc = 0
        self.world.export_stdout = b"not a zip"
        self.assertIn("no VP3", bootstrap.check_selftest(self.root).detail)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("x.vp3", b"")
        self.world.export_stdout = buf.getvalue()
        self.assertIn("empty", bootstrap.check_selftest(self.root).detail)
        self.world.export_stdout = None
        self.world.stitches = "0"
        self.assertIn("no stitches", bootstrap.check_selftest(self.root).detail)

    def test_selftest_svg_is_two_layers_in_pipeline_format(self):
        svg = bootstrap.SELFTEST_SVG
        self.assertEqual(svg.count('inkscape:groupmode="layer"'), 2)
        self.assertEqual(svg.count("<path "), 2)
        self.assertIn("inkstitch_svg_version", svg)
        self.assertLess(len(svg), 4000)


class DoctorTests(Base):
    def test_doctor_all_good(self):
        self.world.make_ready()
        with mock.patch.object(bootstrap.shutil, "disk_usage",
                               return_value=DiskUsage(100 * 1024 ** 3, 0, 100 * 1024 ** 3)):
            code, out = self.call(bootstrap.run_doctor, self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("Everything is ready", out)
        self.assertNotIn("[FAIL]", out)
        self.assertIn("two rectangles became a VP3 with 4321 stitches", out)

    def test_doctor_missing_uv_is_a_failure_with_the_install_page(self):
        self.world.make_ready()
        (self.bin / "uv").unlink()
        code, out = self.call(bootstrap.run_doctor, self.root)
        self.assertEqual(code, 1)
        self.assertIn("uv is not installed", out)
        self.assertIn(bootstrap.UV_INSTALL_PAGE, out)

    def test_doctor_fails_loudly_when_a_package_is_missing(self):
        self.world.make_ready()
        del self.world.installed["gamma"]
        code, out = self.call(bootstrap.run_doctor, self.root)
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] Libraries", out)
        self.assertIn("gamma is missing", out)
        self.assertIn("Fix: Run: python3 digitize.py setup", out)
        self.assertIn("[skip] Export self-test", out)
        self.assertIn("Not ready", out)
        self.assertEqual(self.world.ran("inkstitch.py"), [], "the export must not run on a broken setup")

    def test_doctor_without_venv(self):
        code, out = self.call(bootstrap.run_doctor, self.root)
        self.assertEqual(code, 1)
        self.assertIn("there is no .venv folder", out)
        self.assertIn("python3 digitize.py setup", out)
        self.assertIn("[skip] Libraries", out)

    def test_doctor_wrong_commit(self):
        self.world.make_ready()
        self.world.set_head(self.root / "inkstitch", "b" * 40)
        code, out = self.call(bootstrap.run_doctor, self.root)
        self.assertEqual(code, 1)
        self.assertIn("not the pinned", out)

    def test_doctor_does_not_treat_a_plain_folder_as_inkstitch(self):
        # a folder inside this git project must not be judged by the project's own HEAD
        self.world.make_ready()
        shutil.rmtree(str(self.root / "inkstitch" / ".git"))
        c = bootstrap.check_inkstitch(self.root)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("no git history", c.detail)
        self.assertEqual(self.world.ran("rev-parse"), [])


class SetupTests(Base):
    def test_setup_without_uv_stops_with_a_plain_message(self):
        (self.bin / "uv").unlink()
        code, out = self.call(bootstrap.run_setup, self.root)
        self.assertEqual(code, 2)
        self.assertIn("uv is not installed", out)
        self.assertIn("https://docs.astral.sh/uv/getting-started/installation/", out)
        self.assertIn("curl -LsSf https://astral.sh/uv/install.sh | sh", out)
        self.assertEqual(self.world.calls, [], "nothing may run without uv")
        self.assertFalse((self.root / ".venv").exists())

    def test_setup_from_nothing_then_again_changes_nothing(self):
        usage = DiskUsage(100 * 1024 ** 3, 0, 100 * 1024 ** 3)
        with mock.patch.object(bootstrap.shutil, "disk_usage", return_value=usage):
            code, out = self.call(bootstrap.run_setup, self.root)
            self.assertEqual(code, 0, out)
            self.assertIn("1/5 uv ... ok", out)
            self.assertIn("2/5 Python 3.13 and .venv ... ok", out)
            self.assertIn("Setup is done", out)
            cmds = [" ".join(c[:3]) for c in self.world.calls]
            self.assertIn("uv python install", cmds)
            self.assertIn("uv venv --python", cmds)
            self.assertTrue(self.world.ran("fetch", "--depth", "1", "origin", PIN))
            self.assertTrue((self.root / "inkstitch" / "inkstitch.py").exists())
            self.assertFalse((self.root / "inkstitch.partial").exists())
            self.assertFalse((self.root / "output").exists())

            before = self.tree()
            self.world.calls.clear()
            code, out = self.call(bootstrap.run_setup, self.root)
            self.assertEqual(code, 0, out)
            self.assertIn("already there", out)
            self.assertIn("already installed", out)
            self.assertEqual(self.world.ran("uv", "venv"), [])
            self.assertEqual(self.world.ran("uv", "python"), [])
            self.assertEqual(self.world.ran("uv", "pip"), [])
            self.assertEqual(self.world.ran("fetch"), [])
            self.assertEqual(self.world.ran("init"), [])
            self.assertEqual(self.tree(), before)

    def test_setup_does_not_touch_a_venv_with_the_wrong_python(self):
        self.world.make_venv("3.12.4")
        code, out = self.call(bootstrap.run_setup, self.root)
        self.assertEqual(code, 2)
        self.assertIn("3.12.4", out)
        self.assertIn("rm -rf .venv", out)
        self.assertEqual(self.world.ran("uv", "venv"), [])
        self.assertEqual(self.world.ran("uv", "pip"), [])

    def test_setup_leaves_inkstitch_at_another_commit_alone(self):
        self.world.make_ready()
        self.world.set_head(self.root / "inkstitch", "c" * 40)
        sentinel = self.root / "inkstitch" / "my-edit.txt"
        sentinel.write_text("mine")
        code, out = self.call(bootstrap.run_setup, self.root)
        self.assertEqual(code, 2)
        self.assertIn("cccccccccccc", out)
        self.assertIn(PIN[:12], out)
        self.assertIn("mv inkstitch inkstitch.old", out)
        self.assertEqual(sentinel.read_text(), "mine")
        self.assertEqual(self.world.ran("fetch"), [])
        self.assertEqual(self.world.ran("init"), [])
        self.assertEqual(self.world.ran("checkout"), [])
        self.assertNotIn("Setup is done", out)

    def test_failed_download_leaves_no_half_folder(self):
        self.world.fetch_fails = True
        code, out = self.call(bootstrap.run_setup, self.root)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", out)
        self.assertIn("Fix: Check your internet connection", out)
        self.assertFalse((self.root / "inkstitch").exists())
        self.assertFalse((self.root / "inkstitch.partial").exists())
        # the next run starts clean and succeeds
        self.world.fetch_fails = False
        usage = DiskUsage(100 * 1024 ** 3, 0, 100 * 1024 ** 3)
        with mock.patch.object(bootstrap.shutil, "disk_usage", return_value=usage):
            code, out = self.call(bootstrap.run_setup, self.root)
        self.assertEqual(code, 0, out)

    def test_leftover_partial_folder_is_replaced(self):
        (self.root / "inkstitch.partial").mkdir()
        (self.root / "inkstitch.partial" / "junk").write_text("x")
        self.assertIsNone(bootstrap._fetch_inkstitch(self.root))
        self.assertTrue((self.root / "inkstitch" / "inkstitch.py").exists())
        self.assertFalse((self.root / "inkstitch" / "junk").exists())

    def test_an_empty_inkstitch_folder_is_filled(self):
        (self.root / "inkstitch").mkdir()
        self.assertEqual(bootstrap._inkstitch_state(self.root), ("missing", ""))
        self.assertIsNone(bootstrap._fetch_inkstitch(self.root))
        self.assertEqual(bootstrap._inkstitch_state(self.root)[0], "ok")

    def test_the_fetch_uses_the_pinned_commit_and_skips_submodules(self):
        self.assertIsNone(bootstrap._fetch_inkstitch(self.root))
        joined = [" ".join(c) for c in self.world.calls]
        self.assertTrue(any(c.endswith("remote add origin https://github.com/inkstitch/inkstitch") for c in joined))
        self.assertTrue(any("fetch -q --depth 1 origin " + PIN in c for c in joined))
        self.assertTrue(any(c.endswith("checkout -q FETCH_HEAD") for c in joined))
        self.assertFalse(any("submodule" in c or "--recurse" in c for c in joined))

    def test_main_dispatch_and_usage(self):
        code, out = self.call(bootstrap.main, ["--help"], self.root)
        self.assertEqual(code, 0)
        self.assertIn("setup", out)
        code, out = self.call(bootstrap.main, ["setup", "extra"], self.root)
        self.assertEqual(code, 2)


class EntryPointTests(Base):
    def setUp(self):
        super().setUp()
        # a project folder the entry point can load bootstrap.py and the wizard stub from
        wizard = self.root / "tools" / "digitize" / "wizard"
        wizard.mkdir(parents=True)
        (wizard / "__init__.py").write_text("def main(argv):\n    print('WIZARD', argv)\n    return 0\n")
        shutil.copy(str(REPO / "tools" / "digitize" / "bootstrap.py"), str(self.root / "tools" / "digitize"))

    def test_default_without_venv_prints_setup_hint_and_exits_2(self):
        with mock.patch.object(os, "execv") as execv:
            code, out = self.call(entry.run, [], self.root)
        self.assertEqual(code, 2)
        self.assertIn("python3 digitize.py setup", out)
        execv.assert_not_called()

    def test_default_reruns_inside_the_venv(self):
        self.world.make_venv()
        with mock.patch.object(os, "execv") as execv:
            self.call(entry.run, ["--some-flag", "pic.png"], self.root)
        venv_py = str(self.root / ".venv" / "bin" / "python")
        args = execv.call_args[0]
        self.assertEqual(args[0], venv_py)
        self.assertEqual(args[1][0], venv_py)
        self.assertTrue(args[1][1].endswith("digitize.py"))
        self.assertEqual(args[1][2:], ["--some-flag", "pic.png"])

    def test_no_reexec_loop(self):
        self.world.make_venv()
        os.environ["DIGITIZE_REEXEC"] = "1"
        with mock.patch.object(os, "execv") as execv:
            code, out = self.call(entry.run, [], self.root)
        self.assertEqual(code, 2)
        execv.assert_not_called()

    def test_inside_the_venv_the_wizard_runs(self):
        self.world.make_venv()
        with mock.patch.object(sys, "path", list(sys.path)), mock.patch.dict(sys.modules):
            for k in [k for k in sys.modules if k == "tools" or k.startswith("tools.")]:
                del sys.modules[k]
            with mock.patch.object(sys, "prefix", str(self.root / ".venv")), mock.patch.object(os, "execv") as execv:
                code, out = self.call(entry.run, ["a.png"], self.root)
        execv.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn("WIZARD ['a.png']", out)

    def test_setup_and_doctor_are_handled_before_the_venv_exists(self):
        (self.bin / "uv").unlink()
        code, out = self.call(entry.run, ["setup"], self.root)
        self.assertEqual(code, 2)
        self.assertIn("uv is not installed", out)


if __name__ == "__main__":
    unittest.main()
