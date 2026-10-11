# CRITIC-1: independent reproduction of the R1 to R4 findings

Commit `a795612`, worktree `.claude/worktrees/review`. Python is `.venv/bin/python -B`.
Everything below was run by me with my own inputs. No repo file was touched
except this one. All scratch is under

`S=/tmp/claude-1000/-home-roman-git-Digitize-patches/ea4b9216-f705-480b-b7f0-ea8fdbedf18b/scratchpad/review/critic1`

`R` is the worktree path. Fix checks were done on copies of the scripts in `$S`,
never in the repo. For `run.sh` I used a copy of `tools/` in `$S/rt` (so
`output_*` and `work/` land in scratch). The overhang harness is `$S/ov/ov.py`
(vectorize, Ink/Stitch export, VP3 bounds, SVG geometry bounds).

## Verdict table

| Finding | Verdict | Evidence in one line | Suggested fix |
|---|---|---|---|
| R1-1 short flag eats value | PARTIAL | Mechanism real. Overwrite only if the first positional is an existing loadable file. Natural `-o out.svg in.png` fails loudly on `vectorize.py`; it destroys `source.svg` on `svg_digitize.py` when `out.svg` already exists | Right (argparse, or exit on unknown short flag). Low risk |
| R1-2 auto palette NaN | CONFIRMED | 3-colour flat image becomes one grey-purple thread not in the art, exit 0 | Right. Tested on a copy: 3 correct colours |
| R1-5 `mode: off` is boolean | CONFIRMED | Bare `off`, `OFF`, `no` keep the border; quoted `"off"` removes it | WRONG as written. Normalisation alone leaves the border on: `str(False).lower()` is `"false"`. With the validation step added, the bare `off` (and the YAML the HTML builder writes) is rejected with an error. Tested on a copy |
| R3-1 HTML emits bare `off` | CONFIRMED | `make_config.html:144` writes `mode: off` unquoted; same YAML result as R1-5 | HTML quoting is right. The loader half has the R1-5 flaw |
| R1-8 EXIF orientation | CONFIRMED | `Orientation=6` 600x300 JPEG is digitised as a 107 x 53 mm landscape; viewers show 300x600 | Right, low risk |
| R2-8 satin gate pre-fit | PARTIAL | Same shape is dropped at 10 mm authoring and kept at 1000 mm. The "kept stroke falls below Ink/Stitch's gate" half is false: the script lowers the gate in metadata | "Move the gate after the fit" is circular (the scale depends on the satins). Needs a two-pass design |
| R3-3 invert_ink border < 1.0 | CONFIRMED | `--border-mm 0.8` exits 0 with no warning; Ink/Stitch sews it as 2.5 mm running stitch | Right (validate or widen). A metadata gate lowering, as in `svg_digitize.py`, is a third option |
| R4-3 export failure hidden | CONFIRMED | Exit 2, screen ends at `== exporting VP3`, reason only in `work/test.err` | Right. Low risk |
| R4-4 value flag not in list | CONFIRMED | Reproduced with an unknown flag. At this commit every value flag of both scripts is in the `run.sh` list, so no current flag triggers it. It is live on `feat/fit-mm` (`--fit-mm` is missing from `run.sh`) | Idea of "unknown flag takes next token" is risky: a typo'd boolean would swallow the image path. Better: one shared flag list |
| R4-13 docs say `work/` | CONFIRMED | Full run writes `output_inkstitch_svg/` and `output_vp3/`; `work/` holds only `.zip` and `.err` | Right |
| R1-3 border on canvas edge | CONFIRMED | Reproduces the +2.9 mm exactly (see Overhang) | Right. Padded EDT gives 100.5 mm instead of 102.9 mm |
| R1-4 pull compensation | CONFIRMED | Border block in the VP3 is exactly 0.4 mm wider than its SVG geometry | "Set `satin_pull_mm` to 0" is risky: the pull is deliberate fabric compensation |

Counts: CONFIRMED 10, PARTIAL 2, NOT REPRODUCED 0, WRONG 0.
Four reviewer fixes are wrong or risky: R1-5 loader fix (wrong), R2-8 fix
(circular), R4-4 fix idea (swallows the image path), R1-4 option "pull to 0"
(shrinks the sewn patch). Overhang explanation: CONFIRMED, with three
corrections (see the last section).

