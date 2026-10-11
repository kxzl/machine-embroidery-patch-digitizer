# R4: workflow, setup, docs and robustness for a beginner

Scope: `tools/digitize/run.sh` flag handling, end-to-end input probes, doc drift in
`README.md` / `docs/USAGE.md`, fresh clone behaviour, macOS portability by reading,
stale top-level docs, and new function ideas for a non-LLM user.

Worktree: `.claude/worktrees/review` at commit `a795612`. All scratch output under
`SCRATCH=/tmp/claude-1000/-home-roman-git-Digitize-patches/ea4b9216-f705-480b-b7f0-ea8fdbedf18b/scratchpad/review/R4`
(abbreviated `$S` below). No repo files changed except this part file.

Severities: P0 silent wrong output, P1 wrong or fragile, P2 polish.

## Summary

| ID | Sev | File:line | Claim | Status |
|---|---|---|---|---|
| R4-1 | P1 | `vectorize.py:442` | 16-bit grayscale PNG reads as blank white, then "no stitchable objects produced"; misleading error | VERIFIED |
| R4-2 | P1 | `vectorize.py:442`, `:1528` | Missing/empty/text/corrupt inputs all raise raw Python tracebacks with no beginner guidance | VERIFIED |
| R4-3 | P1 | `run.sh:138-140` | Export failures are buried in `work/<base>.err`; `run.sh` exits with nothing on screen | VERIFIED |
| R4-4 | P1 | `run.sh:36-45`, `vectorize.py:208` | A value flag not in `run.sh`'s own list sends its value into the positionals, so the value is used as the image path | VERIFIED |
| R4-5 | P1 | `run.sh:36-40` | Value flag at the end with no value: `$1: unbound variable`, exit 1 | VERIFIED |
| R4-6 | P1 | `run.sh:34-42` | The `--flag=true` form of `run.sh`'s own booleans (`--key-background`, `--no-export`) is silently ignored | VERIFIED |
| R4-7 | P2 | `run.sh:50`, `:74` | A relative input path from another CWD fails after `cd` to the repo root; the error names a path that exists where the user stands | VERIFIED |
| R4-8 | P2 | `run.sh:47`, `vectorize.py:1525` | No usable `--help`; the usage text is outdated and `vectorize.py --help` tries to digitize the hardcoded sample | VERIFIED |
| R4-9 | P2 | `vectorize.py` (no validation) | `--border-mm -1` emits `stroke-width:-5.53` and exits 0 | VERIFIED |
| R4-10 | P2 | `run.sh:74`, `:115` | Output name is the input basename only, so two inputs with the same name overwrite one output silently | VERIFIED |
| R4-11 | P2 | `vectorize.py:579` | Grayscale PNG triggers a numpy `RuntimeWarning: invalid value encountered in divide` (0/0 in the palette merge) | VERIFIED |
| R4-12 | P2 | `vectorize.py` | A 6000 px source runs for minutes with no progress output, so it looks hung | VERIFIED |
| R4-13 | P1 | `docs/USAGE.md:17-20,35`, `README.md:65` | Docs say output lands in `work/`; `run.sh` writes `output_inkstitch_svg/` and `output_vp3/` | VERIFIED |
| R4-14 | P2 | `docs/USAGE.md:155`, `:200` | Docs cite a missing artifact and a regression gate that needs gitignored inputs/configs | VERIFIED |
| R4-15 | P2 | `qa/regress.sh:45`, `run.sh:128` | macOS/BSD portability: `readlink -f`; likely bash 3.2 empty-array failure under `set -u` | READ-ONLY |

---

## R4-1. 16-bit grayscale PNG reads as blank white (P1)

**What is wrong.** `load_image` opens every source with
`Image.open(path).convert("RGBA")` (`vectorize.py:442`). Pillow cannot map a 16-bit
grayscale PNG (mode `I;16`) to RGBA; the conversion produces an all-white image.
The pipeline then sees a single colour, drops it as background and reports
"no stitchable objects produced".

**Impact.** A 16-bit PNG is a normal export from GIMP/Photoshop and from many
scanners. The user gets an error that blames their image ("single-colour image"),
which is false, and a design that clearly has shapes never stitches.

