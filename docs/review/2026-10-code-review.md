# October 2026 code review

Commit `a795612`. Source material: `docs/review/_parts/R1-raster-core.md`,
`R2-svg-path.md`, `R3-tools-and-qa.md`, `R4-workflow-and-beginner.md`,
`CRITIC-1.md`.

Severity scale used by all four reviewers: P0 silent wrong output, P1 wrong or
fragile, P2 polish.

## 1. How this was produced, and what it does not cover

Four reviewers read the code at commit `a795612`, one per area: the raster path,
the native SVG path, the tools and QA scripts, and the workflow for a beginner.
They produced 54 findings. A fifth reviewer, the critic, independently
reproduced 12 of the 54 with its own inputs: 10 confirmed, 2 partly confirmed.
The other 42 are reviewer-only. Every finding below carries a status label saying
which of the two it is.

No fixes were implemented. This is a report. Two prior review rounds
(`review.md`, `space_bunny-review.md`) were read for context, and findings they
fixed are not repeated here.

Not covered: performance profiling, the Ink/Stitch internals beyond the satin
gate, the thread chart and thread substitutions, and any run on macOS or on real
fabric.

### Status labels

- `CONFIRMED by critic`: the critic reproduced it.
- `PARTLY CONFIRMED`: the critic reproduced part of it and narrowed the claim.
- `REVIEWER ONLY, reproduced by the reviewer`: verified in that reviewer's own
  run, not independently checked.
- `REVIEWER ONLY, from reading`: found by reading the code, not executed.

### Corrections from the critic

- The suggested fix for R1-5 is wrong as written. `str(False).lower()` is
  `"false"`, so the border stays on. The fix must map boolean `False` to `"off"`
  first, then validate.
- The suggested fix for R2-8 is circular. The scale depends on the satins, and
  dropping a stroke changes the bounds and the scale, so the fix needs a
  two-pass design.
- R1-1's impact is narrower than the reviewer wrote. See the entry below.
- R4-4 cannot be triggered by any flag at commit `a795612`. The three flag lists
  are in sync. It was live on branch `feat/fit-mm` until `run.sh` was fixed.
- The rule "unknown flag takes the next token" is risky. A mistyped boolean
  would swallow the image path. The better fix is one shared flag list.
- Setting satin pull to 0 (R1-4) is risky. The pull compensation is deliberate
  fabric compensation.

## 2. Top findings in plain words

**R1-1, PARTLY CONFIRMED, P0, `vectorize.py:213-214`.** A short flag is dropped
without consuming its value, so the positionals shift. The file is destroyed
only if the first positional is an existing loadable file. On `svg_digitize.py`
a re-run can overwrite the source SVG. On `vectorize.py` the natural
`-o out.svg in.png` fails with a traceback and loses nothing, so the critic rates it P0 for the SVG path and P1 for the raster path. Fix: `argparse`, or
exit on an unknown short flag.

**R1-2, CONFIRMED by critic, P0, `vectorize.py:577-581`.** The auto palette
merges two empty clusters, divides `0/0` and puts NaN in a centroid. A flat
3-colour image then stitches as one thread in a colour that is not in the
artwork, at exit 0. It hit 25 to 50 percent of the critic's synthetic flat
designs, all of them transparent artwork. Fix: delete one of the pair when the
total share is zero. The critic tested this on a copy and got 3 correct colours.

**R1-5, CONFIRMED by critic, P1, `vectorize.py:341` and `:672`.** YAML parses a
bare `off` as boolean `False`, and the loader tests for the string `"off"`. The
one control meant to disable the border keeps it on, and a mode typo such as
`FORCE_BLACK` falls through to `auto`. Fix: map booleans first (`False` becomes
`"off"`), then lower-case, then validate against `auto`, `off`, `force_black`.
The fix suggested in the part file does not work.

