# R2: native SVG path (svg_digitize.py, satinize.py)

Scope: `tools/digitize/svg_digitize.py` (1702 lines) and `tools/digitize/satinize.py`,
plus stale claims in `HANDOFF.md` and `docs/adr/*.md` that touch this path.
Checkout `a795612`. Scratch: `$SCRATCH=/tmp/claude-1000/.../scratchpad/review/R2`.
`$SCRATCH/svg/` holds every test SVG; `$SCRATCH/scav.svg` is the real-input run.
No repo file was modified except this one.

The two prior reviews cover the raster path (`vectorize.py`, `skeleton.py`,
`run.sh`, tools). This path was reviewed only "where it shares a problem", so
almost everything below is new. `svg_digitize.py` shares the hand-rolled argument
parser and the import-time-execution shape with `vectorize.py`; those are called
out as still open rather than re-derived.

## Summary

| ID | Sev | file:line | claim | status |
|----|-----|-----------|-------|--------|
| R2-1 | P1 | `svg_digitize.py:595,615-642,1550` | `fill-rule` is never read; every fill is even-odd XOR, so the SVG default (nonzero) is wrong | VERIFIED |
| R2-2 | P1 | `svg_digitize.py:573,780,820-867` | Gradient / `<use>` / `<text>` / `<image>` artwork is silently dropped, with no warning and no count | VERIFIED |
| R2-3 | P1 | `svg_digitize.py:595,780,810,939-957` | CSS `class` rules and group-level `fill`/`stroke` are ignored, so the shape is stitched black | VERIFIED |
| R2-4 | P1 | `svg_digitize.py:595,780` | `clip-path` and `mask` are ignored, so clipped-away geometry is stitched | VERIFIED |
| R2-5 | P2 | `svg_digitize.py:820-867` | A path with both `fill` and a wide `stroke` loses its stroke silently | VERIFIED |
| R2-6 | P2 | `svg_digitize.py:595,945` | `opacity="0"` and `visibility="hidden"` elements are stitched | VERIFIED |
| R2-7 | P1 | `svg_digitize.py:1480-1484` | The trim skip tests `d_min` only, dropping the raster path's `d_max` guard; a jump whose worst one-sided travel is ~97 mm is left sewn | VERIFIED |
| R2-8 | P1 | `svg_digitize.py:817,903,1015` | The 1.0 mm satin gate is applied in pre-fit millimetres, so the same shape is a satin or a dropped stroke depending on the fit scale | VERIFIED |
| R2-9 | P1 | `svg_digitize.py:1592` | Any input `<metadata>` replaces the defaults wholesale, so `inkstitch_svg_version=4` is lost and Ink/Stitch runs the legacy update | VERIFIED |
| R2-10 | P2 | `svg_digitize.py:984-986,1005-1008` | The fit-box pull budget is added to the size but not to the anchor, so a satin at the min edge stitches 0.2 mm outside the box | VERIFIED |
| R2-11 | P2 | `svg_digitize.py:1057-1069` | Border detection uses bounding-box overlap only, so a diagonal rail satin becomes the border and the perimeter gets none | VERIFIED |
| R2-12 | P2 | `svg_digitize.py:1645` | `angle_cycle` with an empty list raises `ZeroDivisionError` | VERIFIED |
| R2-13 | P2 | `svg_digitize.py:80-83,726` | The hand-rolled parser lets `-o` overwrite the input file; a missing input raises a raw traceback | VERIFIED |
| R2-14 | P2 | `HANDOFF.md:3,118,120,143,156`; `docs/adr/0002:62,98,102` | Stale technical claims: zero code written, TOLERANCE 0.15, strokes always dropped, border carved, density 0.4, "not applied" | VERIFIED |
| R2-15 | P2 | `svg_digitize.py:793,897` | Dead `n_skipped_nonpath`; the widening log prints the widened value as the original | VERIFIED |

---

## R2-1 P1: `fill-rule` is ignored and every fill is even-odd XOR

**What is wrong.** `element_style` collects `fill-rule` (`:595`) but nothing ever
reads it. `rings_to_geom` (`:615-642`) builds each fill as the symmetric
difference (XOR) of its subpaths, and `fill_el` stamps `fill-rule="evenodd"`
(`:1550`). SVG's initial `fill-rule` is `nonzero`, so any path with overlapping
same-winding subpaths is filled as a union by a renderer and as XOR here.

