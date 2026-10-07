# Peace Upgrade Patch - Nano Banana prompt

**Shape:** circle · **Size:** 60 x 60 mm · **Threads:** 1 fill (the white symbol sews as unstitched holes) · **Palette:** #111111 near-black (field + border), #FFFFFF white (symbol — dropped as paper / keyed to alpha)

## Prompt

```
Bold screen-print / tattoo-flash peace sign, round patch design: a huge solid near-black circle on a plain white square, white margins to all four corners — the disc is the patch shape, no drawn border ring. One giant white peace symbol fills the disc, tilted a hard 25° clockwise and shoved off-centre toward the upper right, so its thick ring crowds the disc edge until only a bold near-black rim 5 mm wide is left and the symbol looks ready to burst out, while a wide open black wedge stays at the lower left. Build it as one connected white shape: a heavy ring, a full vertical bar from the ring's top to its bottom, and two heavy diagonals reaching the ring's lower left and lower right — every stroke one bold equal width, merged into the ring, blunt squared ends. The tilted vertical bar drives the disc's diagonal corner to corner; the lower-left diagonal thrusts into the empty black wedge.

Exactly two flat colours: solid near-black and solid white. Flat solid fills only — no gradients, shading, highlights, texture, halftone or bevels. Large bold shapes only; every stroke thick, every gap bold; no hairlines, no fine detail. High contrast, hard edges. No text, no lettering, no numbers. Must still read as a peace sign, even small and tilted.
```

## Follow-up edits

- "The symbol has drifted back to a small, dead-centre, upright flat icon — blow it up until it nearly fills the disc, tilt it a hard 25° clockwise, and shove it toward the upper right so the ring crowds the edge and the lower-left black wedge opens wide."
- "Grey tones, gradients, glow or soft shading crept in — flatten everything back to exactly two colours, solid near-black and solid white, hard edges only."
- "Strokes thinned or fine detail appeared — restore one bold equal width across the ring and all three bars, keep the near-black rim bold, and strip every hairline and small shape."
- "The stark two-value read flattened into muddy greys or a second dark tone crept in — lock it back to one flat near-black field and one flat white symbol; the drama is the black/white contrast and the composition, not a new colour."
- "The black rim between the white ring and the disc edge became a hairline or vanished — widen it back to a bold rim about 5 mm wide, clear of the satin border's up-to-3.5 mm carve, clean hard boundary, never a thin line."
- "The margins evened into a symmetric ring of black — restore the asymmetry: the ring crowding the edge at the upper right, a wide open black wedge at the lower left, and the tilted vertical bar sweeping the diagonal between them."
- "The symbol lost a leg, shortened the vertical bar, or flattened into a circle — restore the full vertical bar from the ring's top to its bottom and both diagonals reaching the ring, all one bold equal width, tilted but still unmistakably a peace sign, not a Mercedes logo."
- "Remove any outer border ring or keyline drawn around the black disc — the disc's own edge is the patch boundary; the satin border is added later by the pipeline."

## Spec

- **Subject:** DCC Peace Upgrade Patch — black round patch with a white screen-printed peace symbol, canon look.
- **Composition:** one giant white peace symbol on a solid near-black disc, tilted a hard 25° clockwise and shoved off-centre toward the upper right, so its thick ring crowds the disc edge (only a bold near-black rim about 5 mm wide left, the symbol ready to burst out) with a wide open black wedge at the lower left; one connected white shape — heavy ring + full vertical bar + two heavy lower diagonals, all one bold equal width, merged, blunt ends; the tilted vertical bar sweeps the diagonal corner to corner; the symbol spans ~92% of the disc; no drawn border ring. The boldness is scale, hard tilt and the asymmetric crowding, not clutter.
- **Finished size:** 60 x 60 mm circle, unchanged — same size as the Earth patch. Shape and size stay; the drama is purely compositional.
- **Embroidery notes:** **1 fill thread.** The white symbol is paper-coloured, so the raster path drops it as background (or keys it to alpha) and the symbol sews as unstitched holes in the near-black fill — the two-colour artwork needs only one thread. Strokes are thickened to ~7 mm and the ring-to-edge rim is held to ~5 mm at its thinnest, clear of the satin border's up-to-3.5 mm carve. A second charcoal tone step was considered and rejected: on a symbol this simple it would break the patch's canon one-thread stark read and add clutter, so the depth comes from scale, hard tilt and the near-burst at the edge, not a new colour. No third colour and no extra iconography.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 2 --size-mm 60 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.
