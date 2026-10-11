# R1: raster path core (`vectorize.py`, `skeleton.py`, `key_background.py`, `trim_vp3.py`)

Commit `a795612`. Scope: the raster path. The two earlier reviews (`review.md`,
`space_bunny-review.md`) describe a ~900 line `vectorize.py`; at this commit it is
1553 lines and has been split into functions behind `main()`, so several of their
findings are fixed and are not repeated here (see "Still open" for the ones that
survived). All scratch output is under
`SCRATCH=/tmp/claude-1000/-home-roman-git-Digitize-patches/ea4b9216-f705-480b-b7f0-ea8fdbedf18b/scratchpad/review/R1`
(exported as `$S` in the commands). Line numbers are from this worktree.

VERIFIED = I reproduced it with the command shown. READ-ONLY = from reading the
code or its consumer in `inkstitch/`.

## Summary

| ID | Sev | file:line | Claim | Status |
|---|---|---|---|---|
| R1-1 | P0 | `vectorize.py:213-214` | Short flags are dropped without consuming their value, so `-o a.png victim.png` reinterprets the positionals and overwrites `victim.png` with SVG (silent, exit 0) | VERIFIED |
| R1-2 | P0 | `vectorize.py:577-581` (call site 551-554) | S3 auto palette merges two empty clusters, divides `0/0` into NaN, and collapses a low-colour artwork to a single thread colour | VERIFIED |
| R1-3 | P1 | `vectorize.py:677-704` | When the silhouette touches the canvas border, the distance transform is blind to the outside, erosion removes nothing, and the satin border is centred on the very edge: `border_mm/2` is stitched off the patch each side | VERIFIED |
| R1-4 | P1 | `vectorize.py:1418` + `inkstitch/lib/elements/satin_column/satin_column.py:218-232` | Every satin (outline and border) carries `pull_compensation_mm="0.2 0.2"`, which Ink/Stitch applies outward from the centreline at export: +0.2 mm per side beyond the SVG geometry | READ-ONLY |
| R1-5 | P1 | `vectorize.py:341`, `672` | `border: mode: off` is YAML boolean `False`, so the border is never disabled; typos like `FORCE_BLACK` silently behave as `auto` | VERIFIED |
| R1-6 | P1 | `vectorize.py:204-212`, `278-338` | `--flag=value` on booleans is ignored; a value-less `--colors` becomes `int(True)=1` (one-thread design, exit 0) | VERIFIED |
| R1-7 | P1 | `vectorize.py:907-909` | Opaque art drops the globally lightest cluster as "paper", which can be a real accent colour; the actual background is stitched as a fill | VERIFIED |
| R1-8 | P1 | `vectorize.py:442` | EXIF orientation is ignored, so a phone photo tagged `Orientation=6` is digitised 90 degrees from what any viewer shows | VERIFIED |
| R1-9 | P2 | `vectorize.py:289`, `344-345` | `satin_max_mm:` in YAML is never read (only `--satin-max-mm`) | VERIFIED |
| R1-10 | P2 | `vectorize.py:411-414` | `--density -1` emits `row_spacing_mm="-1.0"` with only a printed warning; Ink/Stitch silently clamps to 0.378 mm | VERIFIED |
| R1-11 | P2 | `vectorize.py:221-225`, `936`/`941` | A missing `--config` is silently ignored; a non-mapping YAML dies with a raw `AttributeError`; `order:`/`skip_colors:` hexes without `#` are silently ignored | VERIFIED |
| R1-12 | P2 | `vectorize.py:1515` | `write_preview` uses `rsplit(".",1)[0]`, so the posterized PNG lands in a parent directory when the output path has a dot in a directory name | VERIFIED |

## R1-1. P0: short flags cause silent data loss

**What is wrong.** `parse_args` (`vectorize.py:213-214`) discards any `-x` short
flag *without consuming its value*:

```python
elif a.startswith("-") and a != "-":
    pass  # ignore short flags
```

So in `vectorize.py -o a.png victim.png`, `-o` is dropped and the two positionals
become `args[0]=a.png` (input) and `args[1]=victim.png` (output). `main` then
writes the SVG with `open(out, "w")` (`:1501`), truncating `victim.png`.