## R1-1 short flag drops its value

PARTIAL. The mechanism is real (`vectorize.py:213-214`, `pass`). The reviewer's
impact line "any user who types `-o OUT IN` loses the second file" is too broad.

Command and output (throwaway copies of a PNG):

```
cp in/patch.png r1/dl/a.png; cp in/patch.png r1/dl/victim.png
$R/.venv/bin/python $R/tools/digitize/vectorize.py -o r1/dl/a.png r1/dl/victim.png
before: 2611 bytes, magic 89504e47
exit=0
after : 5988 bytes, magic 3c3f786d6c   (<?xml, an SVG over a PNG)
```

Natural order, which is what a user types:

```
vectorize.py -o nat/out.svg nat/in.png   (out.svg absent)  -> FileNotFoundError: 'nat/out.svg'
vectorize.py -o nat/out.svg nat/in.png   (out.svg exists)  -> UnidentifiedImageError: 'nat/out.svg'
in.png still png: 89504e47
```

Correct statement: on `vectorize.py` the loss needs the first positional to be
a readable raster. The natural order fails with a traceback and loses nothing.
On `svg_digitize.py` the first positional only has to be a parseable SVG, so a
re-run loses the source:

```
svg_digitize.py --no-border -o nat/out2.svg nat/source.svg   (out2.svg from an earlier run)
exit=0   source bytes before: 253  after: 1505   (source.svg now holds the output)
```

So P0 is fair for `svg_digitize.py` on a second run, P1 for `vectorize.py`.

## R1-2 auto palette NaN

CONFIRMED. I searched random flat 3-colour transparent designs for one that
collapses. Seed 2 does. Drawn colours (30,119,209), (77,87,71), (184,65,253).

```
$R/.venv/bin/python -B $R/tools/digitize/vectorize.py in/collapse3.png r2/collapse3.svg
vectorize.py:579: RuntimeWarning: invalid value encountered in divide
note: image has 1 distinct colours, fewer than --colors 5
image 300x300 -> 111x111 mm (2.7 px/mm), palette k=1
order: ['#7961bb']
```

The one thread is none of the three artwork colours. Frequency, from my batch of
48 synthetic designs run through `load_image` then `auto_palette(px, 5)`:

```
(transparent, drawn colours): [runs, NaN warning, palette smaller than distinct colours]
(False, 2) [8, 0, 0]   (False, 3) [8, 0, 0]   (False, 4) [8, 0, 0]
(True, 2)  [8, 4, 1]   (True, 3)  [8, 3, 3]   (True, 4)  [8, 2, 2]
```

It is data dependent and only seen on transparent art (the median filter in
`load_image` changes the pixel set). Rerun of the batch, 24 transparent and 24
opaque designs, `auto_palette(px, 5)`, colours compared in Lab:

```
transparent designs (24): NaN warning 9, a drawn colour with no palette entry within dE 20: 6,
                          a palette entry more than dE 20 from every drawn colour: 4
opaque designs (24):      NaN warning 0, lost colours 0
```

So about one in four flat transparent designs loses a drawn colour. Not every NaN
warning loses a colour (9 warnings, 6 losses).

Fix check on a copy: in `merge`, `if total <= 0: del cen[j], share[j]; return`.

```
note: image has 3 distinct colours, fewer than --colors 5
palette k=3
order: ['#1e77d1', '#b841fd', '#4d5747']
```

The reviewer's fix works.

## R1-5 and R3-1 `mode: off`

CONFIRMED. Distinct file names per case (my first loop reused one name for
`off` and `"off"`; rerun below is clean).

```
printf 'border:\n  mode: off\n'   > r5/bare.yaml     (also "off" -> quoted.yaml, OFF -> upper.yaml)
vectorize.py --config r5/<case>.yaml in/patch.png r5/<case>_orig.svg
grep -c 'inkscape:label="Border"' r5/<case>_orig.svg

bare    orig  border layers: 1      <- wanted none
quoted  orig  border layers: 0
upper   orig  border layers: 1
```

