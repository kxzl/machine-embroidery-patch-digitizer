# Authored satins, satinized thin fills, and hotspot control

The operator sewed the first Scavenger's Daughter patch and reported: the base
fabric shows through fills that should be solid, thread bunches where many
stitches pack into small areas ("hotspots"), colour boundaries open up under
thread pull, the satin border does not cover the artwork's horns, and the green
centipede reads as stripes instead of satin. This ADR records the fixes and the
evidence behind them.

## What the input already had

The artist's `Outline` layer is **not** a hairline to drop. It is a rail-based
satin column (`inkstitch:satin_column="True"`, 2 rails + 51 rungs). Exported
as-is it produces **4,230 stitches at 242.2 x 157.2 mm** — byte-for-byte the
same footprint as the hand-digitized reference VP3's border block (4,292
stitches, 242.3 x 157.1 mm). The pipeline used to drop it as a sub-1 mm stroke
and substitute a synthetic 2.5 mm band that insets 1 mm and bridges notches, so
horns and spikes lost their coverage.

**Decision.** A path tagged `satin_column` with two or more subpaths is emitted
as a rail satin. If its footprint spans >= 95 % of the fill silhouette it
becomes the border, the synthetic border is skipped, and the fills keep their
full footprint beneath it (no carve). Single-subpath authored satins narrower
than Ink/Stitch's 1 mm gate are widened to 1.5 mm instead of dropped. The
synthetic border stays as the fallback for designs without an authored satin.

## Fill density

Measured on the VP3s: our 0.4 mm pitch covers 96.7 % of the silhouette at thread
radius 0.2 mm; the reference sews 0.38 mm and covers 97.1 %, and at radius
0.15 mm the gap is 16.7 % vs 13.7 %. 10 % of the artwork is thinner than
0.3 mm, where a single pass must cover the full width.

**Decision.** `ROW_SPACING_MM` 0.4 -> **0.3** on the native SVG path (the
documented needle-safe floor; the reference's own machine sewed the 0.25 mm
hand file). Per-colour YAML overrides still apply.

## Hotspots

Attribution against the emitted SVG showed the top 1 mm cells at 17.2 mm of
thread vs 2.5 mm for a solid fill, concentrated on:

1. **Thin slivers** (172 paths <= 0.8 mm inscribed diameter) each carrying an
   underlay pass, tie-in/tie-out locks and a running-stitch ladder. Ink/Stitch
   has no small-shape exemption (`fill_stitch.py` applies underlay to every
   non-legacy fill; `ties` defaults to Both).
2. **The 1 mm colour-overlap carve**, which turned hidden green into 1 mm
   strips: median green component 2.55 -> 0.36 mm2, components under 0.5 mm2
   63 -> 122, each a separate element with its own locks.

**Decisions.**

- Fills smaller than 2.5 mm2 **or** thinner than 1 mm (max inscribed circle) are
  emitted with `fill_underlay="false"` and `ties="3"`.
- After the overlap carve, any component **fully hidden** under a later colour
  is dropped. The underlap that matters (attached to the visible component at
  the colour edge) is kept, so the 1 mm registration margin is unchanged.
- The `fill_underlay_max_stitch_length_mm="2"` override was removed; underlay
  stitches now use the fill's max stitch length (3 mm), i.e. fewer penetrations.

## Green centipede -> satin

Feasibility (measured on the authored subpaths, not the even-odd XOR geometry,
which turns overlaps into crescent slivers with 172 mm2 of holes):

- legs/antennae: 113 subpaths, 0.4-1.5 mm wide, 97/113 cover >= 95 % as satin;
- small segments: 23 subpaths, 1.5-4 mm, 19/23 cover >= 95 %;
- big body ovals: 33 subpaths, 4.2-10.1 mm, need 2-3 parallel columns
  (median coverage 0.96 with the strip method).

