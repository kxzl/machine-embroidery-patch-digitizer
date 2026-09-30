# Digitize Patches — raster image → embroidery

Turn a raster image (WebP/PNG/JPG) into a pre-digitized embroidery **SVG** for
[Ink/Stitch](https://inkstitch.org) and export a machine-ready **VP3** file
(Husqvarna/Viking), fully headless (no Inkscape GUI needed).

```
image → color separation → vectorize (fills + satin border) → SVG → Ink/Stitch → .vp3
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

# common options
tools/digitize/run.sh --trim --border-mm 2.5 path/to/patch.webp
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
| `--trim` | off | Add a **TRIM** command after every object → machine auto-cuts between elements instead of leaving jump stitches. |
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

---

## Tunable constants

These live at the top of `tools/digitize/vectorize.py` and are not CLI flags
(edit and re-run):

| Constant | Default | Meaning |
|---|---|---|
| `SIZE_MM` | `100` | Longest side of the finished design (mm). |
| `ROW_SPACING_MM` | `0.5` | Fill line spacing (density). Higher = lighter/softer. Guideline: 0.4 mm standard, raise to 0.5–0.6 mm for large/layered designs to avoid fabric ripping. |
| `LINEWORK_ROW_SPACING_MM` | `0.6` | Density of the linework stand-in fill (opaque engraving images only). Treated lighter because thin linework re-traced to satin later. |
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
     darkest cluster as **linework** on its own top layer.
2. **Denoise + posterize**: median filter, then k-means to `--colors` flat colors.
3. **Vectorize**: each color becomes closed `fill` regions with holes preserved
   (`fill-rule="evenodd"`); sub-mm components/holes are dropped.
4. **Emit Ink/Stitch SVG** with per-object params: `row_spacing_mm` (density),
   `trim_after` (if `--trim`), and `satin_column` for the border.
5. **Export** via Ink/Stitch headless CLI to `.vp3`.

Stitch order: fills (bottom) → linework (middle, opaque images) → satin border (top).

---

## Notes & known caveats

- **Linework (engraving-type images) is auto-filled, not satin.** Converting that
  connected linework to proper satin/centerlines is a manual step (Inkscape +
  Ink/Stitch stroke→satin) you can do after reviewing the SVG.
- **Pull-compensation and underlay-inset are intentionally omitted** — they made
  the export hang (>20 min) via shapely buffering on the many-holed polygons.
  Add them per-object in Inkscape if you need them.
- **`--trim` trims after every object**, which is the simplest behavior. It adds
  tie-off/tie-in lock stitches (a few % more stitches) but eliminates thread drag.
- **Export time** scales with design complexity (a few minutes for large patches);
  it's a CPU-bound, single-threaded conversion.
- Machine format is **VP3** by default. Ink/Stitch can output `.dst`, `.pes`,
  `.jef`, etc. — change `--format-vp3=True` in `tools/digitize/run.sh`.
