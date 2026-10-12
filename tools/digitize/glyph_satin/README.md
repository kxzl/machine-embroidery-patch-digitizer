# glyph_satin

Per-stroke satin digitizer used for the Desperado Club patch (all white parts satin, black is bare fabric).
It replaces the general skeleton and rail-satin path of `vectorize.py` for this one design.
The code is a prototype: `build.py` reads `input/desperado_club.jpg` from the repo root, and the design layout is hard-coded in `classify()`.

## How it works

1. `load_polygons`: Gaussian-blur the JPG and take subpixel contours at 50 % grey, so edges are smooth, not pixel stairs.
2. `medial_graph` and `prune`: Voronoi medial axis of each white shape, then drop short corner spurs.
3. `build_chains`: join branches that continue within 40 degrees through a junction (a bar passes through, a stem ends against it).
4. `chain_to_satins`: one satin per chain. The centreline is smoothed, rungs are cast perpendicular to it every 0.25 mm, and the rails are where each rung meets the outline. Every 4th rung is emitted as an Ink/Stitch rung. Hairpin turns (the A apex) split the chain.
   Butt joints: strokes that run leaf to leaf are laid first, then strokes that end at a junction. Each later stroke is clipped against the bands already laid (3 px overlap), so two stitch directions never cross at a junction. `repair_rungs` cuts out stations where rungs flip, cross, spin or jump.
5. `patch_residuals`: any white left uncovered (over about 0.1 mm2, compact shape) gets a small chord satin across its short axis.
   Two hand-made exceptions live in `build.MANUAL` (the N of FUN as two stems and a diagonal) and `geom.EXCLUDE` (the hub where the h tail meets the e in "The", filled by one forced patch).
6. Stars are fitted as regular five-point stars: five arm triangles plus a centre pentagon. The pommel is a stack of horizontal chords. The grip bands, guard and blade strips go through the stroke path.
7. Pull compensation per component is `clip((gap - 0.3) / 2, 0.06, 0.2)` mm, where gap is the distance to the nearest other shape, so narrow letter gaps do not close.

## Ink/Stitch pitfall (found the hard way)

A satin with exactly two rungs (four subpaths) is ambiguous: Ink/Stitch cannot tell rails from rungs and picks the two longest. On short pieces the rungs are longer than the rails, so it sews a bow-tie and leaves a hole (the A foot, about 2 mm2). `emit_rungs` in `build.py` never writes exactly two rungs. Check any new satin generator with `tools/digitize/qa/coverage.py` on the exported VP3, not only with a geometry overlay.

## Run

```
cd tools/digitize/glyph_satin
../../../.venv/bin/python run_all.py /abs/path/out.svg tag    # writes out.svg and tag.pkl
./exp.sh /abs/path/out.svg                                    # Ink/Stitch -> .vp3, trim, previews, jam check
../../../.venv/bin/python qa_cover.py tag qa.png 700,100,2100,1450   # uncovered and spill, red and cyan
../../../.venv/bin/python viewpkl.py tag ov.png 66,50,100,68 5       # rails and rungs over a region (mm box)
```

## Known limits

- The pommel crescent highlight and the dark slits in the grip bands are not stitched (under 1 mm).
- Satin stitches reach 8 mm at the pommel (7.7 mm ball).
- The grip bands are separate columns, so a few trims fall within 6 mm (`jam_check` check C warns at 4 to 5 cuts).
- The two special cases above are tied to this artwork's coordinates.