PyYAML: `off`, `OFF`, `no` give `False`; `none` stays the string `'none'` and also
silently falls through to `auto` (border layers 1).

The reviewer's loader fix is WRONG for the bare case. I applied exactly
`_border_mode = str(_border_cfg.get("mode","auto")).strip().lower()` to a copy:

```
bare    fix   border layers: 1      <- still on, str(False).lower() == "false"
quoted  fix   border layers: 0
upper   fix   border layers: 1
```

Correct fix: map booleans first (`False` to `"off"`, `True` to `"auto"`), then
lower-case and validate against `auto|off|force_black`. With only their
validation step the bare `off` would exit with an error, which is loud but
still rejects the YAML the HTML builder just produced.

R3-1 specifics (read): `make_config.html:55-58` has the `off` option and `:144`
writes `mode: ${...value}` unquoted. `make_config.py:159-161` prints the comment
`# Border: mode = auto | off | force_black` right above `mode: auto`, so a user
who edits it by hand to `off` hits the same trap. Quoting in the HTML is the
correct fix for the builder.

## R1-8 EXIF orientation

CONFIRMED.

```
exif = Image.Exif(); exif[0x0112] = 6; 600x300 RGB JPEG saved with it
raw size (600, 300)  exif tag 6  -> viewers show (300, 600)
vectorize.py r8/exif6.jpg r8/exif6.svg
image 600x300 -> 107x53 mm (5.6 px/mm)
viewBox="0 0 600 300"   width="106.95mm" height="53.48mm"
```

`grep -rn exif tools/digitize/*.py` finds nothing. Fix is right.

## R2-8 satin gate in pre-fit mm

PARTIAL. Test SVGs: a red fill rectangle path plus a blue horizontal stroke,
no border, default `--size-mm` 100.

```
svg_digitize.py --no-border small.svg small.out.svg   (10 mm design, 0.5 mm stroke)
note: dropping sub-gate stroke None (0.500 mm <= 1.0 mm satin gate)
artwork: 10.0 x 5.0 mm -> scaled 100.0 x 50.0 mm (x10.0000)      <- the stroke would be 5 mm

svg_digitize.py --no-border big.svg big.out.svg       (1000 mm design, 2 mm stroke)
1 satin(s) ... artwork: 1002.4 x 751.4 mm -> scaled 100.0 x 75.0 mm (x0.0998)
note: narrowest satin 0.20 mm; min_satin_stroke_width_mm set to 0.1 so it stitches as satin
stroke-width:0.20     <inkstitch:min_satin_stroke_width_mm>0.1

control 100 mm design, 0.5 mm stroke: dropped. 100 mm design, 5 mm stroke: kept (4.74 mm)
```

Holds: the keep/drop decision depends on the authoring scale, not the sewn
width.

Does not hold: "a kept stroke can still fall below Ink/Stitch's gate". The
script lowers `min_satin_stroke_width_mm` to the narrowest satin (line 1604), so
the 0.20 mm stroke stitches as satin. The honest problem is the opposite: a
0.2 mm "satin" is kept at all.

Fix risk: the scale is computed from bounds that include the satin footprints
(`svg_digitize.py:977-985`), and `handle_path` runs before that. "Multiply
`sw_mm` by scale" has no scale to multiply by. It needs a two-pass design, and
dropping a stroke changes the bounds and so the scale.

## R3-3 invert_ink border under 1.0 mm

CONFIRMED. Input: 100x80 mm SVG with a white paper path, a green plate and a
black evenodd ring, run with `--ink "#000000" --plate-satin-colors "#00ff00"
--fit-mm 100x80`.

```
border-mm=0.8  rc=0 border: stroke:#ffffff;stroke-width:0.80 | warning lines: 0
border-mm=0.0  rc=0 border: stroke:#ffffff;stroke-width:0.00 | warning lines: 0
border-mm=-1.0 rc=0 border: stroke:#ffffff;stroke-width:-1.00 | warning lines: 0
border-mm=2.0  rc=0 border: stroke:#ffffff;stroke-width:2.00 | warning lines: 0
```