**Impact.** `-o` is the most natural short flag for "output". Any user who types
`-o OUT IN` loses whatever file is named second. Exit code 0, no warning. This is
the still-open finding #1 from `space_bunny-review.md` and it is unchanged.

**Reproduce.**
```bash
$S=/tmp/claude-1000/-home-roman-git-Digitize-patches/ea4b9216-f705-480b-b7f0-ea8fdbedf18b/scratchpad/review/R1
R=/home/roman/git/Digitize_patches/.claude/worktrees/review
cd $S && rm -rf dl && mkdir dl && cp in/patch.png dl/a.png && cp in/patch.png dl/victim.png
stat -c%s dl/victim.png; head -c4 dl/victim.png | xxd -p
$R/.venv/bin/python $R/tools/digitize/vectorize.py -o dl/a.png dl/victim.png
stat -c%s dl/victim.png; head -c4 dl/victim.png | xxd -p
```
Verbatim:
```
victim before: 4446 bytes magic=89504e47
exit=0  (stdout: wrote dl/victim.png)
victim after : 3525 bytes magic=3c3f786d   <- "<?xm", SVG over a PNG
```

**Fix.** Convert `parse_args` to `argparse` (rejects unknown flags, gives
`-o/--out`, prints usage). Stopgap: `sys.exit(f"error: unknown option {a!r}")`
for any unmatched `-x` instead of `pass`.

## R1-2. P0: S3 auto palette collapses a low-colour image to one colour

**What is wrong.** `auto_palette` over-clusters to `max(2N,16)` and agglomeratively
merges. `merge` (`vectorize.py:577-581`) divides by `share[i]+share[j]`:

```python
def merge(i, j):
    total = share[i] + share[j]
    cen[i] = (cen[i] * share[i] + cen[j] * share[j]) / total
```

When `kmeans2` returns empty over-clusters (any image with fewer than ~16 distinct
colours), their `share` is `0.0` (`:552-554`). Merging two of them divides `0/0`,
emits `RuntimeWarning: invalid value encountered in divide` at line 579, and sets
the centroid to NaN. The NaN then dominates the distance comparisons, `min()`
returns whatever order NaN lands in, and the palette collapses to duplicate
centroids. `build_palette` then dedupes them (`:843-853`) to a single colour, which
prints as "image has 1 distinct colours".

**Impact.** A flat, poster-style raster with a handful of colours (no anti-alias
gradient) silently becomes a one-thread design with a colour that is not in the
artwork. `--palette-mode auto` is the default, so this hits the default path.
Also a determinism hazard: `min()` over NaN keys is order dependent.

**Reproduce.**
```bash
cd $S && rm -rf n1 && mkdir n1
$R/.venv/bin/python - <<'PY'
from PIL import Image, ImageDraw
im = Image.new("RGBA",(400,400),(0,0,0,0)); d=ImageDraw.Draw(im)
d.ellipse([20,20,380,380], fill=(20,20,20,255))
d.ellipse([50,50,350,350], fill=(200,40,40,255))
d.ellipse([110,110,290,290], fill=(240,230,60,255))
d.rectangle([140,194,260,206], fill=(20,20,20,255))
im.save("n1/flat4.png")
PY
$R/.venv/bin/python $R/tools/digitize/vectorize.py n1/flat4.png n1/flat4.svg >n1/v.log 2>&1; echo exit=$?
grep -E "invalid value|distinct colours|palette k=|^order:" n1/v.log
```
Verbatim:
```
exit=0
vectorize.py:579: RuntimeWarning: invalid value encountered in divide
note: image has 1 distinct colours, fewer than --colors 5
palette k=1
order: ['#965428']      <- grey-brown average; none of the 3 artwork colours
```

**Fix.** Never divide by zero: when `total <= 0`, delete one of the two clusters
instead of averaging (`del cen[j], share[j]; return`), or filter zero-share
clusters before `closest_pair`. Drop empty over-clusters up front.

## R1-3. P1: border satin overhangs when the silhouette touches the canvas edge (the overhang source)

**What is wrong.** `detect_border` insets the satin centreline by eroding the
silhouette with the distance transform (`vectorize.py:677-684`):

