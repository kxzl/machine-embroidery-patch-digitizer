# Dungeon Crawler Carl — Nano Banana patch prompts

Flat-colour image prompts for the *Enchanted Anarchist's Battle Rattle* patch set.
Paste a prompt into Google's **Nano Banana** (Gemini image generation) to produce
a flat-colour image; the digitizing pipeline turns it into an Ink/Stitch SVG + VP3.

**Set style (all patches):** flat solid fills + one bold dark keyline; 2–5 flat
colours; no gradients, shading, texture, thin lines, pointed/tapering shapes or
fine detail; plain white background; square composition; no text; no drawn border
ring (the pipeline adds the satin border). Canon subject and signature colours only.

**Drama pass:** every patch uses a dramatic angle, overlap for depth, asymmetry /
diagonal energy, and bold secondary shapes. Depth always comes from layering flat
shapes, never shading.

**Before you run:** each patch's Spec ends with a **Pipeline** line giving the exact
`run.sh` command. The raster path only detects a satin border on transparent input
(so `--key-background` is required), and `--border-color` is SVG-only — `run.sh`
drops it for raster inputs and the auto border colour is sampled from the outer band
(the field colour on light patches, i.e. invisible). Pass
`--config patch_descriptions/border_black.yaml` to force a black satin border. Keep a
clear white margin around the artwork so the corner-based background keyer cannot
grab the patch field.

Per-patch source files live in `patch_descriptions/prompts/`. Full prompts are
embedded below in jacket layout order.

| # | Patch | Shape | Size (mm) | Threads | Palette |
|---|---|---|---|---|---|
| 1 | Bomb Upgrade | Square | 90 × 90 | 4 | `#EDE3CF` cream · `#1A1A1A` near-black · `#E8590C` spark orange · `#F2B33D` golden yellow |
| 2 | Midnight Epicure ("Goat Head") | Circle | 80 × 80 | 4 | `#1A1A1A` near-black · `#B0B0B0` grey · `#E8E3D5` bone · `#B5651D` burnt amber |
| 3 | Peace | Circle | 60 × 60 | 1 fill (2 artwork colours) | `#111111` near-black · `#FFFFFF` white (symbol sews as holes) |
| 4 | Reaper Spider ("Spider/Eye") | Die-cut spider | 70 × 70 | 4 | `#1A1A1A` near-black · `#C8CDD4` silver · `#566070` slate · `#F2B33D` amber |
| 5 | Skyfowl ("Arrow") | Square | 75 × 75 | 5 | `#BFA37A` sand · `#8A5A2E` talon · `#D2521F` flame · `#F2B33D` golden yellow · `#221A14` near-black |
| 6 | Four-Leaf Clover ("Lucky Bastard") | Rounded square | 75 × 75 | 5 | `#ECE0C6` bone · `#2E9E44` green · `#D89A66` tan · `#F0B429` golden yellow · `#1D1D1D` near-black |
| 7 | Back Patch (Nine Spinning Skulls) | Circle | 190 × 190 | 3 | `#5E1B1B` oxblood · `#2A0508` dark oxblood · `#F5EBD8` bone-cream |

> Excluded from this batch (already designed): Earth Upgrade, Book Burner, Scavenger's Daughter.
> The Back patch is deliberately recoloured off Scavenger's Daughter's white-on-black.

---


---

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

---

# Midnight Epicure Upgrade Patch ("Goat Head") - Nano Banana prompt

**Shape:** Circle · **Size:** 80 x 80 mm · **Threads:** 4 · **Palette:** #1A1A1A — near-black (field + keyline + forehead mark), #B0B0B0 — mid grey (goat head), #E8E3D5 — bone pale (moon, skull crescent, night marks), #B5651D — burnt amber (eyes)

## Prompt

```
Flat vector illustration of a satanic goat head as a round patch design: solid near-black circle on plain white, square composition. Dramatic low three-quarter angle, strong diagonal: a huge mid-grey goat head looms from lower left, a narrow blunt-ended beard at the lower-left edge, long drooping ears, thick horns sweeping to upper right. Behind it a giant flat bone-pale moon disc offset upper right, clipped by the circle edge; head and long upper horn overlap the moon in front, horn tip cut by the edge. A solid bone crescent on the skull's moonlit upper side gives flat volume. Burnt-amber almond eyes glare along the diagonal; two bold near-black nostril ovals, each at least 6 mm across; a solid black flat diamond on the forehead; three chunky bone flat diamonds fill the black field, upper left to lower right.

Every interior boundary takes one bold near-black keyline at least 2 mm thick. This is not decoration: the mid-grey and bone-pale are too close in tone to separate without it. Exactly four flat colours: near-black, mid grey, bone pale, burnt amber. Solid fills only — no gradients, shading, shadows, texture, denim weave, halftone, stitch marks, bevels. No pointed shapes: every shape ends in a rounded or squared-off end at least 3 mm across — no stars, spikes, or tapering tips. Bold, large, simple shapes; nothing thin or fine; no specks, no hairline gaps. High contrast, hard boundaries. No text, lettering, numbers, extra symbols. No inner border ring; the black circle's clean edge against white forms the patch shape.
```