**Decision.** Add `satinize`: per authored subpath, skeletonise at 0.1 mm/px,
split into runs of roughly constant width (p95), extend the centreline to the
tips, and emit one satin column per run — up to 3 parallel columns across wide
sections (strips across the minimum rotated rectangle). A component is only
converted when the columns cover >= 90 % of it and spill <= 45 % outside it;
otherwise it stays a fill. Converted shapes are removed from the fill entirely
(carving only the bands left sub-mm slivers that became new hotspot elements).
The output metadata's `min_satin_stroke_width_mm` is lowered to match the
narrowest column so sub-1 mm satins stitch as satin rather than silently as
running stitch.

Guard rails found the hard way (each was a visible defect in a rendered VP3):

- a centreline with fewer than two distinct points, or one whose offset fails
  to build two rails, aborts the whole export (`flattened_sections` IndexError).
  Each row is checked against a faithful re-implementation of Ink/Stitch's own
  `convert_path_to_satin` recursion, in inkex user units — the offset is
  scale-invariant but GEOS' vertex splitting is not;
- a centreline bending tighter than ~1.2x its width folds the inner rail and
  Ink/Stitch fans the cross stitches, so the width is clamped to
  `radius / 1.2`;
- **no pull compensation on an authored rail satin.** The reference sews its
  border without one. Widening a rail satin by 0.2 mm per side makes the rails
  overshoot at sharp convex corners; the rendered VP3 showed radiating
  cross-stitch spikes at every horn tip and wider gaps in the spiral hooks.
  With pull compensation off, the border matches the reference band. Centreline
  satins (satinized fills, the synthetic border) keep the compensation;
- a satin shorter than 1.5x its width, or one whose band overlaps a longer
  row by > 25 %, packs short cross stitches and locks into a few mm2 (measured
  70 mm of thread in a 1 mm cell), so both are dropped;
- `stroke-linejoin:round` keeps the rail offset from spiking at corners;
- **0.3 mm zigzag on the authored rail satin** (Ink/Stitch default 0.4). Where
  the rails pinch (horn tips, claw tips) the cross stitches fan out; at 0.4 mm
  the fan leaves 0.5-1.1 mm between the thread ends along the outer rail
  (measured: median 0.42 mm, p90 0.63 mm, max 1.10 mm), which renders as a
  sawtooth edge. 0.3 mm keeps the ends touching. Costs ~1.5 k stitches on a
  66 k design. Rungs every 1-3 mm were tried as an alternative and rejected:
  each extra rung restarts the zigzag phase and opens a notch at the tight
  curves.

## Fill angle

