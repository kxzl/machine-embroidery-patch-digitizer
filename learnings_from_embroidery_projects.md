# Learnings from hand-digitized embroidery projects

**Summary.** Five Ink/Stitch projects the operator digitized by hand were read
both as SVGs (hand-tuned `inkstitch:*` attributes) and, where a VP3 exists, as
actual machine stitches. The single most important finding is that **the samples
never override `row_spacing_mm`, and their stitched output is at the Ink/Stitch
default of 0.25 mm — not our 0.4 mm** (inferred from a 0.75 mm underlay pitch =
3 × fill pitch, and from fill rows landing on a 0.2/0.3 mm alternation of the
0.1 mm VP3 grid). Satin pull compensation of **0.2 mm is confirmed** (Pledd), but
it is the exception, not the rule: four of five files leave it at the default
`0`. Real satin columns range **0.36–8.0 mm** wide, so our `SATIN_MIN_MM 1.2` /
`SATIN_MAX_MM 2.5` window is far narrower than what a digitizer actually draws.
The samples also routinely set `angle`, `fill_underlay`,
`fill_underlay_max_stitch_length_mm=2`, `ties=3` (ties **disabled**) on fills,
`underpath=true`, and
`min_stitch_len_mm=0` / `collapse_len_mm=3` — none of which our planned emit
sets. Details and exact numbers below; anything not directly measured is marked
**(inference)**.

---

## 1. Samples analyzed

All commands run from the repo root with `.venv/bin/python`. Throwaway scripts
lived in `/tmp/opencode/`.

| File | Role | Ink/Stitch elements | VP3 |
|---|---|---|---|
| `SailorMoon/SailorMoon_120_embroider.svg` | digitized, 100×100 mm | 110 carrying `inkstitch:*`: 7 fill paths, 79 satin columns (68 rail-based + 11 auto-fill), 24 running-stitch | 22,657 stitches · 7 threads · 6 colour changes · 35 TRIM · 0 STOP · **97.5 × 96.0 mm** |
| `SailorMoon/SailorMoon_200_embroider.svg` | digitized, 200×260 mm | 134 carrying attrs: 9 fill, 84 satin (72 rail + 12 auto), 41 running | 61,487 stitches · 11 blocks / 10 unique threads · 10 colour changes · 47 TRIM · 0 STOP · **196.9 × 206.5 mm** |
| `Terrier/Terrier_120_120.svg` | digitized, 120×120 mm | 65 carrying attrs: 10 fill, 28 satin (all rail), 27 running | 25,608 stitches · 7 threads · 6 colour changes · 21 TRIM · 0 STOP · **108.3 × 105.6 mm** |
| `Julegaver 2025/Pledd_skilt/pledd.svg` | digitized lettering, 100×100 mm | 172 carrying attrs: 93 satin, 78 running, 1 `<g>` lettering | 3,233 stitches · 1 thread · 0 colour changes · 27 TRIM · 0 STOP · **95.8 × 24.0 mm** |
| `Rave/Rave.svg` | SVG only, **260×200 mm = our hoop** | 12 satin columns, no fills | *(no VP3)* |
| `SailorMoon/SailorMoon_120.svg`, `SailorMoon_200.svg`, `Sailormoon_200mm` | pre-digitization sources | 21 / 24 / 3 attrs | — |
| `Terrier/Terrier.svg`, `Terrier.svg.2024_07_20_08_29_50.0.svg` | pre-digitization sources | **0** `inkstitch:*` attrs | — |
| `SailorMoon/SailorMoon.svg` | **corrupt as SVG** — it is a Windows Metafile (WMF), 4.2 MB, misnamed `.svg`. Skipped. | — | — |