## Follow-up edits

- "The head drifted back to a centred, symmetrical, front-facing pose. Push the skull low and to the left, tilt it into the low three-quarter angle, and sweep the horns up the diagonal so the long horn crosses the moon and its tip cuts the circle's edge."
- "The moon turned into a glow, gradient, or crater-textured ball. Flatten it back to one solid bone-pale disc with a clean hard edge, clipped by the circle."
- "The forehead diamond or the three night diamonds shrank into tiny specks or thin lines — make each one a chunky solid flat diamond at least 10 mm across with blunt corners."
- "The skull crescent disappeared or softened into a shaded highlight. Restore one solid bone crescent on the skull's moonlit upper side with a hard black keyline — flat volume, no gradient."
- "The horns pulled back inside the circle, leaving dead black space at the edges. Push the beard to the lower-left edge and extend the long horn until its tip is cut by the circle's edge."
- "Extra Baphomet sigil elements crept in — orbiting rings, crescents, lettering, or a fifth colour. Strip back to exactly four colours and only the head, moon disc, skull crescent, forehead diamond, and three night diamonds."

## Spec

- **Subject:** The Midnight Epicure ("The Caprid Who Devours the Sky") — the grey satanic goat head ward, now glaring up the diagonal with a bone-pale moon rising behind its horns.
- **Composition:** Solid near-black circular field on white; giant flat bone-pale moon disc offset upper right, clipped by the circle's edge; huge mid-grey head looms from the lower left at a low three-quarter angle — beard at the lower-left edge, horns sweeping to upper right, the long horn crossing in front of the moon with its tip cut by the circle's edge; solid bone crescent on the skull's moonlit upper side gives flat volume; solid black flat diamond on the forehead; burnt-amber almond eyes; three chunky bone flat diamonds in the black field, upper left to lower right; no drawn border ring. The moon and horn tip are clipped at the circle's edge, so the silhouette stays a perfect circle — shape and size unchanged.
- **Finished size:** 80 x 80 mm, unchanged — canon "medium-sized," scaled between the 60 mm Earth patch and the 100 mm default; crescent, eyes, forehead diamond, and night diamonds all sit well above the ~1 mm minimum stitch dimension.
- **Embroidery notes:** 4 threads — near-black (field + keyline + forehead mark), mid grey (goat head), bone pale (moon + skull crescent + night marks), burnt amber (eyes). The near-black keyline on every interior boundary is load-bearing: the mid-grey and bone-pale are too close in tone to separate without it. Only large solid polygons with hard boundaries, so it posterizes and fills cleanly; the clipped moon and horn tip run straight under the pipeline satin border with no gap.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 4 --size-mm 80 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.

---

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

---

# Reaper Spider Minion Patch ("Spider/Eye") - Nano Banana prompt

**Shape:** die-cut spider silhouette (a fan convention; `patches.md` gives no die-cut instruction for this patch and flags its wiki source as thin — overrides the default circle/square/shield list) · **Size:** 70 x 70 mm · **Threads:** 4 · **Palette:** #1A1A1A - near-black (keyline, near legs, pupil, bead eyes, strap), #C8CDD4 - silver grey (body, head, near basket, eye glint), #566070 - slate grey (far legs, far basket — flat depth tone), #F2B33D - amber (jewel eye)

## Prompt