```python
dt = ndimage.distance_transform_edt(img.silhouette)
half = int(round(scale.border_px / 2))
eroded = img.silhouette & (dt > half) if half > 0 else img.silhouette
```

`distance_transform_edt` measures distance to the nearest *transparent* pixel. When
the artwork fills the canvas (its silhouette touches the image border, the normal
case for a cropped patch or a drawn border ring at the canvas edge) there is no
transparent pixel just outside the straight edges. `dt` near those edges is then
large, `dt > half` removes almost nothing, and the traced contour sits on the
silhouette boundary rather than `border_px/2` inside it. The emitted stroke is
centred there, so half the border width is stitched *outside* the artwork.

**Impact.** The stitched extent exceeds the requested size by `border_mm` for a
patch whose silhouette reaches the canvas border, and part of the border thread is
sewn onto bare fabric. This is the residual of `space_bunny-review.md` #3 (which
fixed the ordinary case by adding the erosion); the canvas-edge case still fails.

**Reproduce.**
```bash
cd $S && mkdir -p fx
$R/.venv/bin/python - <<'PY'
from PIL import Image, ImageDraw
im=Image.new("RGBA",(1000,1000),(0,0,0,0)); d=ImageDraw.Draw(im)
d.rounded_rectangle((0,0,999,999),radius=60,fill=(192,57,43,255))
d.rounded_rectangle((60,60,939,939),radius=40,outline=(26,26,26,255),width=40)
d.ellipse((350,350,650,650),fill=(241,196,15,255))
im.save("fx/edge.png")
PY
$R/.venv/bin/python $R/tools/digitize/vectorize.py --size-mm 120 --colors 3 fx/edge.png fx/edge.svg >fx/edge.log 2>&1
$R/.venv/bin/python svgext.py fx/edge.svg        # path extent + satin half-width
# eroded vs silhouette, in px:
$R/.venv/bin/python - <<'PY'
import sys, numpy as np
sys.path.insert(0,"/home/roman/git/Digitize_patches/.claude/worktrees/review/tools/digitize")
import vectorize as V
from scipy import ndimage
img=V.load_image("fx/edge.png"); sc=V.design_scale(img,V.build_settings({"size-mm":"120","colors":"3","no-trim":True},{}))
dt=ndimage.distance_transform_edt(img.silhouette); half=int(round(sc.border_px/2))
er=img.silhouette&(dt>half)
print("border_px=%.1f half=%d silhouette=%d eroded=%d"%(sc.border_px,half,img.silhouette.sum(),er.sum()))
ys,xs=np.where(er); print("eroded bbox x %d..%d (canvas 0..999)"%(xs.min(),xs.max()))
PY
```
Verbatim:
```
fx/edge.svg: design extent 122.5 x 122.5 mm  (canvas 120.0 x 120.0)
border: color (192,57,43) width 2.5 mm (1 path, 29 pts)
border_px=20.8 half=10 silhouette=996856 eroded=993364
eroded bbox x 0..999 (canvas 0..999)      <- erosion removed only the corners
border path bbox x -0.5..999.5, stroke-width 20.83  <- centreline on the edge
```
So the centreline spans the full 120 mm and the stroke adds `2.5/2 = 1.25 mm`
outside on each side. Control (same command on a patch with a 10 px margin,
`fx/wide.png` from the `fit_check.py` `wide()` design) shows the normal path is
fine: `design extent 99.9 x 27.1 mm (canvas 101.3 x 28.4)`, border path bbox
`x 29.5..1471.5` against silhouette `x 10..1489`.

**Where the reported overhang comes from (this is the answer to the scoped
question).** Measured decomposition per side:
1. Border centred on the canvas-edge silhouette: `border_mm/2 = 1.25 mm` (this
   finding, VERIFIED).
2. Satin `pull_compensation_mm="0.2 0.2"` applied at export: `0.2 mm` (R1-4,
   READ-ONLY). Ink/Stitch's own tooltip says it "expands each pair of needle
   penetrations outward from the center of the satin column", unit "mm (each
   side)".
`1.25 + 0.2 = 1.45 mm` per side = **2.9 mm total**, which matches the measured
2.9 mm for the artwork with its own border ring at the canvas edge.