VP3 encoding facts (read from `pystitch/Vp3Reader.py`, not guessed):
- Coordinates are integers in **0.1 mm**; `bounds()` gives min/max in 0.1 mm.
- VP3 has **no true JUMP command**. Travel is written as a long `STITCH`
  (`0x80 0x01` 16-bit move), and a cut is `0x80 0x03` → `TRIM`. The only
  `JUMP` records pystitch produces are the `move_abs` at each colour-block start
  (≤0.22 mm, 6–10 per file). **Do not count VP3 "jumps" to infer jump behaviour**
  — count segments after `TRIM` instead.
- `STOP` = 0 in every file. `END` = 1. All designs are single-end.

Stitch-length distributions (mm, consecutive `STITCH` segments; the `max` is
travel, not a stitch):

| File | mean | p50 | p90 | p99 | max |
|---|---|---|---|---|---|
| SailorMoon_120 | 1.974 | 1.972 | 3.002 | 3.970 | 92.6 |
| SailorMoon_200 | 3.048 | 2.970 | 5.946 | 8.538 | 255.2 |
| Terrier_120_120 | 1.853 | 1.803 | 3.000 | 3.041 | 108.0 |
| Pledd | 1.376 | 1.442 | 1.844 | 2.280 | 69.6 |

---

## 2. Attribute inventory (measured)

Every `inkstitch:*` attribute found on any element across the samples, with the
distribution of values. Counts are per occurrence.

| Attribute | n | Values / distribution |
|---|---|---|
| `satin_column` | 329 | `True` (case-normalised) |
| `pull_compensation_mm` | 93 | **`0.2`** — every one, all in `pledd.svg` |
| `running_stitch_length_mm` | 168 | **`1.5`** (78, all Pledd) or **empty** (90, Terrier/SailorMoon → Ink/Stitch default **2.5**) |
| `fill_underlay` | 68 | `True` / `False`; fills that omit it get Ink/Stitch default `True` |
| `fill_underlay_max_stitch_length_mm` | 24 | **`2`** (every one) |
| `angle` | 62 | distinct **`-45, 15, 30, 45, 60, 330`** (330 = −30) |
| `ties` | 18 | `3` (fills, 4×) or `0` (satins, 14×); Ink/Stitch default is `0` |
| `underpath` | 34 | `True` (every one) |
| `contour_strategy` | 6 | `0` / `1` |
| `fill_method` | 28 | `auto_fill`, `circular_fill`, `contour_fill` |
| `auto_fill` | 21 | `True` |
| `reverse_rails` | 93 | `none` (every one, all Pledd) |
| `trim_after` | 26 | `true` (all Pledd) |
| `trim_before` | 0 | **absent** |
| `row_spacing_mm` | 0 | **absent everywhere** |
| `max_stitch_length_mm` | 0 | **absent everywhere** (only `fill_underlay_max_stitch_length_mm`) |
| `zigzag_spacing_mm` | 0 | **absent** (→ default 0.4) |
| `satin_underlay`, `center_walk_underlay`, `edge_underlay` | 0 | **absent** (→ all off) |
| `fill_underlay_inset_mm`, `fill_underlay_row_spacing_mm`, `fill_underlay_angle`, `fill_underlay_skip_last` | 0 | **absent** |
| `expand_mm` | 0 | **absent** |
| `join_style` | 2 | `0` |
| `smoothness_mm` | 2 | `0` |
| `clockwise` | 2 | `False` |
| `stroke_method` | 2 | `running_stitch` |
| `lettering` | 1 | JSON blob (Pledd text, font `Cirilic_old*`, `trim_option: 3`) |
| Global `<metadata>` | all | `min_stitch_len_mm = 0`, `collapse_len_mm = 3`, `inkstitch_svg_version = 1` or `2` |

Note: `satin_column` `stroke-width` is **decorative** (`0`, `1px`, `0.13px`,
`0.26px`). It is **not** the satin width — width comes from the distance between
the two rail subpaths. Our planned emit using `stroke-width` to carry satin
width is therefore a different mechanism from the samples.

