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

## Guided mode

For people who do not want to learn flags. You answer a few questions and get an SVG and a VP3.

```bash
python3 digitize.py setup     # once: needs uv (https://docs.astral.sh/uv/), takes a few minutes
python3 digitize.py doctor    # optional: checks that everything is ready
python3 digitize.py           # start the wizard
```

Tested on Linux. macOS should work but has not been tried. On Windows use WSL2.
The wizard needs a real terminal.
If it finds none it prints the matching `run.sh` command and stops (exit code 2).

The steps, one question per screen:

1. **Which picture?** Drag the file into the window or type its path. png, jpg, jpeg and webp.
2. **Picture check.** Plain advice, nothing blocks you. It tells you whether the background is
   transparent (best), plain (the wizard offers to remove it first) or busy (the whole picture
   gets stitched). It also says how many pixels per mm the picture gives. Below 3 pixels per mm
   the edges come out rough and fine detail is lost; the advice names how many pixels wide the
   artwork should be.
3. **Hoop.** 120 x 120 mm (most patches), 260 x 200 mm (large back patch) or a custom size from
   20 to 400 mm per side. The stitching never goes outside this area.
4. **Patch size.** The longest side of the patch: 100 mm by default, the whole hoop, or a custom
   size. The picture is never rotated. If turning it 90 degrees would allow a bigger patch, the
   wizard says so.
5. **Colours.** Let the program decide (up to 6), fewer (up to 4: fewer thread changes, simpler
   look) or more (up to 8: more detail, more thread changes).
6. **Your choices.** One summary, then it runs. It takes about a minute.
7. **Results.** Stitched size in mm, stitch count, colour changes, the thread colours in sewing
   order, the files and any warnings. The same text is saved as `summary.txt`.

The stitched file comes out a little bigger than the design the size flags measure (0.3 to 0.5 mm
on plain shapes, about 3 mm when the artwork touches the picture edge). The wizard therefore
measures the VP3 itself. If it is over the hoop area it runs once more with a smaller Fit box. If it
is still over, the summary says **TOO BIG FOR THE HOOP**, the exit code is 1, and you should not sew
the file. It also warns when the design ends within 2 mm of the hoop area edge.

The results list every warning in plain words. Many lines too narrow for a satin stitch are grouped
into one line that gives the count and the narrowest width. If the program left out very short pieces
of the outline, one line says how many. And when the artwork touches the edge of the picture, it says
that the satin border is then stitched about 2.5 mm outside the size you chose, so the patch comes out
bigger than asked: leave a little empty space around the artwork for an exact size.

Files go to `output/<name>/`, where `<name>` is the picture's file name with unusual characters
replaced by `-` (`Scavenger's Daughter.png` becomes `Scavenger-s-Daughter`). If that folder exists,
the wizard asks: keep both (the new one gets `-2`, `-3`), replace, or cancel. Nothing is replaced
without asking. The work happens in a hidden temporary folder inside `output/` and moves into
place only when the run succeeded, so Ctrl-C or an error leaves no half-written folder.

