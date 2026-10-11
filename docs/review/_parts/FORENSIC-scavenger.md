# Forensic: Scavenger's Daughter Inverted (sewn VP3, 260 x 200 hoop)

Subject: `output_vp3/Scavenger's Daughter Inverted.vp3` (Oct 9 20:11), 259.8 x 168.6 mm,
54,233 VP3 entries = 54,141 needle stitches + 89 TRIM + 1 JUMP + 1 COLOR_CHANGE + 1 END, two threads
(#87f70f green, #ffffff white). Read-only investigation. Nothing in the repo was changed.

## How this was checked (applies to all three questions)

- Reproduced the chain in scratch and compared byte for byte:
  `invert_ink.py` on the source SVG gives `input/Scavenger's Daughter Inverted.svg` (identical);
  `svg_digitize.py --width-mm 260 --height-mm 200 --no-border --config work/scavenger_inverted.yaml`
  on that gives `output_inkstitch_svg/Scavenger's Daughter Inverted.svg` (identical).
  So the sewn files match the code at HEAD (a795612).
- Ran Ink/Stitch's own element to stitch-plan path on the final SVG (209 elements, scratch script
  `scripts/stitch_attrib.py`) and tagged every stitch with its element id and type. The plan has
  54,141 stitches; the VP3 has 54,141 STITCH entries in the same order (max coordinate difference
  0.15 mm, VP3 rounding). So every VP3 stitch maps to one final-SVG object. `trim_vp3.py` only
  inserts trims, it removes no stitch.
- Q1 and Q3 coordinates are "design frame" mm (origin top-left of the derived art, border included).
  Q2 cell coordinates are plan / final-SVG frame mm. The final SVG frame is the design frame x 0.99955
  minus (0.15, 0.14), so the two differ by under 0.3 mm. The `preview.py --crop` frame (origin at the
  stitch bounding box) is within about 0.1 mm of the final-SVG frame. Note: `--crop` takes
  `X0,Y0,X1,Y1`, not `x,y,w,h`.
- Density figures in Q2 come from the plan (element attribution) unless marked "VP3 only"; the VP3-only
  numbers use pystitch coordinates (0.1 mm quantised) and differ from the plan numbers by up to 5 %.
- Scratch folder (all scripts, pickles, crops):
  `/tmp/claude-1000/-home-roman-git-Digitize-patches/ea4b9216-f705-480b-b7f0-ea8fdbedf18b/scratchpad/review/forensic/`
  (call it `$F` below).

---

## 1. Missing legs

**Short answer.** The legs exist in the source SVG, inside the green path, but the Black layer is drawn
over them, so they are invisible in the artwork as drawn. `invert_ink.py:763` subtracts the ink from the
green (`G = green - ink`) and the ink is not stitched, so 167 of 173 leg-shaped subpaths (447.6 of
509.5 mm2) vanish at that one step. The 6 legs visible in the art were sewn; two of them lost their thin
tail to the pinched-end trim (`invert_ink.py:409`). No other rule (satin gate, speck cutoff, border,
scale, trim) removes a leg.

### Evidence

**What a leg is here.** The green layer is one `<path id="path3">` with 305 subpaths: 217 filled
shapes and 88 hole subpaths. Of the 217 shapes, 44 are body plates and fangs (inscribed width over 2.5 mm).
173 are thin tapering shapes, mostly 6 to 15 mm long and 0.1 to 2.0 mm wide: the leg segments and
antennae. Width classes (max inscribed circle diameter, design frame): 102 under 1.0 mm, 53 at 1.0 to
1.5 mm, 18 at 1.5 to 2.5 mm; total 509.5 mm2.
Script: `$F/scripts/subpaths.py`, `$F/scripts/legs_visibility.py`.

**Stage by stage.**