**R1-3, CONFIRMED by critic, P1, `vectorize.py:677-704`.** When the silhouette
touches the canvas edge, the distance transform cannot see outside the array,
the erosion removes almost nothing, and the border satin is centred on the
edge. Half the border width is stitched off the patch each side. Fix: pad the
mask before the distance transform. That gives 100.5 mm for a 100 mm design
instead of 102.9 mm. It changes the output for every design that touches the
edge, so the regression gate must be rerun.

**R1-8, CONFIRMED by critic, P1, `vectorize.py:442`.** `load_image` does not
apply EXIF orientation. A phone photo tagged `Orientation=6` is digitised 90
degrees from what every viewer shows. Fix:
`ImageOps.exif_transpose(Image.open(path))` before the RGBA conversion. Low
risk.

**R3-3, CONFIRMED by critic, P1, `invert_ink.py:980-982`.** A single-subpath
border satin below Ink/Stitch's 1.0 mm satin gate is emitted with no widening
and no warning. `--border-mm 0.8` exits 0 and sews as running stitch. The
critic confirmed it in the VP3: a 2.50 mm median step, the running-stitch
length. Fix: validate `--border-mm >= 1.0` and print the same gate warning the
rest of the pipeline uses, or widen it as `svg_digitize.py` does.

**R4-3, CONFIRMED by critic, P1, `run.sh:138-140`.** Export redirects both
streams into `work/<base>.err`, and `set -e` aborts on failure with nothing
printed. On a fresh clone the screen ends at `== exporting VP3` and the prompt
returns. Exit 2. Fix: on failure print `FAIL` plus the tail of the error file
and exit 1, the way `qa/export.sh` already does.

**R4-13, CONFIRMED by critic, P1, `docs/USAGE.md:17-20,35` and
`README.md:65`.** The docs say output lands in `work/`. It lands in
`output_inkstitch_svg/` and `output_vp3/`; `work/` holds the zip and the error
file. A beginner follows the docs, finds nothing, and concludes the run failed.
Fix: rewrite the "What it produces" table with the real paths. The new README on branch `docs/readme` already states the real paths.

## 3. Overhang: why the stitched file is larger than the design

Model, confirmed by the critic:

```
VP3 extent = design bounds + border_mm + 0.4 mm
border_mm applies only when the silhouette touches the picture edge,
           and then the border is centred on that edge
0.4 mm     = 0.2 mm satin pull compensation per side
```

Measured outcomes:

- Ordinary shapes with a margin: +0.4 to +0.5 mm.
- Silhouette touching the picture edge at the default 2.5 mm border: +2.9 mm.
- Thin outline lines at the extremes, widened to 1.2 mm: +0.9 mm.

The trigger is the silhouette touching the picture edge. An artwork's own
border ring is not the trigger: a plain red rounded square touching the edge
with no ring gives the same 102.9 mm.

The one-line padding fix (`np.pad` before the distance transform) makes the
edge case 100.5 mm for a 100 mm design. It changes the output for every design
that touches the edge, so the regression gate must be rerun before shipping it.

`docs/USAGE.md` says `--size-mm` is the "longest side of the finished design".
That is true of the design bounds. The stitched file is larger.

## 4. Full findings table