Not in guided mode: SVG input, other machine formats, automatic rotation, re-run files. Use
`tools/digitize/run.sh` for those (see below).

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
| `--colors N` | `5` | Upper bound on the number of thread colors for the automatic palette. Raise for more shading detail, lower for cleaner/bolder patches. Ignored (with a note) when a palette is pinned. |
| `--palette HEX[,HEX...]` | — | Pin the thread colours, e.g. `--palette "#1A1A1A,#B5651D"`. Every pixel is assigned to the nearest pinned hex in CIELAB and the pinned hexes are emitted verbatim; no clustering or centroid merge runs. Pinned colours with zero pixels are dropped (with a note). CLI wins over YAML `palette:`. |
| `--palette-mode auto\|kmeans` | `auto` | Palette used when nothing is pinned: `auto` is the S3 Lab palette (over-cluster, protected merge, anti-alias blend absorption); `kmeans` restores the legacy RGB k-means exactly. |
| `--border-mm W` | `2.5` | Satin border width (mm). Only applies to transparent-background images. Parts too small/thin for it get a running-stitch edge in the border colour (see Border behaviour). |
| `--no-border` | off | Don't add the satin border. |
| `--density MM` | `0.4` raster / `0.3` SVG | Default fill row spacing (mm). Keep in `0.3–0.6`; below breaks needles, above leaves gaps. The SVG path defaults to `0.3` because `0.4` left the base fabric visible on the Scavenger's Daughter test. **An explicit density (CLI or YAML) overrides the `row_spacing_mm` authored on the artwork** — the Scavenger's paths ship `0.4`, which otherwise silently wins and reopens the gaps. |
| `--no-satin-outlines` | off | Keep the darkest colour entirely as fill instead of turning thin linework into satin. |
| `--no-satin-extend` | off | Outline satin ends are extended by half the local line width where they meet another line (and 0.3 mm at free ends) so junctions close; this flag restores square ends at the junction pixel. |
| `--satin-max-mm W` | `2.5` | Regions of the outline colour thicker than this stay fills (not outlines). |
| `--underlap-mm N` | `0.6` | Grow every fill up to N mm under the layers stitched after it (later fills, satin outlines, satin border), clipped to the silhouette. Closes the colour seams and the fill/border gap that fabric pull opens. `0` disables and reproduces the pre-underlap output byte-for-byte. |
| `--raster-pull-mm N` | `0` | Stretch each fill N mm along its stitch-row angle (`--fill-angle` / YAML `angle` / 0), clipped to the silhouette **grown** by N, so overshooting the outer edge by N is intended. Compensates the pull that narrows a fill along its rows; this is the fast replacement for Ink/Stitch's own `pull_compensation_mm` on fills (see the caveat below). `0` disables; the vadmel profile sets `0.25`. |
| `--profile NAME` | none | Select a named fabric profile (`vadmel`). Sets density, underlap, raster pull and underlay unless each is overridden by an explicit CLI flag or YAML key. See **Fabric profiles**. |
| `--no-skip-last` | off | Fill underlay stitches every row instead of skipping the last one (drops `inkstitch:fill_underlay_skip_last`). YAML `fill_underlay_skip_last: false` / `no_skip_last: true` are equivalent; the vadmel profile sets it. |
| `--size-mm N` | `100` | Longest side of the finished design (mm). Scales the design's own bounds (alpha silhouette for transparent art, non-background bbox for opaque art), not the image canvas. |
| `--fit-mm WxH` | off | Fit box in mm, for example `--fit-mm 120x120` (`x` or `X`; two positive numbers, otherwise exit code 2). Scales the design to fill the box on the side that reaches it first. It is never rotated. Like `--size-mm` it measures the design's own bounds, not the stitched result: the stitching runs about 0.4 mm over the box (satin pull compensation), and up to about 3 mm over when the artwork touches the image edge (the border is then centred on the edge). Pad such images with transparent pixels. With `--size-mm` as well, the smaller result wins and a note names the flag that limited the size. With neither flag the default 100 mm longest side applies. |
| `--overlap-mm N` | `1.0` | SVG inputs: a later colour may overlap an earlier one by at most this much — under-colours are carved out from beneath later colours (a later colour can still cover an earlier one by up to `2 x N` where the later shape is thin). After the carve, fragments fully hidden under a later colour are dropped entirely (they were bare stubs that each cost underlay + tie stitches). `0` disables the carve. |
| `--seam-pull-mm MM` | `0.2` | SVG inputs: thread is laid *centred* on its path, so a fill's **stitched** edge finishes half a thread width outside the drawn edge and eats the earlier colour's detail there (measured on the Scavenger's Daughter artwork: 19 % of the visible green). Pull every later colour back by this much along the colour edges so its stitched edge lands on the drawn edge. Only where a later colour abuts an earlier one — the outer silhouette and white highlights are untouched. `0` disables it. |
| `--fill-angle DEG` | authored | SVG inputs: force this fill angle on every fill. Overrides the artist's per-path `inkstitch:angle`. |
| `--satinize-colors HEX[,HEX]` | — | SVG inputs: turn the named colours' thin/elongated fills into satin columns (see `satinize` below). |
| `--key-background` | off | `run.sh` only: key a flat background to alpha before digitizing (colour auto-detected from the corners). Use it for patches with a drawn border or a dark background — the transparent-patch path then detects the dark ring as the satin border. |
| `--background HEX` | config `fabric_color:` / `#ffffff` | `run.sh` only: canvas colour for the two previews, so white thread on white (or black on black) stays visible. `run.sh` reads `fabric_color:` from `--config` when the flag is absent. Not forwarded to `vectorize.py`. |
| `--no-trim` | off | Trimming is **on by default**; this disables it. |
| `--trim` | on | Explicitly enable trimming (already the default; also overrides `trim.enabled: false` in a YAML config). |
| `--trim-mm N` | `4.0` | Cut a jump longer than this (mm); `0` = cut every long/exposed jump. A jump is skipped only when both its nearest-boundary distance and its worst one-sided travel are under the threshold; jumps under 2 mm are always skipped. The last object of every layer is trimmed when the next object is farther than 2 mm. |
| `--config F` | none | Per-image YAML config (`order`, `skip_colors`, `density`, `angle`, `border`, `trim`, `palette`, `palette_mode`, `profile`, `underlap_mm`, `raster_pull_mm`, `fill_underlay_skip_last`, `fill_underlay_double`, `satin_underlay`, `border_zigzag_spacing_mm`, `fabric_color`, `cleanup`, `threads`). CLI flags win over its values. Generate a starter with `tools/digitize/make_config.py <image>`, which also parses the `**Palette:**` line from `patch_descriptions/prompts/<name>.md` into `palette:` when one exists. |
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
whether the fabric will show through). Both are drawn on the `--background`
colour.

