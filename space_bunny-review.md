# Code Review — `Digitize_patches`

**Scope:** `tools/digitize/{vectorize.py, skeleton.py, run.sh, preview.py, analyze.py, make_config.py, make_config.html}`, `tools/wxstub/wx/__init__.py`, and doc/claim drift against `README.md`, `docs/USAGE.md`, `IMPLEMENTATION_SPEC.md`, `IMPROVEMENTS_SPEC.md`.

**How this was produced.** Four Space Bunny subagents were dispatched to split the work by file; the harness aborted every launch, and three eventually returned (`skeleton.py`, `vectorize.py:1-300`, `vectorize.py:299-578`). **Every finding below was then re-verified by me directly** against this checkout (`.venv`, Python 3.13, numpy 2.2.6, scipy 1.18.1, skimage 0.26.0) with the vendored Ink/Stitch at `inkstitch/`. Where a subagent's claim did not survive re-verification, it is reported as **retracted** rather than passed through. Three of my own earlier hypotheses were wrong and are corrected in place.

No repo files were modified; all probes went to `/tmp/opencode/`.

---

## The short version

The pipeline works end-to-end, and its failure mode is **silence**. Exit code 0, no warning, plausible-looking output. Four defects ship broken output today:

1. **A reasonable command line destroys an unrelated file.** `-o a.png victim.png` writes SVG over `victim.png`. Verified.
2. **The flagship feature doesn't work.** `SATIN_MIN_MM = 0.6` is below Ink/Stitch's 1.0 mm satin gate, so **86.7%** of satin outlines on the repo's own sample art stitch as flat running stitch.
3. **Every patch loses a 1.25 mm ring of stitching** around its entire perimeter (~430 mm² on a 100 mm patch), and ~50% of the border thread is sewn off the edge onto bare fabric.
4. **`border: mode: off` in YAML does nothing** — PyYAML parses unquoted `off` as boolean `False`.

---

## Summary

| # | Sev | Finding | Silent? |
|---|-----|---------|---------|
| 1 | **Critical** | Short/unknown flags shift the positionals → **SVG written over an unrelated source file** | yes |
| 2 | **Critical** | `SATIN_MIN_MM = 0.6` < Ink/Stitch's 1.0 mm satin gate → **86.7%** of satin outlines become running stitch | yes |
| 3 | **Critical** | Border satin centred on the edge, not the ring midline → **1.25 mm unstitched ring** + ~50% of border off-patch | yes |
| 4 | **Critical** | `max(contours, key=len)` picks the **longest** contour, not the outer boundary — a hole or squiggle can steal the border | yes |
| 5 | **High** | One stray `alpha<128` pixel reclassifies an engraving as a patch → 2.5 mm frame around the whole canvas | yes |
| 6 | **High** | `mode: off` is a YAML boolean → border never disabled | yes |
| 7 | **High** | `border: mode` typos silently behave as `auto`; no validation | yes |
| 8 | **High** | `lw_cover`'s `disk(2)` dilation carves fill the satin never covers → bare fabric | yes |
| 9 | **High** | Duplicate k-means clusters are always empty → `order:` silently mis-targeted, `k` over-reported | yes |
| 10 | **High** | 8-neighbour `deg>=3` flags pixels *around* crossings as junctions → centre dropped, 4 columns instead of 2 | yes |
| 11 | **High** | Opaque background = *lightest cluster* → discards a real colour and fills the actual background | yes |
| 12 | **High** | `--flag=value` silently ignored on booleans; `--colors` with no value silently becomes k=1 | yes |
| 13 | Medium | Degenerate input → empty SVG, **exit 0**, then `BadZipFile` downstream | yes |
| 14 | Medium | `int()` truncation zeroes `MIN_COMP_PX`/`MIN_HOLE_PX` below 112/224 px | yes |
| 15 | Medium | `label_all` peaks at **694 MB** for a 17 MB result; **4 GB / hard crash** at 25 MP; no size cap | no |
| 16 | Medium | `contour_paths` = **74% of runtime**; full-image work per component | no |
| 17 | Medium | `stitch_index` full-image compare per object — `O(n·H·W)` | no |
| 18 | Medium | Trim measures nearest-*boundary*, not real travel — 40 mm discrepancy | yes |
| 19 | Medium | `is_hidden` probes a fixed 0.5 mm lattice → over-trims buried jumps | yes |
| 20 | Medium | `pts` = outer ring only → island-in-lake modelled 5.5 mm too far → spurious trim | yes |
| 21 | Medium | `--density -1` emits `row_spacing_mm="-1.0"`; Ink/Stitch silently clamps to 0.378 mm | partly |
| 22 | Medium | `w = max(w_raw, wmin)` inflates a hairline **4.2×**, bleeding over neighbours | yes |
| 23 | Medium | `2·median(EDT)` overshoots **odd** widths by +1 px | yes |
| 24 | Medium | Closed skeleton loops emitted as **open** satin paths | yes |
| 25 | Medium | Staircase skeletons can emit **zero** satin → outline silently becomes fill | yes |
| 26 | Medium | `disc(3)` median filter = 54% of pre-separation time; runs over transparent background | no |
| 27 | Medium | `MIN_COMP_PX` gates raw pixels, simplification then shrinks below it | yes |
| 28 | Medium | `OUT.rsplit(".", 1)` writes the preview to the wrong directory | yes |
| 29 | Medium | EXIF orientation ignored → phone photos digitised 90° wrong | yes |
| 30 | Medium | `nn_sort` O(n²) pure Python | no |
| 31 | Low | `vectorize.py` runs at import time — unimportable, untestable; parser duplicated into `make_config.py` | no |
| 32 | Low | numpy 2 scalar repr (`np.int64(227)`) in every log line | visible |
| 33 | Low | Missing `--config` silently ignored; non-mapping YAML → bare `AttributeError` | yes |
| 34 | Low | Hexes without `#` in `skip_colors`/`order` silently ignored | yes |
| 35 | Low | `--border-mm -1` emits `stroke-width:-4.00` | visible |
| 36 | Low | `satin_max_mm` unreadable from YAML; `satin_outlines` undocumented | yes |
| 37 | Low | `.gitignore` blocks committing any test fixture | yes |
| 38 | Low | `demo()`'s width assertion is **vacuous** — cannot fail | n/a |
| 39 | Low | Dead code: `pts is None` branch, `len(poly) < 2`, unreachable `border_color` fallback | n/a |
| 40 | Low | **"up to ~10× less thread travel" — measured 1.06×** | no |
| 41 | Docs | Hole preservation is credited to `fill-rule="evenodd"`; Ink/Stitch never reads it | no |
| 42 | Docs | Posterized preview ≠ the SVG it claims to preview | no |
| 43 | Docs | Flag table omits `--config`/`--trim`; `SATIN_MAX_MM` double-listed; density floor wrong | no |
| 44 | **High** | Both config generators emit `mode: off` unquoted → the UI's "off (no border)" option does nothing | yes |
| 45 | Medium | `make_config.py` writes an `order:` listing the background colour, three times over | yes |
| 46 | Medium | `make_config.py` hardcodes `BORDER_MM = 2.5` → palette silently diverges from `vectorize.py` | yes |
| 47 | Medium | `make_config.py` duplicates the parser, inheriting `--colors` → k=1; no `mkdir` for `--out` | yes |
| 48 | Low | `analyze.py` uses MEDIANCUT, a different algorithm from the pipeline it debugs | no |

---

# Critical

## 1. A short flag silently overwrites an unrelated file with SVG

**`vectorize.py:52`, `58-61` · data loss**

```python
56:        else:
57:            _flags[_a[2:]] = True
58:    elif _a.startswith("-") and _a != "-":
59:        pass  # ignore short flags
60:    else:
61:        args.append(_a)
```