| ID | Sev | file:line | Claim | Status |
|---|---|---|---|---|
| R1-1 | P0 | `vectorize.py:213-214` | Short flags are dropped without consuming their value, so the positionals shift and the second file is overwritten with SVG, exit 0 | PARTLY CONFIRMED |
| R1-2 | P0 | `vectorize.py:577-581` (call site 551-554) | S3 auto palette merges two empty clusters, divides 0/0 into NaN, and collapses a low-colour artwork to a single thread colour | CONFIRMED by critic |
| R1-3 | P1 | `vectorize.py:677-704` | When the silhouette touches the canvas border the erosion removes nothing and the satin border is centred on the edge, so border_mm/2 is stitched off the patch each side | CONFIRMED by critic |
| R1-4 | P1 | `vectorize.py:1418`, `inkstitch/lib/elements/satin_column/satin_column.py:218-232` | Every satin carries `pull_compensation_mm="0.2 0.2"`, which Ink/Stitch applies outward from the centreline at export | CONFIRMED by critic |
| R1-5 | P1 | `vectorize.py:341`, `:672` | `border: mode: off` is YAML boolean False, so the border is never disabled; mode typos such as `FORCE_BLACK` degrade to `auto` | CONFIRMED by critic |
| R1-6 | P1 | `vectorize.py:204-212`, `:278-338` | `--flag=value` on booleans is ignored; a value-less `--colors` becomes `int(True)=1`, a one-thread design at exit 0 | REVIEWER ONLY, reproduced by the reviewer |
| R1-7 | P1 | `vectorize.py:907-909` | Opaque art drops the globally lightest cluster as paper, which can be a real accent colour; the actual background is stitched as a fill | REVIEWER ONLY, reproduced by the reviewer |
| R1-8 | P1 | `vectorize.py:442` | EXIF orientation is ignored, so a phone photo tagged `Orientation=6` is digitised 90 degrees from any viewer | CONFIRMED by critic |
| R1-9 | P2 | `vectorize.py:289`, `:344-345` | `satin_max_mm:` in YAML is never read; only `--satin-max-mm` is honoured | REVIEWER ONLY, reproduced by the reviewer |
| R1-10 | P2 | `vectorize.py:411-414` | `--density -1` emits `row_spacing_mm="-1.0"` with a printed warning only; Ink/Stitch silently clamps to 0.378 mm | REVIEWER ONLY, reproduced by the reviewer |
| R1-11 | P2 | `vectorize.py:221-225`, `:936`, `:941` | A missing `--config` is silently ignored; a non-mapping YAML dies with a raw `AttributeError`; hexes without `#` in `order:`/`skip_colors:` are ignored | REVIEWER ONLY, reproduced by the reviewer |
| R1-12 | P2 | `vectorize.py:1515` | `write_preview` uses `rsplit(".",1)[0]`, so the preview lands in a parent directory when a directory name holds a dot | REVIEWER ONLY, reproduced by the reviewer |
| R2-1 | P1 | `svg_digitize.py:595,615-642,1550` | `fill-rule` is never read; every fill is even-odd XOR, so the SVG default (nonzero) is wrong and overlaps become holes | REVIEWER ONLY, reproduced by the reviewer |
| R2-2 | P1 | `svg_digitize.py:573,780,820-867` | Gradient, `<use>`, `<text>` and `<image>` artwork is silently dropped, with no warning and no count | REVIEWER ONLY, reproduced by the reviewer |
| R2-3 | P1 | `svg_digitize.py:595,780,810,939-957` | CSS `class` rules and group-level `fill`/`stroke` are ignored, so the shape is stitched black | REVIEWER ONLY, reproduced by the reviewer |
| R2-4 | P1 | `svg_digitize.py:595,780` | `clip-path` and `mask` are ignored, so clipped-away geometry is stitched | REVIEWER ONLY, reproduced by the reviewer |
| R2-5 | P2 | `svg_digitize.py:820-867` | A path with both a fill and a wide stroke loses its stroke silently | REVIEWER ONLY, reproduced by the reviewer |
| R2-6 | P2 | `svg_digitize.py:595,945` | `opacity="0"` and `visibility="hidden"` elements are stitched | REVIEWER ONLY, reproduced by the reviewer |
| R2-7 | P1 | `svg_digitize.py:1480-1484` | The trim skip tests `d_min` only, dropping the raster path's `d_max` guard; a jump with ~97 mm one-sided travel is left sewn | REVIEWER ONLY, reproduced by the reviewer |
| R2-8 | P1 | `svg_digitize.py:817,903,1015` | The 1.0 mm satin gate runs in pre-fit millimetres, so the same shape is a satin or a dropped stroke depending only on the authoring scale | PARTLY CONFIRMED |
| R2-9 | P1 | `svg_digitize.py:1592` | Any input `<metadata>` replaces the defaults wholesale, so `inkstitch_svg_version=4` is lost and Ink/Stitch runs the legacy update | REVIEWER ONLY, reproduced by the reviewer |
| R2-10 | P2 | `svg_digitize.py:984-986,1005-1008` | The fit-box pull budget is added to the size but not the anchor, so a satin at the min edge stitches 0.2 mm outside the box | REVIEWER ONLY, reproduced by the reviewer |
| R2-11 | P2 | `svg_digitize.py:1057-1069` | Border detection uses bounding-box overlap, so a diagonal rail satin becomes the border and the perimeter gets none | REVIEWER ONLY, reproduced by the reviewer |
| R2-12 | P2 | `svg_digitize.py:1645` | `angle_cycle` with an empty list raises `ZeroDivisionError` | REVIEWER ONLY, reproduced by the reviewer |
| R2-13 | P2 | `svg_digitize.py:80-83,726` | The hand-rolled parser lets `-o` overwrite the input file; a missing input raises a raw traceback | REVIEWER ONLY, reproduced by the reviewer |
| R2-14 | P2 | `HANDOFF.md:3,118,120,143,156`, `docs/adr/0002:62,98,102` | Stale technical claims: zero code written, TOLERANCE 0.15, strokes always dropped, fills carved, density 0.4, "not applied" | REVIEWER ONLY, reproduced by the reviewer |
| R2-15 | P2 | `svg_digitize.py:793,897` | Dead `n_skipped_nonpath`; the widening log prints the widened value as the original | REVIEWER ONLY, reproduced by the reviewer |
| R3-1 | P1 | `make_config.html:144`, `vectorize.py:341,672` | The HTML "off (no border)" option emits unquoted `mode: off`, and the loader never normalises it, so the border stays on | CONFIRMED by critic |
| R3-2 | P1 | `qa/pullsim.py:90-103` | pullsim draws a rail satin as one hairline per rail, so a correctly covered band reports ~97 to 100 percent uncovered | REVIEWER ONLY, reproduced by the reviewer |
| R3-3 | P1 | `invert_ink.py:980-982` | A single-subpath border satin below Ink/Stitch's 1.0 mm gate is emitted with no widening and no warning, so `--border-mm 0.8` becomes running stitch | CONFIRMED by critic |
| R3-4 | P2 | `tests/smoke_vectorize.sh:8`, `qa/regress.sh:52-54,116-117` | Every input the only test and the QA gate read lives in a gitignored directory, so a fresh clone can run neither | REVIEWER ONLY, reproduced by the reviewer |
| R3-5 | P2 | `make_config.py:130-152` | The generated `order:` still lists the background colour, which `vectorize.py` discards | REVIEWER ONLY, reproduced by the reviewer |
| R3-6 | P2 | `invert_ink.py:643-645` | `--fit-mm` without an `x` raises `IndexError`; the `len(fit) > 2` branch is dead | REVIEWER ONLY, reproduced by the reviewer |
| R3-7 | P2 | `invert_ink.py:639,975,980` | `--paper` only selects the excluded colour; the emitted paper fill and border are hardcoded `#ffffff` | REVIEWER ONLY, reproduced by the reviewer |
| R3-8 | P2 | `swatch.py:54,199` | The swatch raises `min_satin_stroke_width_mm` to 0.5 (production is 1.0) and its legend claims a fill angle its frames do not use | REVIEWER ONLY, reproduced by the reviewer |
| R3-9 | P2 | `wxstub/wx/__init__.py:43-65,81-125` | The wx stub never fails: any attribute, call or comparison returns a truthy stand-in, so a missing wx name is silently satisfied | REVIEWER ONLY, reproduced by the reviewer |
| R3-10 | P2 | `analyze.py:23,41-43` | `analyze.py` still uses MEDIANCUT and "lightest = background", so its palette and component counts do not match the pipeline | REVIEWER ONLY, from reading |
| R3-11 | P2 | `make_config.py:63-64` | `SIZE_MM` and `BORDER_MM` are dead constants left from the old ring logic | REVIEWER ONLY, from reading |
| R3-12 | P2 | `qa/regress.sh:108,117` | Doc drift: USAGE says exposed travel "> 3 mm" but the gate uses 4.5; the "goat" row is actually midnight-epicure | REVIEWER ONLY, from reading |
| R4-1 | P1 | `vectorize.py:442` | A 16-bit grayscale PNG reads as blank white, then "no stitchable objects produced", an error that blames the image | REVIEWER ONLY, reproduced by the reviewer |
| R4-2 | P1 | `vectorize.py:442`, `:1528` | Missing, empty, text and corrupt inputs all raise raw Python tracebacks with no guidance | REVIEWER ONLY, reproduced by the reviewer |
| R4-3 | P1 | `run.sh:138-140` | Export failures are buried in `work/<base>.err`; `run.sh` exits with nothing on screen | CONFIRMED by critic |
| R4-4 | P1 | `run.sh:36-45`, `vectorize.py:208` | A value flag missing from `run.sh`'s own list sends its value into the positionals, so the value is taken as the image path | CONFIRMED by critic |
| R4-5 | P1 | `run.sh:36-40` | A value flag at the end with no value gives `$1: unbound variable`, exit 1 | REVIEWER ONLY, reproduced by the reviewer |
| R4-6 | P1 | `run.sh:34-42` | The `--flag=true` form of `run.sh`'s own booleans (`--key-background`, `--no-export`) is silently ignored | REVIEWER ONLY, reproduced by the reviewer |
| R4-7 | P2 | `run.sh:50`, `:74` | A relative input path from another CWD fails after `cd` to the repo root, naming a path the user can see | REVIEWER ONLY, reproduced by the reviewer |
| R4-8 | P2 | `run.sh:47`, `vectorize.py:1525` | No usable `--help`; `vectorize.py --help` tries to digitize a hardcoded sample | REVIEWER ONLY, reproduced by the reviewer |
| R4-9 | P2 | `vectorize.py` (no validation) | `--border-mm -1` emits `stroke-width:-5.53` and exits 0 | REVIEWER ONLY, reproduced by the reviewer |
| R4-10 | P2 | `run.sh:74`, `:115` | The output name is the input basename only, so two inputs with the same name overwrite one output silently | REVIEWER ONLY, reproduced by the reviewer |
| R4-11 | P2 | `vectorize.py:579` | A grayscale PNG triggers a numpy `RuntimeWarning: invalid value encountered in divide` from the palette merge | REVIEWER ONLY, reproduced by the reviewer |
| R4-12 | P2 | `vectorize.py` | A 6000 px source runs for minutes with no progress output, so it looks hung | REVIEWER ONLY, reproduced by the reviewer |
| R4-13 | P1 | `docs/USAGE.md:17-20,35`, `README.md:65` | Docs say output lands in `work/`; `run.sh` writes `output_inkstitch_svg/` and `output_vp3/` | CONFIRMED by critic |
| R4-14 | P2 | `docs/USAGE.md:155`, `:200` | Docs cite a missing artifact and a regression gate that needs gitignored inputs and configs | REVIEWER ONLY, reproduced by the reviewer |
| R4-15 | P2 | `qa/regress.sh:45`, `run.sh:128` | macOS portability: `readlink -f`; likely bash 3.2 empty-array failure under `set -u` | REVIEWER ONLY, from reading |