| Stage | Legs present | Source of the number |
|---|---|---|
| Source SVG `input/Scavenger's Daughter Upgrade Patch2.svg`, green `path3` | 173 leg subpaths, 509.5 mm2 | `subpaths.py` |
| Source SVG as rendered (Black group `g2631` is after `path3`, so it paints on top) | 6 leg pieces visible, 57.0 mm2; 167 subpaths have under 0.5 mm2 visible (447.6 mm2, 87.9 %) | `legs_visibility.py`, `legs_table.py` |
| Derived SVG (`invert_ink.py`) | the same 6 pieces, as 3 satin rows and 3 small fills among 103 satin rows + 7 fills | derived SVG, replay in `replay_green.py` |
| Final SVG | same 110 green objects (103 satin, 7 fill); the 6 legs are s106, s107, s44, f77, f45, f78 | `final.svg`, `legs_vp3.py` |
| VP3 | the 6 legs are stitched, 74 to 100 % of their area covered at 0.4 mm thread; the area of the 167 others is bare fabric (0.1 % green and 0.4 % white thread over it) | `legs_cov.py`, `hidden_cov.py` |

**Where they are lost.** `tools/digitize/invert_ink.py:763`:
`vis = _polygonal(g.difference(ink))` (BRIEF step 4, `work/BRIEF_scavenger_inverted.md:104`; the fact
that the Black layer is on top is stated in the BRIEF at line 60). With the ink treated as bare fabric,
a leg under the Black layer has nothing left to stitch.

**Visual proof** (same region, three renders of the source, from `$F/legs_triptych_*.png`):
A is the art as drawn, B is the green layer alone, C is the same art with the green layer moved above the
Black layer. B and C show full legs and antennae; A shows black.
- `$F/legs_triptych_head.png` (design region x 100 to 160, y 30 to 75 in source mm)
- `$F/legs_triptych_right.png`
- Side by side with the sewn VP3 at the same region (left: legs shown, right: VP3 at 0.5 mm thread):
  `$F/crops/compare_head.png`, `$F/crops/compare_right.png`, `$F/crops/compare_botleft.png`
- Raw VP3 crops (`preview.py ... --thread-mm 0.5 --background 101010`):
  `$F/crops/legs_vp3_head.png` (crop 95,4,150,48), `$F/crops/legs_vp3_right.png` (150,88,205,135),
  `$F/crops/legs_vp3_botleft.png` (8,135,70,165)
- Source with thin subpaths outlined in red over the artwork: `$F/ov_src_head.png`, `$F/ov_src_right.png`, `$F/ov_src_botleft.png`
- The hidden embedded raster in the source SVG (`image1`, `display:none`) shows green legs and antennae
  plainly: `$F/hidden_image1.png`. The operator may be comparing against this image.

Per-subpath list for all 173 leg-shaped shapes (centroid, area, width, visible area, whether stitched, final object):
`$F/legs_by_stage.csv`.

**Measured widths (design frame mm, max inscribed width unless stated).**

Lost legs (completely under black, no stitch):

| Leg subpath | Centre (x, y) | Length x width (min rectangle) | Max inscribed width |
|---|---|---|---|
| `path3` subpath 127 | (186.6, 108.0) | 8.6 x 2.1 | 1.46 mm |
| subpath 133 | (192.4, 103.0) | 7.7 x 1.9 | 1.55 mm |
| subpath 17 | (184.8, 153.1) | 8.1 x 2.0 | 1.75 mm |
| subpath 65 | (99.0, 131.1) | 8.5 x 2.3 | 1.44 mm |

All 167 lost legs: median width 0.78 mm, 10th to 90th percentile 0.16 to 1.50 mm.

Sewn legs (visible in the art):

