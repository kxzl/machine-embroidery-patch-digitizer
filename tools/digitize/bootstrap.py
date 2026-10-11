"""Setup and doctor for the guided tool.

Standard library only. This module runs on the system Python (3.9 or newer),
before any virtual environment exists, so it must not import third-party packages.

    python3 digitize.py setup    install Python 3.13, the locked libraries and Ink/Stitch
    python3 digitize.py doctor   check that everything is in place

Pinned values come from docs/design/guided-tool-readme-review.md, section 5.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]

# ---- pinned values (design contract, section 5) ---------------------------------
INKSTITCH_URL = "https://github.com/inkstitch/inkstitch"
INKSTITCH_COMMIT = "d59c9ab1e390285a6c67822436ffd9ba9843d8b4"
VENV_PYTHON = "3.13"
MIN_BOOTSTRAP_PYTHON = (3, 9)

# ---- values from the task, not from the design table ----------------------------
MIN_FREE_BYTES = 3 * 1024 ** 3  # doctor wants more than 3 GB free

# ---- official uv documentation (read at implementation time) --------------------
UV_INSTALL_PAGE = "https://docs.astral.sh/uv/getting-started/installation/"
UV_INSTALL_CURL = "curl -LsSf https://astral.sh/uv/install.sh | sh"
UV_INSTALL_WGET = "wget -qO- https://astral.sh/uv/install.sh | sh"

USAGE = """Usage: python3 digitize.py [setup | doctor]
  (no command)  start the guided wizard
  setup         one-time install of Python 3.13, the libraries and Ink/Stitch
  doctor        check that everything is ready"""

UV_MISSING = (
    "uv is not installed. Setup needs it to get Python %s and the libraries.\n"
    "Install uv from its official page:\n"
    "  %s\n"
    "On Linux, macOS and Windows (WSL2) the page gives this command:\n"
    "  %s\n"
    "or, if you have no curl:\n"
    "  %s\n"
    "Then open a new terminal and run: python3 digitize.py setup"
    % (VENV_PYTHON, UV_INSTALL_PAGE, UV_INSTALL_CURL, UV_INSTALL_WGET)
)

# A hand-written two-rectangle design in the format the pipeline emits (layers named
# by thread colour, Ink/Stitch fill attributes). Kept in code because *.svg is
# gitignored. Doctor exports it to check the whole toolchain.
SELFTEST_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkstitch="http://inkstitch.org/namespace" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd" width="50mm" height="50mm" viewBox="0 0 400 400" inkscape:document-units="mm" sodipodi:docname="selftest.svg">
  <sodipodi:namedview id="namedview1" pagecolor="#ffffff" units="mm" inkscape:document-units="mm" pagewidth="50" pageheight="50" inkscape:pageopacity="0.0" inkscape:pagecheckerboard="0" showgrid="false"/>
  <metadata id="metadata1"><inkstitch:inkstitch_svg_version>4</inkstitch:inkstitch_svg_version><inkstitch:collapse_len_mm>3</inkstitch:collapse_len_mm></metadata>
  <g inkscape:label="#e8590c" inkscape:groupmode="layer" id="color0">
    <path id="f0" style="fill:#e8590c;stroke:none" fill-rule="evenodd" inkstitch:row_spacing_mm="0.4" inkstitch:max_stitch_length_mm="3" inkstitch:running_stitch_length_mm="1.5" inkstitch:fill_underlay_skip_last="true" inkstitch:trim_after="true" d="M 60.0,60.0 L 200.0,60.0 L 200.0,180.0 L 60.0,180.0 L 60.0,60.0 Z"/>
  </g>
  <g inkscape:label="#1a1a1a" inkscape:groupmode="layer" id="color1">
    <path id="f1" style="fill:#1a1a1a;stroke:none" fill-rule="evenodd" inkstitch:row_spacing_mm="0.4" inkstitch:max_stitch_length_mm="3" inkstitch:running_stitch_length_mm="1.5" inkstitch:fill_underlay_skip_last="true" inkstitch:trim_after="true" d="M 220.0,220.0 L 340.0,220.0 L 340.0,340.0 L 220.0,340.0 L 220.0,220.0 Z"/>
  </g>
</svg>
"""