Short flags are discarded **without consuming their value**, and an unknown `--long` flag stores `True` without consuming the next token. Either way the next token becomes `args[0]` = the input image, and the token after that becomes `args[1]` = the output path. `open(OUT, "w")` at line 564 then truncates it.

**Verified — irreversible, exit 0:**

```
victim before: 2349 bytes  magic=b'\x89PNG'
cmd: vectorize.py -o a.png victim.png -> exit=0
victim after : 9194 bytes  magic=b'<?xm'
*** DATA LOSS: victim.png was overwritten with SVG = True ***
stdout: ['wrote /tmp/opencode/verify/victim.png']

unknown long flag --verbose: exit=0  DATA LOSS=True
```

`-o` is the single most natural short flag for "output". Any user who tries it loses whatever file they named second.

**Fix.** Delete lines 42-62 and use `argparse` (see #31) — it rejects unknown flags, supports `-o/--out`, and prints usage instead of reinterpreting positionals. As an immediate stopgap:

```python
elif _a.startswith("-") and _a != "-":
    sys.exit(f"error: unknown option {_a!r}; this script has no short flags "
             f"(did you mean --{_a.lstrip('-')}?)")
```

## 2. `SATIN_MIN_MM = 0.6` is below Ink/Stitch's 1.0 mm satin gate — 86.7% of satin outlines become running stitch

**`vectorize.py:93` (floored at `skeleton.py:85`)**

```python
93: SATIN_MIN_MM = 0.6         # narrower satin than this is widened to it
```

Ink/Stitch refuses to build a `SatinColumn` from a stroke thinner than `min_satin_stroke_width_mm`:

- `inkstitch/lib/utils/settings.py:12` → `"min_satin_stroke_width_mm": 1`
- `inkstitch/lib/elements/element.py:280-282` → `satin_threshold = metadata['min_satin_stroke_width_mm'] * PIXELS_PER_MM`
- `inkstitch/lib/elements/utils/nodes.py:53` → `if satin_column and (... or stroke_width > satin_threshold): SatinColumn(node) ... else: Stroke(node)`

Its own warning class says it plainly (`stroke.py:36-37`): *"This element renders as running stitch while it has a satin column parameter."*

**Verified two independent ways.**

*Isolated A/B export* — same 20 mm line, same `satin_column="true"`, only `stroke-width` differs. Satin = zigzag (many y-reversals); running stitch = walk (none):

```
narrow_0p8mm   stitches=  44  y-span= 0.00mm  zigzag reversals=   0  median step=2.400mm
wide_1p5mm     stitches= 412  y-span= 2.00mm  zigzag reversals= 404  median step=2.000mm
```

*Ink/Stitch's own element dispatcher* on a real pipeline output — the exact exporter code path:

```
    s3  SatinColumn  stroke_width=6.30 satin_threshold=3.78
    s4  SatinColumn  stroke_width=4.41 satin_threshold=3.78
    s5  Stroke       stroke_width=3.15 satin_threshold=3.78   <-- 0.833 mm  RUNNING STITCH
    s6  Stroke       stroke_width=2.27 satin_threshold=3.78   <-- 0.600 mm  RUNNING STITCH
```

*And on the repo's own artwork* (`bomb.svg`, 725 px → 100 mm, 7.25 px/mm), parsing every satin `stroke-width`:

```
bomb: 30 satin strokes, px/mm=7.25
  widths mm: min=0.617 p25=0.617 median=0.781 max=2.499
  BELOW the 1.0mm satin gate: 26/30 = 86.7%
```

**Fix.**

```python
93: SATIN_MIN_MM = 1.2   # Ink/Stitch's min_satin_stroke_width_mm is 1.0
```

Add a guard at emit time so it can never regress silently:

```python
def satin_el(id_, stroke_rgb, d, width_px, trim_after=False):
    width_px = max(width_px, 1.05 * px_per_mm)   # never emit a sub-gate satin
```

⚠️ The same trap applies to `--border-mm`: `--border-mm 0.8` makes the **border** a running stitch. Validate `BORDER_MM >= 1.0` too (#35).

## 3. Border satin is centred on the outer edge, not the ring midline → 1.25 mm unstitched ring, ~50% of the border off-patch

**`vectorize.py:214-227` (ring), `464-470` (stroke) — and its consumer `mask_for:301-302`**

Two different widths are never reconciled:

```python
214:    ring = silhouette & (dt > 0) & (dt <= max(2, BORDER_PX))
223:    border_ring = silhouette & (dt > 0) & (dt <= BORDER_PX) if ring.any() else None
...
235: interior_mask = silhouette & (~border_ring ...)     # fills lose a BORDER_PX-deep band
...
467:    ImageDraw.Draw(bim).line(ring_pts + ring_pts[:1], fill=o["index"],
468:                             width=max(1, int(round(BORDER_PX))), joint="curve")
```

`dt` satisfies `dt = x + 1` for a pixel `x` rows inside a straight edge, so `border_ring` spans `dt = 1 … BORDER_PX`, midline `dt ≈ (1+BORDER_PX)/2`. But the path is the `find_contours(…, 0.5)` contour — sitting at `dt = 0.5`, on the edge — and the stroke is **centred** on it, reaching only `BORDER_PX/2` inward. The code even documents the half-width at lines 462-463 (*"the stroke only reaches half way in"*) without acting on it.

**Verified, three ways.**

Synthetic disc, 4 px/mm, `BORDER_MM=2.5`:

```
patch area                       :   4417.6 mm^2
filled                           :   3853.3 mm^2
border thread ON patch           :    288.3 mm^2  (r 144..150 px)
border thread OFF patch (hangs)  :    297.2 mm^2  (51% of the border!)
UNSTITCHED GAP (neither)         :    275.9 mm^2  (6.2% of the patch)
   gap radii: r 140.0..146.2 px = 1.55 mm wide annulus

CORRECT: satin centre at r=145.5 (ring midline), covering r 140.5..150.5
ACTUAL : satin centre at r=150.0 (the outer edge), covering r 145..155
```

Real artwork, per patch:

```
Bomb_patch.webp  (725x725, 7.25 px/mm)   gap ~1.25 mm, 381.0 mm^2   border off-patch 500.7 mm^2 (48%)
Skyfowl_patch.webp (1000x1000, 10.00)    gap ~1.25 mm, 387.1 mm^2   border off-patch 460.7 mm^2 (49%)
Book_burner_patch.PNG.webp (647x663)     gap ~1.25 mm, 394.2 mm^2   border off-patch 208.6 mm^2 (28%)
```

Straight out of the emitted SVG (Skyfowl, 10 px/mm):

```
border  stroke 25.0 px = 2.50 mm, path min x = 39.5  -> covers x 27.0 .. 52.0
color4  #463428  fill min x = 64.5
  UNSTITCHED BAND = 12.5 px = 1.25 mm
```

Measured effect of the two candidate fixes:

```
current: unstitched ring px 42666 = 426.66 mm^2 | satin outside patch 45142 = 451.42 mm^2
fixed  : unstitched ring px  1545 =  15.45 mm^2 | satin outside patch  2105 =  21.05 mm^2
```

**Fix — two options, both verified.** Either inset the contour:

```python
209:    half = max(1, int(round(BORDER_PX / 2)))
210:    mid = ndimage.binary_erosion(silhouette, structure=morphology.disk(half), border_value=0)
211:    padded = np.pad(mid, 1)
212:    contours = measure.find_contours(padded, 0.5)
```

…or, simpler, stop excluding more than the stroke covers:

```python
223:    border_ring = silhouette & (dt > 0) & (dt <= BORDER_PX / 2) if ring.any() else None
```

**Regression test** (fails today):

```python
def t_border_no_gap():
    # synthetic disc, BORDER_MM=2.5
    assert gap_area == 0 and hanging_area / stroke_area < 0.05
```

## 4. `max(contours, key=len)` picks the *longest* contour, not the outer boundary

**`vectorize.py:210-211`**

```python
210:    contours = measure.find_contours(padded, 0.5)
211:    outer = (max(contours, key=lambda c: len(c)) - 1) if contours else None
```

`len(c)` is the number of marching-squares edge crossings — i.e. **perimeter**. The outer boundary of a patch has the largest *area*, not necessarily the longest perimeter, and `find_contours` returns hole contours and every disconnected component in the same list. Note `contour_paths` already does this correctly at line 347 (sorts by `-areas[i]`) — so the file contradicts itself.

**Verified — a comb-shaped hole beats the patch edge:**

```
contours (sorted by point count):
   pts= 2881 area=   342.47 mm^2      <-- the COMB HOLE
   pts= 1437 area=  6359.53 mm^2      <-- the real patch boundary
max(len) picks pts=2881 area=342.47 mm^2
WRONG PICK
```

```
border: color (...) width 2.5 mm (41 pts)
E-hole case: border path bbox x 150..300 y 120..289 (41 pts, stroke-width 10.00)
```

A satin border is stitched around a hole **21× smaller than the patch**, and the patch edge gets no border at all. A thin squiggle steals it from a big badge the same way:

```
== big badge + long thin squiggle
   contour pts= 2879  area=  169.03 mm^2  <-- PICKED by max(len)
   contour pts=  725  area= 2047.53 mm^2  (largest AREA, 12.1x bigger)
```

**Fix** — match what line 347 already does:

```python
210:    contours = measure.find_contours(padded, 0.5)
211:    if contours:
212:        areas = [abs(np.trapezoid(c[:, 1], c[:, 0])) for c in contours]
213:        outer = contours[int(np.argmax(areas))] - 1
214:    else:
215:        outer = None
```

Still only **one** border for a multi-component silhouette — that's by design (`border_path_d` is a single path) but is undocumented.

---

# High

## 5. One stray transparent pixel reclassifies an engraving as a patch

**`vectorize.py:153-154`, `170-173`, `205`**

```python
153: transparent = alpha < 128
154: has_transparency = bool(transparent.any())
```

All-or-nothing on the *existence* of a single `alpha < 128` pixel. One stray pixel makes `silhouette = ~transparent` mean "everything except that pixel", so the border ring, border contour and interior palette are all computed against the **whole rectangular canvas**.

**Verified** — an opaque image plus one `alpha=0` pixel at (0,0):

```
image 400x400 -> 100x100 mm (4.0 px/mm), palette k=5
order: ['#f5f5f5', '#f5f5f5', '#f5f5f5', '#c82828', '#141414']
```
```xml
<g inkscape:label="Border" ... id="border">
  <path id="s3" style="fill:none;stroke:#f5f5f5;stroke-width:10.00"
        d="M 399.0,399.5 L -0.5,399.0 L -0.5,1.0 L 1.0,-0.5 L 399.5,0.0 L 399.0,399.5 Z"/>
</g>
```

A **2.5 mm near-white satin rectangle around all four edges of the canvas**, because `border_color` samples the outer 2.5 mm of white paper. One stray pixel in a phone photo would do the same.

**Fix**

```python
154: has_transparency = bool(transparent.mean() > 0.01)   # 1% of pixels
```

## 6. `border: mode: off` is a YAML boolean — the border is never disabled

**`vectorize.py:114`, `203`, `207`**

PyYAML implements YAML 1.1, where bare `off`/`on`/`yes`/`no` are **booleans**. `make_config.py:112` writes the template comment `# Border: mode = auto | off | force_black` **unquoted**, so a user editing it to `mode: off` gets `_border_mode is False`, and `False == "off"` is `False`.

**Verified end-to-end** on a transparent-background patch:

```
  mode: off       (unquoted ) -> border emitted? True   <-- BUG: wanted OFF
  mode: "off"     (quoted   ) -> border emitted? False
  mode: auto      (auto     ) -> border emitted? True
```
```
  mode: off            -> False           == 'off'? False
  mode: "off"          -> 'off'           == 'off'? True
```

It also silently corrupts the palette: with the border "off", `border_ring` stays `None`, so the outer ring's colour re-enters the interior palette.

**Fix** — normalise and validate:

```python
114: _border_mode = str(_border_cfg.get("mode", "auto")).strip().lower().replace("-", "_")
115: if _border_mode not in ("auto", "off", "force_black"):
116:     sys.exit(f"error: border.mode must be auto|off|force_black, got {_border_mode!r}")
```

and quote it in the `make_config.py` template: `mode: "auto"`.

## 7. `border: mode` typos silently behave as `auto`

**`vectorize.py:114`, `207`**

`mode: Force_Black`, `FORCE_BLACK`, `none` — none match, none are rejected:

```
  --- b1.yaml: mode: FORCE_BLACK
      border: color (np.int64(200), np.int64(40), np.int64(40))   <-- auto, not black
  --- b2.yaml: mode: force_black
      border: color (np.int64(0), 0, 0)                           <-- correct
```

Fixed by the validation in #6. Same class: `satin_max_mm` isn't readable from YAML at all (#36).

## 8. `lw_cover`'s `disk(2)` dilation carves fill the satin never reaches

**`vectorize.py:384-385`, `396-397`** — a *second*, independent source of unstitched fabric (the first is #3).

```python
384:        lw_cover = ndimage.binary_dilation((np.array(cover_img) > 0) & lw_mask,
385:                                           structure=morphology.disk(2))
...
396:     if c == lw and lw_cover is not None:
397:         mask = mask & ~lw_cover
```

The stroke reaches `width=round(w)` px, but the carve-out reaches `w/2 + 2` px. The halo is bare fabric.

**Verified** (4 px line + 20 px block of the same colour; metric = pixels removed from the fill **and** not covered by satin):

```
    4px line + 20px block @7.0ppmm disk(0)                 BARE=   0 ( 0.000 mm2)
    4px line + 20px block @7.0ppmm disk(1)                 BARE= 156 ( 3.184 mm2) widest=4px=0.571mm
    4px line + 20px block @7.0ppmm disk(2)  <- AS SHIPPED  BARE= 254 ( 5.184 mm2) widest=4px=0.571mm
```

`disk(0)` → **0**, so the dilation is unambiguously the cause — not `approximate_polygon`, whose DP deviation stays inside the satin half-width. Magnitude scales as **0.4 mm wide at 10 px/mm up to 1.0 mm at 4 px/mm** (1.0–15.9 mm²), worst on *low*-resolution sources — the same ones flagged by #14.

Cleanly ruled out: `w_raw > wmax` and the `SATIN_MIN_LEN_MM` cut cannot cause this, since a dropped segment contributes nothing to `cover`, so its pixels stay in the fill.

**Fix**

```python
384:    raw = (np.array(cover_img) > 0) & lw_mask
385:    lw_cover = (ndimage.binary_dilation(raw, structure=morphology.disk(1)) & ~raw) | raw
```

The `disk(2)` halo is deliberate (comment at 382-383: avoid sub-mm slivers) — but the trade is *bare fabric*, not slivers. Either narrow it or log it.

## 9. Duplicate k-means clusters are always empty → `order:` silently mis-targeted

**`vectorize.py:188`, `275`, `285-288` — CORRECTED**

Centroids are clipped and rounded to `int` (line 188) with no dedupe, and `hex_to_idx` (line 275) is **last-wins**. But `label_all` is `np.argmin`, which breaks ties at the **lowest** index — so all pixels of a duplicated colour land on the lowest index and the higher duplicates get **zero components**.

**Verified** (3-colour image, default `--colors 5`):

```
order: ['#f0e63c', '#c82828', '#1e1e1e', '#1e1e1e', '#1e1e1e']
  (240, 230, 60): 1 comps (dropped 0)
  (200,  40, 40): 1 comps (dropped 0)
  ( 30,  30, 30): 2 comps (dropped 0)
  ( 30,  30, 30): 0 comps (dropped 0)     <-- duplicates are EMPTY
  ( 30,  30, 30): 0 comps (dropped 0)
```

> **Retracted.** An earlier draft of this review claimed duplicates produce "three identical fill layers" of the same colour. That is **wrong** — the duplicates are always empty. The real damage is: (a) `order: ['#1e1e1e']` resolves to the *highest* index, naming an **empty** layer, so the requested stitch position is silently discarded and the two emitted SVGs are byte-identical; (b) `palette k=5` over-reports for a 3-colour image; (c) ~0.12 s per duplicate wasted on two full-image morphology passes. A 1600-palette-run search also found **zero** cases of two *distinct* centroids colliding into one hex, so that risk is theoretical.

**Fix** — resolve hexes to the index that actually owns pixels, and dedupe:

```python
275: _owners = np.bincount(label_all[interior_mask], minlength=len(centroids))
276: hex_to_idx = {}
277: for c in range(len(centroids)):
278:     if _owners[c]:                              # first owner wins, matching argmin
279:         hex_to_idx.setdefault(hexkey(c).lower(), c)
...
288: fill_colors = list(dict.fromkeys(listed + [c for c in _default_colors if c not in listed]))
```

plus one warning when the palette collapses.

## 10. 8-neighbour `deg >= 3` flags pixels *around* crossings as junctions

**`skeleton.py:12`, `24-25`, `41-56`**

Under 8-connectivity an arm pixel one step from a crossing centre is diagonally adjacent to both perpendicular neighbours, so it reports degree 3-4. `junctions = {p for p, d in deg.items() if d >= 3}` swallows the whole crossing, and both passes `continue` past it.

**Verified:**

```
  plus: 4 chains, skeleton px=21, covered=20
  DROPPED (in no chain): [(5, 5)]
  chain end points: [(4, 5), (5, 4), (5, 6), (6, 5)]
  all 4 stop ON a junction pixel: True
```

A 4-arm crossing becomes **4 satin columns instead of 2** (double tie-offs, double pull-compensation) with a bare centre. Junction rate on the real designs is low (0.5-2.2% of skeleton pixels), so this is a correctness wart rather than a disaster.

**Fix** — branch on the 4-neighbour count, keeping the 8-count only to stop a diagonal walk:

```python
def _counts(p, S):
    y, x = p
    n4 = n8 = 0
    for dy, dx in _NEIGHBORS:
        if (y + dy, x + dx) in S:
            n8 += 1
            if dy == 0 or dx == 0:
                n4 += 1
    return n4, n8

deg = {p: _counts(p, pts) for p in pts}
junctions = {p for p, (n4, n8) in deg.items() if n4 >= 3 or n8 >= 4}
```

## 11. Opaque background = *lightest cluster* → discards a real colour, fills the real background

**`vectorize.py:260-262`**

```python
260: if not has_transparency:
261:     lum = cluster_rgb.sum(axis=1)
262:     bg = int(np.argmax(lum))     # lightest = paper
```

`argmax` over the global palette picks whatever is brightest *anywhere*, not the cluster touching the canvas border. It also uses `sum(axis=1)` while fill ordering three lines later uses `luma()` — two different brightness metrics.

**Verified** on dark art (bg `#1a1a2e`, detail `#5566aa`, accent `#c87828`):

```
  background (skip) = (np.int64(200), np.int64(120), np.int64(40))     <-- the ORANGE ACCENT
order: ['#5566aa', '#1a1a2e', '#1a1a2e', '#1a1a2e']                    <-- accent gone
fills:
  (85, 102, 170): 1 comps
  (26,  26,  46): 1 comps <-- PAPER stitched as a fill
```

The accent is discarded and the entire background becomes a solid fill. Exit 0.

**Fix** — detect by border contact, and use `luma()` (must move below line 257):

```python
260: if not has_transparency:
261:     edge = np.concatenate([label_all[0, :], label_all[-1, :],
262:                            label_all[:, 0], label_all[:, -1]])
263:     bg = int(np.bincount(edge, minlength=len(centroids)).argmax())
```

## 12. `--flag=value` is silently ignored on booleans; `--colors` with no value becomes k=1

**`vectorize.py:50-52`, `57`, `81`, `83`, `88`**

Line 52 stores the *string* `"true"`; line 81 tests `is True`, which a string never satisfies. And line 57 makes a value-less flag `True`, so `int(flag("colors", "5"))` evaluates `int(True)` = **1**.

**Verified:**

```
  _flags = {'no-border': 'true'}    no-border flag is True?  False
$ ... vectorize.py --no-border=true simple.png out_b.svg
border: color (np.int64(200), np.int64(40), np.int64(40)) width 2.5 mm (5 pts)   <-- border STILL ON

$ ... vectorize.py --no-trim --no-border keepme.png out_k1.svg --colors
   palette k=1
   order: ['#9d3b59']
   -> exit 0, a 1-colour design written with no error
```

Line 111 has the same shape — `--no-satin-outlines=true` is truthy, so `not "true"` is `False` and the YAML override is skipped.

**Fix** — one truthiness helper plus validation:

```python
def flag(name, default=False):
    v = _flags.get(name, default)
    if isinstance(v, str):
        return v.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(v)

_raw = flag("colors", 5)
if not isinstance(_raw, int) or _raw < 1:
    sys.exit(f"error: --colors must be a positive integer, got {_raw!r}")
```

---

# Medium

## 13. Degenerate input → empty SVG, exit 0, then `BadZipFile` downstream

**`vectorize.py:472-473`, `564-565`**

**Verified:**

```
empty: exit=1  svg_written=no     # fully transparent -> correctly fails
one:   exit=0  svg_written=yes    # 1x1          -> silent empty success
flat:  exit=0  svg_written=yes    # single colour -> silent empty success
gray:  exit=0  svg_written=yes    # greyscale      -> silent empty success
```

```
$ cat o_one.svg
<svg ... viewBox="0 0 1 1" ...>
  <sodipodi:namedview id="namedview1" .../>
</svg>
```

`run.sh` (with working `set -e`) then exports it; Ink/Stitch writes to `work/$BASE.err` (buried), emits a non-zip blob, and `run.sh:50` dies on `BadZipFile`. Also: `--colors abc` / `0` / `-1` produce raw `ValueError` tracebacks.

**Fix**

```python
472: if not objs:
473:     sys.exit("error: no stitchable objects produced "
474:              "(single-colour image, or every colour is in skip_colors)")
```

## 14. `int()` truncation silently disables the speck/hole filters

**`vectorize.py:162-163`, `332`**

```
   100x100: px_per_mm=1.00 MIN_COMP_PX=   0 MIN_HOLE_PX=   0
   111x111: px_per_mm=1.11 MIN_COMP_PX=   0 MIN_HOLE_PX=   0
   112x112: px_per_mm=1.12 MIN_COMP_PX=   1 MIN_HOLE_PX=   0
   224x224: px_per_mm=2.24 MIN_COMP_PX=   4 MIN_HOLE_PX=   1
```

**Verified** — identical artwork at 2 resolutions:

```
100x100: (40,40,200): 12 comps (dropped 0)   <-- 12 unstitchable 0.81 mm^2 specks kept
400x400: (40,40,200):  0 comps (dropped 12)  <-- all correctly dropped
```

`docs/USAGE.md:115-116`'s promises are void below 111 px / 224 px. **Fix:** `max(1, int(...))`.

## 15. Label assignment: 694 MB for a 17 MB result, 4 GB and a hard crash at 25 MP

**`vectorize.py:255-257`**

```python
256: d2 = ((flat_all[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
```

Two full `(H·W, K, 3)` float64 temporaries. Measured RSS deltas for this statement alone:

```
===== 2000 x 2000 (opaque 34.8%)  RSS after load: 226 MB
  line 256-257  :   0.63s   RSS     978 MB  (+642 MB)
===== 4000 x 4000                    RSS after load:  684 MB
  line 256-257  :   2.45s   RSS    3560 MB  (+2605 MB)
===== 6000 x 6000                    RSS after load: 1446 MB
  line 256-257  :   5.77s   RSS    7888 MB  (+5831 MB)
```

It is a hard crash, not just slow, with no size guard anywhere in lines 149-165:

```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 2.79 GiB for an array
    with shape (25000000, 5, 3) and data type float64
```

And the transparent pixels are pure waste — both consumers mask by `silhouette` (lines 300, 569), so the line-254 comment is **factually wrong**:

```
(b) line 256 on all 4000000 px : 0.66s
    on the 1539277 silhouette px only: 0.30s (55% faster) ; labels agree: True
    gemm form on all px: 0.34s (49% faster) ; identical labels: True
```

**Fix** — label only the silhouette, via the gemm form (bit-identical output, verified):

```python
255: _pix = rgb[silhouette].astype(np.float32)
256: _d2 = (_pix*_pix).sum(1)[:, None] - 2.0*(_pix @ centroids.T) + (centroids**2).sum(1)[None, :]
257: label_all = np.zeros(H*W, dtype=np.uint8)
258: label_all[silhouette.ravel()] = np.argmin(_d2, axis=1)
```

Plus an explicit size guard near line 157.

## 16. `contour_paths` is ~74% of runtime

**`vectorize.py:331-341`**

```python
331:     comp = (lab == c)                       # full H x W, per component
335:     padded = np.pad(comp, 1)                 # another full H x W
337:     for cnt in measure.find_contours(padded, 0.5):   # scans EVERY contour in the image
```

Cost is `O(n_components · H · W)`. Textbook linear in component count:

```
  ncomp      npix  contour_paths s  ms / comp
      1       576             0.027      27.33
    100     57600             1.245      12.45
   1000    576000            12.382      12.38
```

Flat 12.4 ms per component at 4 Mpx. End-to-end, `contour_paths` alone is **74%** of a 33.5 s run. The fix, measured: **3.76× faster, byte-identical SVG**.

**Fix** — crop to each component's bbox via `ndimage.find_objects`:

```python
lab, n = ndimage.label(mask)
boxes = ndimage.find_objects(lab)
counts = ndimage.sum_labels(mask, lab, index=np.arange(1, n + 1))
for c in range(1, n + 1):
    if counts[c-1] < min_area: dropped += 1; continue
    sl = boxes[c-1]; cmask = lab[sl] == c
    for cnt in measure.find_contours(np.pad(cmask, 1), 0.5):
        poly = measure.approximate_polygon(cnt - 1, tolerance=tolerance)
        poly = poly.astype(float); poly[:,0] += sl[0].start; poly[:,1] += sl[1].start
```

## 17. `stitch_index` is a full-image compare per emitted object

**`vectorize.py:436`** — `O(n_objects · H · W)`:

```
stitch_index: 2000x2000  1000 objects ->   0.738 s  (  0.74 ms/object)
stitch_index: 4000x4000  1000 objects ->   5.769 s  (  5.77 ms/object)
```

Fix with the bbox from #16: `stitch_index[sl][lab[sl] == c] = o["index"]`.

## 18. Trim measures nearest-*boundary*, not the travel the machine makes

**`vectorize.py:479-487`**

`pts` holds only the **outer** ring (line 359), and Ink/Stitch stitches each fill in its own scanline order — so the real exit→entry travel is unrelated to the nearest-boundary distance the code computes.

**Verified** on the exported `Bomb_patch` VP3 (853 objects, 265 `trim_after` flags):

```
largest STITCH->STITCH step: 40.0 mm at record 35064
STITCH->STITCH steps > 4mm (sewn travel across the patch): 6
```

Six transitions the code judged `d <= 4 mm` **and** "hidden" are sewn as unbroken 4-40 mm moves. The trim machinery itself is sound — 266 `TRIM` commands for 265 flags, 0 unexpected `JUMPs`.

**Fix** — be conservative, since the true endpoints are unknowable here: use the centroid distance as the bound.

## 19. `is_hidden` probes a fixed 0.5 mm lattice

**`vectorize.py:492`** — `n` is derived from the mm length, so probe spacing is hard-coded at ≈0.5 mm regardless of `px_per_mm`. Any jump crossing a covering stitch thinner than 0.5 mm is judged exposed:

```
2mm jump straight across a 1px later stitch   n_samples= 44 spacing=0.494mm is_hidden=False truly exposed= 0.25%
```

0.25% of thread shows, yet it gets a lock pair and two cuts. **Fix:** probe per pixel, `n = max(8, int(np.hypot(*(p1 - p0))))`.

## 20. `pts` = outer ring only → spurious trim on island-in-lake geometry

**`vectorize.py:355-359`, `487`**

`keep` holds the outer ring *and* every kept hole ring (joined into `d` at line 354), but only the outer ring reaches `pts`. An island sitting in a lake inside an annulus of the same colour is therefore modelled far away:

```
annulus (pts = outer ring only) vs island inside its hole : modelled gap = 5.971 mm
same pair, but hole ring included in pts                  : true gap      = 0.471 mm
over-estimate = 5.500 mm   TRIM_MIN_MM=2.0 -> modelled: TRIM ; true: no trim
```

**Fix:** `pts.append(np.vstack([np.asarray(p, dtype=float) for p in keep]))`.

## 21. `--density -1` emits `row_spacing_mm="-1.0"`; Ink/Stitch silently clamps to 0.378 mm

**`vectorize.py:144-147`**

The loop only *prints* — contrast lines 121-122, which **do** clamp `TRIM_THRESHOLD_MM`.

**Verified:**

```
  inkstitch PIXELS_PER_MM = 96/25.4 = 3.7795
  fill_stitch floor = 0.1 * that = 0.3780 mm
  --density -1    -> emitted row_spacing_mm=-1.0    warned=yes
  --density 0     -> emitted row_spacing_mm=0.0     warned=yes
  --density 0.2   -> emitted row_spacing_mm=0.2     warned=yes
```

`inkstitch/lib/elements/fill_stitch.py:379`: `max(self.get_float_param("row_spacing_mm", 0.25), 0.1 * PIXELS_PER_MM)`. So the documented "safe 0.3-0.6 mm" band has an unreachable bottom third, and a negative value ships as a malformed SVG parameter. **Fix:** clamp to `min(max(v, 0.38), 0.6)`; correct the docs to `0.38-0.6`.

## 22. `w = max(w_raw, wmin)` inflates a hairline **4.2×**

**`skeleton.py:85` + `vectorize.py:380-381`, `527`**

`cover_draw` is intersected with `lw_mask` (line 384) but the **emitted satin is not** — `satin_el` writes `stroke-width` unclipped:

```
  source line: 2 px wide = 0.286 mm
  emitted satin width: 4.20 px = 0.600 mm (2.1x the source width)
  satin pixels OUTSIDE lw_mask: 100 px -- these overwrite whatever colour sits next to the outline
```

A 1-px hairline becomes 0.600 mm (**4.2×**). The widening is intentional and documented; the bound and the cross-colour consequence are not. **Fix:** `w = min(max(w_raw, wmin), wmin + 1.0)`.

## 23. `2·median(EDT)` overshoots **odd** widths by +1 px — CORRECTED

**`skeleton.py:79`** — I earlier assumed this *underestimates*. **Wrong.** `distance_transform_edt` measures to the first background pixel, so even N is exact and odd N is +1:

```
   N  w_raw  true  err        N  w_raw  true  err
  1   2.00     1  +1.00       6   6.00     6  +0.00
  2   2.00     2  +0.00       7   8.00     7  +1.00
  3   4.00     3  +1.00       8   8.00     8  +0.00
  4   4.00     4  +0.00       9  10.00     9  +1.00
  5   6.00     5  +1.00
```

It is also **insensitive to off-centre skeletons** (0.00 px spread over 1/3-px shifts), which I had predicted would be fragile.

> ⚠️ **Interacts with #2.** Fixing this makes satins *narrower*, pushing more below the 1.0 mm gate. Land `SATIN_MIN_MM = 1.2` **and** this together.

**Fix:** `w_raw = 2.0 * float(np.median(dist[...])) - 1.0`.

## 24. Closed skeleton loops are emitted as **open** satin paths

**`skeleton.py:48-56`, `86`**

**Verified:** `satin d ends with 'Z' (closed)? False`. Across all four repo designs **zero** outline satin columns are closed (553 checked) — each closed outline loop gets two thread ends and two tie-offs mid-ring. The gap is ~0.14 mm, below `TRIM_MIN_MM`, so it's a cleanliness issue, not a hole.

⚠️ **Do not fix by appending `Z`.** `inkstitch/lib/elements/utils/stroke_to_satin.py:87` raises `SelfIntersectionError` when `path[0]` and `path[-1]` are within 1 px; closing would trip it and trigger a recursive `split_path`. Open is correct for Ink/Stitch — document it.

## 25. Staircase skeletons can emit **zero** satin → the outline silently becomes fill

**`skeleton.py:25`, `54-56`, `73` — scope corrected**

```
  step=1: mask=  80 skel=  22 chains=  1 lens=[22] -> satin cols=1
  step=2: mask=  40 skel=  40 chains= 20 lens=[2, 2, 2, 2, 2, 2] -> satin cols=0
  step=3: mask=  28 skel=  28 chains= 14 lens=[2, 2, 2, 2, 2, 2] -> satin cols=0
```

> **Partially refuted.** A subagent claimed 2×2-block staircases break this; my re-test gave a connected 19-px skeleton and 1 satin column. The bug is real but **geometry-dependent** — it needs stride ≥ 2, where `skeletonize` leaves non-adjacent pixels emitted as 2-px chains that `SATIN_MIN_LEN_MM` discards. 45° PIL-rendered diagonals are fine. The consequence is what matters: the outline becomes a plain fill, which is exactly what `--no-satin-outlines` should opt into explicitly. Mostly fixed by #10.

## 26. `disc(3)` median = 54% of pre-separation time, over the transparent background

**`vectorize.py:179-181`**

```
[t] median_filter  1.90s        <-- 54% of all time up to line 300
Scaling: 2.01s @2000², 6.91s @4000², 15.56s @6000²
(a) whole frame 2.12s   silhouette bbox only 1.58s (25% saving)
```

It also runs on a strided view of `arr[..., :3]` (1.14× slower than contiguous). Secondary defect: transparent pixels hold `(0,0,0)`, so at convex corners the median goes black and paints a **black fringe** into the design, feeding both the border-colour sample and the palette.

## 27. `MIN_COMP_PX` gates raw pixels, simplification then shrinks below it

**`vectorize.py:332` vs `:341`**

```
  fill[1] raw_px=138 ( 0.958 mm2, gate=0.80mm2)  emitted_poly_area=115.0px2 ( 0.799 mm2)  <-- BELOW MIN_COMP_MM2!
```

**Fix:** also gate on the simplified area.

## 28. `OUT.rsplit(".", 1)` writes the preview to the wrong directory

**`vectorize.py:576`** — with `OUT = "dir.v2/design"` the preview lands in `dir_posterized.png` one level up. **Fix:** `os.path.splitext(OUT)[0]`.

## 29. EXIF orientation is ignored

**`vectorize.py:149`** — a phone photo tagged `Orientation=6` is digitised 90° from what any viewer shows:

```
$ ... vectorize.py rot.jpg rot1.svg
image 600x300 -> 100x50 mm
raw size : (600, 300)      exif_transpose : (300, 600)
```

**Fix:** `ImageOps.exif_transpose(Image.open(IMG))`.

## 30. `nn_sort` is O(n²) pure Python

**`vectorize.py:413-415`** — clean 4× per doubling: `n=1000 → 0.190s`, `n=2000 → 0.769s`, extrapolating to ~4 min at n=50 000. Only 0.03 s in the measured pipeline, so this is a scale warning. **Fix:** vectorise the inner scan, or `cKDTree` (already imported).

---

# Low

## 31. `vectorize.py` runs entirely at import time

**whole file, esp. `42-66`, `149`, `564`** — no `main()`, no `if __name__ == "__main__":` (contrast `preview.py:82`, `skeleton.py:117`).

```
$ .venv/bin/python -c "import sys; sys.path.insert(0,'.../digitize'); import vectorize"
FileNotFoundError: "Scavenger's_Daughter_by_the_dusty_druid.webp"
```

Importing from a different CWD tries to digitize a hard-coded sample filename. **No function is unit-testable.** Worse, lines 42-62 are **duplicated verbatim** into `make_config.py:23-43` (19 of 20 lines identical), so the same bugs exist twice, and `make_config.py` has already inherited the `int()` crash. Three CLI conventions coexist in one directory: hand-rolled dict parser, raw `sys.argv[1]` (`analyze.py:17-18`), and `argparse` (`preview.py`).

**Fix:** wrap in `main(argv=None)` + guard, convert to `argparse`, delete the duplicate. This fixes #1, #12 and #13's tracebacks in one go.

## 32. numpy 2 scalar repr in every log line

**`vectorize.py:229, 268, 386, 404`** — the repo pins `numpy==2.2.6`:

```
border: color (np.int64(6), np.int64(6), np.int64(5)) width 2.5 mm (104 pts)
  (np.int64(227), np.int64(228), np.int64(233)): 355 comps (dropped 257)
```

`hexkey()` (line 272) already uses `int(v)`; the print sites don't. **Fix:** `"(" + ",".join(str(int(x)) for x in v) + ")"`.

## 33. Missing `--config` silently ignored; non-mapping YAML crashes

```
$ ... --config does_not_exist.yaml ...
   rc=0  (no warning about the missing file)
$ printf 'just-a-string\n' > bad.yaml && ...
AttributeError: 'str' object has no attribute 'get'
```

**Fix:** `sys.exit` on a missing path; validate the root is a dict.

## 34. Hexes without `#` in `skip_colors`/`order` are silently ignored

```
  skip_colors: [c82828]     -> order: [... '#c82828' ...] (unchanged)
  skip_colors: ["#C82828"]  -> works
```

`hexkey` always emits `#rrggbb`. **Fix:** normalise both sides, and warn on unknown keys.

## 35. `--border-mm -1` emits `stroke-width:-4.00`

```
border: color (...) width -1.0 mm (5 pts)
   emitted: stroke-width:-4.00
```

`-1` *is* consumed as the value (line 53 only rejects `--` prefixes). Validate `0 < BORDER_MM`, and enforce `>= 1.0` per #2. Related: `ring` (line 214) uses `max(2, BORDER_PX)` while `border_ring` (line 223) uses `BORDER_PX` — two thresholds for one concept, so below 2 px the palette silently changes:

```
  --border-mm 0.1: order: ['#e1e1e6', '#9fa0a2', '#6e6f70', '#3e3e3f', '#050505']
  --border-mm 2.5: order: ['#e3e4e9', '#d3d3d8', '#848486', '#4c4c4d', '#080908']
```

## 36. `satin_max_mm` unreadable from YAML; `satin_outlines` undocumented

```
  Skyfowl, YAML satin_max_mm: 0.2   -> satin outlines: 176 segments   <-- YAML IGNORED
  Skyfowl, CLI --satin-max-mm 0.2  -> (no satin outlines line)       <-- CLI works
```

Line 117-118 only consults the CLI arg. And `satin_outlines` works but appears **zero** times in `USAGE.md` and `README.md`.

## 37. `.gitignore` blocks committing any test fixture

```
  tools/digitize/tests/fixtures/tiny.png   -> .gitignore:16:*.png
  tools/digitize/tests/fixtures/tiny.webp  -> .gitignore:13:*.webp
  tools/digitize/tests/expected.svg        -> .gitignore:20:*.svg
```

The repo has **no test suite**, and `git add` would silently no-op on any fixture. **Do this before adding tests.** Fix: add `!tools/digitize/tests/**`.

## 38. `demo()`'s width assertion is vacuous

**`skeleton.py:112`** — `w = max(w_raw, wmin)` guarantees `w >= wmin` for *every* input:

```
  combinations tested where w < wmin (i.e. assertion could fail): 0
  -> assertion holds for EVERY input by construction; it cannot fail.
```

Line 97 also passes for any permutation. **Replace with a measurement assertion** (#23) and add a coverage invariant (#10).

## 39. Dead code

- `gap_and_segment`'s `pts is None` branch (481-484) is unreachable — `pts` is never `None`. Same for the `(H/2, W/2)` centroid fallback at line 458.
- `if len(poly) < 2: poly = arr` (`skeleton.py:83-84`) — Douglas-Peucker always keeps first and last vertex. Verified: 0 hits in 4000 cases. **Keep** the `max(1.0, tolerance)` floor on line 82 though.
- `vectorize.py:219-221`'s `else: border_color = black` fallback and the `if ring.any()` guard are unreachable — `ring.any()` is true for any non-empty silhouette.
- `dropped` counts only sub-`MIN_COMP` components; 400 silently-filled holes reported as `dropped 0`.

## 40. "up to ~10× less thread travel" — measured 1.06×

**README feature bullet; `vectorize.py:17-18`** — measured on the real 853-object `bomb.svg`:

```
shipped (needle carried across layers) :   2175.2 mm
baseline (needle reset each layer)     :   2308.1 mm
gain: 132.8 mm = 5.76% reduction, factor 1.061x
```

**Structurally impossible to be 10×**: layers are emitted in strict `fill_colors` order (line 431) because overlap requires light→dark. Only each layer's *starting* point moves. `IMPROVEMENTS_SPEC.md:23` states the accurate original design: *"nearest-neighbor TSP **within each color layer only**."* **Fix the claim**, or implement a real 2-opt over layer order under the precedence constraint.

---

# Docs

## 41. Hole preservation is credited to the wrong mechanism

`docs/USAGE.md:130-131` says holes are preserved via `fill-rule="evenodd"`. I verified the **outcome is correct** — an isolated export with `fill-rule` as a presentation attribute vs inside `style` gives byte-identical results (2034 stitches, 0 in the hole). But **Ink/Stitch never reads `fill-rule`**; it re-derives shell-vs-hole by subpath area:

`inkstitch/lib/elements/fill_stitch.py:934-941`
```python
paths.sort(key=lambda point_list: shgeo.Polygon(point_list).area, reverse=True)
shape = shgeo.MultiPolygon([(paths[0], paths[1:])])
```

The attribute is decorative for the machine file (Inkscape does honour it). The largest-ring-is-shell choice at lines 346-353 is **mathematically safe** — for a connected component the outer ring always wins the sort, and nested hole-in-hole rings are unreachable. Fix the explanation, not the code.

## 42. The posterized preview ≠ the SVG it claims to preview

`vectorize.py:567` comments *"posterized preview (for review)"*, but it's the raw k-means assignment. It shows none of the border-band exclusion, satin carve-out, or sub-`MIN_COMP`/`MIN_HOLE` drops:

```
preview pixels painted as the outline colour : 74520
pixels of that colour that became satin      : 74500
lw_cover (carved out of the fill)            : 57041 px
```

**Fix:** relabel the comment, or derive it from the emitted coverage.

## 43. Flag table and threshold drift

- `--config F` and `--trim` are **absent** from the CLI table (`USAGE.md:68-79`) though both are real and `--trim` is used in USAGE's own example on line 84 — yet the whole YAML feature depends on `--config`.
- `SATIN_MAX_MM` is listed **twice** with contradictory guidance (line 75 as a flag, line 111 as a non-flag "tunable constant").
- The density floor is wrong: both line 73 and 109 say "0.3", but Ink/Stitch clamps to **0.378** (#21).
- `USAGE.md:110` says "Ink/Stitch ignores satin below ~0.3 mm" — the gate is **1.0 mm**. *This doc error is precisely what let #2 through.*
- `USAGE.md:141-142` omits `fill_underlay_skip_last` and `pull_compensation_mm`, both always emitted and both changing the stitch count.
- Nothing documents that a transparent-background patch loses a `BORDER_MM`-deep band from its fills (#3) — the default path for every patch.
- `README.md` claims "Python 3.11+"; the spec pins 3.13 + `numpy==2.2.6`.

---

# Config generators (`make_config.py`, `make_config.html`)

Both are the UI for the YAML feature, and both reproduce bugs already listed above. The subagent assigned to these files was cancelled, so these were reviewed directly.

## 44. Both generators emit `mode: off` **unquoted** → the "off (no border)" control does nothing

**`make_config.py:114`, `make_config.html:145`**

```python
114:    mode: auto            # make_config.py, with the comment "auto | off | force_black"
```
```javascript
145:  L.push(`  mode: ${document.getElementById('borderMode').value}`);   // make_config.html
```

The HTML dropdown has an explicit `<option value="off">off (no border)</option>`. Selecting it writes `mode: off`, which PyYAML parses as boolean `False` — so `False == "off"` is `False` and **the border stays on**. This is finding #6 reached through the UI: the one control whose entire purpose is to disable the border silently fails.

**Verified** (`make_config.py:114` with the value edited to `off`):

```
  mode: off       (unquoted ) -> border emitted? True   <-- BUG: wanted OFF
  mode: "off"     (quoted   ) -> border emitted? False
```

**Fix** — quote in both places:

```python
114:    mode: "auto"
```
```javascript
145:  L.push(`  mode: "${document.getElementById('borderMode').value}"`);
```

…plus the validation from #6 so a hand-edited typo can't silently degrade to `auto`.

## 45. `make_config.py` writes an `order:` listing the background colour — three times

**`make_config.py:89-96`**

`make_config.py` never computes the background cluster. `vectorize.py:260-262` does, and drops it from `fill_colors`. So for any **opaque** image the generated YAML names a colour the pipeline will discard.

**Verified** (opaque image, white paper + red + blue, default `--colors 5`):

```
  make_config detected palette:
    #fafafa
    #fafafa
    #fafafa
    #b41414
    #1414b4
  vectorize order:    ['b41414', '1414b4']
  vectorize background (skip): 250,250,250

  make_config YAML 'order:' lists 5 colours: ['fafafa', 'fafafa', 'fafafa', 'b41414', '1414b4']
```

The user is handed a 5-entry list to reorder, **3 entries of which do nothing**. It also compounds #9: `hex_to_idx` is last-wins, so `order: ['#fafafa', ...]` resolves to whichever duplicate happens to be highest.

Note the palettes **do** agree for transparent-background patches at the default width (verified: `Bomb_patch.webp` → `['e3e4e9','d3d3d8','848486','4c4c4d','080908']` from both tools).

**Fix** — mirror `vectorize.py`'s background logic, and drop empties:

```python
# after centroids
owners = np.bincount(..., minlength=len(centroids))     # reuse the interior mask labels
if not has_transparency:
    lum = np.array([luma(c) for c in centroids])
    bg = int(np.argmax(lum))
centroids = [c for i, c in enumerate(centroids) if i != bg and owners[i]]
```

## 46. `make_config.py` hardcodes `BORDER_MM = 2.5`, so its palette silently diverges from `vectorize.py`

**`make_config.py:51`, `80-85`**

```
  'border-mm' appears in make_config.py: False
  BORDER_MM is a module constant: ['BORDER_MM = 2.5']
```

```python
81: border_px = BORDER_MM * px_per_mm          # 2.5, always
84: ring = silhouette & (dt > 0) & (dt <= max(2, border_px))
```

Two consequences:

- Run `make_config.py` (2.5) then `run.sh --border-mm 4 --config …` → the ring excluded from the palette differs, so the hexes `make_config` printed may not exist in `vectorize`'s palette, and the user's `order:`/`density:` entries silently miss.
- `make_config.py:84` uses `ring` with `max(2, border_px)` while `vectorize.py:223` uses `border_ring` with `border_px` — the same threshold divergence as #35, so below 2 px they disagree.

**Fix** — add `--border-mm` to `make_config.py`'s `_VALUE_FLAGS` and use `border_px` consistently (ideally factor both into one shared helper).

## 47. `make_config.py` inherits every parser bug from the duplicated block

**`make_config.py:23-43` (duplicated from `vectorize.py:42-62`)**

The same 20 lines are copy-pasted (19 of 20 byte-identical), so the same defects exist twice:

```
  --colors with no value -> exit=0
  detected palette (light -> dark):
    #d5a6b2                      <-- k=1, silently
  --colors 0    exit=1  ValueError: Cannot ask kmeans2 for 0 clusters (k was 0)
  --colors abc  exit=1  ValueError: invalid literal for int() with base 10: 'abc'
```

Also `make_config.py:124` writes with `open(OUT, "w")` and **no `os.makedirs`** (unlike `vectorize.py:66`):

```
  --out into a missing directory -> FileNotFoundError, exit 1
```

And `make_config.py:45` hardcodes the same machine-specific default input as `vectorize.py:64`.

**Fix** — delete the duplicated block; share one `argparse`-based parser between the two tools. Add `os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)`.

## 48. `analyze.py` is documented but never invoked

**`analyze.py` (whole file)**

It *is* referenced — `docs/USAGE.md:20` and `README.md` both mention it — so it is not dead code, but nothing calls it: `run.sh` doesn't, and no other tool does. It's a manual debugging aid, which is a legitimate thing to have; the issue is that it's **stale relative to the pipeline it debugs**:

- It uses `Image.quantize(method=Image.MEDIANCUT)` — a different algorithm from `vectorize.py`'s `kmeans2`, so its palette and component counts **do not correspond** to what the pipeline produces.
- It uses raw `sys.argv[1:2]` (line 17-18), a third CLI convention in the same directory.
- `ndimage.label` + `labels == lab` per component (lines 51-54) and `distance_transform_edt(c)` per component (line 61) repeat the O(n·H·W) anti-pattern of #16.
- It classifies background as "lightest colour" (line 42-43), the same flaw as #11.

**Fix** — either wire it to share `vectorize`'s palette code (once #31 lands), or say plainly in `USAGE.md` that it is an approximation that does *not* mirror the pipeline, so nobody debugs against a misleading palette.

---

# Verified non-issues (recorded so nobody re-raises them)

Things that looked like bugs and aren't:

- **`PYTHONHASHSEED` does not break determinism.** `pts` holds *int* tuples; Python randomises only `str`/`bytes` hashes. Full SVGs are byte-identical across seeds 0/7/4242 on all four repo images. (*Walk direction* is arbitrary, so half the outlines stitch "backwards" — cosmetic.)
- **`fill-rule="evenodd"` as a presentation attribute works** (outcome verified) — see #41 for the mechanism caveat.
- **All five `inkstitch:*` parameters are real** and honoured: `row_spacing_mm`, `fill_underlay_skip_last`, `trim_after`, `satin_column`, `pull_compensation_mm`.
- **`satin_el`'s `stroke-width` unit math is right** — `22.5 × (377.95/900) = 9.449` inkstitch-px = **2.500 mm**, exactly `BORDER_MM`.
- **Layer grouping doesn't reorder stitches.** `iterate_nodes` skips groups entirely; emit order == stitch order.
- **Trim machinery is sound** — 265 flags → 266 `TRIM` commands, 0 unexpected `JUMPs`.
- **`run.sh` propagates failures correctly.** `set -euo pipefail` works; a trailing value flag exits 1; a failed export aborts. (My first reading of "exit 0" was the `| tail` pipe reporting `tail`'s status.)
- **The uppercase `.PNG` chain in `run.sh` is consistent**, just ugly (`work/Book_burner_patch.PNG.svg`; every downstream step agrees).
- **`skimage.morphology.skeletonize`/`disk` are not deprecated** in 0.26.0.
- **Grayscale JPEG / palette PNG / 16-bit PNG / CMYK all work** via `.convert("RGBA")`.
- **`_poly_area`, `keep_lab`/`lab_id` bookkeeping, and `gap_and_segment`'s units are correct.**
- **`nbrs()` rebuilding a list per call** is 39% of `trace_skeleton` but only **~1% of total wall time**. Skip it.
- **`preview.py` is fast enough.** `draw.line` per stitch is not a bottleneck: measured **267,068 stitches/sec** on a real 43,409-stitch VP3 (0.16 s), i.e. ~2 s for a 500k-stitch design. Leave it.
- **`wxstub` handles deep submodule packages.** I expected `is_package=(fullname == "wx")` (line 148) to break nested imports; it doesn't — the meta-path finder catches each level:
  ```
  wx ok | wx.lib ok
  deep pkg: wx.lib.agw.aui ok
  ```
- **`preview.py` fails loudly on a missing input** (exit 1), and `_rgb()`'s `or "#000000"` fallback covers a `None` thread.
- **`analyze.py` is not dead code** — it is referenced from `README.md` and `docs/USAGE.md` (just never invoked; see #48).

---

# Recommended order

1. **#1 data loss** — `argparse` (#31) kills this, #12 and #13's tracebacks in one change. Highest severity, smallest diff.
2. **#2 satin gate** — one constant, restores the flagship feature on the repo's own samples.
3. **#3 border offset** — one line; removes a 1.25 mm unstitched ring from every patch.
4. **#6 + #7 + #44 `border.mode`** — YAML booleans plus validation; quote it in **both** `make_config.py:114` and `make_config.html:145`.
5. **#13 empty-success** — one `sys.exit`; stops CI reporting success on empty designs.
6. **#4 contour pick, #5 stray-alpha, #11 background, #9 duplicates** — each a small, self-contained correctness fix.
7. **#14 `max(1, …)`, #33/#34/#35/#36 input validation** — cheap hardening, all currently silent.
8. **#15/#16/#17/#26/#30 performance** — silhouette-only gemm labels, bbox-cropped `contour_paths`, sliced `stitch_index`, bbox-limited median. #16 alone is a measured 3.76× with byte-identical output.
9. **#37 `.gitignore`** — *before* writing tests, or the fixtures silently vanish.
10. Docs (#40-#43), then the rest.

---

# Coverage

Reviewed and verified: all of `vectorize.py`, `skeleton.py`, `run.sh`, `.gitignore`, `make_config.py`, `make_config.html`, `preview.py`, `analyze.py`, `tools/wxstub/`.

Every file in the repo is now covered. The one thing not attempted is the **`inkstitch/` vendored checkout** (gitignored, third-party) — it was read only to verify the emitted `inkstitch:*` contract, the satin gate, the `row_spacing` floor, and `fill-rule` handling.

Not covered, by choice:

- **`run.sh` shell hardening** beyond what I tested. The error paths I probed all behave (`set -e` propagation, trailing-flag exit 1, failed export). Worth a `shellcheck` pass if CI ever grows one; there are no tests for it today.
- **`inkstitch/` itself** — out of scope for this repo's review.