```
Flat vector illustration of a die-cut embroidered patch shaped as a stylized spider merchant mid-stride: the patch is the spider's own silhouette on a plain white background, no border ring. Square composition, dramatic low three-quarter view, strong diagonal: the huge bulbous silver-grey body lunges from the lower left toward the upper right, off-centre, legs stretching corner to corner. Eight thick paddle legs at varied blunt angles — each at least 6 mm wide along its whole length with rounded tips, and white gaps of at least 6 mm between adjacent legs — four far legs in slate grey layered behind the body; one near front leg rears high mid-step. The round head swings toward the viewer: one enormous amber jewel eye with a solid black pupil and one chunky silver crescent glint reading as a glossy jewel without shading, plus two small black bead eyes; friendly-strange, not horror. Two big smooth silver baskets ride the diagonal under one thick black strap — near basket overlapping the body in front, far basket in slate grey behind.

Exactly four flat colours: near-black, silver grey, slate grey, amber gold. Solid fills only — no gradients, no shading, no texture, no wicker, no stitch marks. No pointed shapes: every shape ends in a rounded or squared-off end at least 3 mm across — no spikes or tapering tips. One bold near-black keyline outlines every shape; high contrast, clean hard boundaries. Every shape large and simple. No text, no numbers, no web, no background elements.
```

## Follow-up edits

- "If the spider renders front-on, upright, or centred: tip the body onto the low three-quarter diagonal, mid-stride, head swinging to face the viewer — never a flat symmetric stance."
- "If the slate depth tone disappears or turns into grey shading: keep the four far legs and the far basket as solid flat slate-grey shapes layered behind the silver body — flat colour only, no gradients."
- "If the legs mirror each other or the pose goes static: push the body off-centre toward the upper right, leave more white at the lower left, give every leg a different blunt angle with one near leg rearing high."
- "If the eye glint becomes a gradient, gloss, or a tiny dot: make it one chunky solid silver crescent inside the black pupil, and keep both baskets big, smooth, and simple."
- "If a moon, coin, web, or any background shape appears behind the spider: remove it — the patch is only the spider's own silhouette on pure white, no border ring."
- "If the legs come out spindly or pointed: make every leg a thick blunt paddle at least 6 mm wide with rounded tips, and keep white gaps of at least 6 mm between adjacent legs."
- "If the baskets render with woven wicker texture: make the baskets plain smooth solid shapes with only the black keyline — no weave, no crosshatch."
- "If extra eyes, fangs, or a human-like face appear: keep only the one big amber eye and the two small black bead eyes — no fangs, no mouth, no human features."

## Spec