**Impact.** Silent wrong output: a renderer fills the overlap, this path punches a
hole in it. On the real Scavenger artwork the green path carries no `fill-rule`,
so its overlapping legs XOR into holes (ADR 0003 measures 3,444 mm2 even-odd vs
3,560 mm2 rendered). The residual is documented in ADR 0003, but it applies to
every fill, not just that one path.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/nonzero.svg" "$SCRATCH/svg/nonzero.out.svg"
grep -o 'd="M [^"]*"' "$SCRATCH/svg/nonzero.out.svg"   # two rings = the overlap became a hole
```

```
elements: 1 path(s) visible, 1 fill object(s)
nonzero union area = 1150.0
even-odd XOR area  = 1050.0
```

**Fix.** Thread the path's `fill-rule` into `rings_to_geom`: for `nonzero`, use
`unary_union` of the per-subpath regions instead of `symmetric_difference`.

---

## R2-2 P1: gradients, `<use>`, `<text>` and `<image>` are silently dropped

**What is wrong.** `norm_color` maps `url(...)` to `None` (`:573`), so a
gradient-filled path has no fill; if it also has no stroke it falls out of
`handle_path` with no message and is not counted (`:820-867`). `use` and `text`
are neither in `SKIP_TAGS` (`:780`) nor in `NON_PATH_DRAWABLE` (`:781`), so `walk`
recurses into their (empty) children and returns (`:955-957`). `image` is in
`SKIP_TAGS` by design (the reference tracing layer).

**Impact.** A design can lose whole elements and still report success. If a
gradient or `<use>` is the only geometry the run exits with "no stitchable
geometry found", which is at least loud; mixed with a normal fill it is silent.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/grad2.svg" "$SCRATCH/svg/grad2.out.svg"
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/use2.svg" "$SCRATCH/svg/use2.out.svg"
```

```
grad2: elements: 2 path(s) visible, 1 fill object(s)   # the url(#g) path vanished
use2:  elements: 1 path(s) visible, 1 fill object(s)   # the <use> was never counted
```

**Fix.** Count and warn on every element that is not emitted (unsupported fill
kind, `use`/`text`/nested `svg`), and either resolve `<use>` or exit with the
same clear error `NON_PATH_DRAWABLE` uses.

---

## R2-3 P1: CSS classes and group-level style are ignored, so the fill is black

**What is wrong.** `walk` computes `element_style` from the element alone
(`:944`) and never inherits `fill`/`stroke` from a parent `<g>`. `<style>` is in
`SKIP_TAGS` (`:780`), so CSS rules are never applied. `handle_path` then uses the
SVG initial fill, black (`:810`).

**Impact.** Any SVG that colours by CSS class or by a group attribute is stitched
in the wrong thread colour (`#000000`), silently.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/cssclass.svg" "$SCRATCH/svg/cssclass.out.svg"
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/groupfill.svg" "$SCRATCH/svg/groupfill.out.svg"
grep -o 'style="fill:[^"]*"' "$SCRATCH/svg/cssclass.out.svg"   # -> fill:#000000 (the class said #ff0000)
grep -o 'style="fill:[^"]*"' "$SCRATCH/svg/groupfill.out.svg" # -> fill:#000000 (the group said #00ff00)
```

**Fix.** Inherit `fill`/`stroke`/`stroke-width`/`display` down the `walk`
recursion, and either apply `<style>` rules (a CSS pass) or warn when a `class`
is present and no rule was applied.

---

## R2-4 P1: `clip-path` and `mask` are ignored, so clipped geometry is stitched

**What is wrong.** `clipPath` and `mask` are in `SKIP_TAGS` (`:780`), so their
contents are not stitched, but the `clip-path`/`mask` attributes on a stitched
element are never read (`element_style` `:595` lists only fill/stroke/width/
display/fill-rule/opacity). The full untrimmed geometry is stitched.

**Impact.** Silent over-stitch: thread is laid where the artwork is clipped away.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/clip.svg" "$SCRATCH/svg/clip.out.svg"
```