Rule read in `inkstitch/lib/elements/utils/nodes.py:53`:
`satin_column and (len(path) > 1 or stroke_width > satin_threshold)`. The ring
has one subpath, so 0.8 mm fails the gate. I exported both SVGs and looked at
the last 150 stitches (the border):

```
inv_0.8.vp3 last 150 stitches: median step 2.50 mm, min 0.28 max 2.50   <- running stitch
inv_2.0.vp3 last 150 stitches: median step 2.22 mm, min 0.64 max 2.66   <- satin cross steps
```

A step of exactly 2.50 mm is the Ink/Stitch default running stitch length.

## R4-3 export failure hidden

CONFIRMED. Copy of `tools/` with no `inkstitch/` directory:

```
cd $S/rt && ./tools/digitize/run.sh input/test.png > run.out 2> run.err
exit=2
STDOUT tail: wrote output_inkstitch_svg/test.svg / == exporting VP3
STDERR (screen): (empty)
work/test.zip  0 bytes
work/test.err  .venv/bin/python: can't open file '.../rt/inkstitch/inkstitch.py': [Errno 2] No such file or directory
```

The user sees nothing after `== exporting VP3`. Fix (print `tail work/$BASE.err`,
exit 1) is right.

## R4-4 value flag not in run.sh's list

CONFIRMED, severity depends on the branch.

At `a795612` every value flag of both scripts is in the `run.sh` list (script
comparing `_VALUE_FLAGS` of `vectorize.py` and `svg_digitize.py` with the
`run.sh` case list): `in vectorize but not run.sh: []`, `in svg_digitize but not run.sh: []`.
So no real flag triggers it here. The reviewer's repro used `--fit-mm`, which
does not exist at this commit; it fails the same way for any unknown flag:

```
./tools/digitize/run.sh --no-export --fit-mm 120x120
FileNotFoundError: [Errno 2] No such file or directory: '120x120'
./tools/digitize/run.sh --no-export --colours 4 input/test.png    (typo)
wrote output_inkstitch_svg/test.svg    exit 0, the "4" was silently dropped
```

It is live on `feat/fit-mm`: that branch adds `"--fit-mm"` to `vectorize.py`
`_VALUE_FLAGS` (line 55) and `run.sh` has no `fit` at all.

```
git archive feat/fit-mm tools | tar -x -C rt_fit   (read-only use of the branch)
./tools/digitize/run.sh --no-export --fit-mm 120x120 input/test.png
== digitizing input/test.png -> output_inkstitch_svg/test.svg  (flags: --fit-mm)
error: --fit-mm needs two positive numbers as WIDTHxHEIGHT in mm ..., got 'input/test.png'
exit=2
direct vectorize.py --fit-mm 120x120 ...  -> design size: 120.0 x 120.0 mm  (works)
```

Loud failure, but the documented flag does not work through `run.sh`.
`--fit-mm=120x120` does work. Fix risk: "treat the next token as a value for any
unknown long flag" would let a mistyped boolean swallow the image path. Use one
shared list (export it from `vectorize.py`) or require `--flag=value`.

## R4-13 docs say output lands in work/

CONFIRMED. Full run in `$S/rt` (with `inkstitch` symlinked):

```
./tools/digitize/run.sh input/test.png    exit=0
output_inkstitch_svg/test.svg  output_inkstitch_svg/test_posterized.png
output_vp3/test.vp3  output_vp3/test_stitchplan.png  output_vp3/test_coverage.png
work/test.zip  work/test.err
```

`docs/USAGE.md:17-20,35` and `README.md:65` say `work/<name>.svg` and
`work/<name>.vp3`. `grep -rn "output_inkstitch_svg\|output_vp3" README.md docs/*.md`
finds only `EMBROIDERY_QUALITY.md:463`.

## OVERHANG

### Setup and my numbers

Measure: stitch extent of the VP3 (pystitch bounds, same as
`fit_check.py`; I checked the number is the same before and after
`trim_vp3.py`: 102.9 x 102.9). `fit_check.py` itself needs `--fit-mm`, so I used
`vectorize.py --size-mm N --colors 3` at `a795612`, which maps the design
bounds to N mm. Images are the `edge` design from `fit_check.py` and variants.
Predicted model from R1-3 and R1-4:

