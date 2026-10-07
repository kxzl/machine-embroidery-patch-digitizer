# HANDOFF — native SVG input path, 2-colour 260 mm VP3

**Status: planning complete, zero pipeline code written.** Everything below was
decided in a grilling session and verified against the actual files. Do not
re-open the settled decisions — they are settled. Build from them.

---

## 1. The task

Produce a machine-ready VP3 from `input/Scavenger's Daughter Upgrade Patch2.svg`:
**2 thread colours**, sized to fit a **260 × 200 mm** hoop. Output to
`output_inkstitch_svg/` and `output_vp3/`. The operator will sew it on a real
machine, so give them every artifact (SVG, VP3, stitch plan, numbers).

The routine cannot do this today. That's what the work is.

---

## 2. What is already done

| Artifact | State |
|---|---|
| `.gitignore` | **done** — added `input/`, `output_inkstitch_svg/`, `output_vp3/` |
| `GLOSSARY.md` | **done** — 11 terms: Artwork, Canvas, Layer, Thread colour, Cluster, Stitch order, Satin border, Satin gate, Stitch plan, Fit box |
| `docs/adr/0001-native-svg-input-path.md` | **done** — the one decision that met all three ADR gates |
| `tools/digitize/svg_digitize.py` | **NOT STARTED** |
| `run.sh` dispatch + output folders | **NOT STARTED** |
| `learnings_from_embroidery_projects.md` | **NOT STARTED** — research subagent died (see §8) |

`vectorize.py` and `run.sh` are **unmodified** (`git status` shows only `.gitignore`
modified plus the two new untracked paths). Keep `vectorize.py` byte-identical.

---

## 3. Verified environment

```
python:  .venv/bin/python          # py3.13; lxml numpy shapely scipy skimage PIL pystitch yaml
inkstitch export:
  PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
    .venv/bin/python inkstitch/inkstitch.py --extension=zip --format-vp3=True \
    "out.svg" > "out.zip" 2>"out.err"
  # then: unzip namelist()[0] from out.zip -> out.vp3
stitch plan:  .venv/bin/python tools/digitize/preview.py out.vp3 out_plan.png
available but NOT used: rsvg-convert, inkscape, convert/magick
```

`skimage` is **0.26**. In this version `measure.label(mask)` returns **only the
label array**, not `(labels, n)` — the raster path uses `scipy.ndimage.label`,
which does return both. Easy trap when porting code.

---

## 4. Measured facts about the input file

All verified by reading/rasterizing `input/Scavenger's Daughter Upgrade Patch2.svg`.

**Canvas** — `width="260mm" height="200mm" viewBox="0 0 260 200"`, so
**1 SVG user unit = 1 mm exactly**.

**Transform** — `Layer 2` carries `matrix(2.53133 0 0 2.54815 3.30265 -30.5778)`.
**It must be applied**, or every coordinate is wrong.

**Layers** (document order = stitch order):

| Layer | Count | Style |
|---|---|---|
| untitled green | 1 path | `fill:#87f70f` |
| `Black` | 29 paths | `fill:#030503; fill-rule:evenodd` |
| `Outline` | 1 path | `fill:none; stroke:#000000; stroke-width:0.104177` → **0.104 mm** |

**To skip**: `image1` (a `display:none` base64 JPEG tracing reference) and the
`inkstitch_ignore_layer` `<symbol>` in `<defs>` (has `scale(0.25)`).

**Colours** — the opaque artwork is **79% black, 20% green, 0% white**. White is
*transparent* in this file, i.e. no-stitch. So the natural 2-colour palette is
`#87f70f` + `#030503`. (k-means with `--colors 2` happened to pick `#86f50f` +
`#030503`; we pin the authored hexes instead.)

**Sizes** (rasterized 2600×2000, then /10 for mm):

| | extent |
|---|---|
| Artwork **with** `Outline` | 242.7 × 157.3 mm |
| Artwork **without** `Outline` | **239.2 × 153.9 mm** |
| Existing reference VP3 | 242.3 × 157.1 mm, **49,648 stitches** |

Dropping `Outline` costs only 3.5 mm of footprint — the border replaces it.

**Fit** — artwork aspect 239.2/153.9 = 1.554, so fitted into 260 × 200 it becomes
**260 × 167.3 mm** (width-limited).

**Budget** (artwork without Outline): area 12,083 mm², union perimeter 8,896 mm,
410 components. Green 2,598 mm² / 2,347 mm perim / 75 comps. Black 9,484 mm² /
9,242 mm perim / 428 comps. Scaled to 260 mm wide: 14,277 mm² and 10,512 mm
perimeter.

**Estimated output**: fills ~44,600 stitches (0.4 mm spacing, +25% underlay) +
border satin ~4,200 (10,512 mm / 2.5 mm) ≈ **49,000 stitches** — same order as
the 49,648 reference. **Density needs no change.** Treat this as a sanity
band, not a promise; report the real numbers.