Authored per-path `angle` values are still honoured. New: `--fill-angle` (all
fills) and YAML `angle` (per colour) / `angle_cycle` (cycle angles across a
colour's components) so fill direction can be varied for depth without editing
the artwork.

## Density must beat the artwork's own spacing

The Scavenger's paths carry `inkstitch:row_spacing_mm="0.4"` from the artist's
Inkscape session. The emitter's rule is "authored values win", so the round-3
`density: 0.3` config was silently ignored and the fills stayed at 0.4 — the
exact defect (base fabric showing through) the density change was meant to fix.
An explicit density (CLI `--density`, or YAML `density` global/per colour) now
overrides the path's `row_spacing_mm`; with no density flag the artwork wins.

## Preview rendering: hairline vs thread width

The 1 px stitch-plan rendering draws stitch *centre lines*. A satin lays 0.4 mm
threads that touch, so its band is solid on fabric, but at 1 px the same band
renders as a dashed line and reads as a broken outline. Measured with a 0.4 mm
thread width, our coverage of the artwork geometry at the questioned spots is
99.0 % (top horn) / 98.2 % (left claw) / 94.7 % (bottom-left) against the
reference's 99.6 / 99.6 / 98.3 %, and thread per area is *higher* than the
reference everywhere it was questioned. `preview.py --thread-mm 0.5`
(used by `run.sh` for the stitch plan, at `--width 1600`; 0.5 mm is the 40 wt
thread's flattened width on fabric, 0.4 mm round still leaves aliasing
pinstripes) draws the real thread width so the preview shows what the machine
will sew.

## Trimming must not cut satin cross-stitches

The trim pass (`trim_vp3.py`) inserts a TRIM before any un-trimmed move longer
than the threshold (8 mm). A rail satin that turns a tight tip fans its cross
stitches and those get long — on this artwork 393 of them exceed 8 mm and reach
15.2 mm. Every one still has both ends on the 3.3 mm border band, but the pass
cut them anyway: each cut became a trim plus an unsewn jump, and the horn,
claw and spike tips were left bare. Measured at the operator's five boxes
(0.4 mm thread, fills + band geometry): 86.3 / 85.7 / 76.6 / 91.6 / 98.7 %
covered before, with 20 mm² hole clusters; 99.8 / 99.4 / 99.8 / 99.6 / 99.3 %
after. The pass now leaves a long move alone when its neighbour is comparably
long and doubles back (angle > 120°) — that is a satin zigzag, not travel.
Trims went 461 → 68; all 393 sewn long moves were verified to have a
doubling-back long neighbour, i.e. none is an exposed jump.

Related: `preview.py --crop` used to mirror Y (Y=0 cropped the bottom of the
design) while `docs/USAGE.md` documented the top-left convention; fixed.

## A later colour's stitches finish half a thread width past its drawn edge

The operator circled three spots on the Scavenger's Daughter stitch plan
(top of the body, the right-side legs, the bottom-left body) and wrote
*"centipede legs details are getting embroidered over by black color … washing
out details here"*.

**Measured, in the design's own frame (mm from the artwork bbox top-left,
8 px/mm rasters; artwork truth = the input SVG rendered by `rsvg-convert`,
stitch bands drawn at the real thread width; `output_vp3` post-trim):**

| | artwork | ours before | ours after | reference |
|---|---|---|---|---|
| visible green, whole design (0.4 mm thread) | 3,007.9 mm² | 2,500.3 (83.1 %) | **2,768.5 (92.0 %)** | 2,315.7 (77.0 %) |
| visible green (0.5 mm flattened thread) | 3,007.9 mm² | 2,434.9 (80.9 %) | **2,738.2 (91.0 %)** | 2,433.0 (80.9 %) |
| top spot (141, 12), 16x16 mm | 140.4 mm² | 84.7 % | **94.1 %** | 75.7 % |
| right-side legs (182, 85) | 109.3 mm² | 78.9 % | **93.5 %** | 74.2 % |
| bottom-left body (88, 144) | 34.8 mm² | 81.3 % | **94.9 %** | 71.9 % |

**Mechanism.** The green was *not* missing: 99.0 % of the artwork's visible
green carried our green thread, and the geometry matched (the emitted green
fills + satins cover 96.5 % of the artwork's green and run 0.25-0.5 mm wider
than it, because satins are given a pull compensation). The loss was all at
the colour seam, and it decomposed cleanly:

| where the artwork's 3,007.9 mm² of green went | before | after |
|---|---|---|
| buried by our black **geometry** (the black path's own even-odd fill) | 166.8 mm² (5.5 %) | 31.4 mm² (1.0 %) |
| buried by the black **thread** reaching past that geometry | 395.8 mm² (13.2 %) | 221.0 mm² (7.3 %) |
| never stitched (dropped specks) | 31.4 mm² (1.0 %) | 31.4 mm² (1.0 %) |
| **visible** | 2,434.9 (80.9 %) | **2,738.2 (91.0 %)** |

The dominant term is physical and was in the design the whole time: a fill lays
thread **centred** on its path, so the black's *stitched* edge finishes half a
thread width (measured p99 = 0.25 mm of 0.5 mm flattened thread) outside the
geometry the artist drew, and that band lands on the green. On this artwork
32 % of the visible green lies within 0.5 mm of a colour edge — the centipede
is nothing but thin legs — so a 0.25 mm bite off both sides of a leg is a large
fraction of its width. The erosion profile shows it exactly: before, 76 % of
the 0-0.25 mm band of green and 43 % of the 0.25-0.5 mm band were buried and
everything deeper than 0.5 mm survived at 99 %+; the hand-digitized reference
loses the same 19 % (it does not fix this either — ours is now better than it at
every depth).

**Decision.** Move the colour seam half a thread width into the later colour:
each later colour's fills are pulled back `SEAM_PULL_MM` (default **0.2 mm** =
half of a 40 wt round thread; `--seam-pull-mm` / YAML `seam_pull_mm`) wherever
they abut an earlier colour. Three properties matter and all three are
deliberate:

