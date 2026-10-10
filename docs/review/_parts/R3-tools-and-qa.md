# R3: tools and QA (invert_ink, swatch, preview, analyze, make_config, qa/, tests/, wxstub)

Scope: `tools/digitize/invert_ink.py`, `swatch.py`, `preview.py`, `analyze.py`,
`make_config.py`, `make_config.html`, `tools/digitize/qa/*`, `tools/digitize/tests/smoke_vectorize.sh`,
`tools/wxstub/wx/__init__.py`. Checkout `a795612`. All probes under
`$SCRATCH=/tmp/claude-1000/.../scratchpad/review/R3`.

## Summary

| ID | Sev | file:line | claim | status |
|----|-----|-----------|-------|--------|
| R3-1 | P1 | `make_config.html:144` + `vectorize.py:341,672` | The HTML "off (no border)" option emits unquoted `mode: off`; the loader never normalises it, so the border stays on | VERIFIED |
| R3-2 | P1 | `qa/pullsim.py:90-103` | pullsim draws a rail satin as one hairline per rail (its stroke-width), so a correctly-covered band reports ~97-100% uncovered | VERIFIED |
| R3-3 | P1 | `invert_ink.py:980-982` | A single-subpath border satin below Ink/Stitch's 1.0 mm gate is emitted with no widening and no warning, so `--border-mm 0.8` silently becomes running stitch | VERIFIED |
| R3-4 | P2 | `tests/smoke_vectorize.sh:8`, `qa/regress.sh:52-54,116-117` | Every input the only test and the QA gate read lives in a gitignored dir, so a fresh clone can not run either | VERIFIED |
| R3-5 | P2 | `make_config.py:130-152` | The generated `order:` still lists the background colour, which `vectorize.py` discards (earlier #45) | VERIFIED |
| R3-6 | P2 | `invert_ink.py:643-645` | `--fit-mm` without an `x` raises `IndexError`; the `len(fit) > 2` branch is dead | VERIFIED |
| R3-7 | P2 | `invert_ink.py:639,975,980` | `--paper` only selects the excluded colour; the emitted paper fill and border are hardcoded `#ffffff` | VERIFIED |
| R3-8 | P2 | `swatch.py:54,199` | The swatch raises `min_satin_stroke_width_mm` to 0.5 (production is 1.0) and its legend claims a fill angle its frames do not use | VERIFIED |
| R3-9 | P2 | `wxstub/wx/__init__.py:43-65,81-125` | The wx stub never fails: any attribute, call or comparison returns a truthy, equal-everything stand-in | VERIFIED |
| R3-10 | P2 | `analyze.py:23,41-43` | `analyze.py` still uses MEDIANCUT and "lightest = background", so its palette and components do not match the pipeline (earlier #48) | READ-ONLY |
| R3-11 | P2 | `make_config.py:63-64` | `SIZE_MM` and `BORDER_MM` are dead constants left over from the old ring logic | READ-ONLY |
| R3-12 | P2 | `qa/regress.sh:108,117` | Doc drift: USAGE says exposed travel "> 3 mm" but the gate uses 4.5, and the "goat" row is actually midnight-epicure | READ-ONLY |

---

## R3-1 P1: `mode: off` from the HTML config builder is a YAML boolean and the border stays on

**What is wrong.** `make_config.html:144` writes the border mode unquoted:
`L.push(\`  mode: ${document.getElementById('borderMode').value}\`)`. The dropdown
has `<option value="off">off (no border)</option>` (`:57`). PyYAML parses bare
`off` as boolean `False`. On the loader side `vectorize.py:341` reads it with no
normalisation (`_border_mode = _border_cfg.get("mode", "auto")`) and `:672`
tests `settings.border_mode == "off"`, which is `False` for a boolean, so the
border is never disabled. The Python generator (`make_config.py:161`) now
hardcodes `mode: auto` and no longer offers `off`, but the HTML still does.

**Impact.** The one control whose whole purpose is to disable the border does
nothing, silently: the operator gets a satin border on a design that asked for
none, and the outer ring also re-enters the interior palette.

**Reproduce.**

```bash
.venv/bin/python - <<'PY'
import yaml
for t in ["border:\n  mode: off\n", 'border:\n  mode: "off"\n']:
    m = yaml.safe_load(t)["border"].get("mode","auto")
    print(repr(t), "-> mode =", repr(m), "== 'off'?", m=="off")
PY
# end-to-end: 64x64 transparent patch, clip in $SCRATCH
for cfg in off_bare off_quoted; do
  .venv/bin/python tools/digitize/vectorize.py --colors 3 --size-mm 50 \
    --config "$SCRATCH/$cfg.yaml" "$SCRATCH/patch.png" "$SCRATCH/out_$cfg.svg"
  echo "$cfg border_layer=$(grep -c 'label="Border"' "$SCRATCH/out_$cfg.svg")"
done
```

```
'border:\n  mode: off\n' -> mode = False == 'off'? False
'border:\n  mode: "off"\n' -> mode = 'off' == 'off'? True
off_bare border_layer=1
off_quoted border_layer=0
```

**Fix.** Quote it in the HTML (`mode: "${...value}"`) and normalise/validate in
the loader: `_border_mode = str(_border_cfg.get("mode","auto")).strip().lower()`,
then reject anything outside `auto|off|force_black`.

---

## R3-2 P1: pullsim mis-measures rail satins

**What is wrong.** `qa/pullsim.py:90-103` handles any `inkstitch:satin_column`
by drawing each subpath as a line of width
`stroke-width + 2*pull_compensation - 2*satin_pull`. That is correct only for a
single centreline satin, where `stroke-width` is the full band width. A rail
satin (2 or more subpaths, `stroke-width` near 0) is drawn as a few hairlines,
so the band interior is reported as bare. `invert_ink.py:968` (plate satins,
`stroke-width:0.1`), `svg_digitize.py` authored satins, and any hand-drawn
Ink/Stitch satin are rail satins. The docstring scopes pullsim to "raster-path
SVGs", but those files are also M/L/Z paths, so a user will run it on them.

**Impact.** The seam metric is meaningless for rail-satin designs: a
correctly-stitched band reports ~97-100% uncovered and a red map, so the number
can not be trusted.

**Reproduce.**

```bash
.venv/bin/python - "$SCRATCH" <<'PY'
import sys; from PIL import Image, ImageDraw
d=sys.argv[1]
im=Image.new("RGBA",(400,200),(0,0,0,0))
ImageDraw.Draw(im).rectangle([50,70,350,130], fill=(0,255,0,255))
im.save(d+"/band_keyed.png")
h='<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkstitch="http://inkstitch.org/namespace" width="40mm" height="20mm" viewBox="0 0 40 20"><path style="fill:none;stroke:#000000;stroke-width:%s" inkstitch:satin_column="true" inkstitch:pull_compensation_mm="0.15 0.15" d="%s"/></svg>'
open(d+"/rail_satin.svg","w").write(h%("0.1","M 5.00,7.00 L 35.00,7.00 M 5.00,13.00 L 35.00,13.00"))
open(d+"/cl_satin.svg","w").write(h%("6","M 5.00,10.00 L 35.00,10.00"))
PY
.venv/bin/python tools/digitize/qa/pullsim.py "$SCRATCH/rail_satin.svg" "$SCRATCH/band_keyed.png"
.venv/bin/python tools/digitize/qa/pullsim.py "$SCRATCH/cl_satin.svg"   "$SCRATCH/band_keyed.png"
```

```
rail (2 subpaths, sw=0.1): fill pull 0.25 / satin pull 0.15 : uncovered 100.00%
centerline (1 subpath, sw=6): fill pull 0.25 / satin pull 0.15 : uncovered  0.00%
```

**Fix.** When a satin has 2+ subpaths, treat the first two as rails and fill the
polygon between them (rails plus rungs), instead of stroking each rail.

---

## R3-3 P1: invert_ink emits a sub-gate border satin silently

**What is wrong.** The border is a single closed subpath (`ring_d`,
`invert_ink.py:982`). Ink/Stitch decides satin vs running at
`inkstitch/lib/elements/utils/nodes.py:53`, where a single-subpath satin needs
`stroke_width > satin_threshold` (default 1.0 mm,
`inkstitch/lib/utils/settings.py:12`). `invert_ink.py:980-981` writes
`stroke-width:{args.border_mm}` with no clamp and no warning. The rest of the
pipeline guards this: `vectorize.py:1410-1416` prints a warning when a satin is
at or below the gate, and `svg_digitize.py:893` widens a single-subpath satin to
1.5 mm. invert_ink does neither.

**Impact.** `--border-mm 0.8` silently produces a running-stitch border instead
of a satin one, and `0` / negative produce `stroke-width:0.00` /
`stroke-width:-1.00`. Exit 0, no message. Default 2.0 is safe.

**Reproduce.**

```bash
for bm in 0.8 0.0 -1.0 2.0; do
  .venv/bin/python tools/digitize/invert_ink.py --ink "#000000" \
    --plate-satin-colors "#00ff00" --border-mm "$bm" --fit-mm 100x80 \
    "$SCRATCH/art.svg" "$SCRATCH/inv_bm$bm.svg" >"$SCRATCH/inv_bm$bm.log" 2>&1
  echo "border-mm=$bm rc=$? border $(grep -oE 'stroke-width:[-0-9.]+' "$SCRATCH/inv_bm$bm.svg" | tail -1) warnings=$(grep -icE 'warning|gate' "$SCRATCH/inv_bm$bm.log")"
done
```

```
border-mm=0.8 rc=0 border stroke-width:0.80 warnings=0
border-mm=0.0 rc=0 border stroke-width:0.00 warnings=0
border-mm=-1.0 rc=0 border stroke-width:-1.00 warnings=0
```

**Fix.** Validate `--border-mm >= 1.0` and print the same gate warning
`vectorize.py` uses (or widen to 1.05-1.5 mm, like `svg_digitize.py`).

---

## R3-4 P2: a fresh clone can not run the only test or the QA gate

**What is wrong.** `smoke_vectorize.sh:8` reads `input/earth.jpg`;
`regress.sh:52-54` read three files under `input/` and `:116-117` read
`work/book_burner.yaml` and `patch_descriptions/border_black.yaml`. All of
`input/` (`.gitignore:12`), `work/` (`:19`) and `patch_descriptions/` (`:16`)
are gitignored, and `.venv/` (`:2`) and `inkstitch/` (`:6`) are needed too. This
worktree only runs the smoke test because `input/` and `.venv` are symlinks to
the main checkout; the two YAML configs do not even exist here. The tests carry
no fixtures of their own (the earlier `.gitignore` fix at `:37-38` un-ignores
`tools/digitize/tests/`, but no fixture was added).

**Impact.** CI or a second machine gets `FileNotFoundError` /
`key_background.py: no such file` and the suite is not runnable or portable.

**Reproduce.**

```bash
git check-ignore -v input/earth.jpg work/book_burner.yaml patch_descriptions/border_black.yaml
git ls-files --error-unmatch work/book_burner.yaml   # not tracked
```

```
input/earth.jpg                 .gitignore:12:input/
work/book_burner.yaml           .gitignore:19:work/
patch_descriptions/...yaml      .gitignore:16:patch_descriptions/
error: pathspec 'work/book_burner.yaml' did not match any file(s) known to git
```

**Fix.** Commit a small fixture image under `tools/digitize/tests/fixtures/`
(already un-ignored) and inline the configs, or have the scripts generate a
synthetic input instead of reading `input/`.

---

## R3-5 P2: make_config still lists the background colour in `order:`

**What is wrong.** `make_config.py:130-152` clusters the whole silhouette and
writes every centroid into `order:`. For an opaque image the background is a
cluster too, and `vectorize.py:830` drops it (`background (skip)`). So the
generated list names a colour the pipeline discards. This is earlier finding
#45, unchanged after the palette-pinning work.

**Impact.** The user is handed an `order:` with a dead entry that does nothing,
and on a degenerate palette it can also repeat (the auto palette returned
`#e1bfd1` twice for a 3-colour input).

**Reproduce.**

```bash
PYTHONPATH=tools/digitize .venv/bin/python tools/digitize/make_config.py \
  input/earth.jpg --colors 4 --out "$SCRATCH/earth.yaml"
sed -n '/^order:/,/^skip_colors:/p' "$SCRATCH/earth.yaml"
.venv/bin/python tools/digitize/vectorize.py --colors 4 --size-mm 60 \
  input/earth.jpg "$SCRATCH/earth_out.svg" | grep -E "background|order:"
```

```
order:
  - '#fefefe'
  - '#54a342'
  - '#0776b9'
  - '#010101'
  background (skip) = (254,254,254)
order: ['#54a342', '#0776b9', '#010101']
```

**Fix.** Mirror `vectorize.py`'s background detection (border-contact or the
same luma/alpha rule) and drop the background and empty centroids before
writing `order:`.

---

## R3-6 P2: `invert_ink.py --fit-mm` without an `x` crashes

**What is wrong.** `invert_ink.py:643-645` splits on `x` then indexes `[1]`
without checking the length. `--fit-mm 100` raises `IndexError`. The
`if len(fit) > 2:` branch is dead (it reassigns `fit_h` to the value already
parsed from `fit[1]`).

**Impact.** A malformed `--fit-mm` gives a raw traceback instead of a usage
error; a third dimension is silently ignored.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/invert_ink.py --ink "#000000" \
  --plate-satin-colors "#00ff00" --fit-mm 100 "$SCRATCH/art.svg" "$SCRATCH/inv_bad.svg"
```

```
  File ".../tools/digitize/invert_ink.py", line 644, in main
    fit_w, fit_h = float(fit[0]), float(fit[1])
IndexError: list index out of range
```

**Fix.** Validate the split (`try: fit_w, fit_h = (float(v) for v in fit)`
with a `sys.exit` on a bad count) and delete the dead `len(fit) > 2` branch.

---

## R3-7 P2: `--paper` does not set the emitted paper colour

**What is wrong.** `invert_ink.py:639` uses `--paper` only to exclude that
colour from `art_parts`. The paper fill (`path_fill("#ffffff", ...)`, `:975`)
and the border stroke (`:980`) are hardcoded `#ffffff`, so an off-white paper
still emits white thread. The docstring presents `--paper` as "paper colour",
which reads as the fill colour.

**Impact.** A second user with an off-white paper cannot choose the fill/first
thread colour from the CLI; they must post-edit the SVG or add a parsing
wrapper.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/invert_ink.py --ink "#000000" --paper "#f0f0e0" \
  --plate-satin-colors "#00ff00" --fit-mm 100x80 "$SCRATCH/art2.svg" "$SCRATCH/inv_paper.svg"
grep -oE 'fill:#[0-9a-f]{6}|stroke:#[0-9a-f]{6}' "$SCRATCH/inv_paper.svg" | sort | uniq -c
```

```
      1 fill:#00ff00
      1 fill:#ffffff      <- --paper was #f0f0e0
      1 stroke:#ffffff
```

**Fix.** Emit `path_fill(paper, ...)` and colour the border from the paper/plate
variable instead of the literal `#ffffff`.

---

## R3-8 P2: the swatch calibrates under a laxer satin gate than production, and its legend is wrong

**What is wrong.** `swatch.py:54` writes
`min_satin_stroke_width_mm = 0.5` into the metadata, below the production
default of 1.0 (`settings.py:12`). This is what lets the 1.0 mm satin column
pass Ink/Stitch's strictly-greater gate; the swatch therefore measures satin
behaviour that production will not reproduce. Separately, the legend says
"Fill angle 0 everywhere" (`swatch.py:199`) while every dark frame is emitted at
`FRAME_ANGLE = 90` (`:38,130,143`).

**Impact.** The calibration sew-out can pick a satin width/underlay that behaves
differently in production, and the legend mis-describes the seams under test.

**Reproduce.**

```bash
.venv/bin/python tools/digitize/swatch.py --out "$SCRATCH/swatch.svg"
grep -n "Fill angle 0 everywhere" "$SCRATCH/swatch_legend.md"
grep -oE '<inkstitch:min_satin_stroke_width_mm>[^<]*' "$SCRATCH/swatch.svg"
```

```
4:Canvas 96.0 x 70.5 mm. Fill angle 0 everywhere.
<inkstitch:min_satin_stroke_width_mm>0.5
```

**Fix.** Drop the metadata override (or set it to 1.0) so the swatch uses the
production gate, and say "light fills angle 0, frames angle 90" in the legend.

---

## R3-9 P2: the wx stub never fails when Ink/Stitch needs something it lacks

**What is wrong.** `tools/wxstub/wx/__init__.py` makes every attribute resolve
to a fresh metaclass (`_Meta.__getattr__`, `:52`), makes every comparison true
(`__eq__` `:43`, `__ne__` `:46`, `__hash__` `:49`), every value truthy
(`__bool__` `:64`), and every call return an always-truthy `_Instance` (`:15,
81-125`). So a dialog choice (`if wx.MessageBox(...) == wx.NO`) always takes the
positive branch and a missing constant is silently satisfied rather than
raising. Only `int()`/uses needing a numeric protocol raise, and only because
the stand-in lacks `__int__`.

**Impact.** For headless export this is the intended trade (the GUI is unused),
but any code path that needs a real wx value silently no-ops instead of failing
loudly, so a broken assumption is hidden. There is no allow-list of the handful
of wx names export actually touches.

**Reproduce.**

```bash
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0,"tools/wxstub"); import wx
print("bool(wx.anything) =", bool(wx.anything))
print("wx.YES == wx.NO ->", wx.YES == wx.NO)
print("wx.MessageBox() == wx.NO ->", wx.MessageBox("x") == wx.NO)
try: int(wx.CONST)
except Exception as e: print("int(wx.CONST):", type(e).__name__)
PY
```

```
bool(wx.anything) = True
wx.YES == wx.NO -> True
wx.MessageBox() == wx.NO -> True
int(wx.CONST): TypeError
```

**Fix.** Keep the permissive import surface but make the stub record every name
requested and print a warning on first access, so a new wx dependency shows up
instead of silently resolving.

---

## R3-10 P2: analyze.py is stale against the pipeline it debugs (earlier #48)

**What is wrong.** `analyze.py:23` quantizes with `Image.MEDIANCUT` and `:41-43`
classifies the background as the lightest colour. Neither matches
`vectorize.py` (S3 Lab auto palette, border/alpha background detection), and it
uses raw `sys.argv` with a hardcoded `work/` output dir (`:19`). READ-ONLY: the
findings are from reading; running it writes `work/` and needs an input, so it
was not executed here.

**Impact.** Debugging against it gives a palette and component counts that do
not correspond to what the pipeline produces. Still referenced from
`README.md` / `docs/USAGE.md`.

**Fix.** Either share `vectorize.auto_palette` and its background rule, or state
plainly in `USAGE.md` that it is an approximation.

---

## R3-11 P2: make_config.py dead constants

**What is wrong.** `make_config.py:63-64` define `SIZE_MM = 100.0` and
`BORDER_MM = 2.5`. Neither is referenced anywhere in the file now that it calls
`vectorize.auto_palette`; they are leftovers from the old ring-exclusion code
(which also made the palette diverge from `vectorize.py`). READ-ONLY (grep).

**Impact.** None functional; a reader may assume they affect the generated
config.

**Fix.** Delete both lines.

---

## R3-12 P2: regress.sh doc drift and a mislabelled row

**What is wrong.** `docs/USAGE.md:200` says the gate reports "exposed travel
> 3 mm", but `regress.sh:108` runs `travelmap.py --red-mm 4.5` and the header
says ">4.5mm". Separately, `regress.sh:117` labels the midnight-epicure keyed
image "goat" (`run_design "goat" goat "$OUT/me_keyed.png"`). READ-ONLY.

**Impact.** The documented threshold does not match the gate, and the table row
names a design it does not run, which confuses comparisons against older
results.

**Fix.** Pick one threshold, use it in both places, and rename the row to
"midnight epicure" (or point it at the real goat input).

---

## Still open from earlier reviews

- **#6 / #7 / #44 `border.mode`**: still open. The loader (`vectorize.py:341`)
  still does not normalise or validate, and `make_config.html:144` still emits an
  unquoted value. `make_config.py:161` changed to a hardcoded `mode: auto` (the
  `off` option is gone from the Python template only). See R3-1.
- **#45 `make_config.py` `order:` lists the background**: still open. See R3-5.
- **#48 `analyze.py` stale (MEDIANCUT, lightest = background)**: still open. See
  R3-10.
- **#37 `.gitignore` blocks test fixtures**: partly fixed. `:37-38` now
  un-ignore `tools/digitize/tests/`, but no fixture was added, and the tests
  still read gitignored `input/` and `work/` (R3-4).

## Checked and fine

- **preview.py units, crop and thread width.** Ran on a real VP3
  (`preview.py earth.vp3 ... --crop 0,0,15,10 --thread-mm 0.4`): the reported
  size matches the stitch bbox (60.5 x 60.4 mm), the crop uses a top-left origin
  (image convention), and `thread_mm * 10 * scale` gives the correct px width.
  No unit bug found.
- **make_config.html YAML other than `border.mode`.** `order:`, `skip_colors:`,
  `density:` (quoted hex keys), `trim: enabled/threshold_mm` and
  `border.thickness_mm` are all consumed by the loader (`vectorize.py:335-342,
  360-376`). Only the unquoted `mode` value is a problem (R3-1).
- **invert_ink.py on a generic 3-colour SVG.** Runs end to end, prints parse
  and area diagnostics, exits loudly on missing ink or missing art
  (`sys.exit("error: no ink geometry found...")`), and has no hardcoded absolute
  paths (`qa/export.sh` is likewise now repo-relative, the old hardcoded
  `cd /home/roman/...` is gone). The remaining genericity issues are R3-3, R3-6,
  R3-7 and the cosmetic naming (layer id/label `green`, variables `green_*`,
  `--fit-mm` default `260x200`, `--skip-outline-label Outline`).
- **swatch.py stitch order and emission.** The dark layer is emitted before the
  light layer (`swatch.py:183-189`), so the frame sews first as documented, and
  the SVG carries `inkstitch_svg_version` 4.
- **wxstub deep submodule imports.** `import wx`, `wx.lib`, `wx.lib.agw.aui`
  all resolve (re-confirmed indirectly; unchanged since the previous review).