For the 0.3 to 0.8 mm seen on real designs that do *not* touch the canvas, the
border contributes nothing and the sources are smaller: the outline satin free-end
extension of `0.3 mm` (`skeleton.py:22`, `_FREE_END_CLIP_MM = 0.3`; asserted in
the module `demo()`), the widening of a thin outline to `SATIN_MIN_MM = 1.2 mm`
(up to `(1.2 - true_width)/2` beyond the drawn line, `vectorize.py:380-381`,
`skeleton.py:193`), and the `0.2 mm` satin pull above.

**Fix.** Make the erosion see the outside: run the distance transform on a padded
mask and crop back, e.g. `dt = distance_transform_edt(np.pad(silhouette, 1))[1:-1,1:-1]`
(and treat an all-foreground mask as background outside). Alternatively detect
canvas-edge contact and inset the border centreline by `border_px/2` explicitly.

## R1-4. P1: satin pull compensation enlarges every satin at export

**What is wrong.** `satin_el` writes `inkstitch:pull_compensation_mm="0.2 0.2"`
on every satin column (`vectorize.py:1418`) when `SATIN_PULL_MM` is non-zero.
Ink/Stitch reads it (`satin_column.py:218-232`, `get_split_mm_param_as_px`) and
expands each stitch pair outward from the centreline by that amount, so the stitched
satin is wider than the drawn/emitted geometry on both sides.

**Impact.** The VP3 is larger than the SVG by up to `SATIN_PULL_MM` per side on
every satin edge (outlines and the border). It is part of R1-3's measured
overhang and is invisible when inspecting the SVG.

**Reproduce (READ-ONLY).**
```bash
grep -o 'pull_compensation_mm="[^"]*"' $S/fx/edge.svg | head -1
# -> pull_compensation_mm="0.2 0.2"
sed -n '218,232p' $R/inkstitch/lib/elements/satin_column/satin_column.py
```
Verbatim (Ink/Stitch tooltip): "expands each pair of needle penetrations outward
from the center of the satin column by a fixed length", `unit=_('mm (each side)')`.

**Fix.** Either set `satin_pull_mm` to 0 for a fit-exact file, or fold the pull
(and the E3 extension) into the fit/scale maths, or document that the stitched
size is the drawn size plus `2 x (SATIN_PULL_MM + free-end ext)`.

## R1-5. P1: border `mode: off` does nothing and mode typos degrade to `auto`

**What is wrong.** `build_settings` reads the mode raw (`vectorize.py:341`):
```python
_border_mode = _border_cfg.get("mode", "auto")
```
PyYAML parses bare `off`/`on`/`yes`/`no` as booleans, so `mode: off` gives
`False`, and `detect_border` tests `border_mode == "off"` (`:672`), which is
`False`. No validation runs, so `FORCE_BLACK`/`none` also fall through to `auto`.

**Impact.** The one YAML control whose purpose is to disable the border silently
keeps it on (and re-pollutes the palette with the outer ring). A mistyped mode
silently switches to `auto` with no warning. Still open: `space_bunny-review.md`
#6 and #7.

**Reproduce.**
```bash
cd $S && rm -rf bm && mkdir bm && cp in/patch.png bm/
for m in off '"off"' auto; do printf 'border:\n  mode: %s\n' "$m" > bm/c.yaml; \
  $R/.venv/bin/python $R/tools/digitize/vectorize.py --config bm/c.yaml in/patch.png bm/$m.svg >bm/$m.log 2>&1; \
  printf 'mode=%-7s %s\n' "$m" "$(grep -m1 '^border:' bm/$m.log || echo NO-BORDER)"; done
```
Verbatim:
```
mode=off     border: color (20,20,20) width 2.5 mm (1 path, 45 pts)   <- wanted OFF
mode="off"   NO-BORDER
mode=auto    border: color (20,20,20) width 2.5 mm (1 path, 45 pts)
```

**Fix.** `_border_mode = str(_border_cfg.get("mode","auto")).strip().lower()` and
`sys.exit` when it is not in `{auto, off, force_black}`. Quote the template in
`make_config.py`/`make_config.html`.

## R1-6. P1: `--flag=value` on booleans ignored; `--colors` without a value becomes k=1