---

## Fabric profiles

A profile bundles the fill/satin settings that differ by fabric. `--profile NAME`
(CLI) or `profile: NAME` (YAML) selects one. Precedence is **CLI flag > explicit
YAML key > profile > built-in default**, so a profile is a starting point you can
still override key by key.

| Profile | Fabric | What it changes |
|---|---|---|
| `vadmel` | black felted wool (65 % wool / 25 % nylon / 10 % polyester) on stiff stabiliser | density `0.35`; underlap `0.6`; raster pull `0.25`; keeps every fill-underlay row (`fill_underlay_skip_last` off); a perpendicular double underlay (`fill_underlay_angle="<a+90> <a>"`) on fills whose CIELAB **L\* > 70** (light thread on dark fabric); centre-walk + contour underlay on the outline and border satins (`contour_underlay_inset_mm 0.4`); border `zigzag_spacing_mm 0.35`; preview `fabric_color` `#101010`. |

`vectorize.py` prints the resolved profile values to stdout. The profile's
`fabric_color` is only a default: set `fabric_color:` explicitly in YAML to
override it. `run.sh` resolves `profile: vadmel` in the YAML config → `#101010`
for the preview canvas when the config has no `fabric_color`, so the
profile-implied dark background reaches `preview.py`. A profile selected only with
`--profile` on the command line does not change the preview canvas: put
`profile:` in the YAML, or pass `--background` explicitly.

The vadmel numbers come from `work/review_artifacts/RESEARCH_vadmel.md`; the
fabric-specific ones are extrapolated, so calibrate with `tools/digitize/swatch.py`
before trusting them.

```yaml
# work/example.yaml
profile: vadmel
palette: ["#1A1A1A", "#B5651D"]
border:
  mode: force_black
```

```bash
# CLI wins over the profile: density 0.4 instead of vadmel's 0.35
tools/digitize/run.sh --profile vadmel --density 0.4 --config work/example.yaml image.png
```

### Border behaviour (`border:` YAML / `--border-mm`)