```
elements: 1 path(s) visible, 1 fill object(s)
artwork: 50.0 x 50.0 mm -> scaled 100.0 x 100.0 mm   # clip was 25x25, full 50x50 stitched
```

**Fix.** At minimum detect `clip-path`/`mask` on a stitched element and warn;
better, intersect the element geometry with the referenced clip geometry.

---

## R2-5 P2: a path with fill and a wide stroke loses the stroke silently

**What is wrong.** The fill branch (`:820`) runs and returns (`:867`) whenever
`fill_c is not None` and the path is not an authored satin. A path carrying both
a fill and a `stroke` never reaches the stroke branch, so the stroke is dropped
regardless of width.

**Impact.** An artist's filled shape with a thick outline is stitched without the
outline, with no message.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/fillstroke.svg" "$SCRATCH/svg/fillstroke.out.svg"
grep -o 'style="fill:[^"]*"' "$SCRATCH/svg/fillstroke.out.svg"
```

```
elements: 1 path(s) visible, 1 fill object(s), 0 satin(s)
        1 style="fill:#00ff00;stroke:none"   # the 3 mm black stroke is gone
```

**Fix.** When a fill path also has a stroke at or above the gate, emit it too
(a satin item), or print a note that the stroke is dropped.

---

## R2-6 P2: `opacity="0"` and `visibility="hidden"` elements are stitched

**What is wrong.** `element_style` collects `opacity` (`:595`) but nothing reads
it, and `visibility` is not collected at all. Only `display:none` is handled
(`:945-947`).

**Impact.** Invisible elements are stitched, adding colour changes and geometry
the operator cannot see in the source.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/hidden.svg" "$SCRATCH/svg/hidden.out.svg"
```

```
elements: 3 path(s) visible, 3 fill object(s)
thread colours: 3 (#ff0000, #00ff00, #0000ff)   # opacity:0 and visibility:hidden both stitched
```

**Fix.** Skip (with a note) when `opacity == 0` or `visibility` is `hidden` or
`collapse`, inherited down the `walk` recursion.

---

## R2-7 P1: the trim skip tests `d_min` only, dropping the raster path's `d_max` guard

**What is wrong.** `plan_trims` here skips as soon as `d_min <= TRIM_MIN_MM`
(`:1480-1482`). The raster sibling (`vectorize.py:1367-1368`) skips only when
**both** `d_min <= trim_min` and `d_max <= threshold`. The SVG path dropped the
`d_max` half, so a pair whose nearest boundaries nearly touch but whose far
boundaries are far apart is left sewn.

**Impact.** The exact regression review.md 2.8 fixed on the raster path (a
Book Burner jump 0.74 mm at the nearest boundary, 59.7 mm at the row end) can
reappear: a long exposed thread sewn across the design.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/trimedge2.svg" "$SCRATCH/svg/trimedge2.out.svg"
```

```
artwork: 50.0 x 2.5 mm -> scaled 100.0 x 5.0 mm (x2.0000)
trim: 0 cut(s) / 2 objects (0 authored, threshold 4.0 mm, min 1.5 mm)
# independent: d_min = 1.0 mm (post-fit), d_max = 97.1 mm (post-fit)
```

**Fix.** Mirror `vectorize.py:1364-1369`: compute `short = d_min <= TRIM_MIN_MM
and d_max <= TRIM_THRESHOLD_MM` and `continue` on `short`.

---

## R2-8 P1: the satin gate is applied in pre-fit millimetres

**What is wrong.** `sw_mm = sw_uu * s * MM` (`:817`) is the stroke width in the
input's own millimetres. The gate test `if sw_mm <= SATIN_GATE_MM` (`:903`, and
the widening at `:894`) runs before `to_fit` (`:1015`). The emitted SVG is the
fitted design, where Ink/Stitch applies its 1.0 mm gate, so the decision is made
on the wrong scale.

**Impact.** The same physical design is treated differently depending only on the
authoring scale: a stroke that will be 5 mm after fitting is dropped as
"sub-gate" when authored small, and kept when authored large. Ink/Stitch's real
gate is then applied to the fitted width, so a kept stroke can still fall below
it.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/small.svg" "$SCRATCH/svg/small.out.svg"  # 10mm design, 0.5mm stroke
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/big.svg"   "$SCRATCH/svg/big.out.svg"    # 10x design, 5mm stroke
```