---

## 5. Settled decisions

Every row was answered by the operator. Do not re-litigate.

### Dispatch & scope
| Decision | Choice |
|---|---|
| Input path | **Native SVG**, not rasterize-and-retrace |
| Architecture | New `tools/digitize/svg_digitize.py`; `run.sh` picks by extension; `vectorize.py` untouched |
| Elements | `<path>` **only**. Skip `<defs>`, `<symbol>`, `display:none`, non-drawable. Clear error on `rect`/`circle`/`ellipse`/`polygon`/`polyline`/`line` |
| Flattening | **None** — no Inkscape CLI subprocess |
| Transforms | Applied, including the Layer 2 matrix |
| Cleanup | **Only** curve simplification at `TOLERANCE_MM` = 0.15 mm. No `MIN_COMP_MM2` / `MIN_HOLE_MM2` dropping — authored detail is deliberate |
| Fills | **Stayed fills. Never skeletonise.** `--no-satin-outlines` is meaningless on this path |
| Sub-gate strokes | **Always dropped**, border or no border (kills the `Outline` layer). Reason: below Ink/Stitch's 1.0 mm `min_satin_stroke_width_mm` they silently become running stitch |

### Colour & order
| Decision | Choice |
|---|---|
| Thread colours | Distinct fill hexes, automatic. No `--color` flag |
| Stitch order | **SVG document order** |
| `--colors` | Ignored, with a printed note |
| YAML config | Applies to both paths — `skip_colors`, `density`, `border`, `trim`. **`order` is ignored** with a printed note |

### Scale
| Decision | Choice |
|---|---|
| Fit box | `--width-mm 260 --height-mm 200` |
| What it fits | The **Artwork** (union of stitchable geometry), *not* the canvas |
| Aspect | Preserved; here width-limited → 260 × 167.3 mm |
| Default | Unchanged — longest side 100 mm, so existing raster runs are unaffected |

### Satin border
| Decision | Choice |
|---|---|
| Width | `--border-mm`, default 2.5 |
| Colour | `--border-color`, **explicit and required**; must exactly match an authored fill or it's an error. Run uses `--border-color #030503` |
| Placement | **Inside** the Artwork edge; fills **carved** where it overlaps. Footprint stays exactly the fitted Artwork |
| Edge source | Union of all stitchable geometry → `unary_union(...).exterior` |

### Output
| Decision | Choice |
|---|---|
| SVG | `output_inkstitch_svg/<name>.svg` |
| VP3 | `output_vp3/<name>.vp3` |
| Stitch plan | `output_vp3/<name>_stitchplan.png` (via `preview.py`) |
| Intermediates | `work/` |
| stdout | Thread-colour count, stitch count, extent in mm, trim-cut count |

### Stated but not formally grilled (low controversy — flag if wrong)
- Density stays 0.4 mm; trim stays on (4 mm threshold, 2 mm floor)
- `--density`, `--trim-mm`, `--no-trim`, `--no-border`, `--skip-colors` carry over
- Tests and doc updates were **deferred** — operator asked for files on the machine first

---

## 6. Implementation plan for `svg_digitize.py`

1. **Parse** with `lxml`. Walk from the root, accumulating transforms. Skip
   `defs`, `symbol`, `image`, and anything with `display:none` in its style.
2. **Units**: `uu_per_mm = viewBox_width / width_in_mm`. Convert every coordinate
   and every `stroke-width` to mm early. Work in mm from here on.
3. **Path parser**: full `d` support — `M m L l H h V v C c S s Q q T t A a Z z`.
   Flatten cubics/quadratics/arcs to polylines at `TOLERANCE_MM` = 0.15 mm.
   **Check first** whether `matplotlib.path.Path` is in the venv — if it is, its
   `to_polygons()` handles arcs and is far less code. If not, hand-roll.
4. **Thread colours**: distinct `fill` hexes across visible paths, in first-seen
   document order. One stitch layer per colour.
5. **Drop sub-gate strokes**: any stroked path with width < 1.0 mm is dropped,
   with a printed note.
6. **Scale**: artwork bbox → `scale = min(box_w/art_w, box_h/art_h)` → emit at
   260 × 167.3 mm.
7. **Border**: `union = unary_union(all_polys)`;
   `centre = union.exterior.buffer(-border_mm/2, join_style=2).buffer(0)`;
   emit as `satin_column` stroked at `border_mm`;
   `carve = centre.buffer(+border_mm/2) − centre.buffer(−border_mm/2)`;
   apply `carve` to every fill polygon via `.difference()`.
8. **Travel ordering**: one object per authored `<path>`, nearest-neighbour sweep
   within each thread-colour layer, needle position carried across layers.