- **Colour.** `mode: force_black` uses the darkest palette thread when its CIELAB
  L\* < 25, else `#000000`, so the satin border shares that thread's colour block
  instead of adding an extra colour change. `mode: auto` samples the outer ring
  and snaps to the nearest palette thread within 40 RGB units.
- **Small/thin parts.** A part too small or too thin to carry the full border
  width gets a running-stitch outline (`bean_stitch_repeats=1`) along its own
  edge in the border colour. The run prints the count.
- **Satin params.** The border satin carries `short_stitch_inset="20"` and
  `max_stitch_length_mm="7"`, which inset the crossed stitches and split the long
  cross-stitches where the border fans at a tight tip (a horn/claw point) instead
  of leaving a long bar of thread.
- **Circle ring.** `mode: circle` fits a circle to the patch's outer edge (rays
  that break out, such as horns or a beard, stay out of the fit) and stitches a
  satin ring `thickness_mm` wide whose outer edge is that circle. Everything the
  art draws in the ring band or outside the circle is removed (its own thin rim,
  edge chips), except shapes that cross the circle: those are found by angle and
  kept. Keys:
  - `color: '#rrggbb'`: the ring's source colour (mapped through `threads:`).
    Default: the darkest stitched colour.
  - `order: first` sews the ring as one closed satin before the fills, so the
    crossing shapes lie on top of it. `order: last` (default) sews it on top and,
    with `gaps: true` (default), stops it 1 mm short of each crossing shape, so
    it is cut into arcs with a trim between them.
  - `underlay: true` adds centre-walk and contour underlay to the ring (wide
    rings want it).

---

## QA tools (`tools/digitize/qa/`)

Instruments for measuring a raster-path SVG/VP3 instead of eyeballing it. All
are repo-relative, take `--help`, and are what the regression gate below runs.
Full definitions and known artefacts are in their module docstrings.

| Script | Measures | Known artefact / use |
|---|---|---|
| `qa/pullsim.py <design.svg> <keyed.png>` | Simulates fabric pull: erodes each fill along its stitch angle by 0.25 mm/side (minus its own pull comp) and draws satins 0.15 mm narrower/side; reports silhouette pixels with no thread, and gaps ≥ 0.1/0.5 mm². | The only metric that reproduces the colour-seam defect. Thin-rectangle even-odd artefact ≈ 0.1–0.2 % floor; judge by gaps ≥ 0.5 mm². |
| `qa/coverage.py <vp3> <keyed.png> <size_mm>` | Stitched coverage of the silhouette from the VP3 (bbox-centre aligned, closes sub-0.3 mm row pinstripes). | Reports ~0 % for everything at pull 0 — use it only as a "nothing is grossly missing" gate. |
| `qa/travelmap.py <vp3> <out.png>` | Draws trimmed travel (cyan) and untrimmed moves > 5 mm (red); prints **exposed travel** = red moves that are not satin cross-stitches. | Red satin fans at tips are legitimate; exposed travel is the number that must be 0. `--red-mm` lowers the threshold. |
| `qa/export.sh <svg>` | Ink/Stitch export + stats (stitches, trims, colour changes, thread m, untrimmed > 8 mm) + both previews. | Writes next to the SVG. |
| `qa/regress.sh <outdir> [--vectorize PATH]` | Runs the three reference designs (book burner, goat, earth) end to end and prints one markdown table row each: stitches, colour blocks, trims, export s, pullsim uncovered %, pullsim gaps ≥ 0.5 mm², exposed travel > 3 mm, palette. | `--vectorize` points at a baseline copy; `REGRESS_EXTRA` appends flags to every vectorize call. |