**Reproduce.**

```
$S=/tmp/claude-1000/-home-roman-git-Digitize-patches/ea4b9216-f705-480b-b7f0-ea8fdbedf18b/scratchpad/review/R4
.venv/bin/python - <<'PY'
from PIL import Image; import numpy as np
Image.open("$S/probes/patch600_16bit.png").convert("RGBA")   # mode I;16 -> all 255
PY
tools/digitize/run.sh --no-export $S/probes/gray16_shapes.png
```

Observed (16-bit gray with three distinct tones):

```
image 200x200 -> 100x100 mm (2.0 px/mm), palette k=1
  background (skip) = (255,255,255)
order: []
error: no stitchable objects produced (single-colour image, or every colour skipped via skip_colors?)
exit=1
```

`Image.open(...).convert("RGBA")` on `patch600_16bit.png` gives exactly 1 unique
colour (`range 255 255`). This contradicts the "16-bit PNG ... works via
`.convert("RGBA")`" line in `space_bunny-review.md` "Verified non-issues".

**Fix (1-2 lines).** In `load_image`, handle `I;16`/`I` first (e.g.
`im = im.point(lambda v: v / 256).convert("L")` or `np.array(im).astype(np.uint8)`),
and add a regression fixture `gray16*.png`. Alternatively validate the mode and
tell the user to export 8-bit.

---

## R4-2. Bad input files give raw tracebacks, no guidance (P1)

**What is wrong.** Every load failure reaches the top level unhandled
(`vectorize.py:1528` calls `load_image`, `:442` does the open). Missing file, empty
file, a text file renamed `.png`, and a truncated/corrupt PNG all raise a Python
traceback.

**Impact.** A beginner cannot tell whether the file is missing, corrupt or the wrong
format, or what to do next. The traceback is 10-20 lines of Pillow/numpy frames.

**Reproduce and observed (exit 1 unless noted, `--no-export`, no SVG written).**

```
tools/digitize/run.sh --no-export $S/probes/does_not_exist.png   # FileNotFoundError
tools/digitize/run.sh --no-export $S/probes/empty.png            # UnidentifiedImageError
tools/digitize/run.sh --no-export $S/probes/notimage.png         # text file: UnidentifiedImageError
tools/digitize/run.sh --no-export $S/probes/corrupt_trunc.png    # OSError: image file is truncated
```

Each prints `Traceback (most recent call last): ... main() ... load_image ...`.
No output file remains (see the probe matrix below).

**Fix.** Wrap `load_image` in a try/except and `sys.exit("error: cannot read
<path>: <reason>. Supported: webp/png/jpg, 8-bit; see docs/USAGE.md#setup")`.

---

## R4-3. Export errors are buried; `run.sh` exits with no message (P1)

**What is wrong.** The export step redirects both streams:
`... "$OUT_SVG" > "work/$BASE.zip" 2>"work/$BASE.err"` (`run.sh:138-140`). If the
export command itself fails (missing `inkstitch/`, missing module, bad flag), the
message lands in `work/<base>.err`, the zip stays 0 bytes, and `set -e` aborts the
script right there. Nothing after it runs, and nothing is printed.

**Impact.** On a fresh clone (or after a botched setup) the user sees
`== exporting VP3` and then the prompt, with no reason. The failure is invisible
unless they know to open `work/<base>.err`.

**Reproduce (fresh clone without `inkstitch/`; `$S/clone2` has `.venv` symlinked).**

```
S=/tmp/claude-1000/-home-roman-git-Digitize-patches/ea4b9216-f705-480b-b7f0-ea8fdbedf18b/scratchpad/review/R4
cd $S/clone2 && tools/digitize/run.sh input/test.png
```

Observed: stdout ends at `== exporting VP3`, exit 2, and

```
$ cat $S/clone2/work/test.err
.venv/bin/python: can't open file '.../clone2/inkstitch/inkstitch.py': [Errno 2] No such file or directory
$ stat -c %s $S/clone2/work/test.zip
0
```

`qa/export.sh:10` does this correctly (`|| { echo FAIL; tail "$B.err"; exit 1; }`);
`run.sh` does not.