Relevant Ink/Stitch defaults (repo `inkstitch/lib/utils/settings.py` and
`elements/fill_stitch.py` / `satin_column.py`), for the comparison:
`row_spacing_mm=0.25`, `max_stitch_length_mm=4.0`, `fill_underlay=True`,
`fill_underlay_row_spacing_mm = 3×row_spacing`, `angle=0`, `ties=0`,
`running_stitch_length_mm=2.5`, `zigzag_spacing_mm=0.4`,
`min_stitch_len_mm=0.1`, `collapse_len_mm=3`, `min_satin_stroke_width_mm=1`.

---

## 3. Fills

### 3.1 Density / row spacing (inference, strong)

The samples **never set `row_spacing_mm`**, so they use the default. The stitched
output shows what that default actually produced:

- **Terrier white fill (VP3, 0.1 mm grid).** Horizontal rows at distinct y =
  −476, −475, −472, −470, −467, −465, −462 … → successive gaps
  `3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2` (0.1 mm units). That is a **0.25 mm
  pitch alternating 0.3/0.2 mm** under 0.1 mm quantisation. (The −476/−475 pair
  is a tie-in artefact.)
- **SailorMoon_120 #ffde77 fill.** The underlay pass (see §3.2) sits on rows
  ~0.75 mm apart; `fill_underlay_row_spacing_mm` defaults to **3 × fill row
  spacing**, so fill spacing ≈ 0.75/3 = **0.25 mm**.
- **Terrier #fdfdfd fill** and **SailorMoon #ffde77 fill** main rows both give
  turn-to-turn perpendicular steps clustering at 0.2–0.4 mm (curved rows smear
  the exact value); the straight Terrier case is the reliable one.

**Our `ROW_SPACING_MM = 0.4` is ~60 % too open.** The samples' fills are ~1.6×
denser than ours. (Our `docs/USAGE.md` safe band 0.3–0.6 is a needle-safety
guide, not what the digitizer chose.)

### 3.2 Underlay (measured)

`fill_underlay` defaults to **True**; the samples only ever set it to `False`
to *disable* it on specific elements. Observed underlay in the VP3:

- **SailorMoon_120 #ffde77:** an underlay pass of ~2.0 mm stitches at ~0.75 mm
  row pitch, running **perpendicular to the fill angle** (fill ≈ +30°, underlay
  ≈ −59.5°; difference ≈ 90°, matching Ink/Stitch's default underlay angle =
  fill angle + 90°). This precedes the main fill (3.0 mm stitches, ~0.25 mm
  rows).
- `fill_underlay_max_stitch_length_mm = 2` is set explicitly on 24 elements
  (Ink/Stitch default would be `max_stitch_length`).
- Elements with `fill_underlay="False"` (e.g. SailorMoon_200 `#7796ff`,
  `#ffffff`, `#ffe9c9`; SailorMoon_120 `#fec03b`) show **no** underlay pass.

### 3.3 Angle (measured)

Per-element fill angles `-45, 15, 30, 45, 60, 330` are hand-chosen. Our raster
path emits no angle (defaults to 0° = horizontal), and `svg_digitize` has no way
to know the intended angle from geometry. This is a real quality gap (§7).

### 3.4 Method (measured)

`fill_method` is `auto_fill`, `circular_fill` or `contour_fill` — **not** plain
`tatami_fill`. `auto_fill="True"` appears on 21 elements (mostly auto-satin
regions). `contour_strategy` 0/1, `clockwise=False`, `join_style=0`,
`smoothness_mm=0` appear a few times. This reflects older Ink/Stitch naming
(`inkstitch_svg_version` 1–2); the repo's current code names the default
`tatami_fill`.

### 3.5 Max stitch length (measured)

Main fill stitches are **exactly 3.0 mm** in the straight Terrier rows and in
SailorMoon_120 #ffde77. `max_stitch_length_mm` is not set on any element, so
this is their Ink/Stitch version's default (the repo's current default is
4.0 mm). Underlay max is 2.0 mm (explicit).

---

## 4. Satin

### 4.1 Width (measured from rails)