```
VP3 extent = D + 2*h + 2*p
D = design bounds (= size-mm)
h = border_mm/2   only if the silhouette touches the canvas edge, else 0
p = 0.2 mm        satin pull compensation, applied to every satin
```

### Table (mm, width x height, all `--size-mm` N unless noted)

| Case | Predicted | Measured VP3 |
|---|---|---|
| `edge` 100, border 2.5 (default) | 100 + 2.5 + 0.4 = 102.9 | 102.9 x 102.9 |
| `edge` 120 | 122.9 | 122.9 x 122.9 |
| `edge` 200 | 202.9 | 203.0 x 202.9 |
| `edge` 100, `--border-mm 1.5` | 101.9 | 101.9 |
| `edge` 100, `--border-mm 4.0` | 104.4 | 104.4 |
| `edge` 100, `--no-border` | 100 (no satin) | 99.7 x 99.6 |
| `edge` on a 1200 px canvas, 100 px margin | 100 + 0.4 = 100.4 | 100.5 x 100.5 |
| red rounded square touching the canvas edge, no dark ring | 102.9 | 102.9 x 103.0 |
| same on a canvas with margin | 100.4 | 100.5 x 100.6 |
| `wide` (10 px margin) | 100.4 | 100.4 wide |
| two 0.75 mm dark lines as top and bottom extremes, border off (`thin.png`, 6 px high) | height 90.0 + 0.45 widening + 0.4 pull = 90.85 | height 91.0 (+1.0 over the 90.0 design); the SVG satins sit 0.29 above and 0.32 below the design, the width model gives 0.225 |
| `spike` (`fit_check.py` design), 100 | height 59.5 + about 0.9 (see below) | 99.9 x 60.3, height +0.8 over the 59.5 design |
| `spike`, 120 | height 71.4 + about 0.9 | 119.8 x 72.3, height +0.9 over the 71.4 design |
| `edge` with the padded-EDT fix (copy of `vectorize.py`) | 100.4 | 100.5 x 100.5 |

The slope is 1.0 mm of overhang per mm of `border_mm` (1.5, 2.5, 4.0 give
101.9, 102.9, 104.4). The overhang is the same at 100, 120 and 200 mm because
`border_mm` is physical. That matches the main session's constant +2.9.

### Where the millimetres are (SVG geometry against VP3 colour blocks, `edge` 100)

SVG user units are pixels (`viewBox 0 0 1000 1000`, `width=100mm`), so 10 px per
mm. The border path centreline spans -0.05 to 99.95 mm and the stroke is
2.5 mm wide.

```
border satin (red, last block):  SVG bbox with half stroke  -1.30..101.20 = 102.5 mm
                                 VP3 block 3                  102.9 mm   (+0.4 = 2 x 0.2 pull)
red fill:    SVG 98.6 mm   VP3 98.7 mm   (+0.1)
dark ring:   SVG 88.0 mm   VP3 88.0 mm   (0.0)
yellow:      SVG 31.3 mm   VP3 31.3 mm   (0.0)
```

So the 2.9 mm is 2.5 mm (the border centred on the canvas edge, stroke sticks
out by 1.25 mm per side, visible in the SVG alone) plus 0.4 mm (pull, visible
only in the VP3). Fills add nothing, so the 0.6 mm underlap does not add overhang.
The extent of the red fill in the VP3 is inside its SVG polygon (+0.1).

Mechanism for the canvas edge: `distance_transform_edt` sees no transparent
pixel beyond the array edge, so `dt > half` removes only the rounded corners;
the traced contour sits at the edge pixel, i.e. -0.5 to 999.5 px.
Applying the reviewer's `np.pad(..., 1)` fix to a copy moves the stroke inside:
satin bbox -0.10..100.00 mm and VP3 100.5 mm.

### The spike case ("+0.8 with a thin protrusion"): reproduced, other cause

Design bounds come from the PNG alpha (script `$S/ov/design_vs_vp3.py`):

