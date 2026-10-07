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
# Python 3.13 venv (the tested version; `numpy==2.2.6` below is pinned)
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
put on `PYTHONPATH` automatically by `run.sh` for the Ink/Stitch export step.
`vectorize.py` imports no `wx` and does not need it.

> `inkex` must be installed with `--no-deps` to skip its `PyGObject` requirement
> (which needs a C compiler and is only used for the Inkscape GUI).

---

## Command-line options

| Flag | Default | Meaning |
|---|---|---|
| `--colors N` | `5` | Number of posterized thread colors (k-means). Raise for more shading detail, lower for cleaner/bolder patches. |
| `--border-mm W` | `2.5` | Satin border width (mm). Only applies to transparent-background images. |
| `--no-border` | off | Don't add the satin border. |
| `--density MM` | `0.4` raster / `0.3` SVG | Default fill row spacing (mm). Keep in `0.3–0.6`; below breaks needles, above leaves gaps. The SVG path defaults to `0.3` because `0.4` left the base fabric visible on the Scavenger's Daughter test. **An explicit density (CLI or YAML) overrides the `row_spacing_mm` authored on the artwork** — the Scavenger's paths ship `0.4`, which otherwise silently wins and reopens the gaps. |
| `--no-satin-outlines` | off | Keep the darkest colour entirely as fill instead of turning thin linework into satin. |
| `--satin-max-mm W` | `2.5` | Regions of the outline colour thicker than this stay fills (not outlines). |
| `--size-mm N` | `100` | Longest side of the finished design (mm). Scales the design's own bounds (alpha silhouette for transparent art, non-background bbox for opaque art), not the image canvas. |
| `--overlap-mm N` | `1.0` | SVG inputs: a later colour may overlap an earlier one by at most this much — under-colours are carved out from beneath later colours (a later colour can still cover an earlier one by up to `2 x N` where the later shape is thin). After the carve, fragments fully hidden under a later colour are dropped entirely (they were bare stubs that each cost underlay + tie stitches). `0` disables the carve. |
| `--seam-pull-mm MM` | `0.2` | SVG inputs: thread is laid *centred* on its path, so a fill's **stitched** edge finishes half a thread width outside the drawn edge and eats the earlier colour's detail there (measured on the Scavenger's Daughter artwork: 19 % of the visible green). Pull every later colour back by this much along the colour edges so its stitched edge lands on the drawn edge. Only where a later colour abuts an earlier one — the outer silhouette and white highlights are untouched. `0` disables it. |
| `--fill-angle DEG` | authored | SVG inputs: force this fill angle on every fill. Overrides the artist's per-path `inkstitch:angle`. |
| `--satinize-colors HEX[,HEX]` | — | SVG inputs: turn the named colours' thin/elongated fills into satin columns (see `satinize` below). |
| `--key-background` | off | `run.sh` only: key a flat background to alpha before digitizing (colour auto-detected from the corners). Use it for patches with a drawn border or a dark background — the transparent-patch path then detects the dark ring as the satin border. |
| `--no-trim` | off | Trimming is **on by default**; this disables it. |
| `--trim` | on | Explicitly enable trimming (already the default; also overrides `trim.enabled: false` in a YAML config). |
| `--trim-mm N` | `4.0` | Cut a jump longer than this (mm); `0` = cut every long/exposed jump. Jumps under 2 mm are always skipped. |
| `--config F` | — | Per-image YAML config (`order`, `skip_colors`, `density`, `border`, `trim`). CLI flags win over its values. Generate a starter with `tools/digitize/make_config.py <image>`. |
| `--no-export` | off | `run.sh` only: stop after writing the SVG, skip the Ink/Stitch VP3 export. Not forwarded to `vectorize.py`. |
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
# zoom into the top-left 80x60 mm of the design
.venv/bin/python tools/digitize/preview.py work/out.vp3 work/detail.png --crop 0,0,80,60 --line-width 2
# render stitches at their real 0.4 mm thread width (satin bands look solid)
.venv/bin/python tools/digitize/preview.py work/out.vp3 work/plan.png --width 1600 --thread-mm 0.4
```

`--crop X0,Y0,X1,Y1` is in mm from the design's top-left corner, so the
operator can inspect coverage and hotspots close up.

`--thread-mm 0.4` draws every stitch at the width the needle actually lays
down. Without it the preview uses 1 px hairlines: a satin band whose threads
touch each other then reads as a dashed/broken line when zoomed in, which is a
rendering artefact, not a coverage gap. `run.sh` writes **two** previews:
`<name>_stitchplan.png` (1600 px, hairlines — individual stitches visible, use
this to judge stitch layout and alignment) and `<name>_coverage.png` (1600 px,
`--thread-mm 0.5`, the 40 wt thread's flattened width — use this to judge
whether the fabric will show through).

---

## Native SVG inputs (`tools/digitize/svg_digitize.py`)

When the input is an `.svg` with authored flat fills, `run.sh` dispatches to the
native path instead of the raster one. Its extra behaviour:

- **Authored satins are kept.** A path tagged `inkstitch:satin_column` with two
  or more subpaths is emitted as a rail-based satin (the artist's `Outline`
  layer on the Scavenger's Daughter is exactly this). If such a satin spans the
  whole silhouette it is used as the **border** instead of a synthetic one, and
  the fills keep their full footprint beneath it — that is what stops the base
  fabric showing at the border. A single-subpath satin narrower than Ink/Stitch's
  1 mm gate is widened to 1.5 mm rather than dropped.
- **Density 0.3 mm default** (see above), `--fill-angle` and YAML `angle` /
  `angle_cycle` for fill-direction depth.
- **Hotspot control:** fills thinner than 1 mm or smaller than 2.5 mm² get no
  underlay and no tie stitches (`ties="3"`); fully hidden under-colour fragments
  are dropped after the overlap carve.
- **Colour seam.** Thread is laid centred on its path, so a later colour's
  *stitched* edge finishes ~half a thread width outside the geometry the artist
  drew and covers that much of the earlier colour. `--seam-pull-mm` (default
  `0.2`, half of a 40 wt round thread) pulls each later colour back along the
  colour edges so the stitched edge lands on the drawn edge; the under-colour
  keeps `overlap - seam_pull` = 0.8 mm of underlap beneath it, so the seam still
  cannot open. Only the colour edges move: the outer silhouette and the
  artwork's white highlights are stitched to their drawn size.
- **`satinize`** (YAML or `--satinize-colors`) converts thin/elongated fills of
  the listed colours into satin columns — the green centipede case. One satin
  column per skeleton run, up to 3 parallel columns across wide sections; a
  component is only converted when the columns cover it and do not spill far
  outside it.

```yaml
# work/scavenger.yaml
density: 0.3
seam_pull_mm: 0.2      # pull a later colour back off a colour edge (see above)
satinize:
  colors: ["#87f70f"]
  max_row_mm: 4.5    # widest single satin column
  max_rows: 3        # 1-3 columns per section
  min_coverage: 0.9  # below this the component stays a fill
  max_overhang: 0.45
angle_cycle:         # optional: cycle fill angles per component for depth
  "#030503": [-30, 15, -45, 30]
border:
  mode: auto         # use an authored rail satin when present
trim:
  enabled: true
  threshold_mm: 4.0
```

---

## Tunable constants

These live at the top of `tools/digitize/vectorize.py` and are not CLI flags
(edit and re-run):

| Constant | Default | Meaning |
|---|---|---|
| `SIZE_MM` | `100` | Longest side of the finished design (mm). |
| `ROW_SPACING_MM` | `0.4` | Fill line spacing (density). `0.35–0.45` is the safe band for 40 wt thread: `<0.3` packs the needle and breaks it, `>0.6` leaves the fabric showing through. A warning is printed outside `0.3–0.6`. |
| `SATIN_MIN_MM` | `1.2` | Thinner outline runs are widened to at least this. Must stay above Ink/Stitch's 1.0 mm satin gate (`min_satin_stroke_width_mm` in `inkstitch/lib/utils/settings.py`): a satin narrower than that is silently stitched as running stitch. |
| `SATIN_MAX_MM` | `2.5` | Outline-colour runs thicker than this stay fills, not satin. |
| `SATIN_MIN_LEN_MM` | `2.0` | Drop outline runs shorter than this (removes specks/micro-segments). |
| `SATIN_PULL_MM` | `0.2` | Satin pull compensation per side (closes the gap where satin meets its neighbours). |
| `TRIM_MIN_MM` | `2.0` | Jumps shorter than this are never cut, even with `--trim-mm 0`. |
| `MIN_COMP_MM2` | `0.8` | Drop filled components smaller than this (mm²). Anything sub-mm can't be stitched cleanly. |
| `MIN_HOLE_MM2` | `0.2` | Fill in holes smaller than this (removes unstitchable specks). |
| `OPEN_RADIUS` / `CLOSE_RADIUS` | `1` / `2` | Morphological cleanup (px) to remove specks/spurs and close tiny gaps. |
| `TOLERANCE_MM` | `0.25` | Polygon simplification tolerance (mm) — smaller = smoother curves, bigger = fewer points. `0.25` measured ~1.5× faster export than `0.15` with ~0.8% fewer stitches and no visible difference (see `docs/adr/0002-export-performance.md`). |

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
5. **Order for travel**: layer order is fixed (light→dark); within each layer
   components are swept nearest-neighbour, starting from where the previous
   layer left the needle.
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
  overrides go in the YAML `density:` map. A density given on the command line or
  in the YAML *overrides* the `row_spacing_mm` authored on the artwork; with no
  density flag the artwork's value wins.
- **Export time** scales with design complexity (a few minutes for large patches);
  it's a CPU-bound, single-threaded conversion.
- Machine format is **VP3** by default. Ink/Stitch can output `.dst`, `.pes`,
  `.jef`, etc. — change `--format-vp3=True` in `tools/digitize/run.sh`.
