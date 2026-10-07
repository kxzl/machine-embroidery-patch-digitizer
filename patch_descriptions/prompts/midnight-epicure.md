# Midnight Epicure Upgrade Patch ("Goat Head") - Nano Banana prompt

**Shape:** Circle · **Size:** 80 x 80 mm · **Threads:** 6 · **Palette:** #1A1A1A — near-black (field + keyline + forehead mark), #5A5A5A — dark grey (shadow planes: jaw and horn undersides), #B0B0B0 — mid grey (goat head base), #D8D8D8 — light grey (highlight planes: brow and cheekbone), #E8E3D5 — bone pale (moon, skull crescent, night marks), #B5651D — burnt amber (eyes)

## Prompt

```
Bold screen-print / tattoo-flash satanic goat head, round patch design: a huge solid near-black circle on a plain white square with a clear white margin at all four corners. A massive grey goat head fills the disc on a strong diagonal at a low three-quarter angle, chin and blunt beard at the lower left, two thick horns sweeping upper right with broad chunky pointed tips, the long horn crossing a giant flat bone-pale moon disc offset upper right, clipped by the circle edge. Build the head from three flat grey tone steps: dark grey shadow planes under jaw and horns, mid grey base, light grey highlights on brow and cheekbone. A solid bone-pale crescent on the skull's moonlit side. Burnt-amber almond eyes glare up-diagonal. Two bold near-black nostrils; a solid black flat diamond on the forehead; three chunky bone diamonds across the field.

Every interior boundary takes one bold near-black keyline at least 2 mm thick; the greys are too close to separate without it. Exactly six flat colours. Solid fills only — no gradients, shading, texture, halftone. Large bold shapes only, internal lines at least 1.5 mm thick; horn tips chunky, never tapering below 1.5 mm. High contrast, hard edges. No text. No inner border ring; the black circle's clean edge against white forms the patch shape.
```

## Follow-up edits

- "The head drifted back to a flat, centred, symmetrical icon. Push the skull low and to the left, tilt it into the low three-quarter angle, let it fill the disc edge to edge, and sweep the long horn across the moon until its tip is cut by the circle's edge."
- "Soft gradients, airbrush shading, or a glow crept in. Rebuild every form from flat solid tone steps with hard boundaries — no gradients, no soft blending, no drop shadows, no texture."
- "Fur strokes, horn ridges, or bone cracks turned into fine linework. Delete them and replace each with one large bold flat shape — broad fur planes, a single chunky horn ridge, a thick bone crack at least 1.5 mm wide."
- "The head collapsed to a single flat grey. Restore all three grey tone steps — dark grey shadow planes under the jaw and horns, mid grey base, light grey highlight on the brow and cheekbone — as separate solid shapes, each with its own black keyline."
- "The moon turned into a glow, gradient, or crater-textured ball. Flatten it back to one solid bone-pale disc with a clean hard edge, clipped by the circle."
- "The forehead diamond or the three night diamonds shrank into tiny specks or thin lines — make each one a chunky solid flat diamond at least 10 mm across with blunt corners."
- "Extra Baphomet sigil elements crept in — orbiting rings, crescents, lettering, or a seventh colour. Strip back to exactly six colours and only the head, moon disc, skull crescent, forehead diamond, and three night diamonds."

## Spec

- **Subject:** The Midnight Epicure ("The Caprid Who Devours the Sky") — the grey satanic goat head ward, now a brutal, heavy goat skull/head with real horn construction, layered grey tone steps, and a bone-pale moon rising behind its horns.
- **Composition:** Solid near-black circular field on white; giant flat bone-pale moon disc offset upper right, clipped by the circle's edge; a massive mid-grey head fills the disc from the lower left at a low three-quarter angle — chin and blunt beard at the lower-left edge, two thick horns sweeping to upper right, the long horn crossing in front of the moon with its tip cut by the circle's edge; three flat grey tone steps (dark grey shadow planes under the jaw and horn undersides, mid grey base, light grey highlight on the brow and cheekbone) give layered flat volume; a solid bone crescent on the skull's moonlit upper side; a solid black flat diamond on the forehead; burnt-amber almond eyes; three chunky bone flat diamonds in the black field, upper left to lower right; no drawn border ring. The moon and horn tip are clipped at the circle's edge, so the silhouette stays a perfect circle — shape and size unchanged.
- **Finished size:** 80 x 80 mm, unchanged — canon "medium-sized," scaled between the 60 mm Earth patch and the 100 mm default; crescent, eyes, forehead diamond, and night diamonds all sit well above the ~1 mm minimum stitch dimension.
- **Embroidery notes:** 6 threads — near-black (field + keyline + forehead mark), dark grey (shadow planes), mid grey (head base), light grey (highlight planes), bone pale (moon + skull crescent + night marks), burnt amber (eyes). The near-black keyline on every interior boundary is load-bearing: the grey tones are too close to separate without it. Only large solid polygons with hard boundaries, so it posterizes and fills cleanly; the clipped moon and horn tip run straight under the pipeline satin border with no gap.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 6 --size-mm 80 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.