Counts: 54 findings. 10 confirmed by the critic, 2 partly confirmed, 38
reviewer-only reproduced, 4 reviewer-only from reading.

## 5. Workflow improvements

**Setup.** A fresh clone is missing `.venv/` and `inkstitch/`, and the export
then fails with no message (R4-3). A preflight check at the top of `run.sh`
should list what is missing. Missing `.venv` currently exits 127 with
`.venv/bin/python: No such file or directory`.

**Tests need gitignored inputs.** `tests/smoke_vectorize.sh` and
`qa/regress.sh` read `input/`, `work/` and `patch_descriptions/`, all gitignored,
and carry no fixture of their own (R3-4, R4-14). `.gitignore` already
un-ignores `tools/digitize/tests/`. Commit a small fixture image there, inline
the configs, or have the scripts generate a synthetic input. The gate should
preflight and say what is missing and where to get it.

**One shared flag list.** `run.sh`, `vectorize.py` and `svg_digitize.py` each
keep their own list of value flags. They are in sync at this commit, and that is
what keeps R4-4 and R4-6 dormant. The critic's advice is to export one list
from the Python side rather than hand-maintain it. Moving to `argparse` in both
Python scripts fixes R1-1, R1-6, R2-13 and R4-8 at once, and gives a real
`--help`.

