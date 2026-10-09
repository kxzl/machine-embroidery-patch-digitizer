# Review: raster → Ink/Stitch SVG → VP3 pipeline

Audience: the agents that will implement the next round. Scope (agreed with the
operator): the **raster path** (`tools/digitize/vectorize.py` + `skeleton.py`,
`run.sh`, `key_background.py`, `trim_vp3.py`), prioritised, with tested recipes.
The native SVG path (`svg_digitize.py`) is covered only where it shares a problem.

Every claim below is **measured** (command given), **cited** (source in
`work/review_artifacts/RESEARCH_vadmel.md`), or marked **UNVERIFIED**. Prototype
code, QA scripts and raw results are in `work/review_artifacts/` (gitignored —
copy what you need into the repo; do not import from there).

---

## 0. TL;DR — what to do, in order

| # | Pri | Change | Why (measured) | Effort |
|---|---|---|---|---|
| 1 | P0 | **Underlap**: every fill grows up to 0.6 mm under every later-stitched layer (later fills, satin outlines, border) | Simulated fabric pull opens 4.6–4.7 % of the silhouette at colour seams and at the border (Book Burner, goat, earth). Underlap → 0.25–0.36 %. Export time unchanged. | S |
| 2 | P0 | **Palette**: YAML/CLI `palette:` pins thread hexes (Lab nearest); otherwise the S3 auto-palette | k-means drops the goat's amber eyes, spends 2 threads on black, and creates anti-alias "blend" clusters (Book Burner tan, Earth teal) that stitch nothing or — with underlap — 52 junk objects | M |
| 3 | P0 | **Emit `inkstitch_svg_version` 4 metadata + explicit stitch params** | Unversioned SVGs are silently "legacy-updated" at export (14,293 vs 12,649 stitches for the same goat) and pop an "Unversioned file" dialog in Inkscape | S |
| 4 | P1 | **Pull compensation for fills**, done in the raster (stretch each mask along its row angle, 0.2–0.25 mm) — *not* via `inkstitch:pull_compensation_mm` | Ink/Stitch's own fill pull comp works but makes export 7–14× slower (goat 16 → 136 s, Book Burner 20 → 220–271 s). Raster stretch: same export time, pull-gap metric at noise floor | S |
| 5 | P1 | **Vadmel profile**: density 0.35 mm, full underlay (drop `fill_underlay_skip_last`), satin underlay (centre-walk + contour) on border and outlines, water-soluble topping | Operator sews on black felted wool; light thread showed speckle (photo). Sources in research file. Fabric numbers are partly UNVERIFIED → calibrate with a swatch (#9) | S |
| 6 | P1 | **Border**: snap `force_black` to the design's darkest thread; underlay; fills tuck under it (covered by #1); outline the parts too small for the border | `force_black` emits `(0,0,0)` next to a `#1a1a1a` palette → an extra colour change. Book Burner embers/flame tips have no border → ragged edge (photo) | S |
| 7 | P1 | **Satin outlines**: extend ends at junctions by ½ local width (E3) | Keyline coverage 68.0 → 75.6 % (goat), 58.9 → 62.9 % (Book Burner); no export cost | S |
| 8 | P1 | **Trims**: VP3 has no jump command — every untrimmed jump is a *sewn* stitch. Trim layer-to-layer transitions in `vectorize.py`, not only in the `trim_vp3.py` post-pass | Goat: a 78 mm untrimmed black stitch outline → border exists in the raw export (caught only by `trim_vp3.py`) | S |
| 9 | P1 | **Calibration swatch generator** for fabric settings | Every felt/vadmel number in the literature is extrapolated; one swatch replaces guessing | M |
| 10 | P2 | QA tools into the repo (`pullsim`, `travelmap`, coverage), regression command, doc drift fixes | `coverage.py` at pull 0 reports 0 % for everything — only the pull simulation discriminates | M |
| 11 | P2 | Satin auto-route (E4) **only with `--trim=true`**; variable-width rail satins (E5); split satin > 7 mm | E4 with `--trim=false` "saves" 22 trims by sewing 11 jumps (89 mm of black thread) on top of the fills | M |

**For the operator's midnight-epicure test today (no code change):** see §5.

---

## 1. What was looked at

**Inputs:** `input/earth.jpg`, `input/patch_book_burner.jpg`,
`input/nano_banana/midnight-epicure.png` (+ its prompt
`patch_descriptions/prompts/midnight-epicure.md`), and the sewn photos.

**Fabric (operator):** black *vadmel* (65 % wool, 25 % nylon, 10 % polyester,
SelfMade art. 300001), stiff stabiliser behind. Husqvarna/Viking, VP3, auto thread
cutter (the long threads in the skull-pile photo are tails clipped by hand, and that
photo is from the first code version).

**Sewn results (photos):**

| Design | Observed | Diagnosis (§ below) |
|---|---|---|
| Earth (60 mm, 3 threads) | Clean; good border; full coverage | Reference for "good". Simple, large shapes; the black ring hides the edge |
| Book Burner (100 mm, 5 threads) | Black fabric visible **at colour seams** (flame red/yellow, brown page lines vs cream) and **at the outer edge**; cream areas speckled; embers have ragged edges; a few loose jump tails | §2.1 seams, §2.4 density/underlay, §2.5 border |
| Skull pile (first version) | Long thread tails across black areas | Historic; the current file has only trimmed travel + satin fans (§2.7) |

**Re-runs:** all three raster designs were re-run with the documented commands
(`book_burner`: `key_background.py` + `--config work/book_burner.yaml`; goat:
`--key-background --colors 6 --size-mm 80 --config patch_descriptions/border_black.yaml`).
They reproduce the shipped files (Book Burner 22,098 vs 22,107 stitches).

### 1.1 QA instruments used (copy into `tools/digitize/qa/`)

| Script | What it measures | Note |
|---|---|---|
| `qa/pullsim.py <design.svg> <keyed.png>` | **Design-level fabric-pull simulation.** Rasterises every fill, erodes it *along its stitch angle* by 0.25 mm per side (minus its own `pull_compensation_mm`), draws satins 0.15 mm narrower per side, reports silhouette pixels with no thread. | The only metric that reproduces the seam defect the operator saw. Known artefact: thin rectangle outlines where even-odd sub-rings coincide (≈0.1–0.2 % floor) |
| `qa/coverage.py <vp3> <keyed.png> <size_mm> --res 20` | Stitched coverage of the silhouette from the VP3 (bbox-centre aligned, closes sub-0.3 mm row pinstripes) | Reports ~0 % for everything at pull 0 → useful only as a "nothing is grossly missing" gate |
| `qa/travelmap.py <vp3> <png>` | Draws trimmed travel (cyan) and untrimmed moves > 5 mm (red) | Red = sewn thread; satin fans also show red (expected) |
| `qa/export.sh <svg>` | Ink/Stitch export + stats (stitches, trims, colour changes, thread m, untrimmed > 8 mm) + both previews | hard-codes `cd /home/roman/git/Digitize_patches`; make it repo-relative when porting |

The `tools/digitize/qa/` paths used in §3 do not exist yet — creating them from
`work/review_artifacts/qa/` is part of step 7 in §4.

---

## 2. Findings

### 2.1 P0 — Colour seams and the border open up on the fabric (no underlap, no pull comp)

**Symptom:** black vadmel shows at colour seams and between the fills and the
border (Book Burner photo). On black fabric every gap is a black line.

**Root cause (code):**
- Each colour's mask is cut from the same k-means label image
  (`mask_for`, `vectorize.py:503`), so neighbours meet **edge to edge**: zero
  overlap. Each is then opened/closed independently (`OPEN_RADIUS`/`CLOSE_RADIUS`)
  and simplified independently at `TOLERANCE_MM = 0.25` (`contour_paths`,
  `:541`), which can move each side of a seam inward by up to 0.25 mm.
- Fills carry no pull compensation (`el()`, `:810`); `docs/USAGE.md` says it
  "made the export hang". Measured now: it does **not** hang (§2.3).
- The border ring is carved out of every fill (`interior_mask`, `:390`) and the
  satin covers exactly the carved ring → zero overlap there too.
- Thread pulls the fabric in along the stitch direction, so a fill sews narrower
  along its rows; the seams open. (Ink/Stitch push/pull tutorial; Embroidery Legacy.)

**Evidence (pullsim, fill pull 0.25 mm/side, satin 0.15 mm/side):**

| Design | baseline | + underlap 0.6 | + underlap + Ink/Stitch pull 0.2 | + underlap + raster pull 0.25 |
|---|---|---|---|---|
| Goat (80 mm) | 4.71 % (86 gaps ≥ 0.5 mm²) | 0.25 % (7) | 0.05 % (1) | 0.23 %* |
| Book Burner (100 mm) | 4.64 % (110) | 0.36 % (3) | 0.05 % (0) | 0.16 %* |
| Earth (60 mm) | 4.57 % (39) | — | 0.09 % (0) (`full`) | — |

\* remaining "gaps" are mostly the pullsim even-odd artefact (thin rectangles),
i.e. at the measurement floor. Baseline map:
`work/review_artifacts/bb_pullsim_baseline.png` (red lines = seams that open).

**Fix A — underlap (do this first).** Prototype (`work/review_artifacts/proto_vectorize.patch`,
flag `--underlap-mm`):

```python
# after the per-colour masks are built, before contour_paths
later = lw_cover | border_ring        # satin outlines and border stitch after all fills
for c in reversed(fill_colors):       # walk from the top layer down
    m0 = masks[c]
    masks[c] = m0 | (binary_dilation(m0, disk(UL_PX)) & later & silhouette)
    later |= m0
```

- Default **0.6 mm** (research: 0.6–1.0 mm seam overlap; fills ½ border width
  under a satin border). Expose as `--underlap-mm` / YAML `underlap_mm`.
- It must run **after the palette is cleaned** (§2.2) — otherwise it revives the
  slivers of anti-alias clusters: Earth with the default `--colors 5` went from
  0 to **52 teal components**, +1 colour change, 13 → 36 trims.
- The trim "hidden" test (`stitch_index`, `:694`) already uses the grown
  `keep_lab`; verify the trim counts do not jump (goat 67 → 72, Book Burner
  106 → 129 measured; most of the Book Burner rise is the tan blend cluster).

**Fix B — pull compensation (see §2.3 for which implementation).**

**Acceptance:** pullsim with default settings ≤ 0.4 % uncovered and ≤ 5 gaps ≥ 0.5 mm²
on goat, Book Burner, Earth; colour-change count unchanged vs the palette;
export time within 1.5× of today.

---

### 2.2 P0 — Palette: lost accents, duplicated blacks, blend clusters

**Symptom (goat):** `--colors 6` gives
`#ece6d3 #c4c2c3 #989797 #5c5958 #242122 #010101`: **no amber eyes** (0.3 % of
pixels, 15.7 mm², the focal point), two blacks (field `#242122` + keyline
`#010101`, which the prompt defines as one thread). **Book Burner:** a tan
`#b78e6d` anti-alias cluster with 0 stitchable components (and 12,609 fragments).
**Earth (`--colors 5`):** grey `#bfbfbe` and teal `#218181` blend clusters.

**Root cause:** `kmeans_palette` (`:267`) is RGB k-means weighted by pixel count;
small saturated accents lose to large near-duplicate darks; the merge rule is a
fixed 20 RGB units (`_MERGE_DIST`, `:437`), which never merges `#242122`/`#010101`
(59 apart).

**Fix 1 — pinned palette (operator's choice, primary).**
- YAML `palette: ["#1A1A1A", "#5A5A5A", …]` and CLI `--palette HEX,HEX`.
- Assign pixels to the nearest pinned colour in **CIELAB** (`skimage.color.rgb2lab`).
- **Skip every merge** when pinned (the prototype first merged pinned bone
  `#E8E3D5` into `#D8D8D8` because they are 19.6 RGB apart).
- Emit the pinned hexes as thread colours. The prompt files already carry the
  palette (`**Palette:**` line in `patch_descriptions/prompts/*.md`):
  `make_config.py` should copy it into the YAML.
- Measured (goat, pinned to the prompt palette): amber eyes back (2 components),
  one black, 6 threads, 12,099 stitches. Render:
  `work/review_artifacts/me_pinned_palette_coverage.png`.

**Fix 2 — S3 auto-palette (fallback when nothing is pinned).** Over-cluster in Lab
(k = max(2N, 16)), agglomeratively merge the closest pair, never merge a saturated
(C* > 25) cluster into a neutral one, absorb small (< 2 %) clusters lying within
ΔE 6 of the segment between two others (anti-alias blends), Lloyd polish.
Code: `work/review_artifacts/palette/winner_auto_palette.py` (≈80 lines, drop-in
for `kmeans_palette`). Verified independently:

| Image | current | S3 |
|---|---|---|
| goat N=6 | amber lost, 2 blacks, ΔE max 55.5 | `#ece6d3 #c4c2c3 #989797 #b16523 #595858 #1e1c1d`, ΔE max 7.8 |
| Book Burner N=5 | 5 incl. dead tan | 4 real threads, no blend |
| Earth N=3 | 3 | identical |

~1 s per image. `--colors` becomes an upper bound (already tolerated downstream).

**Side effect to handle:** with one black, the outline colour `lw` (`:498`) is the
*whole* black (field + keylines). Keylines that touch the field merge into the
field fill and are no longer satin. On the goat this looks right (same thread),
but the satin-outline logic must not try to skeletonise the field: the existing
`SATIN_MAX_MM` gate keeps it a fill — verify `satin outlines:` count stays sane.

**Acceptance:** goat → amber present, ≤ 6 threads, 1 black; Book Burner → no
cluster with 0 components; Earth unchanged.

---

### 2.3 P1 — Pull compensation on fills: implement it in the raster

Measured export wall times (same machine, `qa/export.sh`):

| | goat | Book Burner | Earth |
|---|---|---|---|
| underlap only | 16 s | 20 s | — |
| + `inkstitch:pull_compensation_mm="0.2"` | **136 s** | **220 s** | 112 s |
| + raster pull 0.25 (prototype `--raster-pull-mm`) | 16 s | 15 s | — |

So `docs/USAGE.md`'s "hung > 20 min" is out of date, but Ink/Stitch's
implementation (`adjust_shape_for_pull_compensation` rebuilds the polygon from
every row) is slow. The raster version is equivalent in effect for tatami rows:

```python
def line_struct(angle_deg, r):            # 1-px line, length 2r+1, at the row angle
    ...
sil_grow = binary_dilation(silhouette, disk(RP_PX))     # may overshoot the edge by RP
for c in fill_colors:
    a = fill angle of c (FILL_ANGLE / YAML angle / 0)
    masks[c] |= binary_dilation(masks[c], line_struct(a, RP_PX)) & sil_grow
```

- Clip to the **grown** silhouette, not the silhouette: overshooting the outer edge
  by the pull amount is the point (clipped version measured 0.21 % vs 0.16 %).
- Default 0.2 mm on stable twill, **0.25 mm for vadmel** (research: 0.2 stable,
  0.4–0.5 heavy/fleece; felt-specific value UNVERIFIED → swatch, §2.9).
- Keep `inkstitch:pull_compensation_mm` available as an opt-in for the operator's
  GUI edits; never both (they add up).

---

### 2.4 P0 — Unversioned SVG: the export is not what Inkscape shows

The raster SVG has no `<metadata>`. `InkstitchExtension.load()` →
`update_inkstitch_document()` (`inkstitch/lib/update.py`) treats it as version 0 and
runs every legacy update: fills get `running_stitch_length_mm=1.5` and
`max_stitch_length_mm=3`, satins get `reverse_rails=none`, … Headless, the wx stub
silently says "Update". In the GUI the operator gets *"Unversioned Ink/Stitch SVG
file detected"*; Cancel gives a different file.

Measured (goat SVG, only the metadata differs): **14,293** stitches unversioned vs
**12,649** with `inkstitch_svg_version=4`; with version 4 + explicit
`max_stitch_length_mm=3`, 13,726.

**Fix:** write (as `svg_digitize.py` already does, `:1590`):

```xml
<metadata id="metadata1">
  <inkstitch:inkstitch_svg_version>4</inkstitch:inkstitch_svg_version>
  <inkstitch:collapse_len_mm>3</inkstitch:collapse_len_mm>
</metadata>
```

and pin the values the update used to inject: fills
`inkstitch:max_stitch_length_mm="3"` (samples sew exactly 3.0 mm,
`learnings_from_embroidery_projects.md` §3.5) and
`inkstitch:running_stitch_length_mm="1.5"` (fill travel). Re-baseline stitch
counts afterwards. **Acceptance:** opening the SVG in Inkscape shows no update
dialog; headless and GUI exports are identical.

---

### 2.5 P1 — Vadmel profile: density, underlay, topping

Research summary (`work/review_artifacts/RESEARCH_vadmel.md`, sourced; felt/vadmel
specific numbers UNVERIFIED):

| Setting | Today (raster) | Recommended start | Source/status |
|---|---|---|---|
| Fill row spacing | 0.40 | **0.35** (0.30 for white/cream on black) | 0.40–0.45 twill; patches ≤ 0.3; the operator already saw fabric at 0.4 on the SVG path |
| Fill underlay | default + `fill_underlay_skip_last="true"` | default, **drop skip_last** | no hand sample sets skip_last (`learnings…` §8.2) |
| Second underlay for light-on-dark | none | `inkstitch:fill_underlay_angle="<a+90> <a>"` (two passes) on colours with L* > 70 | Ink/Stitch accepts a list; research: perpendicular double underlay on pile |
| Satin underlay (border, outlines ≥ 1.5 mm) | **none** | `center_walk_underlay="true"`, `contour_underlay="true"`, `contour_underlay_inset_mm="0.4"` | Ink/Stitch satin docs; "German" underlay for ≥ 2 mm |
| Satin zigzag spacing | 0.4 default | 0.35 border/outlines | SVG path uses 0.3 on its border (ADR 0003) |
| Satin pull comp | 0.2/side | 0.2 + `pull_compensation_percent="10"` on borders > 2 mm | Embroidery Legacy 0.15 @2 mm → 0.3 @7 mm |
| Topping | — | water-soluble film on vadmel (operator action) | Hatch/BERNINA/Sulky |
| Needle | — | 75/11 sharp | Madeira |

Measured cost (`full` = underlap 0.6 + pull 0.2 + density 0.35 + no skip_last):
goat 14,293 → 15,784 stitches, Book Burner 20,082 → 25,264 (version-4 baseline),
Earth 6,636 → 11,653 (Earth inflated by the teal blend, §2.2).

Implement as a profile, not new hard-coded defaults: YAML
`profile: vadmel` (or `fabric:`) selecting density / underlay / pull values, so
twill runs stay reproducible.

---

### 2.6 P1 — Satin border

1. **Colour snap.** `force_black` sets `(0,0,0)` (`:350`); the snap to the palette
   only happens within 40 RGB units (`:457`). With a `#1a1a1a` thread (pinned) it
   does not snap → **an extra colour change** (goat pinned: 7 blocks for 6 threads).
   Fix: `force_black` = the darkest palette thread if its L* < 25, else `#000000`.
2. **Underlay** — see §2.5 (none today).
3. **Fills under the border** — covered by underlap (§2.1): `border_ring` is part
   of `later`.
4. **Parts with no border.** Book Burner: "4 part(s) too small to border, 8 part(s)
   too thin for the border width" — embers and flame tips keep a bare fill edge
   (ragged in the photo). Options, in order: (a) give those parts a border
   `min(BORDER_MM, 0.6 × inscribed diameter)` if ≥ 1.2 mm; (b) otherwise a
   running-stitch outline (`bean_stitch_repeats="1"`) in the border colour along
   the part's edge; (c) accept and say so in stdout.
5. **On black fabric a black border is invisible.** It still gives the cut edge,
   so keep it for cut-out patches; for patches sewn onto the garment
   (Book Burner) let YAML choose a border colour from the palette. Print a note when
   the border colour is within ΔE 15 of a declared `fabric_color`.
6. **Spikes.** Goat horn tip leaves the circle (operator wants the border to follow
   it). The satin fans at the tip; set `short_stitch_inset="20"` on the border and
   split satin stitches > 7 mm (`max_stitch_length_mm="7"`).

---

### 2.7 P1 — Satin outlines (keylines)

**Root cause:** `skeleton.trace_skeleton` splits at every junction; each run is a
constant-width centreline satin ending square *at* the junction pixel; runs shorter
than `max(2.5 mm, 1.5 × width)` are dropped (`vectorize.py:591`). Result: notches
at every T/X junction, missing short pieces, and each piece is its own object
(ties, often a trim). Coverage overlays:
`work/review_artifacts/satin/` (red = keyline not covered).

**Measured experiments** (`work/review_artifacts/satin/RESULTS_satin.md`;
"keyline cov" = thin dark pixels covered by satin):

| Variant | goat cov | goat trims (total / black block) | Book Burner cov | verdict |
|---|---|---|---|---|
| base | 68.0 % | 67 / 37 | 58.9 % | |
| E1 spur pruning | 68.1 % | 67 / 37 | −0.8 pp | **no** — deletes real keyline |
| E2 merge collinear branches at junctions | 69.1 % | 68 / 38 | −4.3 pp | **no** — constant width breaks at corners |
| **E3 extend junction ends by ½ local width, free ends 0.3 mm** | **75.6 %** | 66 / 36 | **62.9 %** | **yes** |
| E4 Ink/Stitch auto-route, `--trim=false` | 69.1 % | 45 / 15 | 58.5 % | **no** as-is — see below |

**Correction to E4 (re-measured by the reviewer).** Counting untrimmed non-satin
moves > 3 mm in the black block: base 13 (134 mm), E4 `--trim=false` **11 (89 mm
of black thread sewn on top)**, E4 `--trim=true` (with `trim_after` stripped first)
**1** (the 46 mm outline → border jump, caught by `trim_vp3.py`) but 45 trims.
In VP3 an untrimmed jump is sewn (§2.8), so E4 only makes sense with
`--trim=true`; its value is routing (running-stitch underpaths, consistent
direction), not fewer trims. Keep it optional.

**Do:** port E3 (`work/review_artifacts/satin/diff_skeleton.patch`, function
`extend_ends`, flag-gated; ~40 lines). Underlap (§2.1) already pushes the fills
*under* the keylines, so any remaining notch shows fill colour, not fabric.
**Later (P2):** E5 — rail satins whose width follows the distance transform
(two offset rails + rungs every ~5 mm) instead of one `stroke-width`; that is what
can lift the Book Burner ceiling (tapered brush lines).

---

### 2.8 P1 — Trims and jumps

- `pystitch/Vp3Writer.py` **drops JUMP records**: "VP3 has no jump commands.
  These are skipped." The next stitch is written from the jump's start to its end
  as a long stitch → **every untrimmed jump is a sewn thread on top.** Only a
  TRIM before the move prevents it.
- `vectorize.py` trims on `d_max > threshold` or "not hidden" (`:797`), but objects
  at layer boundaries rely on the post-pass `trim_vp3.py 8`: the raw goat export
  had a **78 mm** untrimmed stitch from the last outline satin to the border.
- **Fix:** always set `trim_after` on the last object of each group (fills colour
  → outlines → border) when the next object's nearest boundary is > `TRIM_MIN_MM`;
  keep `trim_vp3.py` as a safety net and print how many it inserted (it should be 0).
- **Check after every run:** `qa/travelmap.py` → no red segment outside satin fans.
- Satin fans: the current Scavenger file still sews 670 untrimmed > 6 mm moves at
  horn/claw tips (up to 15.2 mm); they are legitimate satin stitches but a snag risk
  on a worn patch → `max_stitch_length_mm="7"` (split satin) on wide/fanning satins.

---

### 2.9 P1 — Calibration swatch

Felt/vadmel numbers are extrapolated. Add `tools/digitize/swatch.py` that writes
an Ink/Stitch SVG (≈ 90 × 60 mm) with:

- 3 × 3 grid of 12 × 12 mm two-colour squares (light thread on dark thread
  neighbour) varying **row spacing 0.30 / 0.35 / 0.40** × **pull 0 / 0.2 / 0.3**,
  with the seam in both row-parallel and row-perpendicular orientation;
- satin columns 1.0 / 1.5 / 2.5 / 4 mm wide with and without contour underlay;
- labels as running-stitch numerals (or a printed legend).

The operator sews it once on vadmel (+ topping) and records the winning values in
the YAML profile. This is cheaper than iterating on full patches.

---

### 2.10 P2 — Docs drift and code health

- `docs/USAGE.md`: "pull compensation … made the export hang (>20 min)" → measured
  136–271 s with current Ink/Stitch; update after §2.3.
- `README.md` "Smart trimming … jumps under 2 mm are skipped" is right, but add the
  VP3 no-jump fact (§2.8) to `docs/EMBROIDERY_QUALITY.md` §7.
- `docs/EMBROIDERY_QUALITY.md` §8 and §9 still say `preview.py --crop` measures Y
  from the bottom. That is **stale**: `preview.py` now crops from the top-left
  (`preview.py:55-61`, verified). Delete the caveat — it already misled one agent
  into rendering empty crops.
- `preview.py` always draws on white, so **white thread is invisible**: the
  stitch plan of `Scavenger's Daughter Inverted` showed only the centipedes, even
  though the file holds 43,878 white stitches. Add `--background HEX` (default the
  fabric colour from YAML, e.g. `#101010` for black vadmel), and have `run.sh`
  pass it.
- `vectorize.py` is a 900-line top-level script (argument parsing, I/O and
  algorithm interleaved), so nothing can be unit-tested and every agent copies it
  to experiment. Minimal step: wrap the body in functions (`load`, `palette`,
  `masks`, `outlines`, `emit`) behind `main()`, no behaviour change, then add a
  regression command (§3).
- Prototype patch hard-codes `sys.path.insert(0, "/home/roman/…")` — do not port that line.

---

## 3. Regression gate (run before and after each change)

```bash
# inputs (keyed once)
.venv/bin/python tools/digitize/key_background.py input/patch_book_burner.jpg work/bb_keyed.png
.venv/bin/python tools/digitize/key_background.py input/nano_banana/midnight-epicure.png work/me_keyed.png
.venv/bin/python tools/digitize/key_background.py input/earth.jpg work/earth_keyed.png

# per design: vectorize → export → QA
.venv/bin/python tools/digitize/vectorize.py --config work/book_burner.yaml work/bb_keyed.png /tmp/q/bb.svg
tools/digitize/qa/export.sh /tmp/q/bb.svg
.venv/bin/python tools/digitize/qa/pullsim.py /tmp/q/bb.svg work/bb_keyed.png --out /tmp/q/bb_pull.png
.venv/bin/python tools/digitize/qa/travelmap.py /tmp/q/bb.vp3 /tmp/q/bb_travel.png
```

Record per design: stitches, colour changes, trims, export s, pullsim %,
gaps ≥ 0.5 mm², red segments in travelmap. Gates for this round:

| Gate | goat | Book Burner | Earth |
|---|---|---|---|
| threads (colour blocks) | 6 (pinned) | 4–5 | 3 |
| amber eyes present | yes | — | — |
| pullsim uncovered | ≤ 0.4 % | ≤ 0.4 % | ≤ 0.4 % |
| untrimmed travel > 3 mm outside satins | 0 | 0 | 0 |
| export time | ≤ 1.5 × today | ≤ 1.5 × today | ≤ 1.5 × today |
| no Ink/Stitch update dialog | yes | yes | yes |

Then the operator sews. A design is accepted on the sewn result, not on these numbers.

---

## 4. Suggested implementation order (one PR each)

1. Metadata + explicit params (§2.4) → re-baseline the gate numbers.
2. Palette: `palette:` pinning + S3 fallback (§2.2), `make_config.py` reads the prompt palette.
3. Underlap (§2.1) + raster pull (§2.3), flags + YAML, defaults on.
4. Border: snap, underlay, small-part outline (§2.6); trims at layer boundaries (§2.8).
5. Satin E3 (§2.7).
6. Vadmel profile + swatch generator (§2.5, §2.9).
7. QA tools into the repo, docs (§2.10).

---

## 5. Midnight-epicure: how to run it

**Today, without code changes** (keeps the amber eyes):

```bash
tools/digitize/run.sh --key-background --colors 8 --size-mm 80 \
  --config patch_descriptions/border_black.yaml --density 0.35 \
  input/nano_banana/midnight-epicure.png
```

Measured palette with `--colors 8`: `#ece6d3 #c4c2c3 #989797 #b26523 #6c6b6c #4a4a4a #242122 #010101`
(the eyes `#b26523` survive as 2 components). Verified end to end in `/tmp`:
15,396 stitches, 80.3 × 80.3 mm, 68 + 5 (`trim_vp3`) trims, export in seconds.
**Known artefact in that run:** one black outline satin cuts diagonally across the
right (amber) eye — a skeleton run of the eye outline that `approximate_polygon`
straightened across the loop. Before sewing, open
`output_inkstitch_svg/midnight-epicure.svg` in Inkscape, select that stroke in the
`Outline` layer, delete it, and save as `.vp3` from Inkscape with Ink/Stitch.
When Ink/Stitch shows "Unversioned Ink/Stitch SVG file detected", click **Update**;
that matches what the headless export does (§2.4). Also expect a few white specks (dropped slivers) at the
left eye and the nostril until underlap ships.
That is 8 colour blocks; on the
machine load **the same black spool for `#242122` and `#010101`** and the
same dark grey for `#6c6b6c`/`#4a4a4a`. Expect visible seams between the greys
on vadmel until underlap ships; use water-soluble topping.

**After §4 steps 1–4** (target recipe):

```yaml
# work/midnight-epicure.yaml
palette: ["#1A1A1A", "#5A5A5A", "#B0B0B0", "#D8D8D8", "#E8E3D5", "#B5651D"]
density: 0.35
underlap_mm: 0.6
raster_pull_mm: 0.25
border:
  mode: force_black      # snaps to #1A1A1A, no extra colour change
  thickness_mm: 2.5
```

```bash
tools/digitize/run.sh --key-background --size-mm 80 --config work/midnight-epicure.yaml \
  input/nano_banana/midnight-epicure.png
```

The horn tip outside the circle is kept (operator's choice); check the border tip
in the stitch plan for a fan > 7 mm.

---

## 6. Appendix — artefacts

`work/review_artifacts/`:
- `proto_vectorize.patch` — palette pinning, Lab merge, underlap, raster pull,
  fill pull attr, no-skip-last, metadata (all flag-gated, experimental quality)
- `palette/winner_auto_palette.py`, `palette/RESULTS_palette.md`, comparison JPGs
- `satin/diff_skeleton.patch`, `satin/diff_vectorize.patch`, `satin/e4_autoroute.py`,
  `satin/RESULTS_satin.md`, `satin/metrics.py`
- `qa/pullsim.py`, `qa/coverage.py`, `qa/travelmap.py`, `qa/export.sh`, `qa/run_exp.sh`
- `RESULTS_fill.md` (all fill-variant numbers), `RESEARCH_vadmel.md` (sources)
- `bb_pullsim_baseline.png`, `bb_travel_map.png`, `me_pinned_palette_coverage.png`
