# Bomb Upgrade Patch - Nano Banana prompt

**Shape:** Square · **Size:** 90 x 90 mm · **Threads:** 6 · **Palette:** #EDE3CF - eggshell cream (field + crescent highlight), #1A1A1A - near-black (bomb, fuse, keyline, shrapnel, rivets), #5C5C5C - iron grey (casing band), #8E1B0F - deep red (blast outer), #E8590C - spark orange (blast mid, embers), #F2B33D - golden yellow (blast core)

## Prompt

```
Flat vector illustration of a heavy iron bomb caught mid-blast, as a square patch design. A solid eggshell-cream square field sits in a clear white margin on plain white, reaching all four corners — no border ring. Dramatic low three-quarter angle, strong diagonal: a big near-black iron bomb looms low and left, tilted toward the viewer, a thick iron-grey casing band with four large near-black rivet domes at its waist, one bold cream crescent on its upper-left. Its chunky tapered fuse — never thinner than 4 mm — whips up and right into the blast. Behind it, a huge layered blast fills the upper right corner to corner: deep-red outer lobes, a spark-orange mid mass, a solid golden-yellow core, each a big flat hard-edged shape. Chunky near-black shrapnel shards and three big orange ember discs fly off the blast.

Exactly six flat colours: eggshell cream, near-black, iron grey, deep red, spark orange, golden yellow. Solid fills only — no gradients, no shading, no texture, no thin lines, no fine detail. Chunky pointed tips are allowed on the fuse, shrapnel and flame licks, but every tip stays blunt, never below 3 mm. Every shape large, bold, separated; one heavy near-black keyline around the bomb, fuse, shrapnel and blast; high contrast, clean hard boundaries; readable at small size. No text, no lettering, no numbers.
```

## Follow-up edits

- "The bomb snapped back to a flat, centred, symmetric icon — restore the dramatic low three-quarter diagonal: bomb low and left, tilted toward the viewer, fuse and layered blast sweeping to the upper right, filling the square corner to corner."
- "A gradient, glow, bevel or soft shading crept onto the bomb, casing or blast — flatten everything: the bomb is one flat near-black with an iron-grey casing band and a single cream crescent, and the blast is exactly three flat layers, deep red behind spark orange behind golden yellow, hard edges only."
- "The blast collapsed to one flat blob or lost its three tone steps — rebuild it as three stacked flat shapes: deep-red outer lobes, a spark-orange mid mass, a solid golden-yellow core."
- "Rivets, shrapnel or blast lobes shrank into tiny specks, hairline lines or fussy detail — make every rivet a big bold dome at least 6 mm across, every shard a chunky block, every lobe a large shape; nothing thinner than 3 mm."
- "The casing band and rivets merged into the near-black bomb or vanished — restore the iron-grey band as a bold stripe with four large near-black rivet domes and a heavy near-black keyline."
- "The fuse thinned into a rope squiggle or a wire — restore a thick chunky tapered fuse at least 4 mm thick along its whole length, with a chunky flame at its tip."
- "A tip came back as a hairline needle point — on the fuse, shrapnel or flame licks — blunt it to a chunky tip at least 3 mm across; no thin spikes."
- "Tiny specks, sparkles or debris appeared around the blast — keep only three or four chunky ember discs and a few big shrapnel shards, each a large simple shape."
- "A drawn border ring, frame or lettering appeared — remove it; the cream field ends flat at the square's edge, the white margin reaches all four corners, and the satin border is added later by the pipeline."

## Spec

- **Subject:** Classic round bomb mid-blast with a thick tapered fuse, a big layered fireball and shrapnel — the canon Bomb Upgrade Patch ("finely made", one hot accent), rebuilt gritty and heavy-iron rather than cute.
- **Composition:** Big near-black iron bomb low-left, tilted toward the viewer, wearing a thick iron-grey casing band with four large near-black rivet domes and one bold cream crescent on its upper-left; a huge layered blast fills the upper right corner to corner — deep-red outer lobes, a spark-orange mid mass, a solid golden-yellow core; a chunky tapered fuse whips from the bomb into the blast; chunky near-black shrapnel shards and big orange ember discs fly off; one heavy near-black keyline on every major shape — diagonal, corner-to-corner energy.
- **Finished size:** 90 x 90 mm — canon "Medium" patch: clearly larger than the 60 mm tiny Earth/Peace pair, a notch under the 100 mm default kept for bigger feature patches. Shape and size unchanged.
- **Embroidery notes:** 6 threads (cream field + crescent, near-black bomb/fuse/keyline/shrapnel/rivets, iron-grey casing band, deep-red blast outer, spark-orange blast mid/embers, golden-yellow blast core). Every region is ≥4 mm at its narrowest — the fuse 4 mm, the rivet domes 6 mm, the cream crescent 6 mm, and the blast lobes and shards much larger — so posterize → vectorize → Ink/Stitch fills plus satin keyline stitch cleanly with no thin runs or islands. The near-black keyline between the iron-grey band and the near-black bomb is load-bearing: those two tones sit close, so the band and rivets must carry a bold keyline to stay separate.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 6 --size-mm 90 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.