Measured as the median nearest distance between rail subpath 1 and rail subpath
2, with all SVG transforms applied (`scale(0.264583)` px→mm, plus Pledd's
non-uniform `matrix(0.09499, 0, 0, 0.12507, …)`). Validated by the fact that
SailorMoon_200 is exactly 2× SailorMoon_120.

| File | n | min | p25 | median | p75 | max |
|---|---|---|---|---|---|---|
| SailorMoon_120 | 68 | 1.00 | 1.29 | 2.00 | 2.01 | 4.24 |
| SailorMoon_200 | 72 | 1.91 | 2.07 | 4.01 | 6.00 | 8.02 |
| Terrier_120_120 | 28 | 1.80 | 1.80 | **1.80** | 1.80 | 1.81 |
| Rave (SVG only) | 12 | 5.00 | 5.02 | 6.45 | 6.95 | 7.95 |
| Pledd | 93 | 0.36 | 0.76 | **0.99** | 1.21 | 1.97 |

Terrier is a constant 1.8 mm satin width; Rave (our hoop size) uses 5–8 mm
satin bands; Pledd's lettering satins are sub-1 mm. So **explicit satin columns
range 0.36–8.0 mm**, with no evidence of a 2.5 mm ceiling.

### 4.2 Stitch length / zigzag spacing (measured)

Pledd satin stitches alternate a cross-stitch and an along-column step:

```
-43.7,-10.4  ->  -43.7,-11.2   dy=0.80   (cross, = column width)
-43.7,-11.2  ->  -44.1,-10.4   d =0.89
-44.1,-10.4  ->  -44.1,-11.2   dy=0.80
```

i.e. **cross-stitch length ≈ column width (0.8 mm)** and **zigzag spacing ≈
0.4 mm** (the Ink/Stitch default; `zigzag_spacing_mm` is never set). This
matches the Terrier median stitch length of 1.8 mm for its 1.8 mm satins.
**Satin stitch length scales with column width; the along-column step does not.**

### 4.3 Pull compensation (measured)

`pull_compensation_mm = 0.2` on all 93 Pledd satins. **The other four files do
not set it at all** (Ink/Stitch default `0`). Our `SATIN_PULL_MM = 0.2` matches
the one digitizer who bothered; it is a safe value but not a universal one.

### 4.4 Underlay / reverse rails / running length

- **No satin underlay attributes are set anywhere** — `satin_underlay`,
  `center_walk_underlay`, `edge_underlay` are absent, so all default off. Satin
  stability comes from pull compensation and (see below) separate running paths.
- `reverse_rails = none` on all 93 Pledd satins (explicit); absent elsewhere.
- `running_stitch_length_mm`: **1.5 mm** on Pledd's 78 running paths; **empty**
  on Terrier/SailorMoon's running paths → default **2.5 mm**. Ink/Stitch's satin
  default is 2.5.
- Separate `autosatinrun*` running-stitch paths accompany the auto-satins:
  Pledd 78 paths totalling 259 mm (≈23 % of its 1,135 mm of satin rails),
  Terrier 27 paths / 608 mm (≈31 % of 1,967 mm), SailorMoon_200 39 / 893 mm.
  These are running-stitch companions to satin elements; whether they are
  centre-walk underlay or thin-detail fallbacks is **not certain (inference)**,
  but they are the only satin underlay present.

---

## 5. Trims, jumps, ties

- **TRIM counts:** SailorMoon_120 35, SailorMoon_200 47, Terrier 21, Pledd 27.
  Pledd has 26 explicit `trim_after="true"` attributes → its trims are
  deliberate. The other files have **zero** explicit `trim_after`, so Ink/Stitch
  auto-inserted their trims at export.
- **Trimmed jump lengths** (distance from the TRIM record to the next stitch):

