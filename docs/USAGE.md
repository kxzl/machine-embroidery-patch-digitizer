# Digitize Patches — raster image → embroidery

Turn a raster image (WebP/PNG/JPG) into a pre-digitized embroidery **SVG** for
[Ink/Stitch](https://inkstitch.org) and export a machine-ready **VP3** file
(Husqvarna/Viking), fully headless (no Inkscape GUI needed).

```
image → color separation → vectorize (fills + satin outlines + satin border) → SVG → Ink/Stitch → .vp3
```

---

## What it produces

| File | Purpose |
|---|---|
| `work/<name>.svg` | Pre-digitized vector design. Open in Inkscape to review, tune, or run the Simulator. |
| `work/<name>.vp3` | Machine file for Husqvarna/Viking (VP3 format). |
| `work/<name>_posterized.png` | Flat-color preview of the posterization (compare against the original). |
| `work/regions.json` (via `analyze.py`) | Color/region statistics for debugging separation. |

---

## Quick start

```bash
# one-shot: image → svg + vp3
tools/digitize/run.sh path/to/image.webp

# common options (trim + satin outlines are on by default)
tools/digitize/run.sh --border-mm 2.5 path/to/patch.webp
tools/digitize/run.sh --density 0.35 --colors 8 path/to/image.webp
```

Output lands in `work/` alongside the repo.

---

## Setup (one-time)

The repo is wired for a Linux environment with **no `sudo`/`apt`**. Reproduce with:

```bash
# Python 3.13 venv (Python 3.11+ works; 3.13 is what's here)
python3 -m venv .venv

# Ink/Stitch runtime deps (wxPython/PyGObject are NOT needed headless)
.venv/bin/python -m pip install --no-deps "inkex==1.4.1"
.venv/bin/python -m pip install pystitch "lxml<6" cssselect "numpy==2.2.6" pyparsing \
  tinycss2 packaging pillow pySerial webencodings networkx "shapely>=2.0.0" platformdirs \
  "jinja2>2.9" requests colormath2 "flask>=2.2.0" fonttools "trimesh>=3.15.2" diskcache \
  flask-cors scipy scikit-image

# Ink/Stitch source (already cloned here; re-clone on a fresh machine)
git clone --recurse-submodules https://github.com/inkstitch/inkstitch
```

`tools/wxstub/` is a synthetic wx shim that lets Ink/Stitch run headless; it's
put on `PYTHONPATH` automatically by `run.sh` and `vectorize.py` usage below.

> `inkex` must be installed with `--no-deps` to skip its `PyGObject` requirement
> (which needs a C compiler and is only used for the Inkscape GUI).

---

## Command-line options

| Flag | Default | Meaning |
|---|---|---|
| `--colors N` | `5` | Number of posterized thread colors (k-means). Raise for more shading detail, lower for cleaner/bolder patches. |
| `--border-mm W` | `2.5` | Satin border width (mm). Only applies to transparent-background images. |
| `--no-border` | off | Don't add the satin border. |
| `--density MM` | `0.4` | Default fill row spacing (mm). Keep in `0.3–0.6`; below breaks needles, above leaves gaps. |
| `--no-satin-outlines` | off | Keep the darkest colour entirely as fill instead of turning thin linework into satin. |
| `--satin-max-mm W` | `2.5` | Regions of the outline colour thicker than this stay fills (not outlines). |
| `--no-trim` | off | Trimming is **on by default**; this disables it. |
| `--trim-mm N` | `4.0` | Cut a jump longer than this (mm); `0` = cut every long/exposed jump. Jumps under 2 mm are always skipped. |
| (positional) input | — | Path to the source image (`.webp`/`.png`/`.jpg`). |
| (positional) output | `work/design.svg` | Output SVG path. |

`run.sh` forwards any `--*` flag to `vectorize.py`, e.g.:

```bash
tools/digitize/run.sh --colors 8 --trim --border-mm 3 Patch.png
```

To run `vectorize.py` directly and skip the export:

```bash
.venv/bin/python tools/digitize/vectorize.py [flags] input.webp work/out.svg
```

To render a machine file to a colour stitch-plan preview:

```bash
.venv/bin/python tools/digitize/preview.py work/out.vp3 work/out_plan.png
```

---

## Tunable constants

These live at the top of `tools/digitize/vectorize.py` and are not CLI flags
(edit and re-run):

| Constant | Default | Meaning |
|---|---|---|
| `SIZE_MM` | `100` | Longest side of the finished design (mm). |
| `ROW_SPACING_MM` | `0.4` | Fill line spacing (density). `0.35–0.45` is the safe band for 40 wt thread: `<0.3` packs the needle and breaks it, `>0.6` leaves the fabric showing through. A warning is printed outside `0.3–0.6`. |
| `SATIN_MIN_MM` | `0.6` | Thinner outline runs are widened to at least this (Ink/Stitch ignores satin below ~0.3 mm and recommends ≥1 mm). |
| `SATIN_MAX_MM` | `2.5` | Outline-colour runs thicker than this stay fills, not satin. |
| `SATIN_MIN_LEN_MM` | `2.0` | Drop outline runs shorter than this (removes specks/micro-segments). |
| `SATIN_PULL_MM` | `0.2` | Satin pull compensation per side (closes the gap where satin meets its neighbours). |
| `TRIM_MIN_MM` | `2.0` | Jumps shorter than this are never cut, even with `--trim-mm 0`. |
| `MIN_COMP_MM2` | `0.8` | Drop filled components smaller than this (mm²). Anything sub-mm can't be stitched cleanly. |
| `MIN_HOLE_MM2` | `0.2` | Fill in holes smaller than this (removes unstitchable specks). |
| `OPEN_RADIUS` / `CLOSE_RADIUS` | `1` / `2` | Morphological cleanup (px) to remove specks/spurs and close tiny gaps. |
| `TOLERANCE_MM` | `0.15` | Polygon simplification tolerance (mm) — smaller = smoother curves, bigger = fewer points. |

---

## How it works

1. **Classify the image**:
   - *Transparent background* → patch: uses the alpha channel as the silhouette,
     detects the dark outer ring as the **satin border**, and fills the interior.
   - *Opaque* → flat art: drops the lightest cluster (paper) and treats the
     darkest cluster as **outlines** on its own top layer.
2. **Denoise + posterize**: median filter, then k-means to `--colors` flat colors.
3. **Vectorize**: each color becomes closed `fill` regions with holes preserved
   (`fill-rule="evenodd"`); sub-mm components/holes are dropped.
4. **Outlines → satin**: the darkest colour's *thin* regions (thinner than
   `--satin-max-mm`) are skeletonized into centerlines and emitted as simple
   satin columns whose width follows the local line thickness; its solid regions
   stay fills.