# Runs inside the venv: compares installed versions with the lock and imports the
# first public top-level module of every package. argv: <1 to import | 0 for versions
# only> <json file {name: version}>. Prints one JSON line {name: [kind, detail]} for
# the packages that are not fine.
_PKG_SCRIPT = r"""
import importlib, importlib.metadata as md, json, re, sys
do_import = sys.argv[1] == "1"
with open(sys.argv[2], encoding="utf-8") as fh:
    want = json.load(fh)
norm = lambda s: re.sub(r"[-_.]+", "-", s).lower()
by_dist = {}
for mod, dists in md.packages_distributions().items():
    for d in dists:
        by_dist.setdefault(norm(d), []).append(mod)
bad = {}
for name, ver in want.items():
    try:
        have = md.version(name)
    except md.PackageNotFoundError:
        bad[name] = ["missing", ""]
        continue
    if have != ver:
        bad[name] = ["version", have]
        continue
    if not do_import:
        continue
    mods = sorted(m for m in by_dist.get(norm(name), []) if not m.startswith("_") and m not in ("test", "tests"))
    if not mods:
        continue
    try:
        importlib.import_module(mods[0])
    except BaseException as exc:
        bad[name] = ["import", "%s: %s" % (mods[0], str(exc).splitlines()[0] if str(exc) else type(exc).__name__)]
print(json.dumps(bad))
"""


class Check(NamedTuple):
    """One doctor line. status is 'ok', 'FAIL' or 'skip'."""

    name: str
    status: str
    detail: str
    fix: str = ""


# ---- small helpers -------------------------------------------------------------


def venv_dir(root: Path = ROOT) -> Path:
    return Path(root) / ".venv"


def venv_python(root: Path = ROOT) -> Path:
    return venv_dir(root) / "bin" / "python"


def lock_path(root: Path = ROOT) -> Path:
    return Path(root) / "requirements.lock"


def inkstitch_dir(root: Path = ROOT) -> Path:
    return Path(root) / "inkstitch"


def _run(cmd: Sequence, cwd=None, env=None, text: bool = True, timeout: Optional[float] = None):
    """Run a command, capture output, never raise. Tests replace this function."""
    args = [str(c) for c in cmd]
    try:
        return subprocess.run(
            args,
            cwd=None if cwd is None else str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=text,
            timeout=timeout,
        )
    except OSError as exc:
        empty = "" if text else b""
        return subprocess.CompletedProcess(args, 127, empty, "cannot start %s: %s" % (args[0], exc) if text else str(exc).encode())
    except subprocess.TimeoutExpired:
        empty = "" if text else b""
        return subprocess.CompletedProcess(args, 124, empty, "timed out after %s s" % timeout if text else b"timed out")


def _tail(text, lines: int = 6) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    rows = [r.rstrip() for r in (text or "").strip().splitlines() if r.strip()]
    return "\n".join("  " + r for r in rows[-lines:])


def parse_lock(path) -> List[Tuple[str, str]]:
    """Read requirements.lock as (name, version) pairs. Anything not 'name==version' is an error."""
    pins: List[Tuple[str, str]] = []
    text = Path(path).read_text(encoding="utf-8")
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9._+!-]+)", line)
        if not m:
            raise ValueError("requirements.lock line %d is not 'name==version': %s" % (no, raw.strip()))
        pins.append((m.group(1), m.group(2)))
    return pins


def venv_version(root: Path = ROOT) -> Tuple[Optional[str], str]:
    """Python version of the venv as 'X.Y.Z', or (None, reason)."""
    py = venv_python(root)
    if not py.exists():
        return None, "no .venv"
    proc = _run([py, "-I", "-c", 'import sys; print("%d.%d.%d" % sys.version_info[:3])'], timeout=60)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not re.fullmatch(r"\d+\.\d+\.\d+", out):
        return None, _tail(proc.stderr, 3) or "the Python inside .venv does not start"
    return out, ""


def _inkstitch_state(root: Path = ROOT) -> Tuple[str, str]:
    """('missing' | 'ok' | 'other', detail). 'other' means: there, but not ours to touch."""
    d = inkstitch_dir(root)
    if not os.path.lexists(str(d)):
        return "missing", ""
    if not d.is_dir():
        return "other", "inkstitch exists but is not a folder (or is a broken link)"
    if not any(d.iterdir()):
        return "missing", ""
    if not (d / ".git").exists():
        return "other", "the inkstitch folder has no git history, so its version cannot be checked"
    proc = _run(["git", "-C", d, "rev-parse", "HEAD"], timeout=60)
    head = (proc.stdout or "").strip()
    if proc.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", head):
        return "other", "git cannot read the commit of the inkstitch folder"
    if head == INKSTITCH_COMMIT:
        return "ok", head
    return "other", "the inkstitch folder is at commit %s, not the pinned %s" % (head[:12], INKSTITCH_COMMIT[:12])