| Leg | Centre | Length x width | Stitched as | Cross-stitch median (p10 to p90) | Thread coverage |
|---|---|---|---|---|---|
| subpath 33 (bar at the left head) | (16.9, 148.4) | 15.1 x 1.4 | satin s106, 1 row, rail gap 0.61 to 1.60 | 1.59 mm (1.28 to 2.15) | 74.1 % |
| subpath 34 (second bar) | (21.8, 145.4) | 12.1 x 1.6 | satin s107, 1 row, rail gap 0.56 to 1.38 | 1.17 mm (0.72 to 1.70) | 100 % |
| subpath 124 (right-hand leg) | (170.6, 110.4) | 11.1 x 3.6 (inscribed 1.46) | satin s44, rail gap 1.09 to 4.22 | 2.04 mm (1.23 to 3.94) | 89.0 % |
| subpath 27, 114, 98 | (170.3,150.0), (163.6,116.3), (113.0,126.5) | inscribed 1.75, 1.27, 0.95 | green fills f77, f45, f78 | n/a | 98 to 100 % |

**Rules checked and ruled out as the cause.**

| Candidate rule | Where | Finding |
|---|---|---|
| Satin gate 1.0 mm | `inkstitch/lib/elements/utils/nodes.py:53`: `len(element.path) > 1 or stroke_width > satin_threshold` | Does not apply. Every plate satin has 2 rails plus rungs (3 or more subpaths), so the gate is bypassed. All 209 final elements produced stitches (0 empty). |
| Minimum area | `invert_ink.py:772` (under 0.5 mm2 dropped), `:776` (under 2 mm2 becomes fill) | Dropped 8 plate specks, 0.22 mm2 in total (largest 0.07 mm2), none a stand-alone leg. One visible leg piece (1.19 mm2) became a fill (f78), 98 % covered. |
| Plate satin colour rules | `try_plate_satin`, `invert_ink.py:514` | 6 plates fell back to fill (two of them are visible legs, f77 and f45); fills are still stitched. |
| Speck cutoff in svg_digitize | `svg_digitize.py` "components" step | 5 specks dropped, none green: green fills are 7 in the derived SVG and 7 in the final SVG. 0 hidden fragments dropped. |
| Border carve | `--no-border`; border is authored white satin 2 mm outside the silhouette | Not applied to the interior. Band over ink is 7.99 mm2 in total. |
| Fit scale | x1.0686 (invert_ink), then x0.99955 (svg_digitize) | Scales up. No loss. |
| Trim | `trim_vp3.py` | 54,141 plan stitches = 54,141 VP3 STITCH entries. |
| Pinched-end trim (the only shrink) | `invert_ink.py:406` `ROW_END_MIN_MM = 1.0`, `_trim_pinched_ends` `:409` (it keeps the whole column when the good run is under half the length, `:430`) | Re-run in scratch with the trim on and off (`$F/scripts/pinch_check.py`): leg s106 rails 15.3 to 8.7 mm (6.6 mm cut), leg s44 16.0 to 12.1 mm (3.9 mm cut), leg s107 not cut. Thread coverage 74.1 %, 89.0 % and 100 % match. The cut part is the tail narrower than 1 mm. A shortened leg, not a lost one. |

Earlier evidence that the same thing happened in the non-inverted run: ADR 0003 records the operator note
"centipede legs details are getting embroidered over by black color" (`docs/adr/0003-authored-satin-and-hotspot-fixes.md:162`).
There the black thread covered the legs. Here the black fabric does, for the same reason (Black layer above green).

**If the legs were un-hidden** (scratch forecast, `$F/scripts/hidden_forecast.py`, not run in the pipeline):
the current plate rules would still not sew them as satin. Of the 167 hidden legs: 55 are under 0.5 mm2
(dropped, 9.0 mm2), 38 are under 2 mm2 (fill, 44.7 mm2), 66 fail the rail test (61 "rails interleave",
gap 0.11 to 0.40 mm, because the leg tapers to a point; 318 + 21 mm2) and only 8 would become satin
(54.3 mm2). Width classes of the hidden legs: 60 under 0.5 mm, 41 at 0.5 to 1.0 mm, 49 at 1.0 to 1.5 mm,
17 at 1.5 mm or more. So removing the subtraction alone would produce mostly ladder fills and drops.

### Confidence

- Measured: leg counts and areas, hidden fraction, widths, stitch coverage of the 6 visible legs, the
  one-to-one stitch to element mapping, byte-identical reproduction of both SVGs, rules ruled out.
