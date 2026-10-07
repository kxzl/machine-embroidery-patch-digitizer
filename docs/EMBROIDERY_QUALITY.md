# Embroidery quality bar

This document is the **quality bar** for VP3s this pipeline produces. It is
written for the AI agents that generate, review, and re-export designs: read it
before judging a stitch plan, and run the [checklist](#10-pre-acceptance-checklist)
before accepting a VP3.

It is deliberately *not* a how-to for the pipeline. The pipeline mechanics live
in:

- `docs/adr/0003-authored-satin-and-hotspot-fixes.md` — authored satins, density,
  hotspot control, preview rendering (the decisions behind the current settings);
- `docs/USAGE.md` — flags, constants, tunables, the two preview renders;
- `GLOSSARY.md` — this repo's vocabulary (Artwork, Rail satin, Satinize, Hotspot,
  Satin gate, Stitch plan);
- `learnings_from_embroidery_projects.md` — what five hand-digitized samples and
  the Scavenger's Daughter reference actually contain, measured from the files.

Every non-obvious claim below is either **cited** (with a URL in
[Sources](#sources)), **measured** in this repo (with the command or the file it
was measured from), or explicitly marked **unverified**. Where published guidance
and this repo disagree, both are stated and the repo's measured value is called
out.

---

## 1. The physical model

Machine embroidery is not printing: a needle pushes thread through fabric, and
the result depends on how thread, needle, stabiliser and fabric interact.

| Element | Value this repo assumes | Source / status |
|---|---|---|
| Thread | 40 wt polyester/rayon, two plies (~120D/2) | industry standard thread; Wilcom: 40 wt + Nm 75/11 is the global standard combination ([Wilcom](https://wilcom.com/resources/blog/thread-thickness-and-needle-size)) |
| Needle | 75/11 (Nm 75 = 0.75 mm shaft) | Wilcom; Embrilliance's rule of thumb: "if the needle is, for example, 0.4 mm thick, then the holes it makes shouldn't be closer than 0.4 mm … that would just cause the needle to go into the same hole" ([Embrilliance](https://embrilliance.com/start/hitchhiker)) |
| Laid thread width | ~0.4 mm round, ~0.5 mm flattened on fabric | **measured** here; the ADR records 0.5 mm as the flattened width used by `run.sh`'s coverage render (`docs/adr/0003`); **no external source states the flat width directly** (see [Unverified](#unverified)) |
| Minimum hole spacing | 0.4 mm between penetrations | Embrilliance (needle width argument above); Madeira's catalogue recommends "Density: 0.4 mm" for standard 40 wt ([Madeira product catalogue](https://www.madeira.com/fileadmin/user_upload/ecatalog/PDF/MADEIRA_Product%20Catalogue.pdf)) |
| Stabiliser | always; stitches anchor to the stabiliser, not the fabric | Embrilliance (Rule 1: "Always use stabilizer") |
| Fabric pull | every stitch pulls the fabric inward along the stitch direction and pushes it out at open ends; compensation is fabric-, stabiliser- and density-dependent | Ink/Stitch push/pull tutorial ([link](https://inkstitch.org/tutorials/push-pull-compensation/)); Embroidery Legacy ([link](https://embroiderylegacy.com/push-pull-compensation-embroidery-digitizing/)) |

**Why spacing ≤ thread width is the whole game.** A fill is rows of thread. If
row spacing equals the laid thread width, adjacent rows just touch and the
region reads as solid; if spacing is larger, base fabric shows between rows.
0.4 mm is the industry's standard starting row spacing for 40 wt for exactly this
reason ([StitchTuner density](https://stitchtuner.com/digitizing/stitch-density/),
[StitchFast](https://stitchfast.co.uk/blog/pull-compensation-underlay-density-technical-guide.html),
Madeira). This repo runs **0.3 mm** on the native SVG path because 0.4 mm left the
base fabric visible on the Scavenger's Daughter test — see
[§4](#4-density-and-needle-safety) for the trade-off and the measurements.

The needle also sets a hard floor: Embrilliance's rule of thumb is that
penetrations should not be closer than the needle's working width (~0.4 mm), or
the needle re-enters the same hole and stacks thread instead of laying new
thread (Embrilliance; StitchTuner: "the needle swings back and forth almost in
the same holes … stitches pile into the same holes"). This is why tiny satins and
stacked passes are dangerous.

---

## 2. Stitch types — and when each is correct

Ranges are for standard 40 wt thread. "Width" is the finished, sewn width, not
the artwork width (design scale matters: a shape authored at 1 mm sewn at 0.5x is
a 0.5 mm shape).

| Type | Use | Width / length | Spacing | Source |
|---|---|---|---|---|
| Running stitch (run) | fine lines, underlay, travel paths | stitch length ~1.5–3 mm; shorter on curves; below ~1 mm stitches can break thread | — | [StitchTuner stitch types](https://stitchtuner.com/digitizing/stitch-types/) |
| Triple run / bean | bold outlines that must read on knits/fleece | length ~2–3 mm; each hole hit 3× | — | StitchTuner |
| Satin (column) | borders, letters, small shapes; the repo's rail satins and satinized fills | **~1 mm to 7 mm** (to ~10 mm on stable fabric); below ~1 mm it becomes a lumpy cord and stacks holes | satin ~0.4 mm; **narrow satins (<2 mm) want 0.45–0.5 mm** because short stitches don't spread | StitchTuner; Ink/Stitch: "recommended to only use satins wider than 1 mm" ([preferences](https://inkstitch.org/docs/preferences/)) and stroke satins "larger than 1.5 mm" ([satin column](https://inkstitch.org/docs/stitches/satin-column/)) |
| Tatami fill | large areas, backgrounds | stitch length ~3–4 mm | rows **0.4–0.45 mm** for 40 wt; **0.3 mm or less for patches/badges** where full coverage is mandatory | StitchTuner; StitchFast; this repo: 0.3 mm SVG / 0.4 mm raster (`docs/USAGE.md`) |
| Underlay (fill) | flattens fabric, lifts top stitches, adds coverage | rows much wider than top stitching; Ink/Stitch default = **3× top row spacing** | 90° to the top fill by default | Ink/Stitch [fill stitch](https://inkstitch.org/docs/stitches/fill-stitch/); `inkstitch/lib/elements/fill_stitch.py` (row default 0.25 mm, underlay 3×) |
| Underlay (satin) | centre-walk (thin columns), contour/edge run ("rails" that hold a clean edge), zigzag; edge+zigzag = "German" underlay | — | zigzag underlay much lighter than the top | Ink/Stitch satin column; [Mr X Stitch underlay](https://www.mrxstitch.com/underlay/) |

**Shapes too narrow for their chosen type.** In order of preference:

1. **Satin if ≥ ~1 mm and ≤ ~7 mm.** The repo's `satinize` (see `GLOSSARY.md`)
   converts elongated fills into one or more parallel satin columns; it only
   converts a component when the columns cover ≥ 90 % of it and spill ≤ 45 %
   outside it (`docs/USAGE.md`).
2. **Widen** a sub-1 mm stroke to the nearest workable width when it carries a
   line the design needs (the raster path widens outline runs to
   `SATIN_MIN_MM = 1.2 mm`; the satin gate below 1 mm is lowered deliberately for
   authored satins, see `docs/adr/0003`).
3. **Run or triple run** for genuinely thin linework (StitchTuner: under ~1 mm).
4. **Drop** specks that cannot be stitched cleanly (repo: components < 0.8 mm²,
   holes < 0.2 mm², `docs/USAGE.md`).

**Contradiction to know about.** Published guidance says narrow satins should be
*less* dense (0.45–0.5 mm) and that Ink/Stitch should not render satins narrower
than 1 mm ("To not produce hard stitches", preferences). This repo
deliberately goes below both: it lowers `min_satin_stroke_width_mm` to 0.5 and
runs **0.3 mm zigzag** on the authored rail satin. That is a measured exception:
the reference digitizer's own Pledd file has satins down to 0.36 mm, and at
0.4 mm zigzag the Scavenger's border fans open to a sawtooth edge (median end gap
0.42 mm, max 1.10 mm); 0.3 mm keeps the ends touching (`docs/adr/0003`). Treat
sub-1 mm satins as **needle-risk**: they are acceptable here only because they
replace worse artefacts, and they must pass the density checks in
[§4](#4-density-and-needle-safety).

---

## 3. Coverage — what "covered" means and how it is measured

**Definition.** A region is covered when every point of the artwork's stitchable
geometry lies within half a thread width of a stitch segment. Because the machine
lays ~0.4 mm of thread centred on each segment, a point ≤ 0.2 mm from a segment
is under thread; beyond that, base fabric can show.

**Method (the repo's working method).** The implementation used for all numbers
in this document and in `docs/adr/0003`:

1. Build a **geometry raster** from the *emitted* SVG at 12–16 px/mm (for the
   hand-digitized reference, the source artwork SVG serves as the geometry):
   - fills: rasterise the SVG with satin strokes neutralised (`rsvg-convert`);
   - rail satins: polygon = symmetric difference of the first two rail subpaths
     (the band between the rails — the emitted `stroke-width` is decorative);
   - centreline satins: stroke width as drawn.
2. Build a **stitch raster** from the VP3: every consecutive STITCH pair is drawn
   as a line of the real thread width (0.4 mm, round caps); TRIM/JUMP/colour
   changes break continuity. Remember that VP3 encodes travel as long STITCH
   records ([§7](#7-travel-and-trims)): moves > 12 mm should be excluded (or
   drawn as jumps), otherwise travel lines over-credit coverage.
3. **Coverage** = fraction of geometry pixels within `thread/2` of a stitch
   pixel. Report uncovered fraction and cluster the uncovered pixels; a cluster
   ≥ 1 mm² is a hole.
4. Report **fills and the rail band separately** (see the caveat below).
5. Classify every hole against the *artwork*: a hole over artwork-white (a
   highlight line, the gap between two prongs) is a fidelity difference; a hole
   over artwork-black is a defect.

**Thresholds this repo accepts** (repo convention, not an industry standard —
see [Unverified](#unverified)):

| Region | Target | Defect |
|---|---|---|
| Each fill region | ≥ 98 % at 0.4 mm thread | any hole ≥ 1 mm² |
| Whole artwork geometry incl. border band | ≥ 98 % at 0.4 mm thread | any hole ≥ 1 mm² that is over artwork-black |
| Preview at flattened width (0.5 mm) | no visible fabric | any hole ≥ 1 mm² still visible |

**Caveat — the band is not the sewn area.** The polygon between a rail satin's
two rails (symmetric difference) includes "bays" where the column folds back on
itself (U-turns at horn tips, prong gaps). Those bays are not stitched and are
often genuinely white in the artwork, so a band hole is a **measurement
artefact** until classified. Measured on the current output: of the 13 holes
≥ 1 mm² in the fills+band geometry, **all 13 are in-band and none in fills**;
12 survive at 0.5 mm thread; the largest (22.4 mm² at 0.4 mm thread, 21.6 mm² at
0.5 mm, top horn) is the widened white highlight discussed in
[§8](#8-how-to-judge-a-preview) and is real.

**Measured coverage** (whole silhouette, fills + rail band, measured with the
coverage raster at each thread width, bbox-centre aligned):

| Design | 0.4 mm thread | 0.3 mm thread | 0.2 mm thread |
|---|---|---|---|
| ours (Patch2) | **99.91 %** (0.09 % uncovered) | 98.79 % | 81.09 % |
| reference (hand-digitized) | **97.10 %** (2.90 %) | 86.35 % | 64.60 % |

At the operator-questioned spots the ADR records ours 99.0 % (top horn) /
98.2 % (left claw) / 94.7 % (bottom-left) vs reference 99.6 / 99.6 / 98.3 at
0.4 mm (`docs/adr/0003`). Fill-only coverage of the current output is 98.06 % at
0.4 mm with **no** hole ≥ 1 mm², and 99.97 % at 0.5 mm.

---

## 4. Density and needle safety

**Vocabulary.**

- **Row spacing / density** — distance between fill rows (or between satin
  passes). Smaller = denser.
- **Zigzag spacing** — peak-to-peak distance between satin cross stitches
  (Ink/Stitch default 0.4 mm; `inkstitch/lib/elements/satin_column.py`).
- **Penetration** — one needle hole (one stitch point).

**Safe bands** (40 wt, stable woven patch fabric):

| Setting | Published guidance | This repo | Status |
|---|---|---|---|
| Fill row spacing | 0.4–0.45 mm standard; ≤ 0.3 mm for patches/badges | **0.3 mm SVG**, 0.4 mm raster | repo is at the dense end on purpose (`docs/adr/0003`); reference sews 0.38 mm |
| Satin zigzag spacing | ~0.4 mm; narrow satins 0.45–0.5 mm | 0.3 mm on the authored border, 0.4 default elsewhere | deliberate exception, see [§2](#2-stitch-types--and-when-each-is-correct) |
| Fill underlay rows | much wider than top; "no tighter than 2–3×" | 3× top (Ink/Stitch default) | consistent |
| Penetrations per mm² | no universal number; "certain combinations of fabric and stabilizer have limits on the number of stitches per square millimeter" | see below | no published safe value — **unverified** |

**Why density is dangerous.** Past a point, extra stitches only cause damage:
puckering, needle deflection and breaks, thread shredding, "bulletproof"
stiffness, and perforated knits (StitchTuner density; Sassy Digitizing:
"Too many stitches per square inch causes fabric puckering, needle breakage,
thread breaks"; Embrilliance density-repair: limits per mm² depend on
fabric/stabiliser). The repo's mitigations (`docs/adr/0003`, `docs/USAGE.md`):

- fills < 2.5 mm² **or** thinner than 1 mm get **no underlay** and `ties="3"`
  (no tie stitches) — this removes the biggest hotspot mechanism;
- fully hidden under-colour fragments are dropped after the carve instead of
  being ladder-filled;
- satinizer rows that are shorter than 1.5× their width, or overlap a longer row
  by > 25 %, are dropped (measured: a 1 mm² cell held 70 mm of thread otherwise);
- underlay stitches use the fill's max stitch length (3 mm), not a 2 mm override.

**Measured density baselines** (1 mm cells, travels excluded; packing = needle
points within a radius):

| Metric | ours (Patch2) | reference | pre-fix run (earlier 2026-10-07 export) |
|---|---|---|---|
| max thread in a 1 mm cell | 24.7 mm (30 points) | 18.7 mm (23 points) | 17.2 mm (24 points) |
| mean thread / cell | 2.45 mm | 1.97 mm | 1.68 mm |
| max points within 1.5 mm | **145** | 137 | 135 |
| max points within 1.0 mm | 72 | 70 | 76 |
| median points within 1.5 mm | 27 | 25 | 24 |

**Flag thresholds used by this repo's reviews** (derived from the reference,
which the operator accepted): investigate any 1.5 mm disk > 140 points, any
1 mm cell > 20 mm of thread, or any cell > 5× the solid-fill baseline
(solid fill at 0.3 mm pitch ≈ 3.3 mm/cell). The current output flags on both
counts: 145 points and 24.7 mm at the serpent head / top-horn satin fan — the
worst cell is 32 % above the reference and the packing is 7 % worse than the
pre-fix run. Hotspot fixes are not finished; see the known defects in
[§10](#10-measured-baselines-scavengers-daughter).

---

## 5. Edges

**Satin edge quality.** A satin's clean edge comes from the thread ends landing
on the same rail line. Where the column pinches or turns, cross stitches fan and
the ends separate; at 1 px the preview then looks "sawtoothed". Two measured
repo rules:

- **Clamp satin width to `radius / 1.2`** where the centreline bends: a
  centreline bending tighter than ~1.2× its width folds the inner rail and
  Ink/Stitch fans the cross stitches (`docs/adr/0003`).
- **0.3 mm zigzag on the authored border** keeps the ends touching (at 0.4 mm
  the measured end gap was median 0.42 mm / p90 0.63 / max 1.10 mm, which reads
  as a sawtooth). Extra rungs were tried and rejected — each rung restarts the
  zigzag phase and opens a notch (`docs/adr/0003`).

**Corners.** The inside of a corner has less length than the outside but the
same number of stitches, so stitches stack and can bunch; the standard fixes are
short stitches on the inside, mitered corners, capped corners, or splitting the
column into two overlapping objects ([ColDesi](https://shop.coldesi.com/blogs/news/creating-sharp-embroidered-corners);
[Embrilliance cornering](https://embrilliance.com/Help/Platform%20Mac%201170/satincolumncorneringlevel2.htm)).
Ink/Stitch exposes this as short-stitch settings and rungs at tricky corners
(satin column docs). **Corner overshoot**: compensation applied to a rail satin
widens the rails, which makes them overshoot at sharp convex corners; the
rendered VP3 showed radiating cross-stitch spikes at every horn tip and wider
gaps in the spiral hooks (`docs/adr/0003`).

**Pull compensation.**

- Sign and magnitude: pull makes a column sew *narrower* than drawn, so satins
  are widened outward from the centre. The wider the stitch, the more
  compensation: ~0.15 mm at 2 mm width, ~0.3 mm at 7 mm width
  (Embroidery Legacy). Ink/Stitch applies it per rail (mm and %).
- Push: columns sew *longer* at open ends; cut back about one stitch (~0.4 mm)
  at open ends (Embroidery Legacy).
- **When not to apply it:** on the authored rail satin in this repo. Measured:
  widening it by 0.2 mm per side caused spikes at horn tips; with compensation
  off the border matches the reference band (`docs/adr/0003`). The repo's
  centreline satins (satinized fills, synthetic border) keep 0.2 mm per side.
- Fills in this repo intentionally carry **no** pull compensation: buffering
  many-holed polygons hung the exporter (`docs/USAGE.md`). This is a known
  implementation compromise, not a quality preference; registration is handled
  by the 1 mm underlap in [§6](#6-colour-layering) instead.

**Rule of thumb from all of the above:** compensate the *inside* stitches, keep
borders/outlines true to the artwork, and never widen a rail satin that already
matches its rails (Embroidery Legacy: "Always adjust the push and pull
compensation with the stitches that are on the inside").

---

## 6. Colour layering

The order is the input's Layer order, fills first, satin outlines, satin border
last (`docs/USAGE.md`, `GLOSSARY.md`). What matters for quality:

- **Under-colour overlap (underlap).** A later colour should overlap the earlier
  colour at the shared edge so fabric pull cannot open a seam. The repo's SVG
  path carves earlier colours out from under later ones with a **1 mm
  registration margin** (`--overlap-mm 1.0`): the later colour may cover the
  earlier one, and the earlier one keeps a 1 mm underlap strip. Keep the margin:
  it is what covers pull at the boundary (`docs/USAGE.md`).
- **Carving must not create slivers.** Carving turned the Scavenger's green into
  1 mm ladders, each its own element with underlay + ties, which was the single
  biggest local-density cause (`docs/adr/0003`, measured: median green component
  2.55 → 0.36 mm², components < 0.5 mm² 63 → 122). Rule: after carving, any
  component that is too thin to fill cleanly should be **satinized or dropped**,
  never ladder-filled.
- **Fragments fully hidden under a later colour are dropped.** They cost
  underlay and tie stitches and are invisible; the underlap strip attached to the
  visible component is kept (`docs/adr/0003`).
- **Ordering rules.** Stitch order is document order, and the border stitches
  last; dark outlines should stitch after the fills they outline. A colour may be
  used in two separate blocks rather than merging distant elements (the
  reference reuses black first and last), so keep document order = stitch order
  (`learnings_from_embroidery_projects.md` §7).
- **Reference comparison (measured).** The hand-digitized reference stitches the
  green **uncarved** as one large component per authored path; this repo carves.
  The carve is the reason ours has more, smaller elements. If a colour boundary
  shows gaps after sewing, the fix order is: increase underlap/overlap, check
  underlay, and only then tighten density (StitchTuner: "If fabric color shows
  through, add or change underlay before tightening the top density").

---

## 7. Travel and trims

**VP3 encoding facts** (read from `pystitch/Vp3Reader.py`; see
`learnings_from_embroidery_projects.md` §1):

- VP3 has **no jump command**. A travel move is written as a long STITCH
  (0x80 0x01, 16-bit deltas); a cut is 0x80 0x03 → `TRIM`.
- A "JUMP" in a previewer or a long segment in the stitch list is not necessarily
  a sewn stitch — it is the machine moving. **Never count VP3 jumps from a
  naive renderer**; count segments after TRIM instead.
- Ink/Stitch adds tie-off/tie-in lock stitches around gaps longer than
  `collapse_len_mm` (default 3 mm), so a long move is usually secured at both
  ends even without a trim.

**When a jump must be trimmed:**

| Case | Action |
|---|---|
| Jump > 4 mm and exposed (not covered by a later-stitched layer) | **trim** (repo default `--trim-mm 4.0`) |
| Jump > 8 mm | **always trim** (`tools/digitize/trim_vp3.py` pass) |
| Jump < 2 mm | never trim (`TRIM_MIN_MM = 2.0`) |
| Jump hidden under a later fill/satin (underpath) | may stay uncut; it will be covered |
| Within one satin (cross stitches, fan) | never trim — satin cross stitches are legitimately up to ~8 mm |

Ink/Stitch itself warns that cuts cost time and should be minimized by routing
first ([commands doc](https://inkstitch.org/docs/commands/): "Cutting threads
should be avoided as much as possible … Do not use this option when you can
optimize routing instead"). The repo trims aggressively because exposed jumps on
a finished patch must otherwise be cut by hand; an exposed jump is a loose
thread lying across the embroidery ([DigitEmb](https://digitemb.com/blog/how-to-remove-jump-stitches),
[MaggieFrame](https://www.maggieframes.com/blogs/embroidery-blogs/mastering-stitch-jump-in-machine-embroidery-trimming-prevention-and-efficiency-tips)).

**Measured trim baselines:**

| | ours (Patch2) | reference |
|---|---|---|
| TRIMs | 461 | 31 |
| moves > 8 mm **not** preceded by a trim | **0** | 340 (136 > 12 mm, 54 > 20 mm, max 126 mm) |
| travel (moves > 12 mm) | 0 m | 5.0 m |

The reference leaves hundreds of long untrimmed moves — most are routed under
later-stitched black fills (Ink/Stitch's `underpath` default), but some cross
areas the black never covers (visible in the reference's own stitch plan), so the
reference is not a model for jump hygiene. Our file has no exposed move > 8 mm.
**Contradiction to be aware of:** Ink/Stitch's guidance prefers routing over
cutting, and our 461 trims each add ~10 lock stitches (~0.5–1.5 mm each;
measured in the pre-fix hotspot analysis behind `docs/adr/0003`). If trim count
becomes a problem, reduce trims only where the jump is provably covered by a
later layer.

---

## 8. How to judge a preview

The repo writes two renders (`docs/USAGE.md`):

- `<name>_stitchplan.png` — 1 px hairlines. Shows every needle penetration and
  the travel path. Use it for **layout, alignment, and stitch direction**.
- `<name>_coverage.png` — `--thread-mm 0.5`. Draws the thread's flattened width.
  Use it for **whether fabric will show through**.

```bash
.venv/bin/python tools/digitize/preview.py <file.vp3> <out.png> --width 1600
.venv/bin/python tools/digitize/preview.py <file.vp3> <out.png> \
    --width 1000 --crop X0,Y0,X1,Y1 --thread-mm 0.4
```

**Known tool caveat (verified 2026-10-07).** `preview.py --crop` maps `Y=0` to
the **bottom** of the design, while `docs/USAGE.md` documents it as from the
top-left, and the uncropped render is top-down. To inspect a region at design
y from the top, pass `Y = design_height - y`. Example: the top horn (design
y 20–38 mm of a 168.4 mm-tall design) is shown by
`--crop 88,130.4,105,148.4`, not `--crop 88,20,105,38`. Always sanity-check a
crop against the full render before drawing conclusions.

**Rendering artefacts vs real gaps:**

| Looks bad | Actually |
|---|---|
| Satin band renders as a dashed line at 1 px | artefact — the cross stitches touch on fabric; re-render with `--thread-mm 0.4/0.5` |
| Pinstripes between fill rows at 0.4 mm thread | the true row pitch; at 0.5 mm flattened width the rows close |
| Boundary fringes / sub-0.1 mm² speckles at region edges | rasterisation aliasing, not holes |
| Holes inside the rail band at U-turns / prong gaps | band-geometry artefact unless the artwork is black there; overlay the artwork |
| A long thread line across the design | a VP3 travel encoded as a long STITCH, not necessarily sewn — check for a TRIM before it |

**Real defects:** holes ≥ 1 mm² that survive `--thread-mm 0.5`; holes over
artwork-black; fanned satin ends with > 0.5 mm gaps along a rail; stacked
cross stitches radiating at a tip; exposed jumps (a long segment with no TRIM
that crosses later-stitched geometry is hidden; one that crosses white is not).

---

## 9. Pre-acceptance checklist

Run before accepting any generated VP3. "Region" = each fill component and the
border band; measure with the method in [§3](#3-coverage--what-covered-means-and-how-it-is-measured).
The current Scavenger's Daughter values are in [§10](#10-measured-baselines-scavengers-daughter).

The concrete tools:

```bash
# 1. full renders (hairline + real thread width)
.venv/bin/python tools/digitize/preview.py <file.vp3> /tmp/hair.png  --width 1600
.venv/bin/python tools/digitize/preview.py <file.vp3> /tmp/cov.png   --width 1600 --thread-mm 0.5
.venv/bin/python tools/digitize/preview.py <file.vp3> /tmp/spot.png  --width 1000 --thread-mm 0.4 \
    --crop X0,Y0,X1,Y1          # y is measured from the bottom — see §8

# 2. VP3 statistics (stitch count, thread length, trims, long moves) with pystitch
.venv/bin/python - <<'PY'
import math, pystitch
pat = pystitch.read("<file.vp3>")
recs = [(s[0]/10, s[1]/10, s[2] & pystitch.COMMAND_MASK if len(s) > 2 else pystitch.STITCH)
        for s in pat.stitches if len(s) >= 2]
trims = sum(1 for *_, c in recs if c == pystitch.TRIM)
last, thread, jumps = None, 0.0, 0
for x, y, c in recs:
    if c == pystitch.TRIM: last = None; continue
    if c != pystitch.STITCH: continue
    if last is not None:
        L = math.hypot(x-last[0], y-last[1])
        if L <= 12: thread += L
        else: jumps += 1
    last = (x, y)
print(pat.count_stitches(), "records,", round(thread/1000, 1), "m thread,",
      trims, "trims,", jumps, "moves > 12 mm")
PY

# 3. trim pass (dry count: copies the file only when it inserts)
.venv/bin/python tools/digitize/trim_vp3.py <file.vp3> 8    # copy first!
```

Coverage, row pitch, and the density grid follow the methods in
[§3](#3-coverage--what-covered-means-and-how-it-is-measured) and
[§4](#4-density-and-needle-safety); there is no committed tool for them yet.

| # | Check | Command / measurement | Pass |
|---|---|---|---|
| 1 | File is readable, fits the hoop, one END, no STOP surprises | `pystitch.read()`, `.count_stitches()`, bbox | size ≤ hoop; count matches preview label |
| 2 | Stitch count / thread length sane for the area | thread ÷ bbox area | 1.5–3.6 mm/mm² for a filled patch (ours 2.55, ref 2.09, dense small `earth` 3.6) |
| 3 | Fill row spacing at target | projection of row midpoints (see `learnings…` §3.1 method) | 0.30 ± 0.03 mm SVG fills; ≤ 0.4 mm |
| 4 | Fills covered | coverage raster, fills only, 0.4 mm thread | ≥ 98 %; **0** holes ≥ 1 mm² |
| 5 | Border/band covered | coverage raster incl. rail band, 0.4 mm thread | ≥ 98 %; every hole ≥ 1 mm² classified against artwork-black |
| 6 | No real hole at flattened width | same raster at 0.5 mm thread | no hole ≥ 1 mm² over artwork-black |
| 7 | Density hotspots | max thread / 1 mm cell; max points / 1.5 mm | ≤ 20 mm/cell and ≤ 140 points/1.5 mm (ref: 18.7 / 137) |
| 8 | Tiny shapes not double-stitched | find components < 2.5 mm² or < 1 mm thick; confirm no underlay/tie ladder | no element > 10 mm thread per mm² (heuristic; pre-fix worst was 38) |
| 9 | Satins ≥ 1 mm (or justified) | measure rail separation / satin stroke width | all ≥ 1 mm, or sub-1 mm flagged as needle-risk and coverage-checked |
| 10 | Satin ends touch at pinches | thread-width crop of every tip/curve | no rail gap > 0.5 mm |
| 11 | No untrimmed exposed jumps | list moves > 8 mm without a preceding TRIM | 0 |
| 12 | Trims don't cut inside satins | `trim_vp3.py` threshold vs satin cross-stitch lengths | threshold > longest cross stitch (repo uses 8 mm) |
| 13 | Colour seams have underlap | check overlap margin at each colour boundary | 0.5–1 mm underlap kept; hidden fragments dropped |
| 14 | Preview reviewed at both renderings | `--thread-mm 0.5` full + `--crop` on every flagged spot | no visible fabric; crops sanity-checked for the y-flip caveat |
| 15 | Side-by-side with the reference | same crop, same thread width, ours vs reference | no regression in the worst region |

---

## 10. Measured baselines (Scavenger's Daughter)

Measured 2026-10-07 on the files copied out of `output_vp3/` (export 15:06) and
the hand-digitized reference. Method: `pystitch` for records/segments, coverage
raster at 12–16 px/mm as in [§3](#3-coverage--what-covered-means-and-how-it-is-measured).

| Metric | ours (Patch2) | reference (hand-digitized) |
|---|---|---|
| Size | 259.6 × 168.4 mm (artwork scaled up ~6.6 % vs native) | 242.3 × 157.1 mm (artwork native) |
| Stitch records / sewn segments | 67,195 / 66,271 | 49,648 / 49,581 |
| Thread colour blocks | 2 (border merged into black) | 3 (border is its own block) |
| Thread length | 111.4 m | 79.7 m |
| Thread per area | 2.55 mm/mm² | 2.09 mm/mm² |
| TRIMs | 461 | 31 |
| Travel > 12 mm | 0 m (0 moves) | 5.0 m (136 moves) |
| Untrimmed moves > 8 mm | 0 | 340 |
| Fill row pitch | **0.30 mm** (largest black fill, median of row peaks) | **0.38 mm** (green 0.37–0.40, black 0.38–0.42) |
| Coverage @ 0.4 mm thread | **99.91 %** | 97.10 % |
| Coverage @ 0.3 mm thread | 98.79 % | 86.35 % |
| Green (visible) coverage @ 0.4 mm | 99.76 % | 95.97 % |
| Black (visible) coverage @ 0.4 mm | 99.90 % | 96.70 %* |
| Fill-only coverage @ 0.4 mm | 98.06 %, 0 holes ≥ 1 mm² | — (reference fills + uncarved green) |
| Largest hole | 22.4 mm² at 0.4 mm / 21.6 mm² at 0.5 mm, top-horn white highlight | thin white highlight, not a hole at 0.4 mm |
| Max thread / 1 mm cell | 24.7 mm (30 points) | 18.7 mm (23 points) |
| Max points / 1.5 mm | 145 | 137 |
| Worst spot | serpent head / top-horn satin fan | serpent head |
| Border block | ~4,230 records (authored satin, `docs/adr/0003`) | 4,292 records (`docs/adr/0003`) |

\* the reference's black-visible number includes the exact rail band, which
over-reports holes at notches (see the [§3 caveat](#3-coverage--what-covered-means-and-how-it-is-measured)).

**Known defects in the current ours file** (for the next round):

1. ~~Top-horn white highlight widened to a 22.4 mm² gap~~ **resolved in round
   3e** (see below): it was the trim pass cutting the rail satin's fan
   cross-stitches at the tips. Largest hole is now 0.164 mm².
2. Hotspot counts slightly worse than both the pre-fix run and the reference at
   the serpent head (145 vs 137 points/1.5 mm) — re-measure before trusting;
   the table above is the 15:06 export.
3. ~~461 trims~~ **68 trims after round 3e** (each with ~10 lock stitches);
   correctness was always fine (0 exposed jumps) — review before scaling to
   bigger designs.

### Round 3e re-measure (export 16:53, `trim_vp3.py` satin rule)

| Metric | value |
|---|---|
| Stitch records | 66,802 |
| TRIMs | 68 |
| Sewn thread | 115.7 m |
| Long moves > 8 mm | 393, all sewn, each with a doubling-back long neighbour (0 exposed jumps) |
| Coverage, whole design @ 0.4 mm thread | 98.99 % (16 px/mm raster; 28 k clusters are sub-pixel edge specks) |
| Largest hole | 0.164 mm² |
| Coverage at the operator's five boxes | 99.8 / 99.4 / 99.8 / 99.6 / 99.3 % (was 86.3 / 85.7 / 76.6 / 91.6 / 98.7 %) |

The lesson for future agents: **coverage must be measured on the file that
ships** (post-trim). The pre-trim export measured ~99 % while the shipped VP3
was 76 % at the claw, because the trim pass had turned the fan's cross-stitches
into unsewn jumps. See ADR 0003, "Trimming must not cut satin cross-stitches".

Other outputs spot-checked: `earth.vp3` (60.5 × 60.4 mm, 7,109 stitches,
0.40 mm rows, max 74 points/1.5 mm) and `patch_book_burner_rgba.vp3`
(100 × 94.9 mm, 9,916 stitches, 0.40 mm rows) use the raster path's 0.4 mm
density; they were pitch/density-checked only, not coverage-checked here.

---

## Sources

| Topic | URL |
|---|---|
| Ink/Stitch — satin column (underlay types, pull/push, zigzag, minimum stroke width > 1.5 mm) | https://inkstitch.org/docs/stitches/satin-column/ |
| Ink/Stitch — tatami fill (underlay 90°, wider rows, default on) | https://inkstitch.org/docs/stitches/fill-stitch/ |
| Ink/Stitch — preferences (minimum satin width: only use satins wider than 1 mm) | https://inkstitch.org/docs/preferences/ |
| Ink/Stitch — push/pull tutorial (fabric distortion factors) | https://inkstitch.org/tutorials/push-pull-compensation/ |
| Ink/Stitch — visual commands / trim ("cutting threads should be avoided") | https://inkstitch.org/docs/commands/ |
| Ink/Stitch — defaults in source: fill row spacing 0.25, underlay 3×, satin zigzag 0.4, min satin stroke 1.0, collapse 3.0 | https://github.com/inkstitch/inkstitch/blob/main/lib/elements/fill_stitch.py · https://github.com/inkstitch/inkstitch/blob/main/lib/elements/satin_column.py · https://github.com/inkstitch/inkstitch/blob/main/lib/utils/settings.py |
| Wilcom — 40 wt + Nm 75/11 standard, needle metric = 0.01 mm | https://wilcom.com/resources/blog/thread-thickness-and-needle-size |
| Embrilliance — Hitchhiker's Guide (needle 0.4 mm → holes ≥ 0.4 mm apart; stabiliser; jumps avoided) | https://embrilliance.com/start/hitchhiker |
| Embrilliance — density repair kit (stitches/mm² limits) | http://www.embrilliance.com/Help/Platform%20Mac%201148/productdensityrepairkit.htm |
| StitchTuner — stitch types and width ranges (satin 1–7/10 mm, run < 1 mm, fill 0.4–0.45) | https://stitchtuner.com/digitizing/stitch-types/ |
| StitchTuner — density (narrow satins 0.45–0.5; underlay before density; needle deflection) | https://stitchtuner.com/digitizing/stitch-density/ |
| StitchFast — pull comp / underlay / density (0.4–0.5 fill, ≤ 0.3 patches) | https://stitchfast.co.uk/blog/pull-compensation-underlay-density-technical-guide.html |
| Embroidery Legacy (John Deer) — pull comp 0.15 mm @ 2 mm to 0.3 mm @ 7 mm; push cut-back ~0.4 mm | https://embroiderylegacy.com/push-pull-compensation-embroidery-digitizing/ |
| Mr X Stitch — underlay types, German underlay, can allow up to 10 % lighter top density | https://www.mrxstitch.com/underlay/ |
| ColDesi — sharp corners (short stitches inside, mitered/capped) | https://shop.coldesi.com/blogs/news/creating-sharp-embroidered-corners |
| Madeira — product catalogue (standard 40 wt density 0.4 mm) | https://www.madeira.com/fileadmin/user_upload/ecatalog/PDF/MADEIRA_Product%20Catalogue.pdf |
| Madeira USA — 75/11 needles for standard threads | https://www.madeirausa.com/education/the-basics-of-75-11-needles-and-when-to-use-them/ |
| Sassy Digitizing — density effects (puckering, needle break) | https://sassydigitizing.com/knowledgebase/embroidery-density-guide |
| DigitEmb / MaggieFrame — exposed jump stitches must be cut by hand | https://digitemb.com/blog/how-to-remove-jump-stitches · https://www.maggieframes.com/blogs/embroidery-blogs/mastering-stitch-jump-in-machine-embroidery-trimming-prevention-and-efficiency-tips |
| Hooping Station — minimum satin width 1 mm absolute, aim 1.5 mm | https://hoopingstation.com/blogs/articles/run-satin-and-fill-the-only-3-stitch-types-you-need-to-digitize-and-stitch-almost-anything |

Repo-measured sources: `docs/adr/0003-authored-satin-and-hotspot-fixes.md`,
`docs/USAGE.md`, `learnings_from_embroidery_projects.md`, and the analysis run
for this document (coverage raster, 1 mm density grid, packing, trim scan).

## Unverified

- **"≥ 98 % per region / > 1 mm² holes are defects"** is this repo's convention.
  No embroidery-industry document publishes a coverage-percentage or hole-area
  acceptance criterion; coverage is normally judged visually at arm's length
  (StitchTuner: "Look at coverage at arm's length … Close-up perfection usually
  means overkill"). The numbers are kept because they are reproducible and the
  reference is measured with the same method.
- **Laid thread width 0.4 mm round / 0.5 mm flat** is measured in this repo and
  consistent with the industry's 0.4 mm density convention, but no source found
  states the flat width of 40 wt thread directly.
- **Safe penetrations per mm²**: sources only say that a limit exists and depends
  on fabric/stabiliser (Embrilliance density repair; Sassy Digitizing). The
  thresholds in [§4](#4-density-and-needle-safety) are derived from the
  reference file, not from published limits.
- **Satin end-gap < 0.5 mm** as an acceptance threshold is the repo's measured
  fix (`docs/adr/0003`), not a published number.
- **Trim threshold 4 mm** is this repo's setting; the samples' operators cut as
  short as 1.57 mm and Ink/Stitch's own guidance is routing over cutting.