| File | n | min | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|
| SailorMoon_120 | 33 | 1.81 | 5.02 | 10.00 | 14.41 | 17.85 | 92.60 |
| SailorMoon_200 | 46 | 0.20 | 8.25 | 18.20 | 31.60 | 58.18 | 255.18 |
| Terrier_120_120 | 19 | 0.14 | 14.92 | 33.50 | 50.78 | 61.80 | 108.00 |
| Pledd | 25 | **1.57** | 2.72 | 3.74 | 4.67 | 6.17 | 69.64 |

  Pledd's operator cut jumps as short as **1.57 mm**; SailorMoon cut at 1.81 mm.
  This sits right around our `TRIM_MIN_MM = 2.0` floor (slightly below it).
- **Ties (measured):** Ink/Stitch semantics (`elements/element.py`):
  `ties` is `0 = Both`, `1 = Before`, `2 = After`, `3 = Neither`. The samples set
  `ties="3"` on 4 fill elements — i.e. ties **disabled** there — and `ties="0"`
  (= Both, the default) on 14 satins. Default behaviour already adds tie-in/out;
  no emit is needed.
- **Global:** `min_stitch_len_mm = 0` (overriding the 0.1 default),
  `collapse_len_mm = 3`.

---

## 6. Travel / underpath

- Travel after a trim is encoded as a long `STITCH`, e.g. SailorMoon_120
  `TRIM` at `(-409,-56)` then `STITCH` to `(-477,14)` = 9.76 mm; Terrier
  `TRIM` at `(-21,-237)` then 47.3 mm travel. The `STITCH`-length `max` column
  in §1 is these travels.
- `underpath = True` on 34 satin/auto-fill elements and is the fill default
  (`fill_stitch.py:496`), so the digitizer let Ink/Stitch route travel under
  later-stitched geometry rather than expose it. Our planned emit sets no
  `underpath`; the default is `True` for fills, so behaviour matches unless we
  override it.
- Untrimmed long travel still exists (up to 73.9 mm SM120, 162 mm SM200,
  62.7 mm Terrier), mostly at colour-block boundaries where the needle changes
  thread — expected, since a thread change already moves without sewing.

---

## 7. Thread colours & order (measured)

| File | Blocks | Order (hex, stitches) |
|---|---|---|
| SailorMoon_120 | 7 | `#ffe9c9`(5955) → `#ffcbab`(1399) → `#ffde77`(7645) → `#fec03b`(1550) → `#ffcec7`(425) → `#ff8d82`(190) → `#000000`(5493) |
| SailorMoon_200 | 11 (10 unique) | `#000000`(1163) → `#7796ff`(3902) → `#ffffff`(3001) → `#ff565d`(1452) → `#ffe9c9`(13605) → `#ffcbab`(2672) → `#ffde77`(17350) → `#fec03b`(3060) → `#ffcec7`(844) → `#ff8d82`(396) → **`#000000`(14042)** |
| Terrier | 7 | `#d58d34`(4625) → `#bf641e`(2080) → `#fdfdfd`(8869) → `#dcddd7`(4546) → `#db2e3c`(208) → `#000000`(5203) → `#ffffff`(77) |
| Pledd | 1 | `#000000`(3233) |

Observations: the designs are **fill-heavy, not outline-satin-heavy** — the
largest blocks are fills (e.g. SailorMoon_200 `#ffde77` 17,350 stitches). Dark
`#000000` is used both first and last in SailorMoon_200 (11 blocks for 10
colours), i.e. the digitizer reused the black thread at the end rather than
merging layers — consistent with keeping **document order = stitch order**.
`Rave.svg` is the one file drawn at exactly 260×200 mm and contains only 12
wide satin columns and no fills; treat it as a hoop-size satin study, not a
complete design.

---

## 8. What our code should do

Each item states the value, the evidence, and where it applies.

1. **Fill row spacing → `0.25` mm.**
   Applies to **raster constant `ROW_SPACING_MM`** and the **`svg_digitize`
   emit** (`inkstitch:row_spacing_mm="0.25"`).
   Evidence: Terrier fill rows alternate 0.3/0.2 mm on the 0.1 mm grid = 0.25;
   underlay pitch 0.75 = 3 × 0.25. The samples never set the attribute.
   *Caveat:* 0.25 mm roughly doubles our current stitch count (~49k → ~70k at
   260 mm). If needle load is a concern, 0.30 mm is the closest safe compromise,
   but 0.25 is what was actually sewn.