# ---- doctor checks -------------------------------------------------------------


def check_python(version_info=None) -> Check:
    vi = tuple(sys.version_info if version_info is None else version_info)
    have = ".".join(str(x) for x in vi[:3])
    need = ".".join(str(x) for x in MIN_BOOTSTRAP_PYTHON)
    if tuple(vi[:2]) >= MIN_BOOTSTRAP_PYTHON:
        return Check("Python", "ok", "this machine runs Python %s (%s or newer is needed)" % (have, need))
    return Check(
        "Python", "FAIL", "this machine runs Python %s, but %s or newer is needed" % (have, need),
        "Install a newer Python, then run the command again.",
    )


def check_platform(platform: Optional[str] = None) -> Check:
    p = sys.platform if platform is None else platform
    if p.startswith("win") or p == "cygwin":
        return Check(
            "Platform", "FAIL", "native Windows is not supported",
            "Install WSL2 (Windows Subsystem for Linux) and run this tool inside it.",
        )
    return Check("Platform", "ok", "%s is supported" % p)


def check_uv() -> Check:
    path = shutil.which("uv")
    if not path:
        return Check("uv", "FAIL", "uv is not installed", UV_MISSING)
    proc = _run(["uv", "--version"], timeout=60)
    ver = " ".join((proc.stdout or "").split()[:2]) or "uv"
    if proc.returncode != 0:
        return Check("uv", "FAIL", "uv is on the PATH but does not run: %s" % _tail(proc.stderr, 2).strip(),
                     "Reinstall uv: %s" % UV_INSTALL_PAGE)
    return Check("uv", "ok", "%s found" % ver)


def check_venv(root: Path = ROOT) -> Check:
    ver, why = venv_version(root)
    if ver is None and why == "no .venv":
        return Check("Python %s environment" % VENV_PYTHON, "FAIL", "there is no .venv folder in %s" % root,
                     "Run: python3 digitize.py setup")
    if ver is None:
        return Check("Python %s environment" % VENV_PYTHON, "FAIL", "the Python inside .venv does not start\n%s" % why,
                     "Delete the folder with: rm -rf .venv   then run: python3 digitize.py setup")
    if ver.split(".")[:2] != VENV_PYTHON.split("."):
        return Check("Python %s environment" % VENV_PYTHON, "FAIL",
                     ".venv uses Python %s, but the tool needs %s" % (ver, VENV_PYTHON),
                     "Delete the folder with: rm -rf .venv   then run: python3 digitize.py setup")
    return Check("Python %s environment" % VENV_PYTHON, "ok", ".venv uses Python %s" % ver)


def check_packages(root: Path = ROOT, imports: bool = True) -> Check:
    name = "Libraries"
    fix = "Run: python3 digitize.py setup (it installs the locked versions)"
    lock = lock_path(root)
    if not lock.exists():
        return Check(name, "FAIL", "requirements.lock is missing in %s" % root,
                     "Get the file back from the project (git checkout -- requirements.lock).")
    try:
        pins = parse_lock(lock)
    except (ValueError, OSError) as exc:
        return Check(name, "FAIL", str(exc), "Get a clean copy of requirements.lock from the project.")
    proc = _run_pkg_script(root, pins, imports)
    if proc.returncode != 0:
        return Check(name, "FAIL", "could not inspect the libraries in .venv\n%s" % _tail(proc.stderr, 4), fix)
    try:
        bad: Dict[str, List[str]] = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return Check(name, "FAIL", "could not read the library check result\n%s" % _tail(proc.stdout, 4), fix)
    if not bad:
        return Check(name, "ok", "all %d locked libraries are installed at the locked version%s"
                     % (len(pins), " and import" if imports else ""))
    locked = dict(pins)
    lines = []
    for pkg in sorted(bad, key=str.lower):
        kind, detail = bad[pkg]
        if kind == "missing":
            lines.append("%s is missing (needs %s)" % (pkg, locked.get(pkg, "?")))
        elif kind == "version":
            lines.append("%s is %s, the lock says %s" % (pkg, detail, locked.get(pkg, "?")))
        else:
            lines.append("%s is installed but cannot be imported (%s)" % (pkg, detail))
    shown = lines[:8]
    if len(lines) > len(shown):
        shown.append("and %d more" % (len(lines) - len(shown)))
    return Check(name, "FAIL", "%d of %d libraries are not right:\n" % (len(bad), len(pins))
                 + "\n".join("  - " + s for s in shown), fix)