- Assumed: that "legs" in the operator's words means these thin green leg and antenna shapes and not
  the black bottom-edge drips (those are bare fabric by design). I did not ask the operator.
- Not known: whether the artist meant the Black layer to cover the legs. The embedded raster says the
  original drawing has visible green legs, so the stacking order in the SVG looks like a tracing
  artefact, but that is an inference.
- Fidelity of "visible" is from my shapely replay of the evenodd/nonzero rules and was cross-checked by
  eye against `rsvg-convert` renders.

---

## 2. Density jams

**Short answer.** The density map has 361 cells (13.2 % of all needle points) above 3 x the median
of 2.22 stitches/mm2, spread over 198 small clusters. The VP3 passes the repo's point metric (max 95
needle points within 1.5 mm, flag 140) and fails its thread metric (max 35 mm in a 1 mm cell, flag 20 mm,
72 cells over). The worst cells by thread are pinched ends where 2 or 3 satin rows of one plate (zigzag 0.35 mm
plus centre-walk and contour underlay) converge. The most numerous cells by point count are thin white
parts at 0.3 mm row spacing, where every row turn adds a stitch.

### Evidence

**Needle stitches by type** (54,141; locks attributed to the nearest object by sequence):

| Class | Type | Stitches | Share |
|---|---|---|---|
| White fills (98 objects) | top | 26,154 | 48.3 % |
| White fills | underlay | 8,316 | 15.4 % |
| Green plate satins (103 rows) | top zigzag | 8,376 | 15.5 % |
| Green plate satins | centre-walk underlay | 1,278 | 2.4 % |
| Green plate satins | contour underlay | 1,493 | 2.8 % |
| Green fills (7) | top / underlay | 987 / 353 | 1.8 % / 0.7 % |
| White border satin (1) | top (no underlay set) | 6,504 | 12.0 % |
| Tie locks (in and out) | | 680 | 1.3 % |

Assumption: Ink/Stitch tags only the edge stitches of a satin top pass, so the 5,614 (green) and 5,974
(border) untagged satin stitches are counted as satin top; the underlay passes carry their own tags.
Underlay in total is 11,440 stitches (21.1 %): 8,669 fill underlay + 2,771 satin underlay.
By colour: white 40,974 (75.7 %, of which border 6,504), green 12,487 (23.1 %), plus 680 locks. Total thread 93.7 m,
2.14 mm per mm2 of bounding box (repo band 1.5 to 3.6).

**Density map** (script `$F/scripts/density.py`, `heatmap.py`; image `$F/crops/density_heatmap.png`):
- 1.5 mm cells with at least 1 needle point: 8,631. Median density 2.22 stitches/mm2 (5.0 per cell), mean 2.79,
  90th percentile 5.33, 99th 9.64, max 19.56.
- Above 3 x median (6.67/mm2): 361 cells holding 7,137 stitches (13.2 % of all). Above 2x: 1,141. Above 4x: 112.
- The 361 cells join into 198 clusters (125 are single cells, 23 have 4 or more cells). The largest cluster is
  13 cells at about (110.5, 119.1) (final-SVG frame).
- What the 361 cells are made of (first matching class): 144 white fill, row turns at edges (2,810 stitches);
  77 green, two or more satin rows overlapping (1,487); 42 both threads in one cell (871); 42 white fill with
  underlay (848); 22 green fill; 22 thin white part (mic under 2.5 mm); 10 two white fills meeting; 2 border.
- 42 of the 361 cells contain a stitch of a white highlight fill (see Q3).
- Stitch length: of 53,919 same-object stitches, 12,745 (23.6 %) are under 0.5 mm and 3,479 are under 0.3 mm.
  10,886 of them are white or green fill top stitches, which is 40 % of all fill top stitches: the 0.3 mm
  connecting stitch at every row turn. Only 9 stitches are over 7 mm, all tie locks.