```
small: note: dropping sub-gate stroke None (0.500 mm <= 1.0 mm satin gate)
big:   elements: 1 path(s) visible, 0 fill object(s), 1 satin(s)
```

**Fix.** Move the gate test and the `SATIN_MIN_EMIT_MM` widening after the fit
scale is known (or multiply `sw_mm` by `scale` before comparing).

---

## R2-9 P1: any input metadata replaces the defaults, losing `inkstitch_svg_version=4`

**What is wrong.** `_meta_items = list(input_metadata if input_metadata else
_META_DEFAULTS)` (`:1592`). If the input carries even one `inkstitch:*` metadata
child, the default set (including `inkstitch_svg_version=4`) is discarded
entirely instead of being merged.

**Impact.** The output is unversioned, so Ink/Stitch runs every legacy update at
export. This is the same defect review.md 2.4 fixed for the raster path
(14,293 vs 12,649 stitches, plus the "Unversioned Ink/Stitch SVG file detected"
dialog), reintroduced on the SVG path.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/meta.svg" "$SCRATCH/svg/meta.out.svg"
grep -o '<metadata.*</metadata>' "$SCRATCH/svg/meta.out.svg"
```

```
<metadata id="metadata1"><inkstitch:min_stitch_len_mm>0.2</inkstitch:min_stitch_len_mm></metadata>
# inkstitch_svg_version, collapse_len_mm, min_satin_stroke_width_mm are all gone
```

**Fix.** Merge: start from `_META_DEFAULTS` and overwrite with `input_metadata`
entries by name, so `inkstitch_svg_version` is always present.

---

## R2-10 P2: the fit box does not contain the stitched satin on the min edge

**What is wrong.** When satins exist, the budget adds `2 * SATIN_PULL_MM` to
`art_w`/`art_h` (`:984-986`), but `to_fit` still anchors the raw `minx`/`miny` at
0 (`:1008`). The pull compensation is symmetric, so the min edge overflows by
`SATIN_PULL_MM` while the max edge has that much slack.

**Impact.** A centreline satin at the artwork's min edge stitches 0.2 mm outside
the stated fit box. Small, but it is exactly the "fit box must contain the
stitched result" rule; the reported extent is also wrong on that side.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/onlysat.svg" "$SCRATCH/svg/onlysat.out.svg"
```

```
viewBox 0 .. 100.00 x 0 .. 10.18
emitted satin width mm: 8.98  pull comp per side: 0.2
centreline x: 4.49 .. 94.31
STITCHED band x: -0.2 .. 99.0     # min x is outside the box
```

**Fix.** Expand the bounds used by `to_fit` by `SATIN_PULL_MM` per side (map
`minx - SATIN_PULL_MM` to 0) so the budget is symmetric.

---

## R2-11 P2: border detection uses bounding-box overlap, so a diagonal satin becomes the border

**What is wrong.** The authored rail satin is promoted to the border when its
footprint's bounding box overlaps the fill bbox by `>= 0.95` on each axis
(`:1064-1066`). Bounding-box overlap is not coverage: a diagonal or cross-shaped
satin spanning the bbox qualifies, and then the synthetic perimeter border is
skipped and the fills keep their footprint.