2. **Emit explicit fill underlay attributes; drop `fill_underlay_skip_last`.**
   `svg_digitize` should emit `fill_underlay="true"` (or omit it — default is
   true) and `fill_underlay_max_stitch_length_mm="2"`. **Do not** emit
   `fill_underlay_skip_last="true"`: no sample sets it (default `False`), and it
   removes one stitch per underlay row, reducing density below what was sewn.
   Evidence: 24 elements set `fill_underlay_max_stitch_length_mm=2`; underlay
   rows measured 0.75 mm at ~2.0 mm stitch length.

3. **Emit fill `max_stitch_length_mm="3"`.**
   Applies to `svg_digitize`. Observed main-fill stitches are exactly 3.0 mm;
   the repo default is 4.0 mm. Setting it explicitly pins the behaviour rather
   than inheriting a version-dependent default.

4. **Do not emit `ties="3"` expecting ties. (Corrected.)**
   Ink/Stitch semantics are `0 = Both`, `1 = Before`, `2 = After`, `3 = Neither`
   (`elements/element.py`). `ties="3"` *disables* ties; the 4 sample fills that
   set it are opting out. Our emit sets no `ties`, so the default `0 = Both`
   already adds tie-in/out. No change needed; emit `ties="3"` only if you
   deliberately want to disable ties.

5. **Keep satin pull compensation at `0.2` — but understand it is optional.**
   `SATIN_PULL_MM = 0.2` and `pull_compensation_mm="0.2 0.2"` stay. Evidence:
   Pledd sets exactly 0.2 on 93 satins; the other four files leave it at 0. It
   is a good default, not a universal hand-digitizer choice.

6. **`SATIN_MAX_MM` is too low; raise to ~4.0 mm (or make it configurable).**
   Applies to the **raster constant** (outline→satin classification) and any
   satin-width gate in `svg_digitize`. Real satins measure up to 4.24 mm
   (SailorMoon_120), 8.02 mm (SailorMoon_200) and 7.95 mm (Rave). A 2.5 mm cap
   would classify genuine satin bands as fills.

7. **Reconsider `SATIN_MIN_MM = 1.2`.**
   Pledd's satins go down to 0.36 mm (median 0.99). The 1.2 mm floor distorts
   fine lettering. Note the 1.0 mm `min_satin_stroke_width_mm` gate applies to
   *stroke→satin conversion*, **not** to explicit `satin_column` paths, so
   explicit satins below 1.0 mm are legitimate. Keep 1.2 only for the raster
   path's synthetic satin; do not apply it to authored/explicit satins.

8. **Lower `TRIM_MIN_MM` to `1.5`.**
   Applies to the **raster constant** and the ported trim logic in
   `svg_digitize`. Pledd's operator trimmed jumps as short as 1.57 mm and
   SailorMoon at 1.81 mm; our 2.0 floor would leave those sewn.
   `TRIM_THRESHOLD_MM = 4.0` is consistent with the observed trimmed jumps
   (Pledd median 3.74) — keep 4.0, or lower to 3.0 to match Pledd more closely.

9. **Emit `underpath="true"` and consider satin `zigzag_spacing_mm="0.4"` /
   `running_stitch_length_mm="1.5"` / `reverse_rails="none"`.**
   Applies to `svg_digitize` satin emit. All are the samples' values
   (`underpath=True` on 34 elements; zigzag 0.4 default and measured; Pledd
   running length 1.5; Pledd `reverse_rails=none`). The current planned satin
   emit only carries `satin_column` + `pull_compensation_mm` + `trim_after`.