def _run_pkg_script(root: Path, pins: Sequence[Tuple[str, str]], imports: bool):
    with tempfile.TemporaryDirectory(prefix="digitize-pkgs-") as tmp:
        want = Path(tmp) / "want.json"
        want.write_text(json.dumps(dict(pins)), encoding="utf-8")
        return _run([venv_python(root), "-I", "-c", _PKG_SCRIPT, "1" if imports else "0", want], timeout=300)


def check_inkstitch(root: Path = ROOT) -> Check:
    state, detail = _inkstitch_state(root)
    short = INKSTITCH_COMMIT[:12]
    if state == "ok":
        return Check("Ink/Stitch", "ok", "inkstitch/ is at the pinned commit %s" % short)
    if state == "missing":
        return Check("Ink/Stitch", "FAIL", "the inkstitch folder is not there", "Run: python3 digitize.py setup")
    return Check("Ink/Stitch", "FAIL", detail,
                 "Move it away (mv inkstitch inkstitch.old) and run: python3 digitize.py setup. "
                 "Nothing in inkstitch/ was changed.")


def check_wxstub(root: Path = ROOT) -> Check:
    if (Path(root) / "tools" / "wxstub" / "wx" / "__init__.py").is_file():
        return Check("wx stub", "ok", "tools/wxstub is present")
    return Check("wx stub", "FAIL", "tools/wxstub/wx is missing",
                 "It is part of the project. Restore it with: git checkout -- tools/wxstub")


def check_output(root: Path = ROOT) -> Check:
    out = Path(root) / "output"
    try:
        if out.exists():
            if not out.is_dir():
                return Check("Output folder", "FAIL", "output exists but is a file, not a folder",
                             "Move that file away, then run doctor again.")
            with tempfile.TemporaryFile(dir=str(out)):
                pass
            return Check("Output folder", "ok", "output/ exists and is writable")
        out.mkdir()
        out.rmdir()  # doctor leaves no folder behind
        return Check("Output folder", "ok", "output/ can be created")
    except OSError as exc:
        return Check("Output folder", "FAIL", "cannot write to output/ in %s: %s" % (root, exc),
                     "Check the folder permissions, or move the project somewhere you can write.")


def check_disk(root: Path = ROOT) -> Check:
    try:
        free = shutil.disk_usage(str(root)).free
    except OSError as exc:
        return Check("Disk space", "FAIL", "cannot read the free disk space: %s" % exc, "")
    gb = free / 1024 ** 3
    need = MIN_FREE_BYTES / 1024 ** 3
    if free > MIN_FREE_BYTES:
        return Check("Disk space", "ok", "%.1f GB free (more than %.0f GB needed)" % (gb, need))
    return Check("Disk space", "FAIL", "only %.1f GB free, %.0f GB needed" % (gb, need),
                 "Free some disk space, then run doctor again.")