**Fix.** Use the `export.sh` pattern: on non-zero exit print `FAIL` plus
`tail -n 20 "work/$BASE.err"` and exit 1.

---

## R4-4. A value flag outside `run.sh`'s list turns its value into the image path (P1)

**What is wrong.** `run.sh` keeps its own hand-written list of value flags
(`run.sh:36-39`) that must mirror `vectorize.py:_VALUE_FLAGS` and
`svg_digitize.py:_VALUE_FLAGS`. Any value flag not in that list (a typo, or a new
flag added to a script) falls through to the `-*)` branch (`run.sh:43`) which
forwards the flag alone, so its value becomes the next positional and is taken as
the input image.

**Impact.** Two silent failure modes: (a) with no real input after it, the value is
used as the image path and the run dies on a confusing `FileNotFoundError`; (b) if a
real input follows, it overwrites the value, so a misplaced value is silently
dropped (see R4-5 for the neighbouring case).

**Reproduce.**

```
tools/digitize/run.sh --no-export --fit-mm 120x120      # no real input
```

Observed:

```
== digitizing 120x120 -> output_inkstitch_svg/120x120.svg  (flags: --fit-mm)
...
FileNotFoundError: [Errno 2] No such file or directory: '120x120'
exit=1
```

The same mechanism, with a real flag whose value is a following flag name, silently
changes meaning:

```
tools/digitize/run.sh --no-export --colors --no-trim $S/probes/patch50.png
# run.sh consumes --no-trim as the --colors value; vectorize sees --colors with no
# value -> int(True) = 1
image 50x50 -> 106x106 mm (0.5 px/mm), palette k=1
order: ['#a55226']
exit=0
```

Note `--fit-mm` is only on `feat/fit-mm`, but the trap does not depend on it: any
unknown flag reproduces it today.

**Fix.** Stop hand-maintaining the list. In `run.sh`, treat the next token as a
value whenever the current token is a long flag that is not one of the known
booleans, or better, make each script expose its value-flag set and consume it.

---

## R4-5. Value flag at the end with no value: raw bash error (P1)

**What is wrong.** The value-flag branch does `FLAGS+=("$a" "$1"); shift`
(`run.sh:40`). When the flag is the last token, `$1` is unset and `set -u`
(`run.sh:20`) aborts the whole script.

**Impact.** The user typed a normal-looking command and gets a bash-internal
message that does not mention the flag they forgot to give a value.

**Reproduce.**

```
tools/digitize/run.sh --no-export $S/probes/patch50.png --colors
```

Observed:

```
exit=1
tools/digitize/run.sh: line 40: $1: unbound variable
```

**Fix.** Check `$# -ge 1` before consuming a value and
`exit 2` with `error: --colors needs a value` otherwise.

---

## R4-6. `--flag=true` for `run.sh`'s own booleans is silently ignored (P1)

**What is wrong.** `--background=`, `--config=` are handled explicitly
(`run.sh:31-34`), but every other `--x=y` matches the generic `--*=*` case
(`run.sh:35`) and is forwarded inside `FLAGS` without setting the `run.sh` state
variables. So `--key-background=true` never sets `KEY_BG` and `--no-export=true`
never sets `NO_EXPORT`.

**Impact.** The user asks for a fast SVG-only run or for background keying and gets
the opposite behaviour, with exit 0. The VP3 export (the slow step) still runs, and
the background is not keyed, with no warning.

**Reproduce.**

```
rm -f work/patch600_white_keyed.png
tools/digitize/run.sh --no-export --key-background=true $S/probes/patch600_white.png
# exit=0, work/patch600_white_keyed.png created? NO (keying skipped)

tools/digitize/run.sh --no-export=true $S/probes/patch50.png
# exit=0, prints "== exporting VP3" (export NOT skipped)
```

**Fix.** Parse `--key-background` / `--no-export` and their `=*` forms in one case
each, accepting only `true|false|1|0` and rejecting anything else.

---

## R4-7. Relative input path fails after `cd` to the repo root (P2)

**What is wrong.** `run.sh:50` does `cd "$ROOT"`, but the input path is taken
relative to the caller's CWD (`run.sh:74` uses `$IMG` directly). A relative path
that exists where the user stands stops existing after the `cd`.