**Docs drift.** The output paths in USAGE and README are wrong (R4-13). USAGE
cites a gitignored artifact as a source (R4-14). The density floor of 0.3 mm is
below Ink/Stitch's 0.378 mm clamp (R1-10). The travel threshold in USAGE and
`regress.sh` disagree, and a row is mislabelled (R3-12). HANDOFF.md and ADR
0002 contradict the shipped code (R2-14). `EMBROIDERY_QUALITY.md` says `--crop`
measures Y from the bottom; `preview.py` implements top-left.

**macOS portability.** `qa/regress.sh:45` uses `readlink -f`, which BSD
`readlink` has no. `run.sh:128` expands `${FLAGS[*]:-none}` under `set -u` with
an empty array, which bash 3.2 treats as unbound. Both are from reading: no
macOS host and no bash 3.2 were available.

### Stale top-level docs

| File | Status | Why |
|---|---|---|
| `HANDOFF.md` | stale, archive candidate | Header says "zero pipeline code written"; `svg_digitize.py` implements the plan |
| `IMPLEMENTATION_SPEC.md` | stale, archive candidate | Step 1 "DONE", steps 3-4 "pending review"; superseded by the shipped raster path and `review.md` |
| `IMPROVEMENTS_SPEC.md` | archive candidate | Planning spec; steps are in the code or superseded; keep as a design record |
| `DIGITIZING_PLAN.md` | archive candidate | Original Scavenger's Daughter plan; superseded by the native SVG path and `review.md` |
| `review.md` | current (record) | Most TL;DR items shipped; a few doc-drift items still open |
| `space_bunny-review.md` | current (record) | Many findings fixed; about a dozen still open |
| `learnings_from_embroidery_projects.md` | current | Sample measurements still cited by USAGE and review |
| `CREDITS.md` | current | Matches the input artwork |