**Repo thresholds** (`docs/EMBROIDERY_QUALITY.md` section 4 and check 7). VP3-only run of one script on both
files (`$F/scripts/vp3_metrics.py`: STITCH commands only, travel over 12 mm and trims excluded, thread clipped to
1 mm cells at 0.05 mm sampling, "points" counted in a radius):

| Metric | This VP3 (Inverted) | Flag in the doc | `Upgrade Patch2.vp3` (Oct 7, ink sewn in black), same script |
|---|---|---|---|
| needle stitches | 54,141 | | 66,226 |
| max points within 1.5 mm | 95 | 140 | 94 |
| max points within 1.0 mm | 65 | | 53 |
| max thread in a 1 mm cell | 35.4 mm | 20 mm | 42.7 mm |
| 1 mm cells above 20 mm | 72 | | 48 |
| 1 mm cells above 16.5 mm (5 x solid fill 3.3) | 151 | | 127 |
| total thread, per bbox area | 93.5 m, 2.13 mm/mm2 | band 1.5 to 3.6 | 111.9 m, 2.56 mm/mm2 |

The doc's own baselines (145 points, 24.7 mm for "Patch2") come from another method and an earlier export, so
they do not compare with these numbers; I did not use them. By the same script the Inverted file is
about equal on points, has fewer stitches and a lower worst cell than the earlier Patch2 file, and more cells above 20 mm.
Median thread per 1.5 mm cell is 10.5 mm (plan-based), so the satin pinch cells at 46 to 59 mm hold 4 to 6 times that.

**Top 15 cells above 3 x median**, greedy with centres at least 3 mm apart. This differs from the raw top 15
in two places only: raw rank 6 (117.75, 146.25) sits next to rank 3 and raw rank 11 (183.75, 72.75) next to
rank 1. Ranks 10 to 15 are a tie: 17 cells have 28 or more points, 9 above 28 and 8 at exactly 28, so the
cut inside the 28-point group is arbitrary. Object ids are final-SVG ids; "plate #n" is the plate index in
`$F/green_comps.pkl` (my replay numbering, by area). Thread is the clipped length inside the 1.5 mm cell.

