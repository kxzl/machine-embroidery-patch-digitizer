# Peace Upgrade Patch - Nano Banana prompt

**Shape:** circle · **Size:** 60 x 60 mm · **Threads:** 1 fill (the white symbol sews as unstitched holes) · **Palette:** #111111 near-black (field + border), #FFFFFF white (symbol — dropped as paper / keyed to alpha)

## Prompt

```
Flat vector illustration of a peace symbol patch design with bold poster drama. A single solid near-black filled circle on a plain white background, square composition — the disc is the patch shape itself, no drawn border ring, its own crisp edge bounds the design. Inside the disc, one giant white peace symbol, tilted twenty degrees clockwise and shoved off-centre toward the upper right. Its thick white ring crowds the disc's edge at the upper right, leaving a bold black margin at least 6 mm wide — deliberately wide enough that the patch's satin border, which eats the outer 3.5 mm, cannot remove it — while a wide open black wedge fills the lower left. The tilted vertical bar sweeps diagonally across the disc, the lower-left diagonal bar aiming into that empty wedge, so the energy runs corner to corner. One connected white shape: a thick ring, a full vertical bar from the ring's top to its bottom, and two thick diagonal bars to the ring's lower left and lower right, every stroke one bold equal width, all merged into the ring, every end squared off blunt — no tapering points.

Exactly two flat colours: solid near-black and solid white. Flat solid fills only — no gradients, shading, highlights, soft shadows, texture, stitch marks, or bevels. Bold, large, simple shapes; nothing thin or fine; no hairline gaps. High contrast, hard boundaries. No text, lettering, or numbers. Must still read clearly as a peace sign at a glance, even small and tilted.
```

## Follow-up edits

- "The symbol has drifted back to dead-centre and upright — tilt it twenty degrees clockwise and shove it toward the upper right so the ring crowds the disc edge, keeping the wide black wedge open at the lower left."
- "The margins have evened out into a symmetric ring of black — restore the asymmetry: a bold black margin at least 6 mm wide hugging the disc edge at the upper right, a wide open black wedge at the lower left, and the tilted vertical bar sweeping diagonally between them."
- "The black margin between the white ring and the disc edge has become a hairline or vanished — widen it back to a bold margin at least 6 mm wide at the upper right, clear of the satin border's 3.5 mm carve, clean hard boundary, never a thin line."
- "The strokes have thinned or gone uneven — restore one bold equal width across the ring and all three bars, and keep them merged into the ring as a single connected white shape."
- "Grey tones or soft shading crept in — flatten everything back to exactly two colours, solid near-black and solid white, hard edges only."
- "The symbol lost a leg or shortened the vertical bar — restore the full vertical bar from the ring's top to its bottom and both diagonals reaching the ring, all strokes one bold equal width; tilted, but still reading as a peace sign, not a Mercedes logo."
- "Remove any outer border ring or keyline drawn around the black disc — the disc's own edge is the patch boundary; the satin border is added later by the pipeline."

## Spec

- **Subject:** DCC Peace Upgrade Patch — black round patch with a white screen-printed peace symbol, canon look.
- **Composition:** solid near-black circle on white; one connected bold white peace symbol (ring + full vertical bar + two lower diagonals), tilted ~20° clockwise and offset toward the upper right, spanning ~90% of the disc — bold black margin at the upper right at least 6 mm wide (clear of the satin border's 3.5 mm carve), wide open black wedge at the lower left, tilted vertical bar sweeping the diagonal axis edge to edge.
- **Finished size:** 60 x 60 mm circle, unchanged — canon states it is the same size as the Earth patch, which this set produced at 60 x 60 mm. Shape and size stay; the drama is purely compositional.
- **Embroidery notes:** **1 fill thread.** The white symbol is paper-coloured, so the raster path drops it as background (or keys it to alpha) and the symbol sews as unstitched holes in the near-black fill — the two-colour artwork needs only one thread. The symbol stays a single connected region with ~5 mm strokes; the upper-right black margin is held to ~6 mm at its thinnest, clear of the satin border's 3.5 mm carve. No third colour and no extra iconography — the stark black-and-white read IS the canon look, and all the drama comes from tilt, scale, and asymmetric margins.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 2 --size-mm 60 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.
