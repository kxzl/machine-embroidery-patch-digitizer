# Bomb Upgrade Patch - Nano Banana prompt

**Shape:** Square · **Size:** 90 x 90 mm · **Threads:** 4 · **Palette:** #EDE3CF - eggshell cream (field), #1A1A1A - near-black (bomb, fuse, keyline), #E8590C - spark orange (fireball, embers), #F2B33D - golden yellow (fireball core)

## Prompt

```
Flat vector illustration of a cartoon bomb caught mid-blast, as a square patch design. A solid eggshell-cream square field set inside a clear white margin on a plain white background, so the white background reaches all four corners — no border ring. Dramatic low three-quarter angle, strong diagonal composition: a large near-black bomb sphere looms low and to the left, tilted toward the viewer, its thick rope fuse — at least 5 mm thick along its whole length — whipping up and to the right into the heart of the explosion. Behind and above it, a huge flat spark-orange fireball billows across the upper right with five large rounded lobes, each at least 15 mm across, the notches between them at least 4 mm wide, and a solid golden-yellow core; the bomb overlaps the fireball in front, and a bold cream crescent highlight on the bomb's upper-left reads as a sphere without any shading. Three or four chunky orange ember discs fly off the blast. The bomb and fireball fill the square, corner to corner.

Exactly four flat colours: eggshell cream, near-black, spark orange, golden yellow. Solid fills only — no gradients, no shading, no soft shadows, no texture, no thin lines, no fine detail. No pointed shapes: every shape ends in a rounded or squared-off end at least 3 mm across — no stars, spikes, or tapering tips. Every shape large, bold and clearly separated; high contrast, clean hard boundaries; readable at small size. No text, no lettering, no numbers.
```

## Follow-up edits

- "The blast shrank back to a small four-point star — enlarge it into a big chunky fireball of five large rounded lobes filling the upper right, with a solid golden-yellow core."
- "The fireball gained a soft gradient glow, smoke wisps, or a radial fade — flatten it to exactly two solid shapes (orange cloud + yellow core), hard edges only."
- "The bomb lost its cream crescent highlight or gained grey shading — restore one bold solid cream crescent on the upper-left and keep the bomb one flat near-black."
- "The composition snapped back to centred and symmetric — push the bomb low and left, tilt it toward the viewer, and let the fuse and fireball sweep diagonally to the upper right."
- "Tiny specks, sparkles or debris appeared around the blast — keep only three or four chunky ember discs, each a big simple round shape."
- "Any shape came back with a sharp point — flame lobes, embers or the fuse tip — round it off so it ends in a blunt end at least 3 mm across; no stars or spikes."

## Spec

- **Subject:** Classic cartoon black round bomb mid-blast, thick rope fuse, a large fireball and embers — the canon Bomb Upgrade Patch ("finely made", one hot accent).
- **Composition:** Near-black bomb sphere low-left, tilted toward the viewer, in front of a huge spark-orange fireball of five large rounded lobes with a golden-yellow core sweeping the upper right; a cream crescent highlight gives the sphere volume; chunky ember discs fly off; diagonal, corner-to-corner energy.
- **Finished size:** 90 x 90 mm — canon "Medium" patch: clearly larger than the 60 mm tiny Earth/Peace pair, a notch under the 100 mm default kept for bigger feature patches.
- **Embroidery notes:** 4 threads (cream field, near-black bomb/fuse/keyline, orange fireball/embers, yellow core). Every region is ≥5 mm at the narrowest point — the fuse 5 mm, the lobe notches 4 mm, the cream crescent 6 mm — so posterize → vectorize → Ink/Stitch fills plus satin keyline stitch cleanly with no thin runs or islands.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 4 --size-mm 90 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.