```bash
# quick seam check on one design
.venv/bin/python tools/digitize/qa/pullsim.py /tmp/q/bb.svg work/bb_keyed.png --out /tmp/q/bb_pull.png

# full regression gate
tools/digitize/qa/regress.sh /tmp/q
```

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
| `TRIM_MIN_MM` | `2.0` | Jumps shorter than this are never cut, even with `--trim-mm 0`. A jump is skipped only when both its nearest-boundary distance and its worst one-sided travel are under their thresholds. |
| `MIN_COMP_MM2` | `0.8` | Drop filled components smaller than this (mm²). Anything sub-mm can't be stitched cleanly. |
| `MIN_HOLE_MM2` | `0.2` | Fill in holes smaller than this (removes unstitchable specks). |
| `OPEN_RADIUS` / `CLOSE_RADIUS` | `1` / `2` | Morphological cleanup (px) to remove specks/spurs and close tiny gaps. |
| `TOLERANCE_MM` | `0.25` | Polygon simplification tolerance (mm) — smaller = smoother curves, bigger = fewer points. `0.25` measured ~1.5× faster export than `0.15` with ~0.8% fewer stitches and no visible difference (see `docs/adr/0002-export-performance.md`). |

---

## How it works

1. **Classify the image**:
   - *Transparent background* → patch: uses the alpha channel as the silhouette,
     detects the dark outer ring as the **satin border**, and fills the interior.
     A part too small or too thin for the full border gets a running-stitch
     edge (see Border behaviour).
   - *Opaque* → flat art: drops the lightest cluster (paper) and treats the
     darkest cluster as **outlines** on its own top layer.
2. **Denoise + palette**: median filter, then either assign every pixel to
   the pinned `palette:` hexes in CIELAB, or derive an automatic palette
   (S3 Lab over-cluster + protected merge by default; `--palette-mode kmeans`
   for the legacy RGB k-means). `--colors` bounds the automatic palette.
3. **Vectorize**: each color becomes closed `fill` regions with holes preserved
   (`fill-rule="evenodd"`); sub-mm components/holes are dropped. The cleaned
   masks are then fabric-compensated: **underlap** grows each fill under the
   layers stitched after it (`--underlap-mm`, default on at 0.6 mm), and
   **raster pull** stretches each fill along its row angle (`--raster-pull-mm`).
4. **Outlines → satin**: the darkest colour's *thin* regions (thinner than
   `--satin-max-mm`) are skeletonized into centerlines and emitted as simple
   satin columns whose width follows the local line thickness; its solid regions
   stay fills.
5. **Order for travel**: layer order is fixed (light→dark); within each layer
   components are swept nearest-neighbour, starting from where the previous
   layer left the needle.
6. **Trim**: a jump is cut when it is longer than `--trim-mm` **or** when it is
   not hidden under a later-stitched layer (an exposed jump thread). A jump is
   only skipped when it is short on **both** measures: its nearest-boundary
   distance **and** its worst one-sided travel are under the threshold, so a fill
   whose row end sits close to the next shape but whose row start is far away is
   still cut. The last object of every layer (each colour, the outlines, the
   border) is always trimmed when the next object is farther than 2 mm.
7. **Emit Ink/Stitch SVG** with per-object params: `row_spacing_mm` (density),
   `trim_after`, and `satin_column` for outlines and border. The file carries
   `inkstitch_svg_version` 4 metadata and pins `max_stitch_length_mm="3"` /
   `running_stitch_length_mm="1.5"` on fills, so Ink/Stitch treats it as current
   (no "Unversioned Ink/Stitch SVG file detected" dialog) and stitches the same
   rows the legacy update used to inject.
8. **Export** via Ink/Stitch headless CLI to `.vp3`.

Stitch order: fills (bottom, light→dark) → satin outlines → satin border (top),
with a running-stitch edge in the border colour for parts too small/thin for the
border satin.

---

## Notes & known caveats

- **Outlines are auto-converted to satin** (skeleton centerline + local width) for
  the darkest colour: each skeleton run is classified by its own thickness, so
  thin lines become satin and solid areas stay fills. If a design's outlines are
  not the darkest colour, edit the `order`/`skip_colors` YAML, or disable with
  `--no-satin-outlines`.