**What is wrong.** `parse_args` stores `flags[name] = val` for `--flag=value`
(`:205-206`), but the boolean readers test `is True` (e.g. `:278`, `:280`, `:284`,
`:308`), which a string `"true"` never satisfies. Separately, a value flag at the
end of `argv` falls into the `else` branch and stores `True` (`:211-212`), so
`--colors` alone evaluates `int(True) = 1`.

**Impact.** `--no-border=true` leaves the border on; `--colors` with no number
silently produces a one-colour design at exit 0. Still open:
`space_bunny-review.md` #12.

**Reproduce.**
```bash
cd $S && mkdir -p fl
$R/.venv/bin/python $R/tools/digitize/vectorize.py --no-border=true in/patch.png fl/nb.svg >fl/nb.log 2>&1
grep -c '^border:' fl/nb.log                       # -> 1 (border still emitted)
$R/.venv/bin/python $R/tools/digitize/vectorize.py in/patch.png fl/k1.svg --colors >fl/k1.log 2>&1; echo exit=$?
grep -m1 'palette k=' fl/k1.log
```
Verbatim:
```
--no-border=true -> 1 border line(s)
exit=0 --colors(no value): palette k=1
```

**Fix.** One `truthy(value)` helper for booleans, and validate `--colors` is an
`int >= 1` (exit on a bare flag or non-numeric value).

## R1-7. P1: opaque background is the globally lightest cluster

**What is wrong.** `build_palette` picks the background as the brightest cluster
anywhere (`vectorize.py:907-909`):
```python
if not img.has_transparency:
    lum = cluster_rgb.sum(axis=1)
    bg = int(np.argmax(lum))     # lightest = paper
```
This is not "the cluster touching the canvas border". A light accent colour wins
and is dropped, and the real dark background becomes a fill.

**Impact.** On dark flat art the lightest real colour is discarded and the paper
is stitched as a solid fill, exit 0. Still open: `space_bunny-review.md` #11.

**Reproduce.**
```bash
cd $S
$R/.venv/bin/python - <<'PY'
from PIL import Image, ImageDraw
im=Image.new("RGB",(300,300),(26,26,46)); d=ImageDraw.Draw(im)
d.ellipse((60,60,240,240),fill=(85,102,170)); d.ellipse((130,130,170,170),fill=(200,120,40))
im.save("in/dark_bg.png")
PY
$R/.venv/bin/python $R/tools/digitize/vectorize.py in/dark_bg.png out2/dark_bg.svg >out2/dark_bg.log 2>&1; echo exit=$?
grep -E "background|^order:|^  \(" out2/dark_bg.log
```
Verbatim:
```
exit=0
  background (skip) = (200,120,40)      <- the orange accent, not the navy paper
order: ['#5566aa', '#1a1a2e']
  (26,26,46): 1 comps (dropped 0)       <- navy background stitched as a fill
```

**Fix.** Pick the label that occupies the image border (`np.bincount` over
`label_all[0,:]`, `[-1,:]`, `[:,0]`, `[:,-1]`), matching the `key_background.py`
approach, and use `luma()` instead of `sum()` for consistency with `order_colors`.

## R1-8. P1: EXIF orientation ignored

**What is wrong.** `load_image` does `Image.open(path).convert("RGBA")`
(`vectorize.py:442`) with no `ImageOps.exif_transpose`, so a phone photo tagged
`Orientation=6` is read in sensor order.

**Impact.** The design is digitised 90 degrees from every viewer. Still open:
`space_bunny-review.md` #29.

**Reproduce.**
```bash
cd $S
$R/.venv/bin/python -c "from PIL import Image,ImageOps; \
print('raw', Image.open('in/exif6.jpg').size, 'exif', ImageOps.exif_transpose(Image.open('in/exif6.jpg')).size)"
grep -m1 '^image ' out/exif6.log
```
Verbatim:
```
raw size      : (600, 300)
exif_transpose: (300, 600)
image 600x300 -> 107x53 mm (5.6 px/mm)     <- pipeline used the un-rotated 600x300
```

**Fix.** `im = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")`.

## R1-9. P2: `satin_max_mm` is not readable from YAML

**What is wrong.** `build_settings` sets `satin_max_mm = SATIN_MAX_MM` and only
overrides it from the CLI argument (`vectorize.py:289`, `344-345`); `cfg` is never
consulted.