**Impact.** Running from `input/` or any other directory fails with a
`FileNotFoundError` that names a path the user can see in their shell. README's
`run.sh path/to/image.webp` implicitly assumes the repo root.

**Reproduce.**

```
cd $S/probes
/home/roman/git/Digitize_patches/.claude/worktrees/review/tools/digitize/run.sh --no-export patch50.png
```

Observed:

```
== digitizing patch50.png -> output_inkstitch_svg/patch50.svg  (flags: none)
FileNotFoundError: [Errno 2] No such file or directory: 'patch50.png'
exit=1
```

An absolute path works (exit 0, `wrote output_inkstitch_svg/patch50.svg`).

**Fix.** Resolve the input to an absolute path before `cd`, e.g.
`IMG="$(cd "$(dirname "$IMG")" && pwd)/$(basename "$IMG")"`, or `cd` back to the
caller's directory for the input handling.

---

## R4-8. No usable `--help` (P2)

**What is wrong.** `run.sh --help` is not special-cased, so `--help` becomes the
only "flag" and no input is set, triggering the `${IMG:?...}` guard (`run.sh:47`).
`vectorize.py --help` is not in `_VALUE_FLAGS`, so it sets `flags["help"]=True`, no
positional is given, and the hardcoded default image is loaded (`vectorize.py:1525`).

**Impact.** The single command a beginner tries first either errors or tries to
digitize a sample that is not there.

**Reproduce.**

```
tools/digitize/run.sh --help
# tools/digitize/run.sh: line 47: IMG: usage: run.sh [--no-trim] [--colors N] [--border-mm W] [--config F] <input.webp|png|jpg|svg>
# exit=1

.venv/bin/python tools/digitize/vectorize.py --help
# Traceback ... FileNotFoundError: [Errno 2] No such file or directory: "Scavenger's_Daughter_by_the_dusty_druid.webp"
```

The usage string shown is also outdated (it omits most flags that exist today).

**Fix.** Handle `-h|--help` at the top of `run.sh` and print the header comment
(`run.sh:3-19`); give `vectorize.py`/`svg_digitize.py` argparse with real `--help`.

---

## R4-9. Negative `--border-mm` emits a negative stroke width (P2)

**What is wrong.** `border_mm` is not validated. `--border-mm -1` is consumed
(because `--border-mm` is a value flag) and reaches emit unchanged.

**Impact.** The SVG carries `stroke-width:-5.53`. Ink/Stitch may clamp or drop it,
and the stitching is not what the user asked for. Exit code is 0.

**Reproduce.**

```
tools/digitize/run.sh --no-export --border-mm -1 $S/probes/patch600_alpha.png
grep -oE 'stroke-width:-[0-9.]+' output_inkstitch_svg/patch600_alpha.svg
```