| # | Cell centre (x, y) | Points (per mm2, x median) | Thread | What covers it and what stacks |
|---|---|---|---|---|
| 1 | (183.8, 74.3) | 44 (19.6, 8.8x) | 59 mm | Plate #32 (45 mm2, row width 3.2 to 13.4 mm, 3 rows): satin rows s27, s28, s29 converge at the pinched end (zigzag 20, centre-walk 7, contour 6, locks 6). White f123 (9.5 mm2 sliver, no underlay, not a highlight) ends in the same cell, plus f122 (a plate highlight, 1.9 mm2). Crop: `$F/crops/hot01_plate32_hair.png` |
| 2 | (116.3, 21.8) | 42 (18.7, 8.4x) | 46 mm | Head plate #1 (119 mm2, 3 rows s4, s5, s6, nearest rail gap 0.49 mm): rows pinch against each other, zigzag 22, centre-walk 8, contour 9. White f191 (4.2 mm2) tip in the cell. `$F/crops/hot02_plate1_hair.png` |
| 3 | (116.3, 147.8) | 35 (15.6, 7.0x) | 22 mm | White f147 (444 mm2) at a thin diagonal finger of the fur comb: 25 top + 10 underlay in 2.25 mm2. Rows are cut into short pieces. `$F/crops/hot03_f147_hair.png` |
| 4 | (125.3, 134.3) | 34 (15.1, 6.8x) | 24 mm | White f146 (544 mm2) at ink hairline slits, same mechanism. `$F/crops/hot04_f146_hair.png` |
| 5 | (110.3, 32.3) | 32 (14.2, 6.4x) | 52 mm | Crescent plate #39 beside the head (20 mm2, 2 rows): satin rows s0, s1 overlap and pinch, 5 locks, centre-walk 5, contour 6. |
| 6 | (90.8, 77.3) | 30 (13.3, 6.0x) | 20 mm | White f196 (278 mm2): 20 top + 10 underlay. |
| 7 | (38.3, 137.3) | 29 (12.9, 5.8x) | 15 mm | White f168 (174 mm2): 25 top + 4 underlay. |
| 8 | (140.3, 110.3) | 29 (12.9, 5.8x) | 14 mm | White f195 (506 mm2): 23 top + 6 underlay. |
| 9 | (131.3, 27.8) | 28 (12.4, 5.6x) | 15 mm | Green fill f3 (25.7 mm2, tapered leg-like fang with 5 holes, stays fill because its rails interleave): 26 top + 2 underlay, a ladder. |
| 10 | (219.8, 126.8) | 28 (12.4, 5.6x) | 38 mm | Rows of two adjacent plates (#17: s70, s71; #23: s66, s67) meeting at a seam. |
| 11 | (111.8, 119.3) | 28 (12.4, 5.6x) | 19 mm | Green fill f79 (51.9 mm2, fell back from satin: unequal rails 16.5/80.6 mm): 25 top + 3 underlay. |
| 12 | (96.8, 122.3) | 28 (12.4, 5.6x) | 49 mm | Rows of plates #10 (s80, s81) and #8 (s83, s84) overlapping at a seam. |
| 13 | (92.3, 68.3) | 28 (12.4, 5.6x) | 16 mm | White f178 (160 mm2). |
| 14 | (71.3, 90.8) | 28 (12.4, 5.6x) | 18 mm | White f196 again (second cell of the same element). |
| 15 | (207.8, 153.8) | 28 (12.4, 5.6x) | 15 mm | White f199 (60.5 mm2, underlay) + f198 (5.1 mm2, ties=3), 5 locks. |

Reading: the satin cells (1, 2, 5, 10, 12) carry 38 to 59 mm of thread per 2.25 mm2 against a median of 10.5.
The fill cells (3, 4, 6 to 9, 11, 13 to 15) are high in point count but only 14 to 24 mm of thread.
Highlights are not the main driver: they touch cell 1 (f122) and 42 hot cells overall.

**What stacks up (mechanisms with a measurement behind them).**
1. Multi-row plate satins. Every plate row carries zigzag 0.35 mm + centre-walk + contour underlay
   (inset 0.4 mm), rows overlap by 0.3 mm (`invert_ink.py:405`), and 3 rows converge where a plate pinches.
   103 rows were emitted (24 plates in 3 rows, 12 in 2, 7 in 1).
2. Thin white parts: a fill that is 1 to 2 mm wide has about 2 points per 0.3 mm of length per mm of
   width, so 4 to 5 points/mm2, double the median. The 30 plate highlights measure 4.28 white points/mm2
   with 2.10 green points/mm2 under them (6.4 total, 2.9 x median).
3. Thin ink cuts and diagonal fingers that break the large white fills into combs: many short row
   segments, each with its own 0.3 mm turn stitch. Seen in the crops of cells 3 and 4; assumed the same
   for cells 6, 7, 8, 13, 14 (not looked at).
4. Fill underlay under every white fill of at least 2.5 mm2 and 1.0 mm width: 8,316 stitches.
5. Overlap seams between neighbouring plates and fall-back fills (cells 9, 10, 11, 12).

**Settings against `docs/USAGE.md` and `docs/EMBROIDERY_QUALITY.md`.**
- Row spacing 0.30 mm (`work/scavenger_inverted.yaml: density: 0.30`; all 98 white fills carry `row_spacing_mm="0.3"`).
  USAGE: SVG default 0.3, band "0.3 to 0.6", 0.3 is the documented floor. EMBROIDERY_QUALITY:
  "0.4 to 0.45 standard, 0.3 or less for patches", "repo is at the dense end on purpose", reference sews 0.38.
  The sewn file sits at the floor of the band. Measured from the stitches of f146 and f195: top row pitch
  0.300 mm, underlay pitch 0.900 mm (3 x).
- The `vadmel` profile (density 0.35, double underlay for light thread on dark) is not in effect.
  `run.sh:39` drops `--profile` for SVG input and `svg_digitize.py` has no profile code.
  The YAML has no `profile:` key anyway. The BRIEF chose 0.30 "white on black wool needs full coverage".
- Satin zigzag 0.35 mm on plates and border. Docs: 0.4 default, 0.3 on the authored border,
  narrow satins 0.45 to 0.5. Plates are denser than the doc default.
- Small-shape rule is active: fills under 2.5 mm2 or under 1 mm wide get no underlay and `ties=3`
  (`svg_digitize.py:113-116`, `fill_el` `:1540`). In the final SVG 55 of 98 white fills have no underlay
  (41 set by `invert_ink.py:866`, 14 more with `ties=3` by this rule); 43 carry underlay.
- Trim threshold 3.0 mm: 88 trims.

### Confidence

- Measured: all counts, the density map, the stitch to object mapping, the thresholds against the repo's own
  formulas (clipped thread by sampling every 0.05 mm; "points within 1.5 mm" as a radius).
- Assumed: that "jams" are caused by local density. I did not see the jam locations. The data supports
  satin pinch ends (thread) and thin white parts (point count) as the dense places. Which ones jammed needs the
  operator's markup on `output_vp3/Scavenger's Daughter Inverted_stitchplan.png`.
- Cell classification is first match in a fixed order, so the class counts are indicative.
- Median density depends on the definition (cells with at least 1 stitch). With 3 or more stitches it is 2.67/mm2
  and the hot count changes slightly.

---

## 3. White shadows on the centipede

**Short answer.** 30 white fills (167.6 mm2) lie inside centipede plate outlines: the gloss highlights.
The white step of `invert_ink.py` (`:835-840`) emits them because it takes everything in the silhouette that is
neither ink nor visible green, and the green plates keep their highlight holes. They cost about 1,133 needle
stitches (2.1 % of the file). No flag or YAML key skips them; the smallest change is one expression at
`invert_ink.py:839-840` (fill the plate holes before subtracting), which a scratch check shows removes exactly
those 30 fills.

### Evidence

**Which objects.** Derived-SVG white fills 96 (7,750.6 mm2); final SVG 98 (two extra pieces, f187 and f207,
have no counterpart in the derived SVG: `svg_digitize.py` splits multi-part fills and drops 5 specks, net +2;
neither is near a plate). A white fill is "inside a plate" when at least
half of it lies within a green plate's outer outline (a highlight hole). Script `$F/scripts/whites.py`, `white_cost.py`.
- Inside plates: 30 fills, 167.6 mm2, inscribed width 0.86 to 2.27 mm, area 1.86 to 12.72 mm2, every one
  with `fill_underlay="false"`. Final ids: f110, f111, f112, f113, f114, f115, f116, f117, f120, f121,
  f122, f127, f128, f129, f130, f135, f137, f138, f148, f149, f150, f152, f154, f155, f156, f172, f190, f197,
  f200, f201.
- Abutting a plate: f144 (1.2 mm2) and f191 (4.2 mm2).
- The 58 visible green components (50 over 1 mm2) carry 86 hole outlines (222.3 mm2). 30 became white fills.
  55 further white pieces inside plate outlines fell under the cutoffs below and are not sewn
  (`$F/scripts/rim_slivers.py`); one hole outline is left unaccounted for (probably ink).
- Thin white rim slivers outside the plate outlines: 70 pieces within 0.3 mm of a plate, 2.26 mm2 in total, all
  dropped by the cutoff (not sewn). Kept white within 0.5 mm of a plate and outside the outlines is 4.13 mm2, i.e.
  the two abutting fills only. So no rim sliver is sewn.
- Pictures: the white streaks on the green plates in `$F/crops/compare_botleft.png` and `$F/crops/compare_head.png`
  (right panels); `output_vp3/Scavenger's Daughter Inverted_on_black.png` (art render, not the VP3).

**Which step emits them.** `tools/digitize/invert_ink.py`:
- `:835` `white = S.difference(ink.buffer(0.10))`: all paper inside the silhouette.
- `:836-840` removes `gvis_all.buffer(0.05)`, where `gvis_all = plates - ink` (`:836-838`). That geometry still has
  the highlight holes, so the highlights stay in `white`. This is the BRIEF's intent: BRIEF table (line 16)
  lists "gloss highlights on the centipedes" as white thread, and step 5 (line 109) says "Highlights inside the plates
  are part of Wt (they are holes in G), that is intended."
- `:857` keeps a white component only if inscribed diameter is at least 0.8 mm and area at least 1.0 mm2.
- `:866-867` sets "no underlay" when inscribed diameter is under 2.5 mm or area under 6 mm2 (all 30 qualify);
  `:974` writes `fill_underlay="false"`.
- The green satin under each highlight already covers it: `try_plate_satin` builds rails from
  `Polygon(comp.exterior)` (`:534`), so holes are ignored. In the VP3, green thread covers 100 % of the
  highlight area at 0.4 mm thread (`$F/scripts/hl_cov.py`).

**Stitch cost** (final-SVG element attribution, `$F/scripts/white_cost.py`):

| Set | Fills | Fill top | Locks (est.) | Total | Share of 54,141 |
|---|---|---|---|---|---|
| 30 highlights | 30 | 926 | 207 | 1,133 | 2.09 % |
| 2 abutting | 2 | 46 | 14 | 60 | 0.11 % |

Locks are assigned to the neighbouring object in stitch order, so the lock part is an estimate. No underlay stitches.
A second count by geometry (points inside the highlight outlines) gives white 717, a lower bound because row ends sit
on the outline. Under the white, 351 green points lie inside the same outlines (green is sewn first).

**Is there a switch.** No.
- `invert_ink.py` options: `--min-white-mic-mm`, `--min-white-area-mm2`, `--underlay-off-*`, `--green-clear-mm`,
  `--white-dilate-mm`. None selects "inside a plate". Raising the two minimums to catch every highlight
  (2.3 mm, 12.8 mm2) would also remove 15 other white fills (93.7 mm2) that are skull detail.
- `svg_digitize.py` YAML `skip_colors` skips a whole colour, i.e. all white.
- Highlights could also be deleted by hand in the derived SVG (30 paths), which is not repeatable.

**Smallest change (not applied).** In `invert_ink.py` at `:839-840`, subtract the plate footprint with its
holes filled, using the existing `fill_holes()` (`:177`):
`white = white.difference(fill_holes(gvis_all).buffer(args.green_clear_mm, join_style=2))`.
Add an opt-in flag (for example `--keep-plate-highlights`) to restore today's behaviour.
Scratch check on the real geometry (`$F/scripts/proto_skip_highlights.py`): white fills 96 to 66, area
7,750.6 to 7,582.9 mm2, 30 fills and 167.7 mm2 removed, 0.000 mm2 removed outside plate outlines. Nothing else in
the geometry changes except those 30 objects; element ids shift and trim and lock decisions next to the removed
fills can change. Expected saving: about 1,133 stitches and the white 4.3 points/mm2 of the 6.4 points/mm2 stack
inside the highlights (green 2.1 stays). The two abutting fills (f144, f191) would stay.

### Confidence

- Measured: object classification, ids, stitch counts per element (exact, from Ink/Stitch's own plan), green coverage
  under the highlights, the scratch result of the change.
- Estimated: the 207 lock stitches (nearest neighbour in stitch order).
- Measured: the rim slivers outside the plates are not sewn (70 pieces, 2.26 mm2 dropped at `:857`).
- Assumed: that "white shadows" means the plate highlights. I did not ask the operator.
- Not tested: a full run of the changed script through svg_digitize and Ink/Stitch (kept out of the repo by instruction).

---

## Separate issues (one line each)

- The BRIEF requires exactly one colour change; the VP3 has 1 (green then white).
- If the legs are brought back, the plate rules in `try_plate_satin` (rail gap 0.4 mm) will reject most of them
  (see the forecast in Q1), so that is a separate change.