**Impact.** A design whose only rail satin is not a perimeter gets no perimeter
border; a non-perimeter satin is stitched as the "border".

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --border-color "#00ff00" "$SCRATCH/svg/diagborder.svg" "$SCRATCH/svg/diagborder.out.svg"
```

```
border: using the authored rail satin (2 subpaths, rails 264 mm) instead of a synthetic border; fills keep their full footprint beneath it
thread colours: 1 (#00ff00)
```

**Fix.** Test actual coverage (area of `footprint ∩ fill_union` over
`fill_union.area`) rather than bbox overlap.

---

## R2-12 P2: `angle_cycle` with an empty list raises `ZeroDivisionError`

**What is wrong.** `angle = _ANGLE_CYCLE[_cl][_i % len(_ANGLE_CYCLE[_cl])]`
(`:1645`) divides by the list length. A YAML `angle_cycle: {"#hex": []}` produces
an empty list, which is accepted by the loader (`:208`).

**Impact.** A plausible config typo crashes the run with a traceback instead of a
message.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border --config "$SCRATCH/svg/angles.yaml" "$SCRATCH/svg/fill.svg" "$SCRATCH/svg/angles.out.svg"
```

```
File ".../svg_digitize.py", line 1645, in <module>
    angle = _ANGLE_CYCLE[_cl][_i % len(_ANGLE_CYCLE[_cl])]
ZeroDivisionError: integer modulo by zero
```

**Fix.** Drop empty angle lists at load time (or guard `if not _ANGLE_CYCLE[_cl]`
before indexing).

---

## R2-13 P2: `-o` overwrites the input file; a missing input raises a raw traceback

**What is wrong.** The hand-rolled parser ignores short flags without consuming
their value (`:80-83`), so `-o out.svg source.svg` makes `out.svg` the input and
`source.svg` the output. `etree.parse(SVG_IN)` (`:726`) is not guarded, so a
missing input raises `OSError` with a traceback. Same class as
space_bunny-review.md #1, which was reported for `vectorize.py` only.

**Impact.** `svg_digitize.py -o out.svg source.svg` overwrites `source.svg` with
SVG, exit 0; a typo'd input path prints a parser traceback.

**Reproduce.**

```bash
cp "$SCRATCH/svg/fill.svg" "$SCRATCH/svg/out2.svg"; cp "$SCRATCH/svg/fill.svg" "$SCRATCH/svg/source2.svg"
.venv/bin/python tools/digitize/svg_digitize.py --no-border -o "$SCRATCH/svg/out2.svg" "$SCRATCH/svg/source2.svg"
wc -c "$SCRATCH/svg/source2.svg"
.venv/bin/python tools/digitize/svg_digitize.py /nonexistent.svg "$SCRATCH/svg/x.svg"
```

```
source2 before: 146 ; after: 1212   # overwritten, exit 0
OSError: Error reading file '/nonexistent.svg': failed to load ...
```

**Fix.** Use `argparse` (kills this and space_bunny #12/#31 together), and wrap
the parse in `try/except OSError` with a `sys.exit` message.

---

## R2-14 P2: stale technical claims in HANDOFF.md and ADR 0002

**What is wrong.** HANDOFF still opens with "zero pipeline code written"
(`HANDOFF.md:3`) and its settled-decision tables contradict the shipped code:

- `:118` and `:169`: `TOLERANCE_MM = 0.15`; the code is `0.25` (`svg_digitize.py:141`).
- `:120`: "Sub-gate strokes **Always dropped**"; the code widens an authored
  single-subpath satin to 1.5 mm (`svg_digitize.py:894-901`, ADR 0003).
- `:143`: "fills **carved** where it [the border] overlaps"; when an authored rail
  satin is the border, the fills keep their full footprint, no carve (`:1071-1075`).
- `:156`: "Density stays 0.4 mm"; the SVG path default is 0.3 (`svg_digitize.py:104`).
- `:25`: GLOSSARY has 13 terms now, not 11.

ADR 0002 recommends the TOLERANCE change at "`svg_digitize.py:96`" and ends
"This is a follow-up, not applied here" (`docs/adr/0002:98,102`); the value is
now 0.25 at line 141, and the ADR's baseline note still says the input is
"flattened at `TOLERANCE_MM = 0.15` mm" (`:62`).

**Impact.** An agent building from HANDOFF or ADR 0002 starts from wrong
constants and wrong behaviour. R4 already flags HANDOFF as an archive candidate;
this records the specific contradictions so they are not silently trusted.

**Reproduce.**

```bash
grep -n "zero pipeline code\|TOLERANCE_MM. = 0.15\|Always dropped\|fills \*\*carved\*\*\|Density stays 0.4" HANDOFF.md
grep -n "TOLERANCE_MM = 0.15\|not applied here" docs/adr/0002-export-performance.md
```

**Fix.** Add a one-line "superseded, see docs/review" banner to HANDOFF and mark
the ADR 0002 recommendation as applied (fix the line number and the 0.15 note).

---

## R2-15 P2: dead variable and a misleading widening log

**What is wrong.** `n_skipped_nonpath` is declared (`:793`) and declared `global`
(`:940`) but never incremented or printed. In `handle_path` the widening note
assigns `sw_mm = SATIN_MIN_EMIT_MM` before printing it (`:895-899`), so it always
reports the new value as the old one.

**Impact.** None functional; a reader trusts a log line that is always
"from 1.50 mm to 1.5 mm".

**Reproduce.**

```bash
.venv/bin/python tools/digitize/svg_digitize.py --no-border "$SCRATCH/svg/narrowsat.svg" "$SCRATCH/svg/narrowsat.out.svg" 2>&1 | grep widening
```

```
note: widening authored satin None from 1.50 mm to 1.5 mm (Ink/Stitch gate is strictly > 1.0 mm)
```

**Fix.** Save `old = sw_mm` before overwriting and print `old`; delete
`n_skipped_nonpath`.

---

## Still open from earlier reviews

- **space_bunny #1 data loss (short flags)**: still open, and the same parser is
  copied into `svg_digitize.py:69-84` (see R2-13).
- **space_bunny #12 `--flag=value` on booleans**: still open on this path.
  `--no-border=true` is a string, `flag("no-border", False) is True` is `False`,
  so the border is emitted anyway (verified: "border: colour #ff0000 width 2.5 mm").
- **space_bunny #21 density floor 0.3 vs Ink/Stitch 0.378**: still open and it
  hits the SVG path hardest: the default `ROW_SPACING_MM = 0.3`
  (`svg_digitize.py:104`) is emitted as `row_spacing_mm="0.3"` and Ink/Stitch
  clamps it to `0.1 * 96/25.4 = 0.378` (`inkstitch/lib/elements/fill_stitch.py:379`),
  so ADR 0003's 0.4 to 0.3 density decision does not take effect. Also
  `--density -1` still emits `row_spacing_mm="-1"` (warning only). R4 records the
  same floor issue; not repeated as a new finding here.
- **space_bunny #31 import-time execution / hand-rolled parser**: still open.
  `svg_digitize.py` runs top to bottom with no `main()` and no
  `if __name__ == "__main__"`, so it is unimportable and untestable.
- **space_bunny #32 numpy scalar repr**: still open in this path's sibling,
  `satinize.py:551-554` prints `np.float64(...)` in its smoke test.
- **space_bunny #33 missing `--config` silently ignored**: still open
  (`load_config` returns `{}`, `svg_digitize.py:95-99`; verified silent).
- **ADR 0003 residual (nonzero winding)**: still open, see R2-1.
- **review.md 2.10 `preview.py` white background**: not re-checked here (R3
  scope).

## Checked and fine

- **Transforms**: `parse_transform`/`apply_pts` are consistent with the SVG
  row-vector convention (`translate(10,0) scale(2)` maps x=1 to 12, verified);
  the Layer 2 matrix is applied (real input extent 242.6 x 157.5 mm matches
  HANDOFF's 242.7 x 157.3).
- **Path parser**: `M m L l H h V v C c S s Q q T t A a Z z`, implicit lineto
  after moveto, relative-after-`Z` current point, and the SVG F.6.5 arc sign
  convention (`if large == sweep: co = -co`) all read correctly; malformed `d`
  is caught by the `try/except` around `parse_path` (`:826-829`).
- **Even-odd for standard holes**: nested opposite-winding subpaths become a hole
  in both nonzero and even-odd, so ordinary donut art is correct (only
  same-winding overlaps are wrong, R2-1).
- **Authored rail satin**: detected, emitted with all subpaths (first two rails,
  rest rungs), no pull compensation, 0.3 mm zigzag, and the metadata gate lowered
  to 0.5 mm (`scav.svg`: "min_satin_stroke_width_mm set to 0.5"); matches ADR 0003.
- **`--border-color` validation**: required and checked against an authored fill
  (`:1041-1049`); a non-matching hex exits with the authored list.
- **`--width-mm 0`**: collapses to zero and exits "no stitchable objects
  produced" rather than writing an empty SVG.
- **Overlap carve / seam pull order**: `_drawn` is captured before the overlap
  carve and after the border carve, and the seam pass runs after the component
  split, matching the ADR 0003 ordering.
- **`satinize.component_to_satins` smoke test**: capsule -> 1 row (2.43 mm),
  plate -> 2 rows (3.65 mm), as documented.
- **`--no-border` (space form)**: correctly suppresses the border; the border is
  only required to have a colour when enabled.
