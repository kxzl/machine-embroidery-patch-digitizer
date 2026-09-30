# Embroidey Digitizing Plan — Scavenger's Daughter

Goal: turn `Scavenger's_Daughter_by_the_dusty_druid.webp` into a clean SVG that is
pre-digitized for Inkscape + Ink/Stitch, ready to tune and export to a machine file.

## Key question answered up front

> Is it possible to pre-digitize, i.e. outlines → satin stitch and fill colors → fill stitch?

Yes. Ink/Stitch is fundamentally a "pre-digitize at the SVG level" system. A path in
SVG is not stitches; Ink/Stitch converts SVG geometry into stitches at the moment you
press "Params" / "Simulate" / "Embroider". So we can auto-generate an SVG where:

- **Outlines / linework** are *strok*ed paths that we tag as **Satin** (the path's
  stroke becomes a satin column; we set the satin width).
- **Color regions** are *closed* paths that we tag as **Fill** (auto-fill / contour
  fill with underlay).

The stitch-type assignments are stored as Ink/Stitch parameters directly in the SVG,
so opening it in Inkscape already gives you a "pre-digitized" file. You then only
tune density/underlay/order and export.

The hard part is not the tagging — it is producing *clean* vector geometry
automatically. Outlines especially need centerlines (skeletonization) or Ink/Stitch's
single-sided satin, and usually a pass of manual cleanup.

## Current observations (already measured)

- 1000 × 1000 px, lossy WebP (decoded to PNG without issue).
- Limited, well-separated palette. 4-color median-cut:
  - `#FFFFFF` white / background   ~306k px
  - `#D3D8C7` beige/tan fill      ~296k px
  - `#617C69` green (accent)      ~86k px
  - `#0B0806` near-black linework ~312k px
- Implication: clean color separation + tracing is very feasible.

## Environment

- Present: `python3`, `Pillow` (PIL 12.3), `dwebp`.
- Missing (installable): `numpy`, `scikit-image` or `opencv-python`, `svgwrite`,
  and on the desktop: `inkscape` + `inkstitch`.
- Decision needed: where Inkscape/InkStitch runs (this box vs. another machine), and
  whether we go fully headless here (produce SVG + a machine file via
  Ink/Stitch CLI) or hand off the SVG for manual finishing.

## Pipeline (planned)

Stage 0 — Prep
- Convert WebP → PNG (done for testing).
- Optionally rescale so pixel dimensions map to target physical stitch size.

Stage 1 — Color separation
- Quantize to N target thread colors (N chosen in interview).
- Segment into: background, fill regions (one per color), and linework layer.

Stage 2 — Vectorization
- (a) Outlines: extract dark linework → centerline (skeleton) or edge trace →
      stroked SVG paths → destined for Satin.
- (b) Fills: extract each color region → closed boundary paths → destined for Fill.
- Tool options: Inkscape `Trace Bitmap` (needs GUI), `potrace` (CLI), ImageTracer,
  or OpenCV/scikit-image contour extraction with polygon simplification.

Stage 3 — Pre-digitizing (assign stitch types in SVG)
- Outline paths → Satin parameters (width, density, underlay, pulls, etc.).
- Fill paths → Fill parameters (angle, density/line spacing, underlay, pull comp).
- Set thread colors via SVG `fill` / `stroke`.
- (Optional) Add a perimeter satin border if we are making a *patch*.

Stage 4 — Inkscape + Ink/Stitch finishing
- Import SVG, set correct document size (mm).
- Order layers = stitch order (background fill first, details last).
- Tune overlaps, pull compensation, underlay per object.

Stage 5 — Simulate & export
- Run Ink/Stitch simulator for a preview.
- Export target machine format (e.g. `.pes`, `.dst`, `.jef`, `.vp3`).

## Resolved decisions

1. **Run location**: this Linux box, fully headless — install `inkscape` + `inkstitch`,
   drive via CLI, output both SVG and a machine file (no GUI).
2. **Machine format**: VP3/HUS (Husqvarna/Viking).
3. **Finished size**: 10 cm ≈ 4 in (patch).
4. **Colors** (3 total): black linework + beige fill + green fill. White/background
   is *no-stitch* (skipped).
5. **Automation**: auto-generated clean geometry as the starting point, then manual
   refinement in Inkscape by the user.
6. **Patch**: yes — add a satin-stitch perimeter border.

## All decisions resolved

- **Thread palette**: use measured hex colors for now (black `#0B0806`, beige `#D3D8C7`,
  green `#617C69`); user remaps to actual spools in Ink/Stitch later.
- **Outline satin width**: ≈ 2.5 mm (bold patch-style outline).
- **Fill stitch**: auto-fill (Ink/Stitch default) with underlay.
- (To decide at build time) linework → satin centerline skeleton vs. single-sided satin.