Observed: `border: color (20,20,20) width -1.0 mm`, then `stroke-width:-5.53`.
(Still open from `space_bunny-review.md` #35.)

**Fix.** `if not 1.0 <= border_mm <= 20: sys.exit("error: --border-mm must be >= 1.0
(Ink/Stitch's satin gate) and <= 20 mm")`.

---

## R4-10. Same basename from different directories overwrites silently (P2)

**What is wrong.** `BASE` is `basename "$IMG"` with the extension stripped
(`run.sh:74-75`), and `OUT_SVG` / `OUT_VP3` use only `$BASE` (`run.sh:115`,
`:148`). Two inputs named `patch.png` in different folders map to the same output.

**Impact.** The second run replaces the first output without a word. A user
digitizing `front/patch.png` and `back/patch.png` loses one.

**Reproduce.**

```
cp $S/probes/patch600_alpha.png $S/dirA/patch.png
cp $S/probes/patch600_white.png $S/dirB/patch.png
tools/digitize/run.sh --no-export $S/dirA/patch.png   # wrote output_inkstitch_svg/patch.svg
tools/digitize/run.sh --no-export $S/dirB/patch.png   # wrote output_inkstitch_svg/patch.svg (same file, different content)
```

`md5sum output_inkstitch_svg/patch.svg` changes between the two runs; both exit 0.

**Fix.** Derive the output stem from the full input path (or a hash suffix), and
print `note: overwriting existing <path>` when the target exists.

---

## R4-11. Grayscale PNG emits a numpy RuntimeWarning (P2)

**What is wrong.** The palette merge divides by `share[i] + share[j]`
(`vectorize.py:579`). Two zero-share clusters give 0/0. The `warnings.catch_warnings`
guard only covers the `kmeans2` call (`vectorize.py:531-532`), not the merge.

**Impact.** A scary `RuntimeWarning: invalid value encountered in divide` appears on
stderr for a normal grayscale input, and a NaN centroid can enter the merge. Output
still succeeds, so the warning looks like a crash but is not. This is noise that
hides real warnings.

**Reproduce.**

```
tools/digitize/run.sh --no-export $S/probes/patch600_gray.png
```

Observed:

```
.../tools/digitize/vectorize.py:579: RuntimeWarning: invalid value encountered in divide
  cen[i] = (cen[i] * share[i] + cen[j] * share[j]) / total
image 600x600 -> 125x125 mm (4.8 px/mm), palette k=2
order: ['#292929']
exit=0
```

**Fix.** Guard the merge (`if total <= 0: drop the pair`) and extend the
`catch_warnings` block to cover the whole palette build.

---

## R4-12. A 6000 px source runs for minutes, silently (P2)

**What is wrong.** There is no size limit and no progress output. `run.sh` prints
`== digitizing ...` once, then the next line only when vectorize finishes.

**Impact.** A beginner with a 24 MP photo (a phone or DSLR image is 6000 px on the
long side) sees one line and a frozen terminal. Nothing says "still working" or
"this is slow". The 50 px case even prints a warning; the 6000 px case prints
nothing.

**Reproduce.**

```
tools/digitize/run.sh --no-export $S/probes/big6000flat.png
```

Observed: `exit=143 wall_seconds=150` when the run was stopped, still inside
`vectorize.py`, with no output after the first `== digitizing ...` line. A flat
6000x6000 design (three shapes) was used, so it is not pathological noise. The
earlier review already measured the memory blow-up in the label step
(`space_bunny-review.md` #15); this is the user-visible side.

**Fix.** Print a stage/heartbeat line (`sep`, `vectorize`, `emit`) with elapsed
seconds, and refuse or warn above a pixel threshold with the expected runtime.

Probe matrix for the whole (b) scope is at the end of this file.

---

## R4-13. Docs say output lands in `work/`; it lands in `output_inkstitch_svg/` and `output_vp3/` (P1)

**What is wrong.** `run.sh:115` writes `output_inkstitch_svg/$BASE.svg`, `:148`
writes `output_vp3/$BASE.vp3`, `:169-171` write the two previews into
`output_vp3/`, and `write_preview` (`vectorize.py:1515`) writes
`output_inkstitch_svg/<name>_posterized.png`.

`docs/USAGE.md:17-20` and `:35` and `README.md:65` all say `work/`. No doc mentions
`output_inkstitch_svg/` or `output_vp3/` (grep finds them only in
`docs/EMBROIDERY_QUALITY.md:463`).

**Impact.** The "What it produces" table is the first place a beginner looks. Every
path in it is wrong, so they search `work/`, find only intermediate files
(`*_keyed.png`, `*.zip`, `*.err`), and cannot find their SVG or VP3.

**Evidence.** `grep -rn "output_inkstitch_svg\|output_vp3" README.md docs/USAGE.md`
returns nothing; every `--no-export` run above prints `wrote
output_inkstitch_svg/<name>.svg`.

**Fix.** Rewrite the USAGE table to the real paths and add a short
"where are my files?" section listing the SVG, VP3, posterized preview, and the two
`output_vp3/` previews.

---

## R4-14. Doc references a missing artifact and an unrunnable gate (P2)

**What is wrong.** `docs/USAGE.md:155-156` cites
`work/review_artifacts/RESEARCH_vadmel.md` as the source of the vadmel numbers. That
path is gitignored and is absent from this checkout (it exists only in the operator's
main tree). `docs/USAGE.md:200-208` documents `qa/regress.sh` as the regression gate,
but `regress.sh:52-54,116-117` needs `input/*.jpg`, `work/book_burner.yaml` and
`patch_descriptions/border_black.yaml`, none of which are in the repo.

**Impact.** A reader cannot verify the vadmel numbers, and the documented gate
cannot run on a fresh clone. It fails mid-run with a `FileNotFoundError`, not with
"this gate needs the operator's input/work files".

**Reproduce (fresh clone `$S/clone2` with `.venv` symlinked).**

```
cd $S/clone2 && tools/digitize/qa/regress.sh /tmp/q_r4
# exit=1
# FileNotFoundError: [Errno 2] No such file or directory: 'input/patch_book_burner.jpg'
```

**Fix.** Copy `RESEARCH_vadmel.md` into the repo (or drop the citation), and add a
preflight check to `regress.sh` that prints what is missing and where to get it.

---

## R4-15. macOS/BSD portability by reading (P2)

**What is wrong.**

- `qa/regress.sh:45` uses `readlink -f`. BSD `readlink` (macOS) has no `-f`. The
  GNU behaviour would need `realpath` or a `cd ... && pwd` fallback. This is the
  only clear GNU-ism in the committed scripts.
- `run.sh:128` expands `${FLAGS[*]:-none}` with `set -u` (`run.sh:20`) when `FLAGS`
  can be empty. Bash 3.2 (the macOS `/bin/bash`) treats the empty-array `[*]`
  expansion as unbound even with `:-`; bash 4.4 and later changed this. On macOS
  bash 3.2 the no-flag run likely aborts at line 128.

**Impact.** The QA gate cannot run on macOS as written. `run.sh` may fail before
digitizing at all, depending on the shell.

**Status: READ-ONLY.** No macOS host and no bash 3.2 on this box (`bash --version`
is 5.3), so neither was run. `readlink -f` is a documented BSD/GNU difference and
the bash-3.2 empty-array rule is a documented version difference.

**Fix.** Replace `readlink -f "$VEC"` with a `cd/realdir` fallback; use
`${FLAGS[*]:-}` with an explicit `if ((${#FLAGS[@]}))` guard.

---

## Probe matrix (scope b)

All runs: `--no-export`, from the worktree. "Half output" = a partial SVG/VP3 left
behind. "Guidance" = does the message tell a beginner what to do.

| Input | Exit | What the user sees | Half output | Guidance |
|---|---|---|---|---|
| nonexistent file | 1 | `FileNotFoundError` traceback | no | no |
| empty file | 1 | `UnidentifiedImageError` traceback | no | no |
| text file renamed `.png` | 1 | `UnidentifiedImageError` traceback | no | no |
| truncated/corrupt PNG | 1 | `OSError: image file is truncated` traceback | no | no |
| 16-bit grayscale PNG | 1 | `error: no stitchable objects produced (single-colour image ...)` | no | misleading (R4-1) |
| 50 px image | 0 | `warning: source is too coarse to stitch well (2.13 mm per source pixel ...)` | n/a | yes |
| 6000 px image | 143 (stopped) | only `== digitizing ...`, no further line after 150 s | n/a | no (R4-12) |
| opaque JPG | 0 | `background (skip) = (255,255,255)`, then writes | n/a | n/a |
| transparent PNG | 0 | writes; border detected | n/a | n/a |
| grayscale PNG (8-bit) | 0 | `RuntimeWarning: invalid value encountered in divide` (R4-11) | n/a | no |
| CMYK JPEG | 0 | writes normally | n/a | n/a |
| unwritable output dir | 1 | `PermissionError` traceback (from `emit_svg`) | no | partly (path shown) |
| missing `.venv` (fresh clone) | 127 | `.venv/bin/python: No such file or directory` | no | no |

---

## Doc claim audit (scope c, README.md + docs/USAGE.md)

| Claim | Where | Verdict | Evidence |
|---|---|---|---|
| Output lands in `work/` (`<name>.svg`, `<name>.vp3`, `<name>_posterized.png`) | USAGE:17-20,35; README:65 | FALSE | R4-13; code writes `output_inkstitch_svg/` + `output_vp3/` |
| `run.sh` forwards any `--*` flag to `vectorize.py` | USAGE:99 | FALSE | `run.sh:97-112` drops svg-only and short flags; `run.sh:31-42` consumes its own |
| `regions.json` via `analyze.py` | USAGE:20 | TRUE | `analyze.py:80` writes `work/regions.json` |
| `--colors` default 5 | USAGE:71 | TRUE | `vectorize.py:104` `n_colors=5` |
| `--border-mm` default 2.5 | USAGE:74 | TRUE | `vectorize.py:105` |
| `--density` default 0.4 raster / 0.3 SVG | USAGE:76 | TRUE | `vectorize.py:58`, `svg_digitize.py:104` |
| density warning outside 0.3-0.6 | USAGE:272 | TRUE for the code, but 0.3 is unreachable | `vectorize.py:412`; Ink/Stitch floors at 0.378 (`space_bunny` #21) |
| `--satin-max-mm` / `SATIN_MAX_MM` 2.5 | USAGE:79,274 | TRUE | `vectorize.py:64` |
| `--underlap-mm` 0.6 / `--raster-pull-mm` 0 / `--size-mm` 100 | USAGE:80,81,84 | TRUE | `vectorize.py:126`, defaults |
| `--overlap-mm` 1.0 / `--seam-pull-mm` 0.2 | USAGE:85,86 | TRUE | `svg_digitize.py:122,126` |
| `--trim-mm` 4.0 | USAGE:93 | TRUE | `vectorize.py:108` `trim_threshold_mm=4.0` |
| `SATIN_MIN_MM` 1.2 above the 1.0 gate | USAGE:273 | TRUE | `vectorize.py:62,63` |
| `MIN_COMP_MM2` 0.8, `MIN_HOLE_MM2` 0.2, `OPEN/CLOSE_RADIUS` 1/2, `TOLERANCE_MM` 0.25 | USAGE:278-281 | TRUE | `vectorize.py:67-71` |
| `preview.py --crop` is mm from the design's top-left | USAGE:121-122 | TRUE for `parse_crop`, but `docs/EMBROIDERY_QUALITY.md:373-379` still says bottom | `preview.py:55-63` |
| `--format-vp3=True` in `run.sh` | USAGE:356 | TRUE | `run.sh:139` |
| Vadmel numbers from `work/review_artifacts/RESEARCH_vadmel.md` | USAGE:155 | UNVERIFIABLE | file is gitignored and absent (R4-14) |
| `qa/regress.sh` is the runnable regression gate | USAGE:200-208 | FALSE on a fresh clone | needs gitignored inputs/configs (R4-14) |
| "Measured ~6% less inter-object travel on the Bomb sample (2175 vs 2308 mm)" | README:14 | TRUE | 5.76%; matches `space_bunny` #40 |
| Trim: `>4 mm` cut, `<2 mm` skipped | README:15 | TRUE | `vectorize.py:74` `TRIM_MIN_MM=2.0`, threshold 4.0 |
| Python 3.13 badge | README:115 | TRUE | `.venv` is 3.13; `numpy==2.2.6` installed |

---

## Stale top-level docs (scope f)

| File | Status | Why |
|---|---|---|
| `HANDOFF.md` | stale, archive candidate | Header says "zero pipeline code written", but `svg_digitize.py` implements the whole plan; the 260 mm 2-colour task shipped |
| `IMPLEMENTATION_SPEC.md` | stale, archive candidate | Step 1 "DONE", steps 3-4 "pending review"; superseded by the shipped raster path and `review.md` |
| `IMPROVEMENTS_SPEC.md` | archive candidate | Planning spec for the raster path; all steps are in the code or superseded by `review.md`; keep as design record |
| `DIGITIZING_PLAN.md` | archive candidate | Original Scavenger's Daughter plan; superseded by the current native SVG path and `review.md` |
| `review.md` | current (record) | Most TL;DR items shipped (underlap, palette, metadata, vadmel, border snap, satin E3, trims); a few doc-drift items still open |
| `space_bunny-review.md` | current (record) | Many findings fixed; about a dozen still open (see the Still-open list) |
| `learnings_from_embroidery_projects.md` | current | Sample measurements still cited by `USAGE.md` and `review.md` |
| `CREDITS.md` | current | Matches the input artwork |

---

## New function ideas for a non-LLM user (scope g, ranked)

Already decided for v1 and excluded: image check, hoop presets with fit check,
results summary. Ranked by value vs effort.

| Rank | Idea | Why (observed) | Effort |
|---|---|---|---|
| 1 | Friendly preflight: open the image, report format/size/bit depth/distinct colours, warn on 16-bit/CMYK/EXIF, print the real output paths | R4-1, R4-2, R4-13 | M |
| 2 | Real `--help` and argument validation (argparse in both scripts; reject unknown flags; validate numerics; verbatim errors) | R4-4, R4-5, R4-8, R4-9 | S |
| 3 | Progress/heartbeat lines with elapsed time during digitize and export | R4-12 | M |
| 4 | Surface export failures: print the tail of `work/<base>.err` and exit 1 | R4-3 | S |
| 5 | Normalise common formats in `load_image` (EXIF transpose, 16-bit, CMYK) so they just work | R4-1 | S |
| 6 | Output-collision guard: derive the stem from the full path, warn before overwriting | R4-10 | S |
| 7 | "Where are my files?" doc section plus a troubleshooting table for the common errors | R4-13, R4-14 | S |
| 8 | `--dry-run`: resolve settings and print output paths without exporting | beginner check before a long run (R4-12) | S |
| 9 | Bundled small demo image plus `run.sh demo` so the first run always works | fresh clone has no `input/` or fixtures | S |

---

## Still open from earlier reviews

Re-verified in this scope (not repeated as new findings above):

- `space_bunny-review.md` #1: direct `vectorize.py -o a.png victim.png` still
  overwrites `victim.png` with SVG. VERIFIED, but only when `a.png` already exists
  as a readable image (`FileNotFoundError` otherwise).
- `space_bunny-review.md` #6 / #44: `border:\n  mode: off` (unquoted) still leaves
  the border on; `make_config.html:144` still writes the unquoted value. VERIFIED:
  `mode: off` emits the border, `mode: "off"` does not.
- `space_bunny-review.md` #12: `--colors` with no value still becomes `k=1`
  (`int(True)`). VERIFIED (see R4-4/R4-5).
- `space_bunny-review.md` #33: a missing `--config` is still silently ignored.
  VERIFIED (exit 0, no warning).
- `space_bunny-review.md` #35: `--border-mm -1` still emits a negative
  `stroke-width`. VERIFIED (see R4-9).
- `space_bunny-review.md` #21: the doc "safe band" still starts at 0.3 mm, below
  Ink/Stitch's 0.378 mm floor. Carried over by reading; not re-measured here.
- `space_bunny-review.md` #31: `svg_digitize.py` still runs at import time and uses
  the hand-rolled parser (no `main()`); `vectorize.py` was fixed. Reading.
- `EMBROIDERY_QUALITY.md:373-379,411` still say `--crop` measures Y from the bottom;
  `preview.py:55-63` documents and implements top-left. Reading.

Fixed since the earlier reviews (do not re-raise): #2 `SATIN_MIN_MM` is now 1.2;
#13 empty input now exits with a message (`vectorize.py:1543`); #37 `.gitignore`
now keeps `tools/digitize/tests/**`; #40 README now says ~6%.

## Checked and fine

- Filenames with spaces, apostrophes, non-ASCII, leading dash and dots all work
  (every path is quoted). `O'Brien patch.png`, `Ørsted ærlig.png`, `-dash.png`,
  `two.dots.v2.png`, `UPPER.PNG` all exit 0.
- No half-written output on a load failure: `emit_svg` is the last step, so
  missing/empty/text/corrupt inputs leave no SVG (probe matrix).
- Exit codes: a successful `--no-export` run exits 0; a failing load or a failing
  export exits non-zero. `set -euo pipefail` propagates correctly.
- 50 px input succeeds and prints a useful "source is too coarse" hint.
- CMYK JPEG, GIF, TIFF, BMP and palette PNG all convert and stitch (via
  `.convert("RGBA")`).
- `--no-export` (space form) skips the export; quoted `mode: "off"` disables the
  border.
- `run.sh` creates `work/`, `output_inkstitch_svg/`, `output_vp3/` with `mkdir -p`,
  so a fresh clone's missing output directories are not a failure.
- Clean output naming for normal inputs: `<name>.svg` and `<name>.vp3` match the
  input stem.