- **only the colour edges move.** The reach is built from the earlier colour
  *as drawn*, minus the part of it buried deeper than the pull inside the later
  colour, so the outer silhouette and the artwork's white highlights are
  stitched to their drawn size and the black still covers the artwork's black
  out to its edge (measured 100 % -> 99.8 % of the artwork's black).
- **the registration margin survives.** The under-colour keeps
  `OVERLAP_MM - SEAM_PULL_MM` = 0.8 mm of underlap beneath the later colour
  (docs want 0.5-1 mm), and the earlier colour's own thread finishes wide
  enough to cover the 0.2 mm the later colour gave up, so no seam opens:
  whole-design coverage 98.99 % -> 98.97 %, largest hole 0.164 mm² unchanged,
  the five ADR-0003 boxes 98.84/98.76/99.30/98.97/99.03 ->
  98.72/98.84/99.34/98.93/98.94 % (all >= 98.7 %).
- **it runs after the component split.** The hidden-fragment test then still
  judges "fully hidden under the later colour" against the *drawn* black; a
  fragment that only pokes out because the black was pulled back is still under
  the black's thread and must not come back as its own element (pulling earlier
  in the pipeline resurrected all 56 of them: 64 -> 128 fill components).
- a shape so thin that the pull would erase it keeps its drawn size — a narrow
  seam is better than a missing detail (only 7 artwork-black components
  thinner than 0.8 mm touch the green at all, 2.4 mm² total).

Side effect worth recording: the seam double-stitching went away with it, so
the worst 1.5 mm packing cell dropped from **145 to 94 penetrations** (the
hand-digitized reference is 137) at unchanged max thread per 1 mm cell
(15.5 mm) and −505 stitches / −1.9 m thread.

**Residual (measured, not fixed).** 270 mm² of the artwork's green is still not
visible: 68 mm² is artwork green our geometry never covers, because the
artwork's green path carries no `fill-rule` (SVG default *nonzero*) while the
emitter computes every fill as an even-odd XOR — overlapping subpaths XOR into
holes (measured: even-odd 3,444 mm² vs rendered 3,560 mm² vs plain union
3,642 mm²; the union is not a safe substitute because it would fill the
artist's hole subpaths, i.e. the white highlight slivers); 25 mm² sits under the
authored border rail satin, which is a satin and therefore not pulled; the rest
is thread bleed at the seams the mismatched fill rule moved. Fixing that needs
real SVG nonzero-winding support in `rings_to_geom`, which is a larger change
than this defect warrants.

## Consequences

- The Scavenger's Daughter output keeps the artist's outline satin (horns
  covered), sews fills at 0.3 mm, satinizes the centipede's legs and segments,
  drops hidden fragments instead of ladder-filling them, and pulls each colour
  back off a colour seam by half a thread width so the later colour's thread
  finishes on the drawn edge instead of over the earlier colour's detail.
- Satins narrower than 1 mm require the lowered metadata gate; the emitter does
  this automatically and prints a note.
- The satinizer is opt-in per colour (`satinize.colors`), so other designs are
  unaffected.
- The colour-seam pull is opt-out (`--seam-pull-mm 0`) and defaults on for the
  native SVG path; the raster path has no colour overlap and is unaffected.