```
spike100: design y 3.68..63.19 (h 59.51)
   topmost element  satin w=2.50 (the border)  y_min 3.69  (+0.01 vs design top)
   lowest element   satin w=1.20 (an outline)  y_max 63.67 (+0.49 vs design bottom)
   VP3 w x h = 99.9 x 60.3  -> over design bounds: w -0.10  h +0.79
spike120: design y 4.41..75.82 (h 71.41)
   topmost  satin w=2.50 y_min 4.41 (-0.01)    lowest satin w=1.20 y_max 76.29 (+0.47)
   VP3 w x h = 119.8 x 72.3 -> over design bounds: w -0.20  h +0.89
```

The VP3 height is the SVG geometry plus the pull on both extreme satins:
0.01 + 0.2 + 0.49 + 0.2 = 0.90 predicted, 0.79 and 0.89 measured. The spike
itself is on the other axis and comes out slightly under size. The 0.49 mm comes
from small `w=1.20` satin outlines at the bottom of the circle that reach past
the silhouette and past the border's outer edge (63.18). The fill slivers they
belong to end at 63.04, so the overshoot is bigger than "widened to 1.2 mm"
alone explains. I did not chase why the satin centreline sits about 0.4 mm
lower than the sliver. Neither reviewer list names this mechanism.

### Verdict: CONFIRMED, with three corrections

The model `D + 2h + 2p` predicts the edge-touching and margin cases to 0.1 mm
(+2.9, +0.4 to +0.5). For thin features it needs the satin geometry as it is in
the SVG: thin-line case within 0.15 mm, spike within 0.1 mm once the 0.49 mm
sliver overshoot is included.

Correction 1 (the main session's attribution). It is not the artwork's "own dark
border ring". A plain red rounded square touching the canvas edge with no ring
gives the same 102.9 x 103.0. The trigger is that the silhouette touches the
canvas edge. Margins of 10 px (`wide`) and 100 px (`edge` on a larger canvas)
both give the normal +0.4. I did not test a 1 px margin; by the code, one
transparent pixel next to the edge should be enough for the distance transform.

Correction 2 (R1-3 secondary list). Not everything in it is an overhang.
- Pull 0.2 per side: confirmed (above).
- Widening an outline stroke to `SATIN_MIN_MM` 1.2: confirmed in direction. A
  0.75 mm line becomes a 1.2 mm satin: 0.225 per side by the model, 0.29 to 0.32
  measured in the SVG, plus 0.2 pull.
- Free-end extension of 0.3 mm (`skeleton.py:22`): not supported as an
  overhang. The thin lines run 100.2 mm in the VP3 for a 100.0 mm design (+0.2),
  and the `spike` design is shorter than its bounds in x (99.9 for 100, 119.8
  for 120). The skeleton ends sit about half a width inside the tip and the
  extension closes that gap.

Correction 3 (a mechanism the reviewers missed). Thin satin outlines at the
silhouette edge can reach 0.5 mm past the silhouette (the spike case). They are
what the main session saw as "+0.8 with a thin protrusion". The protrusion
(the spike) is not the cause.

Residual of at most 0.1 mm comes from the half-pixel offset of the traced
contour (-0.05 mm), the 0.1 mm VP3 coordinate step and polygon simplification.

### Fix notes

- R1-3 fix is right and low risk for the border itself. After it, the edge
  case is 100.5 mm. It changes the output of every design that touches the canvas
  edge, so rerun the regression gate.
- R1-4: the stitched VP3 is larger than the drawn geometry on purpose. Fabric
  pulls a satin column narrower, so the compensated file sews out near the drawn
  size. Setting `satin_pull_mm` to 0 makes the VP3 fit-exact and the sewn patch
  about 0.4 mm smaller. If a hoop limit matters, budget `2 x 0.2` (and the
  widening) in the fit maths, as `svg_digitize.py:984-986` already does.

## Side effect to know about

Each Ink/Stitch export appends to `inkstitch/inkstitch.log`. The `inkstitch`
symlink points to the main checkout, so my exports wrote there (the file is
gitignored by `inkstitch/` and is now about 65 MB; the reviewers' and the main
session's exports write to it too). I used `-B` and `PYTHONDONTWRITEBYTECODE=1`
to avoid `.pyc` files. Nothing else outside `$S` and this file was written.