9. **Trim**: port the raster path's rules — `d_min` (nearest boundary pair, via
   `cKDTree`) decides "too short to bother"; `d_max` (one-sided Hausdorff) decides
   "too long to leave sewn"; plus a hidden test that samples points along the jump
   and checks each against the union of *later* polygons with `shapely.contains`.
   Note: `vectorize.py:539-585` is the reference implementation — copy the
   semantics, not the code, since it works on raster masks.
10. **Emit** Ink/Stitch SVG: fills get `inkstitch:row_spacing_mm="0.4"` +
    `fill_underlay_skip_last="true"`; border gets `satin_column="true"` +
    `pull_compensation_mm="0.2 0.2"`. Group layers by thread colour, border last.

**Accepted cost**: trim and travel are reimplemented against polygons rather than
shared with `vectorize.py`. Duplication is deliberate — it keeps `vectorize.py`
provably unchanged.

### `run.sh` changes
- Dispatch on extension: `.svg` → `svg_digitize.py`, else `vectorize.py`
- Add `--width-mm` / `--height-mm`
- Add `--border-color`, and pass `--border-mm` / `--no-border` through
- Write SVG → `output_inkstitch_svg/`, VP3 → `output_vp3/`, intermediates → `work/`
- Run `preview.py` after export

---

## 7. The command to produce the deliverable

```
tools/digitize/run.sh \
  --width-mm 260 --height-mm 200 \
  --border-mm 2.5 --border-color "#030503" \
  "input/Scavenger's Daughter Upgrade Patch2.svg"
```

---

## 8. Open item: embroidery craft research (subagent died)

The operator has hand-digitized projects in **`Embroidery_samples/`**:
`SailorMoon/`, `Terrier/`, `Rave/`, `Julegaver 2025/Pledd_skilt/`. They are saved
**from Ink/Stitch**, so they carry real hand-tuned `inkstitch:*` parameters
(`satin_column`, `running_stitch_length_mm`, `fill_underlay`, `angle`, `ties`,
`underpath`, `contour_strategy`, `fill_method`), plus exported `.vp3` files with
the actual generated stitches.

**A research subagent was launched to extract density/satin/underlay knowledge
into `learnings_from_embroidery_projects.md` and failed** — the configured model
`opencode/deepseek-v4-flash` is unavailable. Relaunch with an available model,
e.g. `opencode/glm-5.3`, `opencode/kimi-k2.7-code` or `opencode/qwen3.6-plus`.

It should write **only** `learnings_from_embroidery_projects.md`, put throwaway
scripts in `/tmp/opencode/`, and **not touch pipeline code** (it will collide
with the build).

Extract: actual *values* of every `inkstitch:*` attribute by element type; stitch
count / colour changes / extent per VP3; stitch-length distributions (which
reveals true density); satin stitch length vs width; jump and trim distributions;
stroke-width-to-satin-width ratios. Compare against the constants in
`vectorize.py` (`ROW_SPACING_MM` 0.4, `SATIN_MIN_MM` 1.2, `SATIN_MAX_MM` 2.5,
`SATIN_PULL_MM` 0.2, `TRIM_MIN_MM` 2.0, `TRIM_THRESHOLD_MM` 4.0,
`MIN_COMP_MM2` 0.8) and say plainly where we are wrong.

`pystitch.read(path)` gives `.stitches` as `(x, y, cmd)` in 0.1 mm. Read
`.venv/lib/python3.13/site-packages/pystitch/` for the exact command-flag
semantics before counting trims or jumps — do not guess.

---

## 9. Trap already found in the raster path (do not copy it)

Running the existing raster path on a rasterization of this file produces
**58 bogus satin border paths in dark green `#1e3705`** that would stitch straight
across the artwork. Cause: the artwork's widest inscribed circle is 2.46 mm, less
than the 2.5 mm border, so `ring = silhouette & (dt <= BORDER_PX)` swallows the
whole silhouette. `vectorize.py:282` prints
`warning: border ring covers the whole silhouette` and recovers — but it recovers
by dropping the ring exclusion while **still emitting `border_paths`**. The
guardrail was chosen but **not yet implemented**. If you touch that code, the fix
is to emit no border at all when the ring swallows the silhouette.

---

## 10. Acceptance numbers for the run

Report these to the operator alongside the files:

- **2** thread colours (`#87f70f`, `#030503`), zero extra colour changes
- Artwork extent **260 × 167.3 mm**, fits inside 260 × 200
- ~49,000 stitches (treat as a band, not a target)
- `Outline` layer absent from the output
- Satin border present, `#030503`, 2.5 mm
- `output_vp3/…_stitchplan.png` exists so the operator can eyeball it

The operator sews this on a real machine and judges quality themselves. Give them
the stitch plan and the numbers; do not claim it looks good.