- **Fill pull compensation runs in the raster, not through Ink/Stitch.** Ink/Stitch's
  own `inkstitch:pull_compensation_mm` on fills works but rebuilds every fill polygon
  from each tatami row and is slow: measured **136 s** (goat) and **220–271 s**
  (Book Burner) per export, versus 8–20 s without it. The historic note here said it
  "made the export hang (>20 min)"; that is out of date: it is slow, not hung. The
  raster path instead stretches each fill mask along its row angle
  (`--raster-pull-mm`), which measures at the same export time and closes
  the pull gap just as well for tatami rows. Satin elements still get a small pull
  compensation (0.2 mm). Don't set both: they add up.
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

---

## Gradients, thin lines and keying

### Gradients (`gradients:` YAML)

`gradients:` is a YAML key in the config file passed with `--config`. It is a
list, and each entry describes one gradient:

- `name`: a label for the entry.
- `stops`: 2 to 4 hex colours, light to dark. Each stop must be close to a
  palette colour (within 30 delta E) and all stops must differ.
- `min_area_mm2`: default 20. Smaller regions stay flat.
- `min_r2`: default 0.5. The straight-line fit must reach this value.
- `row_spacing_mm`: default 0.3.

A region is a connected area of the stop colours whose original pixels follow one
straight colour ramp. A matching region is written as an Ink/Stitch linear
gradient fill: rows of neighbouring colours interleaved. Regions that do not fit
stay flat.

Each gradient region adds one colour block per stop, so each region costs extra
colour changes. Pin the palette (the `palette:` key) so the stops stay distinct.
Without the key the output is unchanged.

```yaml
gradients:
  - name: flame
    stops: ['#f2b33d', '#e8590c', '#8c1c13']
    min_area_mm2: 60
```

### Thin lines (`thin_lines:` YAML)

`thin_lines: widen|run`, default `widen`.

- `widen`: outline runs thinner than 1.2 mm are widened to a 1.2 mm satin. This
  is the old behaviour.
- `run`: outline runs whose measured width is under 1.0 mm (the satin gate) are
  stitched as a bean-stitch running line along the centre line instead. Wider
  runs stay satin.

Use `run` for detailed AI-made art with hairline outlines: the widened satins
pile up where lines meet.

### Small detail (`cleanup:` YAML)

Every connected island of a colour is its own object, with its own lock stitches
and usually a trim. `cleanup:` merges detail below the art's detail limit into the
nearest colour before anything is traced. Without the key the output is unchanged.

```yaml
cleanup:
  min_width_mm: 1.0          # stitched parts thinner than this join their neighbour
  min_area_mm2: 3.0          # stitched islands smaller than this join their neighbour
  fabric_min_width_mm: 1.2   # skipped colours (fabric showing through), see below
  fabric_min_area_mm2: 1.0
```

The `fabric_*` values apply to `skip_colors`. A fabric spot inside a fill is only a
hole and costs no trim, so it can stay small. A thin fabric line is filled in only
when one stitched colour alone lies next to it: a line that splits one colour into
two islands closes, while a keyline between two different colours or along the
patch edge stays. Midnight Epicure (`patch_descriptions/epicure_green.yaml`):
islands 79 -> 43, trims 45 -> 31, both eyes kept.

### Thread colours (`threads:` YAML)

`threads:` maps a source colour to the thread colour written to the SVG and VP3.
Segmentation, `order`, `skip_colors`, `density` and `angle` keep using the source
hexes. The posterized preview shows the thread colours.

```yaml
threads:
  '#4a4947': '#1f5e2b'
  '#93928e': '#6cbf3f'
```

### Small fills (ADR 0003)

A fill smaller than 2.5 mm² or thinner than 1 mm (largest inscribed circle) is
emitted with `fill_underlay="false"`, as `svg_digitize.py` already does: an underlay
on a speck packs the needle. It also gets `ties="3"` (no lock stitches), but only
when no trim and no colour change touches it. Ink/Stitch adds locks only around a
cut or a long jump, and `ties="3"` would remove those too and leave the cut tail
unlocked. Always on.