## 6. New function ideas for a non-LLM user

Ranked by value against effort, from R4 scope g.

Already decided for the guided wizard v1 and excluded from this ranking: image
check, hoop presets with fit check, results summary.

| Rank | Idea | Why | Effort |
|---|---|---|---|
| 1 | Friendly preflight: open the image, report format, size, bit depth and distinct colours, warn on 16-bit, CMYK and EXIF, print the real output paths | R4-1, R4-2, R4-13 | M |
| 2 | Real `--help` and argument validation: `argparse` in both scripts, reject unknown flags, validate numerics, verbatim errors | R4-4, R4-5, R4-8, R4-9 | S |
| 3 | Progress and heartbeat lines with elapsed time during digitize and export | R4-12 | M |
| 4 | Surface export failures: print the tail of `work/<base>.err` and exit 1 | R4-3 | S |
| 5 | Normalise common formats in `load_image`: EXIF transpose, 16-bit, CMYK | R4-1 | S |
| 6 | Output-collision guard: derive the stem from the full path, warn before overwriting | R4-10 | S |
| 7 | "Where are my files?" doc section plus a troubleshooting table for the common errors | R4-13, R4-14 | S |
| 8 | `--dry-run`: resolve settings and print output paths without exporting | R4-12 | S |
| 9 | Bundled small demo image plus `run.sh demo`, so the first run always works | a fresh clone has no `input/` or fixtures | S |