**Impact.** A YAML `satin_max_mm:` value is silently ignored, so the YAML and CLI
paths disagree. Still open: `space_bunny-review.md` #36.

**Reproduce.**
```bash
cd $S && printf 'satin_max_mm: 5\n' > fx/smax.yaml
$R/.venv/bin/python $R/tools/digitize/vectorize.py --colors 3 fx/wide.png fx/y.svg --config fx/smax.yaml >fx/y.log 2>&1
$R/.venv/bin/python $R/tools/digitize/vectorize.py --colors 3 fx/wide.png fx/c.svg --satin-max-mm 5 >fx/c.log 2>&1
grep -m1 'satin outlines:' fx/y.log || echo "YAML: no satin outlines"
grep -m1 'satin outlines:' fx/c.log  || echo "CLI : no satin outlines"
```
Verbatim:
```
YAML: no satin outlines
CLI : satin outlines: 2 segments from (26,26,26)
```

**Fix.** `satin_max_arg = flag("satin-max-mm", None); if satin_max_arg is None: satin_max_arg = cfg.get("satin_max_mm")`.

## R1-10. P2: density is not clamped; a negative value ships

**What is wrong.** Out-of-range density is only *printed* (`vectorize.py:411-414`);
the value is passed straight into `row_spacing_mm` (emitted at `el():1387`).
Ink/Stitch then
clamps with `max(row_spacing_mm, 0.1*PIXELS_PER_MM)` = 0.378 mm
(`inkstitch/lib/elements/fill_stitch.py:379`).

**Impact.** `--density -1` (or `0`) writes a malformed SVG parameter and quietly
stitches at 0.378 mm. The documented "safe 0.3 to 0.6 mm" band also has an
unreachable bottom third. Still open from `review.md` #21 / `space_bunny-review.md`
#21, and the `docs/USAGE.md:76` "0.3" floor is wrong.

**Reproduce.**
```bash
cd $S
$R/.venv/bin/python $R/tools/digitize/vectorize.py --colors 3 --density -1 fx/wide.png fx/neg.svg >fx/neg.log 2>&1
grep -o 'row_spacing_mm="[^"]*"' fx/neg.svg | head -1
grep -m1 'warning: density' fx/neg.log
```
Verbatim:
```
row_spacing_mm="-1.0"
warning: density -1.0 mm (global) is outside the safe 0.3-0.6 mm range
```

**Fix.** Clamp `row_spacing_mm` to `[0.378, 0.6]` (or exit) and correct the
warning/docs to the real floor.

## R1-11. P2: config and hex-key handling is silent

**What is wrong.**
- `load_config` returns `{}` for a missing path (`vectorize.py:221-225`), so a
  mistyped `--config` is silently ignored.
- A non-mapping YAML root reaches `cfg.get(...)` and dies with a raw
  `AttributeError` (e.g. `:266`).
- `order:` and `skip_colors:` compare against `hexkey()` output, which always has a
  leading `#` (`:936`, `:941`); a hex written without `#` never matches. (`palette:`
  is normalised by `_parse_palette`, so the behaviour is inconsistent.)

**Impact.** Silent misconfiguration: the requested order/skip is discarded, or a
traceback instead of a clear error. Still open: `space_bunny-review.md` #33, #34.

**Reproduce.**
```bash
cd $S
$R/.venv/bin/python $R/tools/digitize/vectorize.py --colors 3 --config nope.yaml fx/wide.png fx/mc.svg >fx/mc.log 2>&1; echo "missing config rc=$?"
printf 'just-a-string\n' >fx/bad.yaml
$R/.venv/bin/python $R/tools/digitize/vectorize.py --colors 3 --config fx/bad.yaml fx/wide.png fx/bad.svg >fx/bad.log 2>&1; echo "bad yaml rc=$? -> $(tail -n1 fx/bad.log)"
printf 'skip_colors: [1a1a1a]\n' >fx/no.yaml;   printf 'skip_colors: ["#1a1a1a"]\n' >fx/yes.yaml
$R/.venv/bin/python $R/tools/digitize/vectorize.py --colors 3 --config fx/no.yaml  fx/wide.png fx/nh.svg >fx/nh.log 2>&1
$R/.venv/bin/python $R/tools/digitize/vectorize.py --colors 3 --config fx/yes.yaml fx/wide.png fx/yh.svg >fx/yh.log 2>&1
grep -m1 '^order:' fx/nh.log; grep -m1 '^order:' fx/yh.log
```
Verbatim:
```
missing config rc=0
bad yaml rc=1 AttributeError: 'str' object has no attribute 'get'
skip without #: order: ['#f1c40f', '#c0392b', '#1a1a1a']   <- ignored
skip with #   : order: ['#f1c40f', '#c0392b']              <- applied
```