- **Subject:** Traveling Reaper Spider Minion merchant (Midnight Market trader) — a small "black and silver", die-cut, Shi Maria-like spider carrying multiple wicker baskets lashed over her bulbous body. (Die-cut shape is a fan convention; `patches.md` flags this patch's wiki source as thin.)
- **Composition:** Shape unchanged — still the pure die-cut spider silhouette (no background disc added, so the canon die-cut read survives; depth comes from layering flat slate shapes instead). Dynamic low three-quarter mid-stride pose: bulbous silver body lunging lower-left to upper-right, off-centre, legs reaching corner to corner; four far legs plus the far basket in flat slate grey tucked behind the body; one near leg rearing high; head turned to the viewer with one huge amber jewel eye (solid black pupil, chunky silver crescent glint) and two black bead eyes; two smooth silver baskets riding the diagonal under one thick black strap, near basket overlapping the body in front.
- **Finished size:** 70 x 70 mm — canon "Upgrade Patch (Small)"; one step above the 60 mm tiny Earth/Peace rounds so thick legs and baskets still stitch cleanly, well below the medium patches.
- **Embroidery notes:** 4 threads; near-black carries the satin keyline, near legs, pupil, bead eyes and strap; silver makes the biggest fills (body, head, near basket) plus the eye glint; slate grey is a pure flat depth tone for the far legs and far basket; amber only the eye. Legs are held to ≥6 mm wide with ≥6 mm gaps so each leg's inscribed radius clears the 2.5 mm border carve and can carry its own satin edge; white background unstitched, and the pipeline traces the dynamic spider silhouette for the satin border.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 4 --size-mm 70 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.

---

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

---

# Four-Leaf Clover Patch ("Lucky Bastard") - Nano Banana prompt

**Shape:** rounded square · **Size:** 75 x 75 mm · **Threads:** 5 · **Palette:** #ECE0C6 - bone cream, #2E9E44 - clover green, #D89A66 - tan, #F0B429 - golden yellow, #1D1D1D - near-black

## Prompt

```
Flat vector illustration of a bare human foot caught mid-stomp, as a rounded-square patch design. A solid bone-cream rounded-square field set inside a clear white margin on a plain white background, so the white background reaches all four corners — no border ring. Dramatic low three-quarter angle, strong diagonal composition: a chunky flat-tan foot plunges from the top-left, ankle cropped by the top edge, sole tilted toward the viewer, slamming down the diagonal onto the lower right. Behind the strike a huge flat golden-yellow impact burst bursts open with bold chunky lobes; the foot and clovers overlap it in front. Three big green four-leaf clovers splay from under the sole like squashed springs, and two chunky whole clovers fly off toward the upper right. Each clover leaflet is a rounded rectangle with a blunt rounded outer end at least 6 mm across — no pointed leaf tips. A bold bone-cream crescent highlight on the instep gives the foot flat volume, not shading. Foot, burst and clovers fill the field corner to corner. The foot is a simple mitten with shallow toe scallops — no individual toes, no leg — and every major shape carries one thick near-black keyline.

Exactly five flat colours: bone cream #ECE0C6, clover green #2E9E44, tan #D89A66, golden yellow #F0B429, near-black #1D1D1D. Solid fills only — no gradients, shading, shadows, texture, stitch marks, or bevels. No pointed shapes: every shape ends in a rounded or squared-off end at least 3 mm across — no spikes or tapering tips. Bold, large, simple shapes; no stems, no thin lines, nothing under 2 mm. High contrast between adjacent colours, clean hard boundaries. No text, no lettering, no numbers.
```

## Follow-up edits

- "Remove any border ring, frame, or stitched edge line around the patch — the bone-cream field must end cleanly at the rounded-square silhouette, and keep the field clearly cream, not white."
- "If the foot grows individual toes, toenails, an ankle bone, or a full leg, simplify back to the chunky cropped mitten foot in flat tan, with only shallow toe scallops and the single cream crescent highlight."
- "Delete any thin motion lines, speed streaks, tiny spark flecks, fussy burst rays, stems, or extra tiny clovers — the impact burst must stay one huge flat golden-yellow shape with a few bold chunky lobes only."
- "If the design drifts back to a centred, front-on stomp, restore the low three-quarter diagonal: foot plunging from the top-left corner, strike and burst at the lower right, clovers flying to the upper right, filling the field corner to corner."
- "If any shading, gradient, or soft shadow appears on the foot, burst, or clovers, flatten everything back to solid fills — volume comes only from the cream crescent on the instep."
- "If the clover leaflets taper to points, make each leaflet a rounded rectangle with a blunt rounded outer end at least 6 mm across — no sharp leaf tips."
- "Keep the two flying clovers big and chunky — whole four-leaf clovers with thick leaflets, no stems — never shrinking into specks or thin leaves."

## Spec

- **Subject:** Canon "Lucky Bastard" patch (Book 7, ch. 57): a bare human foot treading on a group of four-leaf clovers, creasing them as it presses down.
- **Composition:** Rounded-square bone-cream field; dramatic low three-quarter view of a chunky tan foot plunging from the top-left corner down the diagonal, sole tilted toward the viewer, overlapping a huge flat golden-yellow impact burst at the lower right; three green four-leaf clovers splay from under the sole and two whole clovers fly toward the upper right; each leaflet a rounded rectangle with a blunt outer end ≥6 mm; a bold bone-cream crescent on the instep gives flat volume; one thick near-black keyline on every major shape; the shapes fill the field corner to corner.
- **Finished size:** 75 x 75 mm — unchanged; shape and size kept, with the drama added purely through angle, layering, and secondary shapes rather than any change to the patch outline.
- **Embroidery notes:** 5 threads (bone cream, clover green, tan, golden yellow, near-black) — golden yellow #F0B429 is the flat impact-burst layer that separates the strike zone from the cream field and creates depth by layering flat shapes rather than shading. Leaflets are blunted to rounded rectangles ≥6 mm so no tip tapers below the satin gate; every region remains a large simple fill bounded by the single satin keyline, nothing thinner than ~2 mm.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 5 --size-mm 75 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.

---

# Back Patch (Nine Spinning Skulls) - Nano Banana prompt

**Shape:** circle · **Size:** 190 x 190 mm · **Threads:** 3 · **Palette:** #5E1B1B - deep oxblood (field, keyline, sockets), #2A0508 - dark oxblood (hub), #F5EBD8 - bone-cream (skulls, hub crescent, motion arc); black satin border via `border_black.yaml`

## Prompt

```
Flat vector illustration of a spinning wheel of skulls caught mid-tumble, as a large round patch design. A solid deep oxblood circle on a plain white background, the white reaching all four corners, square composition; the disc is the patch, no drawn border ring. The skull ring is a strong ellipse rushing toward the viewer, long axis corner to corner — never a flat front-on ring. Exactly nine bone-cream skulls ride the ellipse: four big near skulls lower left, five smaller far skulls upper right, each rotated a further 40 degrees clockwise than the last, each partly overlapping its neighbour. One bold deep-oxblood keyline rims every bone-cream shape, keeping all nine separate and countable. Each skull one bold simple shape: rounded cranium, solid jaw, two big oxblood eye sockets, one oxblood nasal notch; no teeth, no cracks. The wheel's core is a bold dark-oxblood hub disc, one clearly darker red-brown step below the field — never black, never a third red — with near skulls biting over its edge; a bone-cream crescent on its upper-left reads as light on the core. One chunky bone-cream motion arc sweeps inside the ring, trailing the spin. Depth comes only from layering flat shapes.

Exactly three flat colours: deep oxblood, dark oxblood, bone-cream. Solid fills only — no gradients, no shading, no texture, no stitch marks, no motion blur. Every shape large, bold and simple, with blunt rounded or squared ends — no spikes or tapering tips. High contrast, clean hard boundaries. No text, no lettering, no numbers.
```

## Follow-up edits

- "Exactly nine skulls came out as eight, ten, or with a tenth skull face on the hub — restore four big near skulls on the lower left plus five smaller far skulls on the upper right of the tilted ellipse, and keep the hub a plain dark-oxblood disc with only its bone crescent, no face on it."
- "The ring flattened back into a front-on circle of equal-size upright skulls — re-tilt it into a strong ellipse rushing toward the viewer, long axis running corner to corner, with the four near skulls on the lower left clearly bigger than the five far skulls on the upper right, each tumbling a further 40 degrees clockwise than its neighbour."
- "The field drifted to black, or the hub and field merged into one red — make the field deep oxblood (#5E1B1B) and the hub a clearly darker red-brown step (#2A0508), never black and never a third red, so this patch stays distinct from the black Scavenger's Daughter patch."
- "Skulls grew individual teeth, cracks, jaw hinges, or grey soft shading — flatten every skull back to one solid bone-cream shape with only two big oxblood eye sockets and one oxblood nasal notch, hard edges only, exactly three colours."
- "The overlapping skulls melted into one bone blob or lost their keylines — restore the bold deep-oxblood keyline rimming every bone-cream shape so all nine skulls read separate and countable at a glance."
- "The motion arc multiplied into thin speed lines, shrank to a sliver, or turned into extra floating skulls — keep exactly one chunky bone-cream arc inside the ring, thick and bold, and nothing else floating."

## Spec

- **Subject:** DCC large back patch — Donut's Book 6 note that the back-patch skulls spin/move and there are nine heads.
- **Composition:** solid deep-oxblood disc filling the frame on white; nine bone-cream skulls on a tilted elliptical ring rushing toward the viewer, long axis corner to corner (lower-left near, upper-right far) — four big near skulls, five smaller far skulls, each rotated a further 40° clockwise than its neighbour and partly overlapping it; a bold dark-oxblood hub disc (one clearly darker red-brown step below the field) with a bone-cream crescent highlight on its upper-left; one chunky bone-cream motion arc inside the ring; a bold deep-oxblood keyline rims every bone-cream shape — depth from layered flat shapes, never shading.
- **Finished size:** 190 x 190 mm circle — the set's boss patch, sized 10 mm under the project's 260 x 200 mm fit box so registration margin remains.
- **Embroidery notes:** 3 threads — deep oxblood carries the field plus every internal keyline, eye socket and nasal notch; dark oxblood #2A0508 fills only the hub; bone-cream fills skulls, hub crescent and motion arc. The satin border is **black** via the shared `border_black.yaml` config (the set's borders are uniform), not oxblood. At 190 mm the near skulls run ~52 mm tall with ~11 mm sockets and the far skulls ~28 mm with ~7 mm sockets, the hub is ~66 mm across, the keyline ~4 mm thick and the arc ~24 mm thick, so every region digitizes as a few clean fills — no thin satins, tiny islands, or detached teeth. **Deliberately recoloured off Scavenger's Daughter's white-on-black** so the two back-patch candidates don't read as the same patch.
- **Pipeline:** run `tools/digitize/run.sh --key-background --colors 3 --size-mm 190 --config patch_descriptions/border_black.yaml <image>`. The raster path only detects a satin border on transparent input (hence `--key-background`); `--border-color` is SVG-only and `run.sh` drops it for raster inputs, and the auto border colour is sampled from the outer band — the field colour on light patches, i.e. invisible. The shared config forces `border.mode: force_black` so the satin border is always a visible dark line.