## Sewing faults on Scavenger's Daughter

The operator sewed this design in the 260 x 200 mm hoop and reported three faults: some centipede legs are missing, the machine jammed because of density, and the white shading on the centipede was not needed. The centipede satin came out very well. A Sonnet investigator traced each fault on the files below. Full evidence, crops and the top-15 density table are in `docs/review/_parts/FORENSIC-scavenger.md`. Assumption: the sewn file is `output_vp3/Scavenger's Daughter Inverted.vp3` (dated Oct 9, sewn Oct 10, 54,233 stitches); the investigator did not confirm that with the operator.

### 1. Missing legs: removed on purpose by the design step

- The source SVG's green path holds 173 thin leg subpaths (509.5 mm2), but the black ink layer is drawn over them.
- `invert_ink.py:763` (`G = green - ink`, step 4 of the brief) cuts the ink out of the green, because in the inverted design black ink is bare fabric. That removes 167 of the 173 legs (447.6 mm2). They are bare fabric in the VP3.
- Six legs that show in the art were sewn. Two of them lost their thin tail to `_trim_pinched_ends` (`invert_ink.py:409`): one from 15.3 to 8.7 mm, one from 16.0 to 12.1 mm.
- The lost legs are at most 1.4 to 1.75 mm wide (median 0.78 mm, 8 to 9 mm long).
- Ruled out with measurements: the satin gate (it is bypassed at `nodes.py:53`), the speck cutoff, the border, the scale and trims. The plan has 54,141 stitches and so does the VP3.
- Caveat: if the legs were un-hidden, `try_plate_satin` would turn most of them into fills or drop them.
- This is a design decision, not a bug: restoring the legs means drawing green where the source art has black ink.

### 2. Density: where thread piles up

- 361 cells (13.2 percent of all stitches) are above 3 times the median density of 2.22 stitches/mm2, in 198 clusters.
- By stitch points the file passes the check (at most 95 points within 1.5 mm, flag at 140). By thread length it fails: up to 35.4 mm of thread in one 1 mm cell, and 72 cells over 20 mm (flag at 20).
- Worst by thread: the pinched ends of plates, where two or three rows converge (46 to 59 mm per 1.5 mm cell, against a median of 10.5).
- Worst by point count: thin white parts, where 40 percent of the fill top stitches are row-turn stitches under 0.5 mm.
- Row spacing is 0.300 mm on top and 0.900 mm for the underlay, at the documented floor. The `vadmel` profile is never applied to SVG input.
- Stitch counts: white fill 34,470, green satin 11,147, border 6,504, green fill 1,340, locks 680.
- Not known: where the jams happened. The data only shows the dense places.

### 3. White shadows: stitched by design, no switch to skip them

- 30 white fills (167.6 mm2, no underlay) sit in highlight holes of the centipede plates, plus 2 abutting fills.
- They come from the white step at `invert_ink.py:835-840` (`gvis_all` keeps the holes, by design per the brief).
- They cost about 1,133 stitches (2.1 percent; the 207 locks in that figure are an estimate).
- No flag or YAML key skips them. Raising `--min-white-*` would also drop 15 skull fills.
- Smallest change: at `invert_ink.py:839-840` subtract `fill_holes(gvis_all).buffer(...)`. A scratch check gave 96 white fills before and 66 after, exactly those 30, and green thread already covers 100 percent of those areas.

### Confidence

Measured: the leg trace, the stitch counts, the density map, the 30 white fills and the scratch check. Assumed: that "legs" means the thin green legs and antennae and "white shadows" means the plate highlights.