### Keep enclosed background (`--keep-enclosed`)

`--keep-enclosed` is a `run.sh` flag and is used together with
`--key-background`. Background keying removes every pixel near the background
colour. A pale colour enclosed by the artwork (an off-white symbol on a black
disc, on a white margin) can be keyed out in part. With `--keep-enclosed` only
background connected to the image edge becomes transparent.

The flag is off by default, because it changes results for designs with pale
interiors (Book Burner, Goat).

### Jam check

`run.sh` prints `== jam check` after each export. The check lives in
`tools/digitize/qa/jam_check.py` and is also usable alone:

```bash
.venv/bin/python tools/digitize/qa/jam_check.py <file.vp3> \
  [--max-points-15 N] [--max-thread-cell-mm X] \
  [--trim-cluster-n N] [--trim-cluster-mm X] [--strict]
```

It reports:

- Needle packing: needle points within 1.5 mm. It warns above 140.
- Thread per 1 mm cell: it warns above 20 mm. A healthy satin is about 10 to
  12 mm.
- Trim clusters: 4 or more cuts within 6 mm.

Each warning lists up to 5 spots in mm from the top-left of the design. Many
trims and many colour changes make the machine stop often.

### Satin precheck

Some outline satins have a rail geometry Ink/Stitch cannot build (a short hook or loop
narrower than the satin). The export then dies with `IndexError: tuple index out of
range` in `flattened_sections` and names no element. `run.sh` now runs
`tools/digitize/qa/satin_precheck.py` before the export: it builds each satin column on
its own, prints `bad satin: ID` for the ones that raise and removes them from the SVG.
Closed outline loops shorter than 10 satin widths are dropped earlier, in `vectorize.py`
(the note says "closed on themselves"). Used alone:

```bash
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
  .venv/bin/python tools/digitize/qa/satin_precheck.py design.svg [--fix design.svg]
```

### Recipe for a machine that jams

```yaml
thin_lines: run
outline_order: endpoint
underlap_mm: 0.3
trim:
  threshold_mm: 12
  min_mm: 3
```

```bash
tools/digitize/run.sh --key-background --keep-enclosed --no-satin-extend --config work/jam.yaml image.webp
```

- `thin_lines: run` stitches hairline outlines as running lines instead of
  widening them to satin, so satins do not pile up where lines meet.
- `outline_order: endpoint` stitches the outline segments in endpoint order and
  reverses a segment when its far end is nearer, so segments that meet at a
  junction follow each other with no jump and no cut. Default `centroid`.
- `trim: min_mm: 3` never cuts a jump of 3 mm or less (Ink/Stitch adds no lock
  stitches below its 3 mm collapse length). Default 2.
- `outline_zigzag_spacing_mm: 0.5` (0.3 to 0.8) sets the zigzag spacing of the outline
  satins; wider means less thread per mm of line. Default: Ink/Stitch's 0.4.
- For bold black lines keep `thin_lines: widen` (the default) and use the rest of this
  recipe: the pile-ups come from the number of cuts and from junctions, not from the
  line width. Use `thin_lines: run` only when you want hairlines kept thin.
- `underlap_mm: 0.3` lowers the underlap so each fill overlaps its neighbours by
  less.
- `trim: threshold_mm: 12` raises the trim threshold to 12 mm, so the machine
  cuts fewer times.
- `--no-satin-extend` keeps satin outline ends square so they cannot pile up at
  junctions.
- `--keep-enclosed` keeps pale interior colours from being keyed out. Use it
  when the art has off-white parts.
- `border: thickness_mm: 1.8` (default 2.5) when the jam check shows a thread-per-cell spike
  far above the others on the border: the 2.5 mm satin folds at a hairpin between two thin
  parts (a spider's leg tips gave 61.8 mm, 25.8 mm at 1.8).
- `skip_colors: ['#101010']` leaves a colour unstitched, for a patch cut from fabric of that
  colour (the goat's black disc on black twill: 18,488 stitches become 10,038).