def check_selftest(root: Path = ROOT) -> Check:
    """Export a tiny two-rectangle design through Ink/Stitch and read the VP3 back."""
    name = "Export self-test"
    py = venv_python(root)
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="digitize-selftest-") as tmp:
        svg = Path(tmp) / "selftest.svg"
        svg.write_text(SELFTEST_SVG, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(root) / "tools" / "wxstub")
        env["INKSTITCH_OFFLINE_SCRIPT"] = "true"
        proc = _run([py, Path(root) / "inkstitch" / "inkstitch.py", "--extension=zip", "--format-vp3=True", svg],
                    cwd=root, env=env, text=False, timeout=300)
        fix = "Run: python3 digitize.py setup. If it still fails, send the lines above to the maintainer."
        if proc.returncode != 0:
            return Check(name, "FAIL", "Ink/Stitch could not export the test design (exit %s)\n%s"
                         % (proc.returncode, _tail(proc.stderr, 6)), fix)
        try:
            z = zipfile.ZipFile(io.BytesIO(proc.stdout))
            vp3s = [n for n in z.namelist() if n.lower().endswith(".vp3")]
            data = z.read(vp3s[0])
        except (zipfile.BadZipFile, IndexError, KeyError):
            return Check(name, "FAIL", "Ink/Stitch ran but produced no VP3 file\n%s" % _tail(proc.stderr, 4), fix)
        if not data:
            return Check(name, "FAIL", "Ink/Stitch produced an empty VP3 file", fix)
        vp3 = Path(tmp) / "selftest.vp3"
        vp3.write_bytes(data)
        rd = _run([py, "-I", "-c", "import sys, pystitch; print(pystitch.read(sys.argv[1]).count_stitches())", vp3],
                  timeout=120)
        try:
            n = int((rd.stdout or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            n = -1
        if rd.returncode != 0 or n <= 0:
            return Check(name, "FAIL", "the exported VP3 has no stitches (%d bytes)\n%s" % (len(data), _tail(rd.stderr, 3)), fix)
    return Check(name, "ok", "two rectangles became a VP3 with %d stitches in %.0f s" % (n, time.time() - started))


# ---- doctor --------------------------------------------------------------------


def run_doctor(root: Path = ROOT) -> int:
    """Run every check, print one line each and a summary. Exit code 0 only if all pass."""
    root = Path(root)
    results: List[Check] = []

    def show(c: Check) -> Check:
        tag = {"ok": "[ok]  ", "FAIL": "[FAIL]", "skip": "[skip]"}[c.status]
        head, _, rest = c.detail.partition("\n")
        print("%s %s: %s" % (tag, c.name, head), flush=True)
        for row in rest.splitlines():
            print("       " + row.rstrip(), flush=True)
        if c.status == "FAIL" and c.fix:
            for i, row in enumerate(c.fix.splitlines()):
                print("       %s%s" % ("Fix: " if i == 0 else "     ", row), flush=True)
        results.append(c)
        return c

    show(check_python())
    show(check_platform())
    show(check_uv())
    venv = show(check_venv(root))
    wxs = show(check_wxstub(root))
    ink = show(check_inkstitch(root))
    if venv.status == "ok":
        pkgs = show(check_packages(root, imports=True))
    else:
        pkgs = show(Check("Libraries", "skip", "not checked because the Python environment is not ready"))
    show(check_output(root))
    show(check_disk(root))
    if all(c.status == "ok" for c in (venv, wxs, ink, pkgs)):
        show(check_selftest(root))
    else:
        show(Check("Export self-test", "skip", "not run until the problems above are fixed"))

    failed = [c for c in results if c.status != "ok"]
    print("", flush=True)
    if not failed:
        print("Everything is ready: %d of %d checks passed." % (len(results), len(results)), flush=True)
        return 0
    print("Not ready: %d of %d checks did not pass (%s). Fix them and run: python3 digitize.py doctor"
          % (len(failed), len(results), ", ".join(c.name for c in failed)), flush=True)
    return 1


# ---- setup ---------------------------------------------------------------------

_SETUP_STEPS = 5


def _begin(i: int, label: str) -> None:
    print("%d/%d %s ... " % (i, _SETUP_STEPS, label), end="", flush=True)


def _fail(what: str, fix: str, code: int = 1) -> int:
    print("FAILED", flush=True)
    print(what, flush=True)
    print("Fix: " + fix, flush=True)
    return code


def _fetch_inkstitch(root: Path) -> Optional[str]:
    """Shallow-fetch the pinned commit into inkstitch.partial, then move it into place.
    Returns an error text, or None on success. The fonts submodule is not fetched."""
    final = inkstitch_dir(root)
    partial = Path(root) / "inkstitch.partial"
    if partial.exists():
        shutil.rmtree(str(partial), ignore_errors=True)
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    steps = [
        ["git", "init", "-q", partial],
        ["git", "-C", partial, "remote", "add", "origin", INKSTITCH_URL],
        ["git", "-C", partial, "fetch", "-q", "--depth", "1", "origin", INKSTITCH_COMMIT],
        ["git", "-C", partial, "checkout", "-q", "FETCH_HEAD"],
    ]
    for cmd in steps:
        proc = _run(cmd, env=env, timeout=1800)
        if proc.returncode != 0:
            shutil.rmtree(str(partial), ignore_errors=True)
            return "git %s failed:\n%s" % (cmd[3] if cmd[1] == "-C" else cmd[1], _tail(proc.stderr, 6))
    proc = _run(["git", "-C", partial, "rev-parse", "HEAD"], timeout=60)
    head = (proc.stdout or "").strip()
    if head != INKSTITCH_COMMIT:
        shutil.rmtree(str(partial), ignore_errors=True)
        return "the download is at commit %s, expected %s" % (head or "unknown", INKSTITCH_COMMIT)
    try:
        if final.is_dir() and not final.is_symlink():
            final.rmdir()  # an empty folder from an earlier try
        os.replace(str(partial), str(final))
    except OSError as exc:
        shutil.rmtree(str(partial), ignore_errors=True)
        return "could not move the download into place: %s" % exc
    return None


def run_setup(root: Path = ROOT) -> int:
    root = Path(root)
    n = _SETUP_STEPS
    if check_platform().status != "ok":
        print(check_platform().detail + ". " + check_platform().fix, flush=True)
        return 2
    if not check_python().status == "ok":
        print(check_python().detail + ". " + check_python().fix, flush=True)
        return 2

    # 1: uv
    _begin(1, "uv")
    if not shutil.which("uv"):
        print("not found", flush=True)
        print(UV_MISSING, flush=True)
        return 2
    proc = _run(["uv", "--version"], timeout=60)
    print("ok (%s)" % (" ".join((proc.stdout or "").split()[:2]) or "uv"), flush=True)

    # 2: Python 3.13 and the venv
    _begin(2, "Python %s and .venv" % VENV_PYTHON)
    ver, why = venv_version(root)
    if ver is not None and ver.split(".")[:2] == VENV_PYTHON.split("."):
        print("ok (already there, Python %s)" % ver, flush=True)
    elif ver is not None or why != "no .venv":
        shown = "uses Python %s" % ver if ver else "does not start"
        return _fail(".venv exists but %s. Setup does not delete it for you." % shown,
                     "Run: rm -rf .venv   then: python3 digitize.py setup", 2)
    else:
        proc = _run(["uv", "python", "install", VENV_PYTHON], cwd=root, timeout=1800)
        if proc.returncode != 0:
            return _fail("uv could not install Python %s:\n%s" % (VENV_PYTHON, _tail(proc.stderr)),
                         "Check your internet connection, then run: python3 digitize.py setup")
        proc = _run(["uv", "venv", "--python", VENV_PYTHON, ".venv"], cwd=root, timeout=600)
        if proc.returncode != 0:
            return _fail("uv could not create .venv:\n%s" % _tail(proc.stderr),
                         "Run: rm -rf .venv   then: python3 digitize.py setup")
        print("ok", flush=True)

    # 3: locked libraries
    _begin(3, "Libraries from requirements.lock")
    before = check_packages(root, imports=False)
    if before.status == "ok":
        print("ok (already installed)", flush=True)
    else:
        if not lock_path(root).exists():
            return _fail(before.detail, before.fix)
        print("downloading, a few hundred MB, this can take several minutes ... ", end="", flush=True)
        proc = _run(["uv", "pip", "install", "--python", venv_python(root), "--no-deps", "-r", lock_path(root)],
                    cwd=root, timeout=3600)
        if proc.returncode != 0:
            return _fail("uv could not install the libraries:\n%s" % _tail(proc.stderr),
                         "Check your internet connection, then run: python3 digitize.py setup")
        after = check_packages(root, imports=False)
        if after.status != "ok":
            return _fail(after.detail, after.fix)
        print("ok", flush=True)

    # 4: Ink/Stitch
    _begin(4, "Ink/Stitch %s" % INKSTITCH_COMMIT[:12])
    state, detail = _inkstitch_state(root)
    if state == "ok":
        print("ok (already there)", flush=True)
    elif state == "other":
        return _fail("%s. Setup leaves it alone." % (detail[:1].upper() + detail[1:]),
                     "Move it away (mv inkstitch inkstitch.old) and run: python3 digitize.py setup", 2)
    else:
        if not shutil.which("git"):
            return _fail("git is not installed.", "Install git from https://git-scm.com/downloads, then run: "
                         "python3 digitize.py setup", 2)
        print("downloading ... ", end="", flush=True)
        err = _fetch_inkstitch(root)
        if err:
            return _fail(err, "Check your internet connection, then run: python3 digitize.py setup")
        print("ok", flush=True)

    # 5: doctor
    print("%d/%d Checks (python3 digitize.py doctor)" % (n, n), flush=True)
    code = run_doctor(root)
    if code == 0:
        print("Setup is done. Start the tool with: python3 digitize.py", flush=True)
    return code


# ---- command line ----------------------------------------------------------------


def main(argv: Sequence[str], root: Path = ROOT) -> int:
    """Handle `setup` and `doctor`. argv is the command line without the program name."""
    args = list(argv)
    if args in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    if args == ["setup"]:
        return run_setup(root)
    if args == ["doctor"]:
        return run_doctor(root)
    print(USAGE, file=sys.stderr)
    return 2
