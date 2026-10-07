# Skyfowl Upgrade Patch ("Arrow") - Nano Banana prompt

**Shape:** Square · **Size:** 75 x 75 mm · **Threads:** 5 · **Palette:** #BFA37A - warm sand (field + talon crescent highlight), #8A5A2E - weathered golden-brown (talon), #D2521F - flame red-orange (flame mass + embers), #F2B33D - golden yellow (flame core), #221A14 - warm near-black (arrow bundle, fletching, keyline)

## Prompt

```
Flat vector illustration of an eagle talon seizing a bundle of flaming arrows mid-flight, as a square patch design. A solid warm-sand square field set inside a clear white margin on a plain white background, so the white background reaches all four corners — no border ring. Dramatic low three-quarter angle, strong diagonal composition: low and left, a big chunky golden-brown talon clamps the bundle side-on, knuckles toward the viewer, three bold toes biting one thick near-black arrow bundle that sweeps diagonally up to the upper right, corner to corner. Behind the arrowheads, a huge flat red-orange flame mass lashes across the upper right in three big rounded flame lobes with a solid golden-yellow core; the arrowheads overlap it in front for depth. A bold warm-sand crescent on the talon's lead knuckle reads as volume without shading. Near-black blunt fletching blocks crop the field's lower-left corner; three or four chunky red-orange ember discs fly toward the top-left. The bundle and flames fill the square.

Exactly five flat colours: warm sand, golden-brown, near-black, red-orange, golden yellow. Solid fills only - no gradients, no shading, no texture, no bevels, no thin lines, nothing under 2 mm at 75 mm patch size. No pointed shapes: every shape ends in a rounded or squared-off end at least 3 mm across — no spikes, teardrops, or tapering tips. One bold near-black keyline outlines talon, bundle and flame lobes. High contrast between adjacent colours, clean hard boundaries, readable at small size. No text, no lettering, no numbers.
```

## Follow-up edits

- "If twelve separate thin arrow shafts reappear with hairline gaps: merge them into one thick solid near-black bundle — this deliberately departs from the canon's 'a dozen', because twelve separate shafts would produce twelve sub-1 mm slivers at 75 mm. The bundle must still read as a bundle: the fanned tips stay distinct as bold blunt notches at least 8 mm across."
- "If the flame crown breaks into many small flames: consolidate to exactly three large rounded flame lobes as one red-orange mass with one solid golden-yellow core."
- "If a gradient, glow or shading creeps into the flames or talon: flatten fully - the flame mass is one solid red-orange with one solid golden-yellow core, and the talon is one solid golden-brown with a single bold warm-sand crescent highlight."
- "If the composition snaps back to centred and vertical: restore the diagonal sweep - talon low and left, bundle running to the upper right, flame mass behind the arrowheads, fletching cropped at the lower-left corner, embers toward the top-left."
- "If the embers shrink into tiny specks or sparkles: keep only three or four chunky red-orange ember discs, each a big simple round shape."
- "If a stitched border ring or edge outline appears around the square: remove it - the sand field ends flat at the square's edge; the satin border is added later."

## Spec

- **Subject:** An eagle talon clutching black arrows whose tips burn red-orange — the twelve flaming arrows of the Skyfowl hero Radiant Star. The dozen is deliberately merged into one bundle (see below).
- **Composition:** Golden-brown talon low-left and side-on, knuckles toward the viewer, three bold toes gripping one thick near-black arrow bundle that sweeps diagonally to the upper right; a huge flat red-orange flame mass with a solid golden-yellow core lashes behind the arrowheads in the upper right; a bold warm-sand crescent highlights the talon's lead knuckle; near-black blunt fletching blocks crop the field's lower-left corner; chunky red-orange ember discs fly toward the top-left; one bold near-black keyline outlines talon, bundle and flame lobes — diagonal, corner-to-corner energy.
- **Finished size:** 75 x 75 mm - canon calls it a small square patch and merch runs ~3 in (76 mm), so it sits between tiny Earth (60 x 60) and the medium patches (100 x 100).
- **Embroidery notes:** 5 threads; the twelve arrows are deliberately merged into one thick bundle — a defended departure from canon's "a dozen", because twelve separate shafts would produce twelve sub-1 mm slivers at 75 mm; the fanned tips stay distinct as blunt notches ≥8 mm. The flame crown stays two consolidated fills (red-orange mass + golden-yellow core) rather than twelve tiny flames; the talon's crescent highlight reuses the sand field thread so it adds volume without a sixth colour; the near-black keyline does double duty as the arrow colour and the set's satin linework.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 5 --size-mm 75 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.
