#!/usr/bin/env python3
"""Entry point of the guided tool: picture in, SVG and VP3 out.

    python3 digitize.py setup     one-time install (needs uv)
    python3 digitize.py doctor    check that everything is ready
    python3 digitize.py           start the guided wizard

Standard library only, Python 3.9 or newer, so it starts on the system Python
before any virtual environment exists. The wizard itself runs inside .venv.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

NO_VENV = """The tool is not set up yet: there is no .venv folder.
Run this once (it needs uv and an internet connection):
  python3 digitize.py setup
Then start the tool again with: python3 digitize.py"""


def _load_bootstrap(root: Path):
    """Load tools/digitize/bootstrap.py by path (stdlib only, no package import needed)."""
    path = root / "tools" / "digitize" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("digitize_bootstrap", str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules["digitize_bootstrap"] = module
    spec.loader.exec_module(module)
    return module


def run(argv, root: Path = ROOT) -> int:
    if sys.version_info < (3, 9):
        print("This tool needs Python 3.9 or newer. This machine runs Python %d.%d."
              % sys.version_info[:2])
        return 2
    bootstrap = _load_bootstrap(root)
    if argv[:1] in (["setup"], ["doctor"]):
        return bootstrap.main(argv, root)

    venv_py = bootstrap.venv_python(root)
    if not venv_py.exists():
        print(NO_VENV)
        return 2

    inside = os.path.realpath(sys.prefix) == os.path.realpath(str(bootstrap.venv_dir(root)))
    if not inside:
        if os.environ.get("DIGITIZE_REEXEC") == "1":
            print("Could not switch to the Python in .venv. Run: python3 digitize.py doctor")
            return 2
        os.environ["DIGITIZE_REEXEC"] = "1"
        sys.stdout.flush()
        # Do not resolve the symlink: the venv is found through its own path.
        os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve())] + list(argv))
        return 2  # not reached

    sys.path.insert(0, str(root))
    try:
        from tools.digitize.wizard import main as wizard_main
    except ImportError as exc:
        print("The wizard could not start: %s" % exc)
        print("Run: python3 digitize.py doctor")
        return 2
    return int(wizard_main(list(argv)) or 0)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
