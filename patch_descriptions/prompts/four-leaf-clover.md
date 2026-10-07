# Four-Leaf Clover Patch ("Lucky Bastard") - Nano Banana prompt

**Shape:** rounded square · **Size:** 75 x 75 mm · **Threads:** 6 · **Palette:** #ECE0C6 - bone cream, #2E9E44 - clover green, #1C6B2E - deep clover green, #D89A66 - tan, #F0B429 - golden yellow, #1D1D1D - near-black

## Prompt

```
Flat illustration of a heavy bare foot slamming down on four-leaf clovers, as a rounded-square patch. A solid bone-cream rounded-square field sits in a clear white margin on plain white, so white reaches all four corners — no border ring. Dramatic low three-quarter angle, strong diagonal: a massive flat-tan foot crashes from the top-left, ankle cropped, sole tilted toward the viewer; heel, ball and arch are big anatomical blocks split by thick near-black creases. Under the sole, layered clovers splay and crease — big bright-green clovers in front, deep-green clovers crushed behind, each leaflet a bold lobe with a chunky blunt tip at least 6 mm across. Behind the strike a huge golden-yellow burst opens into broad chunky star lobes with a solid bone-cream core — two flat tone steps. A bold bone-cream crescent on the instep gives flat weight. Foot, burst and clovers fill the frame corner to corner.

Exactly six flat colours: bone cream #ECE0C6, clover green #2E9E44, deep clover green #1C6B2E, tan #D89A66, golden yellow #F0B429, near-black #1D1D1D. Solid flat fills only — no gradients, shading, texture or bevels. One heavy near-black keyline on every major shape; internal lines at least 1.5 mm. Chunky shapes, nothing under 2 mm; broad pointed tips on the burst lobes only. High contrast, clean hard boundaries. No text or lettering.
```

## Follow-up edits

- "If the design drifts back to a flat, centred, front-on icon: restore the bold diagonal — the massive foot crashing from the top-left corner, the strike and burst at the lower right, the clovers spilling across the field, filling the frame corner to corner with no dead space."
- "If a gradient, glow, soft shadow, or airbrushed shading creeps into the foot, burst, or clovers: flatten everything to solid fills — volume comes only from the flat tone steps and the bone-cream crescent on the instep."
- "If details become small or fine — hairline creases, thin motion lines, tiny sparks, fussy burst rays, slivers: enlarge or delete them; every internal line stays at least 1.5 mm thick and nothing is thinner than 2 mm at 75 mm."
- "If the clovers or the burst lose their layering and flatten to a single tone: restore two steps — bright clover green in front over deep clover green crushed behind, and a golden-yellow burst with a solid bone-cream core."
- "If the foot turns into a featureless blob or a smooth mitten: rebuild its weight — a big tan foot with real anatomical blocks for heel, ball and arch, separated by thick near-black creases, sole tilted toward the viewer."
- "If the burst lobes or clover tips taper into hairline needle points: keep them chunky — broad blunt points at least 3 mm across, never thinner than 1.5 mm."
- "If a border ring, stitched edge, or any text appears: remove it — the bone-cream field ends cleanly at the rounded-square silhouette, the satin border is added later."

## Spec

- **Subject:** Canon "Lucky Bastard" patch (Book 7, ch. 57): a bare human foot treading on a group of four-leaf clovers, creasing them as it presses down — now rendered as a heavy, aggressive stomp.
- **Composition:** Rounded-square bone-cream field; dramatic low three-quarter view of a massive tan foot crashing from the top-left down the diagonal, sole tilted toward the viewer, its heel, ball and arch built from big anatomical blocks split by thick near-black creases; layered clovers splay and crease under the sole — bright green in front, deep green crushed behind; a huge golden-yellow impact burst opens behind the strike with broad chunky star lobes and a solid bone-cream core (two flat tone steps); a bold bone-cream crescent on the instep gives flat weight; one heavy near-black keyline on every major shape; the shapes fill the frame corner to corner.
- **Finished size:** 75 x 75 mm — unchanged; shape and size kept, with the drama added purely through angle, layering, and secondary shapes rather than any change to the patch outline.
- **Embroidery notes:** 6 threads (bone cream, clover green, deep clover green, tan, golden yellow, near-black) — deep clover green #1C6B2E is the new second green tone that layers the crushed clovers behind the bright ones, and golden yellow #F0B429 with a bone-cream core gives the impact burst its two flat tone steps; all depth comes from stacked solid shapes, never shading. Leaflets and burst lobes end in chunky blunt tips ≥3 mm so no tip tapers below the satin gate; every region remains a large simple fill bounded by the single satin keyline, nothing thinner than ~2 mm.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 6 --size-mm 75 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.