**Fix.** `sys.exit` on a missing `--config`; validate the root is a dict; normalise
hex keys (add `#`, lowercase) in `order`/`skip_colors` (and `satinize_colors`),
warning on entries that match no cluster.

## R1-12. P2: posterized preview written to the wrong directory

**What is wrong.** `write_preview` uses `out.rsplit(".", 1)[0] + "_posterized.png"`
(`vectorize.py:1515`). A dot in a directory name is treated as the extension.

**Impact.** The preview lands one directory up (or with a mangled name), so the
review image does not sit next to the SVG. Still open: `review.md` #28.

**Reproduce.**
```bash
cd $S && rm -rf fx/pv && mkdir -p fx/pv
$R/.venv/bin/python $R/tools/digitize/vectorize.py --colors 3 fx/wide.png 'fx/pv/a.b/design' >fx/pv.log 2>&1
ls fx/pv
```
Verbatim (a_posterized.png is in `fx/pv/`, not `fx/pv/a.b/`):
```
a.b
a_posterized.png
```

**Fix.** `os.path.splitext(out)[0] + "_posterized.png"`.

## Still open from earlier reviews

Confirmed present at `a795612`, not re-sectioned above:

- `review.md` #17 (`stitch_index` full-image compare per object), #18/#19/#20
  (trim distance approximations) still hold.
- `review.md` #22 (`skeleton.py:193` `w = max(w_raw, wmin)` widens a hairline
  without an upper bound), #23 (`skeleton.py:177` `2*median(EDT)` overshoots odd
  widths by 1 px), #24 (closed skeleton loops emitted open), #30 (`nn_sort` O(n^2),
  `vectorize.py:1204`) still hold.
- `space_bunny-review.md` #8 (`lw_cover` still uses `morphology.disk(2)`,
  `vectorize.py:1136-1137`, a halo of bare fabric), #15 (`vectorize.py:834`
  `(H*W, K, 3)` float64 temporaries, unchanged), #35 (`--border-mm` below the
  gate / negative is only warned about, `satin_el:1412-1415`) still hold.
- The following earlier findings are now FIXED and are not repeated:
  `SATIN_MIN_MM` is 1.2 with an emit-time gate guard (space bunny #2); the ordinary
  border is inset correctly (#3, except the canvas-edge case R1-3); the border
  contour is picked by area, not length (#4); the empty/degenerate SVG now exits 1
  with a clear error (#13); duplicate/empty clusters are deduped (#9); numpy scalar
  repr is gone (`_rgb_str`); version-4 metadata and pinned stitch params ship
  (`review.md` #2/#4 TL;DR); underlap, raster pull and profile ship.

## Checked and fine

- 16-bit PNG (`rgb16`, `gray16`), CMYK JPEG (`cmyk.jpg`), LA and palette PNG with
  and without `tRNS` all load and vectorize without error (commands in `$S/out3`).
- Tiny (1x1, 2x2), all-transparent and single-colour opaque inputs exit 1 with a
  clear message instead of writing an empty SVG.
- Two runs on the same input produce byte-identical SVG (kmeans seeds are fixed,
  no wall-clock or set-iteration order in the emit path).
- The ordinary (non-canvas-edge) border is inset correctly: control above
  (`fx/wide.svg`, border path `x 29.5..1471.5` against silhouette `x 10..1489`).
- `--palette` pinning, `--profile vadmel` resolution, and the
  `CLI > YAML > profile > default` precedence for underlap / raster pull / density
  resolve as documented (`build_settings:292-330`).
- `key_background.py` auto-detection and un-blending work on the repo images;
  `trim_vp3.py` protects satin fans and inserts no trims when vectorize already
  trimmed the layer boundaries.