10. **Emit the global metadata the samples rely on.**
    Add `<inkstitch:min_stitch_len_mm>0</inkstitch:min_stitch_len_mm>` and
    `<inkstitch:collapse_len_mm>3</inkstitch:collapse_len_mm>` to the output
    `<metadata>`. All five digitized files set these (they override the 0.1
    default for min stitch length).

11. **Expose a fill angle; do not pretend geometry implies it.**
    Applies to `svg_digitize` (new `--fill-angle`, default `0`). Hand-digitized
    fills use per-element angles `-45, 15, 30, 45, 60, 330`. Neither the raster
    path nor the new SVG path can infer this from shape geometry; leaving it at
    0 is acceptable but should be a stated limitation.

### Behaviours the raster path cannot express (and which of them the SVG path should)

| Hand-tuned behaviour | In samples | Raster path | New `svg_digitize` |
|---|---|---|---|
| Per-element fill `angle` | yes (6 values) | no | add `--fill-angle` (global only) |
| `fill_underlay` per element | yes (T/F) | no | yes, emit |
| `fill_underlay_max_stitch_length_mm=2` | yes | no | yes, emit |
| `fill_method` auto/contour/circular | yes | no (tatami default) | no (intent not recoverable) |
| `contour_strategy`, `clockwise`, `join_style`, `smoothness_mm` | yes | no | no |
| `ties=3` (ties **off**) | yes (4 fills) | no | no — default 0 already ties |
| `underpath=True` | yes | default only | yes, emit |
| `reverse_rails=none` | yes | no | yes, emit (optional) |
| `auto_fill` region satins | yes | no | no |
| `lettering` | yes (Pledd) | no | no |
| `trim_after` | yes (Pledd) | yes | yes |
| `pull_compensation_mm=0.2` | yes (Pledd) | yes (`SATIN_PULL_MM`) | yes |

### Not applicable / no change

- `MIN_COMP_MM2`, `MIN_HOLE_MM2`: samples keep authored detail; HANDOFF §5
  already says the SVG path must not drop components. No change.
- `expand_mm`, `trim_before`, `fill_underlay_inset_mm`,
  `fill_underlay_row_spacing_mm`, `fill_underlay_angle`: absent in all samples;
  leave at defaults.
- `satin_underlay` / `center_walk_underlay` / `edge_underlay`: absent; keep off.
- VP3 "JUMP" counts: meaningless for craft inference (see §1); do not tune to
  them.

---

*Corrupt/unreadable sample: `Embroidery_samples/SailorMoon/SailorMoon.svg` is a
Windows Metafile, not SVG. `Terrier.svg` and
`Terrier.svg.2024_07_20_08_29_50.0.svg` are pre-digitization sources with no
`inkstitch:*` attributes. `SailorMoon_120.svg`, `SailorMoon_200.svg` and
`Sailormoon_200mm` are likewise sources; the `*_embroider.svg` files are the
digitized versions. `Rave/Rave.svg` has no VP3.*

---

## Addendum (round 3): the Scavenger's Daughter reference is 0.38 mm, not 0.25

The §3.1 inference (0.25 mm) came from other samples. Measuring the
Scavenger's Daughter reference VP3 directly (projection of long aligned segment
midpoints on the row normal, three 12x12 mm windows inside large uniform
components) gives:

| design | green pitch | black pitch |
|---|---|---|
| `Scavenger's Daughter Upgrade Patch.vp3` (hand digitized) | **0.378 mm** | **0.386 mm** |
| `output_vp3/...Patch2.vp3` (our 0.4 mm run) | 0.40 mm | 0.386-0.40 mm |

So this reference is only ~5 % denser than our old 0.4 mm, not 60 %. The
hand-digitized file also stitches the green **uncarved** (large components,
long rows) and keeps its border as the authored rail satin (4,292 stitches).
Our 0.3 mm default is therefore already denser than the reference; the coverage
gap was mostly the carve fragmenting green into 1 mm ladders, and the missing
authored outline satin. See `docs/adr/0003-authored-satin-and-hotspot-fixes.md`.