5. **Order for travel**: the needle position is carried across colour layers and
   components (nearest-neighbour), so the sequence is globally short, not just
   short within one colour.
6. **Trim**: a jump is cut when it is longer than `--trim-mm` **or** when it is
   not hidden under a later-stitched layer (an exposed jump thread).
7. **Emit Ink/Stitch SVG** with per-object params: `row_spacing_mm` (density),
   `trim_after`, and `satin_column` for outlines and border.
8. **Export** via Ink/Stitch headless CLI to `.vp3`.

Stitch order: fills (bottom, light→dark) → satin outlines → satin border (top).

---

## Notes & known caveats

- **Outlines are auto-converted to satin** (skeleton centerline + local width) for
  the darkest colour: each skeleton run is classified by its own thickness, so
  thin lines become satin and solid areas stay fills. If a design's outlines are
  not the darkest colour, edit the `order`/`skip_colors` YAML, or disable with
  `--no-satin-outlines`.
- **Pull-compensation and underlay-inset are intentionally omitted for fills** —
  they made the export hang (>20 min) via shapely buffering on the many-holed
  polygons. Satin elements do get a small pull compensation (0.2 mm).
- **Trimming is on by default** and cuts long *and* exposed jumps (thread not
  covered by a later layer). Jumps under 2 mm are never cut. It adds tie-off/tie-in
  lock stitches (a few % more stitches) but eliminates visible jump thread.
  Use `--no-trim` to disable.
- **Density**: `0.4 mm` default; the script warns outside `0.3–0.6 mm`. Per-colour
  overrides go in the YAML `density:` map.
- **Export time** scales with design complexity (a few minutes for large patches);
  it's a CPU-bound, single-threaded conversion.
- Machine format is **VP3** by default. Ink/Stitch can output `.dst`, `.pes`,
  `.jef`, etc. — change `--format-vp3=True` in `tools/digitize/run.sh`.
