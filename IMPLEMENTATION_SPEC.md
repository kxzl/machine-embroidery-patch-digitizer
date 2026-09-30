# Implementation Spec — Dumb-Model-Proof Protocol

This file is the single source of truth for the executing model. Work **one step at
a time**, run **only** the listed commands, capture output **verbatim**, and report
back. Do NOT improvise, do NOT skip verification, do NOT install anything unless a
step explicitly says to.

## Rules for the driver model

1. Execute exactly one step, then stop and report.
2. Always copy command output verbatim into your report (do not paraphrase).
3. If a command errors, stop, report the exact error, do not "fix and continue".
4. Never run interactive commands (no prompts) — use non-interactive flags.
5. Any install step must use `-y`/`--yes` and explicit timeouts.
6. The reviewer (me) will inspect every report before the next step.

## VERIFIED headless Ink/Stitch recipe (working)

Environment: Flatpak Freedesktop SDK 25.08, glibc 2.42, no `sudo`/`apt`/C compiler.
Python 3.13 venv at `.venv`. Ink/Stitch cloned at `inkstitch/`.

Installed deps (no `wxPython` — no Linux wheels; no `PyGObject` — needs C compiler):

- `inkex==1.4.1` installed with `--no-deps` plus its pure-python requirements:
  `lxml<6 cssselect numpy==2.2.6 pyparsing tinycss2 packaging Pillow pySerial webencodings`
- runtime: `pystitch networkx "shapely>=2.0.0" platformdirs "jinja2>2.9" requests colormath2 "flask>=2.2.0" fonttools "trimesh>=3.15.2" diskcache flask-cors`

GUI shim: `tools/wxstub/wx/` (synthetic `wx` package). Put on `PYTHONPATH`.

Run export (headless), from `webp → svg`:

```
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
  .venv/bin/python inkstitch/inkstitch.py --extension=zip --format-vp3=True \
  input.svg > output.zip
```

The zip contains `<name>.vp3`. Also available: `--format-dst=True`,
`--format-pes=True`, `--format-hus=<bool>` (see `pystitch.supported_formats()`).

## Steps

### Step 0 — Environment reconnaissance (read-only, no installs)
Run each and report output exactly:

- `sudo -n true; echo "sudo_exit=$?"`
- `command -v apt-get; command -v sudo; command -v pip3; command -v inkscape`
- `python3 --version; pip3 --version`
- Network / pip reachability: `python3 -m pip download --no-deps --dest /tmp/pipcheck pyembroidery 2>&1 | tail -20`
- `id -u`

Report: sudo_exit value, which commands exist, python/pip versions, and full tail of
the pip download output.

### Step 1 — (DONE) Install Ink/Stitch runtime deps (headless, no sudo/apt, no C compiler)

The repo is ALREADY cloned at `inkstitch/`. The full `requirements.txt` fails
because it pulls GUI-only `wxPython`→`pycairo` (needs a C compiler we lack).
We install ONLY the headless runtime subset below. Use venv `.venv` (Python 3.13).

Run ONE pip install (single line, copy exactly), then the checks:

- `.venv/bin/python -m pip install pystitch "inkex==1.4.1" networkx "shapely>=2.0.0" lxml platformdirs "numpy==2.2.6" "jinja2>2.9" requests colormath2 "flask>=2.2.0" fonttools "trimesh>=3.15.2" diskcache flask-cors 2>&1 | tail -30`
- `.venv/bin/python -c "import pystitch, inkex, shapely, numpy, networkx, trimesh, flask, fonttools, colormath2, diskcache, lxml; print('IMPORTS_OK')" 2>&1`
- `.venv/bin/python -c "import pystitch; print('\n'.join('%s %s' % (f['extension'], f['category']) for f in pystitch.supported_formats() if 'writer' in f))" 2>&1`

Report verbatim outputs. Stop at first failure — report exact error, do NOT fix.
Do NOT run the inkstitch CLI yet. Do NOT install anything else.
### Step 2 — (pending review) Color separation + palette export
### Step 3 — (pending review) Vectorize outlines (linework → satin candidates)
### Step 4 — (pending review) Vectorize fills (color regions → fill candidates)
### Step 5 — (pending review) Assemble pre-digitized SVG with Ink/Stitch params
### Step 6 — (pending review) Install Inkscape + Ink/Stitch, export VP3/HUS
### Step 7 — (pending review) Verify SVG + output machine file for review
