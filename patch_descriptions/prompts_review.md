# Prompt review — Dungeon Crawler Carl patch set (second re-review)

Reviewed 2026-10-07, third pass. Scope: the 7 files in
`patch_descriptions/prompts/`, the combined index
`patch_descriptions/nano_banana_prompts.md`, and the new shared config
`patch_descriptions/border_black.yaml`. Canon: `patch_descriptions/patches.md`.
Quality bar: `docs/EMBROIDERY_QUALITY.md`. Vocabulary: `GLOSSARY.md`. Pipeline
constants read from `tools/digitize/vectorize.py` (raster path — the path a Nano
Banana PNG takes), `tools/digitize/run.sh`, `tools/digitize/key_background.py`
and `tools/digitize/svg_digitize.py` (native-SVG path).

This pass verifies the three fixes applied since the 4.31 round (the border
config, Epicure's blunt anatomy, Skyfowl's fletching) **against the actual
files**, and re-scores. No prompt was modified. No Nano Banana image was
generated (there is no render of any of these 7 prompts in `input/`), so every
claim about what the model will produce is inference from wording, not
measurement. The border mechanism was checked **empirically** by running the
pipeline on synthetic images (§4.1).

**Prior set average: 4.31 / 5. This pass: 4.49 / 5 (Δ +0.18).**

> Data-integrity note on the prior baseline. The prior table's per-patch means
> were miscomputed twice: its Skyfowl row (EF 4, DR 5, CA 4, PQ 4, DG 5) sums to
> 22 → **4.4**, not the 4.6 printed; its Clover row (5, 5, 5, 4, 5) sums to 24 →
> **4.8**, not the 4.6 printed. The two errors are equal and opposite, so the
> prior set mean (30.2 / 7 = 4.31) is unaffected. The "Prior" column below keeps
> the *as-printed* values for comparability and the delta is computed against
> them; where a corrected prior changes the delta it is called out.

Scoring rule (unchanged, so deltas are comparable): each criterion 1–5, mean to
two decimals. EF = 5 only where every load-bearing thin feature is dimensioned
**and** no pointed/tapering element is still explicitly requested in the
prompt's own body; EF 4 where a structural thin-geometry or repeated-element
risk remains. PQ = 5 where the prompt is concrete, dimensioned, states its
constraints and prescribes a runnable Pipeline line; PQ 4 where a load-bearing
dimension lives only in a follow-up, where wording is ambiguous, or where the
Pipeline line contradicts the Spec.

---

## 1. Data table

| Patch | Shape | Size (mm) | Threads | Palette | EF | DR | CA | PQ | DG | **Avg** | **Prior** | **Δ** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Bomb | square | 90 × 90 | 4 | `#EDE3CF` `#1A1A1A` `#E8590C` `#F2B33D` | 5 | 5 | 4 | 4 | 4 | **4.4** | 4.2 | **+0.2** |
| Midnight Epicure | circle | 80 × 80 | 4 | `#1A1A1A` `#B0B0B0` `#E8E3D5` `#B5651D` | 5 | 5 | 4 | 4 | 4 | **4.4** | 4.2 | **+0.2** |
| Peace | circle | 60 × 60 | 1 fill (2 artwork colours) | `#111111` `#FFFFFF` | 4 | 3 | 5 | 5 | 5 | **4.4** | 4.2 | **+0.2** |
| Reaper Spider | die-cut | 70 × 70 | 4 | `#1A1A1A` `#C8CDD4` `#566070` `#F2B33D` | 4 | 4 | 4 | 5 | 5 | **4.4** | 4.2 | **+0.2** |
| Skyfowl | square | 75 × 75 | 5 | `#BFA37A` `#8A5A2E` `#D2521F` `#F2B33D` `#221A14` | 5 | 5 | 4 | 5 | 5 | **4.8** | 4.6 | **+0.2** |
| Four-Leaf Clover | rounded square | 75 × 75 | 5 | `#ECE0C6` `#2E9E44` `#D89A66` `#F0B429` `#1D1D1D` | 4 | 5 | 5 | 5 | 5 | **4.8** | 4.6 | **+0.2** |
| Back (9 skulls) | circle | 190 × 190 | 3 | `#5E1B1B` `#2A0508` `#F5EBD8` | 4 | 4 | 5 | 4 | 4 | **4.2** | 4.2 | **0.0** |

EF = Embroidery fitness · DR = Drama/impact · CA = Canon fidelity ·
PQ = Prompt quality · DG = Drift risk (guards).

**Set average 4.49 / 5** (prior 4.31, Δ +0.18). Thread counts 3–5; Peace is 1
stitched thread over 2 artwork colours. Mean 4.14 threads. Two patches at the
5-colour ceiling (Skyfowl, Clover).

Every score rose by exactly +0.2 except Back, which is flat — because the only
set-wide change is the Pipeline fix, worth +0.2 of PQ on the six prompts whose
PQ was capped at 4, plus +0.2 of EF on Epicure and Skyfowl (taper cleanups) and
−0.2 of EF on Clover (the repeated-geometry risk re-assessed). Back's PQ gain is
cancelled by the new border-colour contradiction (§4.2). No patch lost ground to
an art regression.

### 1.1 Thread / palette sanity

- Bomb 4 · Epicure 4 · Peace **1 fill** · Spider 4 · Skyfowl 5 · Clover 5 ·
  Back 3. All inside the 2–5 *artwork-colour* constraint; Peace is the only
  sub-2 *thread* patch and that is stated correctly (`peace.md:3`, `:28`).
- The two weakest intra-patch colour pairs are unchanged and both guarded by a
  keyline: Epicure grey `#B0B0B0` vs bone `#E8E3D5` (ΔE76 ≈ 20) and Back
  `#5E1B1B` vs `#2A0508` (rgb distance **59.6**). Both clear
  `vectorize.py:437`'s 20.0 merge distance; Back's pair is ~3× clear.

### 1.2 Residual pointed-shape inventory (crescents accepted)

| Prompt | Pointed/tapering element still requested | Line | Status |
|---|---|---|---|
| Bomb | cream crescent highlight (≥6 mm, `:27`) | `bomb.md:8` | accepted |
| Midnight Epicure | "narrow blunt-ended beard"; "thick horns sweeping" | `midnight-epicure.md:8` | residual wording |
| Reaper Spider | silver crescent glint | `reaper-spider.md:8` | accepted |
| Skyfowl | warm-sand crescent; "three bold toes biting" (claws) | `skyfowl.md:8` | accepted / residual |
| Four-Leaf Clover | bone-cream crescent | `four-leaf-clover.md:8` | accepted |
| Back | bone-cream hub crescent; motion arc | `back-nine-skulls.md:8` | accepted |
| Peace | none | — | clean |

A crescent tapers to a point by definition; 6 of 7 prompts contain one, and the
operator has deliberately **kept** them. That is an accepted residual, not a
defect. The set-wide blunt-end ban ("every shape ends in a rounded or
squared-off end at least 3 mm across") instructs them blunt but never says the
crescent is a thick band, so it remains a wording fight the model can lose. The
prior review's proposed crescent clause was not applied. The two *explicit*
taper cleanups (Epicure anatomy, Skyfowl fletching) did land.

---

## 2. Per-patch verdicts

### Bomb — `prompts/bomb.md` · avg 4.4 (+0.2)

Biggest strength: the Pipeline line is now true. `bomb.md:28` prescribes
`--config patch_descriptions/border_black.yaml`, which `run.sh` forwards and
`vectorize.py` turns into a pure-black satin border (§4.1, verified), and the
prompt still carries the set's best dimensions — fuse "at least 5 mm thick
along its whole length", fireball "five large rounded lobes, each at least 15 mm
across, the notches between them at least 4 mm wide" (`:8`, `:27`). Biggest
risk: the fuse is still a "whipping" curvy rope (`:8`), which can pinch below
5 mm where it bends, and the cream crescent is a pointed shape on the one patch
where the field and the highlight share a thread; PQ is held at 4 for that
residual rope/crescent ambiguity. Nothing else regressed.

### Midnight Epicure — `prompts/midnight-epicure.md` · avg 4.4 (+0.2)

Biggest strength: the pointed-anatomy fix landed — `:8` now reads "a narrow
blunt-ended beard at the lower-left edge, long drooping ears", with no "pointed"
anywhere in the file, so EF rises 4 → 5; the clip-the-moon-at-the-edge device
(`:8`) is still the cleverest silhouette-preserving drama in the set. Biggest
risk: "narrow" is an unquantified dimension (a beard is exactly the kind of
shape that renders as a 1 mm sliver), and the horns still "sweep" — a taper,
though the tip is clipped by the circle edge so it does not end in a free point.
PQ stays 4 because the load-bearing ≥10 mm diamond floor lives only in the
follow-up (`:17`), not in the prompt the model reads.

### Peace — `prompts/peace.md` · avg 4.4 (+0.2)

Biggest strength: the Pipeline line is now correct and the "1 fill thread"
accounting (`:3`, `:28`) is the set's most important factual correction; the
white symbol "sews as unstitched holes in the near-black fill" and the
upper-right margin is "at least 6 mm wide … clear of the satin border's 3.5 mm
carve" (`:8`, `:28`), comfortably beyond both the raster carve (≤2.5 mm,
`vectorize.py:369-375`) and the SVG carve (1.0–3.5 mm, `svg_digitize.py:1111-1116`).
Biggest risk: drama is still tilt-plus-margin only (`:8`) — no overlap, no
layering, no secondary shape — the weakest drama in the set (DR 3), and the
6 mm margin text cites the 3.5 mm *SVG* carve rather than the 2.5 mm raster carve
(`:8`, `:17`, `:26`, `:28`); the figure is conservative so the margin is safe,
but the wording is imprecise.

### Reaper Spider — `prompts/reaper-spider.md` · avg 4.4 (+0.2)

Biggest strength: legs are "each at least 6 mm wide along its whole length with
rounded tips, and white gaps of at least 6 mm between adjacent legs" (`:8`),
which clears the border-trace inscribed-radius gate (`vectorize.py:343`, needs
≥2.5 mm radius) with margin to spare, and the die-cut claim is honestly softened
to "a fan convention; `patches.md` gives no die-cut instruction for this patch
and flags its wiki source as thin" (`:3`, `:26`). Biggest risk: it is still the
most complex silhouette — eight appendages on a 70 mm die-cut outline — and the
pipeline traces **one border per eroded part** (`vectorize.py:317-346`); any leg
the model draws under ~5 mm is skipped and left as a raw fill. Canon itself
remains the thinnest in the set (`patches.md:14`, `:29`). PQ rises to 5 with the
Pipeline fix.

### Skyfowl — `prompts/skyfowl.md` · avg 4.8 (+0.2) · **best**

Biggest strength: the fletching fix landed — `:8` now reads "Near-black blunt
fletching blocks crop the field's lower-left corner", the word "chevron" is gone
from the entire prompt set, and the arrow merge remains an explicit, defended
canon trade ("twelve separate shafts would produce twelve sub-1 mm slivers at
75 mm … bold blunt notches at least 8 mm across", `:15`, `:27`). Biggest risk:
the talon still asks for "three bold toes biting" the bundle (`:8`) — claws are
pointed by nature and are not dimensioned the way the legs of Spider are — and
the warm-sand field is one of the three that depended on the border fix, now
correct. The light sand field (`#BFA37A`) is also the most exposed to the
corner-keying risk (§4.3).

### Four-Leaf Clover — `prompts/four-leaf-clover.md` · avg 4.8 (+0.2)

Biggest strength: the leaflets are "a rounded rectangle with a blunt rounded
outer end at least 6 mm across" (`:8`, `:20`), which removed the set's worst
taper count, and the canon read ("bare human foot treading on a group of
four-leaf clovers", `:25`) is literal; the mitten-foot guard (`:8`) pre-empts the
most likely model failure. Biggest risk: five four-leaf clovers at 75 mm is
still a lot of repeated geometry, and **no clover diameter is specified** — only
the leaflet floor — so if the model renders them small (a common behaviour for
repeated elements), leaflets drop toward `MIN_COMP_MM2 = 0.8`
(`vectorize.py:107`) and vanish. EF is re-assessed to 4 for that reason (the
prior review scored it 5 but itself ranked Clover third for defect likelihood);
the prompt text itself is well constructed, so PQ is 5.

### Back (9 skulls) — `prompts/back-nine-skulls.md` · avg 4.2 (0.0) · **weakest**

Biggest strength: it remains the only prompt that dimensioned every feature
(near skulls ~52 mm, sockets ~11 mm, far skulls ~28 mm, hub ~66 mm, keyline
~4 mm, arc ~24 mm, `:27`), the size is "190 x 190 mm … 10 mm under … 260 x 200
mm fit box" (`:26`), and the compound-rotation constraint is guarded (`:15-16`).
Biggest risk: the new shared config **contradicts this prompt's own Spec** — `:3`
and `:27` say the border is deep oxblood (`#5E1B1B`, "stitched as an oxblood
satin border"), but `:28` now prescribes `border_black.yaml`, and `force_black`
overrides the auto-pick to black. Verified: without the config this patch's
border auto-picks `(94,27,27)` = `#5E1B1B`; with it, `(0,0,0)`. PQ drops to 4
for that internal contradiction, which cancels the Pipeline gain and leaves the
average flat.

---

## 3. Overall score and plain verdict

**Overall: 4.49 / 5 (prior 4.31, Δ +0.18).**

The defect that dominated the previous round is gone. Every Pipeline line now
prescribes a mechanism that actually works, and I verified it end-to-end rather
than trusting the claim: `--config` is forwarded for raster input, `force_black`
emits `(0,0,0)`, and the control run reproduces the old failure (cream
auto-picked border; `--border-color` silently dropped). The two explicit taper
cleanups also landed and propagated to the combined index. The remaining issues
are structural (die-cut and repeated geometry), a handful of tolerated tapers,
and one new documentation contradiction on the dark-field Back patch where the
shared black config overrides a border colour the Spec still calls oxblood. Net:
a real, measured improvement, now bounded by art risks rather than a broken
pipeline.

---

## 4. Set-wide findings

### 4.1 The border config works — verified empirically (the prior #1 defect is closed)

`--config` is a value flag (`run.sh:24`) and is **not** in the raster drop-list
(`run.sh:54-58`), so it is forwarded to `vectorize.py`. `vectorize.py:126` reads
`border.mode`, `:303` sets `force_black`, and `:350-351` sets the border colour
to `(0,0,0)`. The border still requires `has_transparency`
(`vectorize.py:301`), i.e. `--key-background`, which all 7 prompts pass. All
three controls behave as the fix claims:

```
# WITH the shared config
$ tools/digitize/run.sh --key-background --colors 3 --size-mm 40 \
    --config patch_descriptions/border_black.yaml --no-export dummy.png
  (flags: --colors 3 --size-mm 40 --config patch_descriptions/border_black.yaml)
  border: color (0,0,0) width 2.5 mm (1 path, 5 pts)          # <-- black, correct

# WITHOUT the config (the pre-fix behaviour)
  border: color (237,227,207) width 2.5 mm                    # <-- cream field = invisible

# WITH the old SVG-only flag (the prior review's broken remedy)
$ run.sh ... --border-color '#123456' ...
  (flags: --colors 3 --size-mm 40)                            # <-- flag dropped
  border: color (237,227,207)                                 # <-- still cream

# WITH the config but WITHOUT --key-background (no transparency)
  (no "border:" line at all)                                  # <-- border needs keying
```

So the light-field patches (Bomb, Skyfowl, Clover) and the indeterminate Spider
silhouette now get a visible dark border. **Caveat:** the config is applied to
all seven, but it was only *needed* on the light-field patches. See §4.2.

### 4.2 New finding — the shared black config overrides Back's oxblood border

`vectorize.py`'s raster config reads only `mode` and `thickness_mm` from the
`border` block (`:125-128`); there is **no `border.color` key**, so the only
config-controllable border colour on the raster path is black. For Back the
auto-pick was already correct and produced the oxblood the Spec promises:

```
# Back-like image (oxblood field), WITHOUT config:
  border: color (94,27,27) width 2.5 mm        # = #5E1B1B, the Spec's border
# Back-like image (oxblood field), WITH shared config:
  border: color (0,0,0) width 2.5 mm           # black, contradicts :3 and :27
```

The border is not snapped back to a palette colour because the nearest cluster
(`#2A0508`, the hub) is 43.0 away, above the 40.0 snap distance
(`vectorize.py:457-461`). Epicure (`#1A1A1A` field) and Peace (`#111111` field)
are unaffected in practice — black is indistinguishable from their near-black
fields, and Peace snaps back to `#111111` — but Back's stated design changes.
This is a documentation/consistency defect, not a stitch defect (a black satin
border still stitches cleanly).

### 4.3 Full-bleed fields can still be keyed out (unchanged, unverified risk)

`--key-background` auto-detects the background as the median of the four 8×8
corner blocks (`key_background.py:47-51`). A square field that reaches the frame
corners would be detected as *background* and keyed out. The prompts say "plain
white background" but none requires a white **margin**; no margin clause was
added this round. Circles (Epicure, Peace, Back) are safe because their corners
are white. Not measured against a real render.

### 4.4 Only the darkest fill is satinized

Unchanged and not a defect: `vectorize.py:498` picks the single darkest fill as
the outline and satinizes only segments ≤ `SATIN_MAX_MM = 2.5` (`:104`). On
Back-nine the darkest fill is the 66 mm hub, so the ~4 mm keyline rings stay
fills, matching the Spec's "no thin satins" claim (`back-nine-skulls.md:27`).

---

## 5. Top 3 strengths (now)

1. **The border fix is verified, not asserted.** I reproduced the failure and
   the fix on synthetic images (§4.1): the old `--border-color` route is dropped
   and yields an invisible field-coloured border, while
   `--config border_black.yaml` yields `(0,0,0)`. The prior round's single
   highest-probability real defect is closed for the patches that needed it
   (`bomb.md:28`, `skyfowl.md:28`, `four-leaf-clover.md:28`,
   `reaper-spider.md:30`).
2. **The two explicit taper cleanups landed and propagated.** Epicure's anatomy
   is blunt (`midnight-epicure.md:8` ≡ `nano_banana_prompts.md:82`) and
   Skyfowl's fletching is blocks (`skyfowl.md:8` ≡ `nano_banana_prompts.md:178`);
   there are **zero** "chevron" or "pointed beard" strings left in the set. The
   combined index matches the per-patch files for all 7 (7 prompts, 7 follow-up
   sections, 7 Pipeline lines).
3. **The load-bearing thin features are dimensioned in millimetres.** Bomb's
   fuse ≥5 mm / lobes ≥15 mm / notches ≥4 mm, Spider's legs and gaps ≥6 mm,
   Skyfowl's notches ≥8 mm, Clover's leaflets ≥6 mm, Back's full inventory. The
   prior round's "the load-bearing features are the ones left as adjectives" is
   largely answered.

---

## 6. Top 3 risks (now)

1. **Repeated and die-cut geometry is the structural weak spot.** Spider's eight
   6 mm legs on a 70 mm die-cut outline (`reaper-spider.md:8`) and Clover's five
   four-leaf clovers (`four-leaf-clover.md:8`) are the two places where a small
   rendering choice crosses `MIN_COMP_MM2 = 0.8` (`vectorize.py:107`) or the
   border inscribed-radius gate (`vectorize.py:343`) and silently drops or
   de-borders a feature. Neither has a specified overall size floor.
2. **Residual tapers in tolerated shapes.** Six of seven prompts carry a
   crescent; Skyfowl still asks for "three bold toes biting" and Epicure for a
   "narrow" beard and "sweeping" horns. The blunt-end ban helps, but these are
   wording fights the model can lose, and the crescent clause proposed last
   round was never added.
3. **Full-bleed fields vs corner-block background keying.** No white-margin
   clause was added (§4.3), so a square field (Bomb, Skyfowl, Clover) that
   bleeds to the frame edge risks being keyed out entirely. Unverified against a
   real render but cheap to guard.

---

## 7. Recommendations (exact wording)

### 7.1 Resolve Back's border-colour contradiction (highest priority)

Either drop the config from `back-nine-skulls.md:28` so the auto-pick keeps the
oxblood the Spec promises, or update the Spec to match the black border. The
raster config cannot set an arbitrary colour (§4.2), so an oxblood border can
only come from the auto-pick.

- Option A (keep the prompt's design): in `back-nine-skulls.md:28`, change
  `--config patch_descriptions/border_black.yaml` → omit it, and keep the
  sentence "the disc's edge doubles as the set's dark keyline, stitched as an
  oxblood satin border" (`:27`).
- Option B (keep the black border): change `back-nine-skulls.md:3`
  "#5E1B1B - deep oxblood (field, keyline, sockets, border)" →
  "#5E1B1B - deep oxblood (field, keyline, sockets)", and `:27` "stitched as an
  oxblood satin border" → "stitched as a black satin border".

### 7.2 Add a white-margin clause to the three full-bleed square fields

Append to `bomb.md:8`, `skyfowl.md:8` and `four-leaf-clover.md:8`:

> "The field sits inside a clear plain-white margin at least 10 mm wide — it
> must not bleed to the frame edge."

This protects the corner-block background detection (`key_background.py:47-51`).

### 7.3 Quantify the tapers the ban still tolerates

- `midnight-epicure.md:8` — "a narrow blunt-ended beard at the lower-left edge,
  long drooping ears, thick horns sweeping to upper right" → "**a blunt beard at
  least 8 mm wide at the lower-left edge, long rounded ears, thick blunt-ended
  horns at least 10 mm wide along their length**".
- `skyfowl.md:8` — "three bold toes biting one thick near-black arrow bundle" →
  "**three bold rounded talon toes, each at least 8 mm across, biting one thick
  near-black arrow bundle**".
- `four-leaf-clover.md:8` — after "at least 6 mm across — no pointed leaf tips",
  add "**each whole clover at least 18 mm across**".
- Add one crescent clause to the six crescent-bearing prompts (`bomb.md:10`,
  `midnight-epicure.md:10`, `reaper-spider.md:10`, `skyfowl.md:10`,
  `four-leaf-clover.md:10`, `back-nine-skulls.md:10`): "**Crescent highlights are
  thick blunt bands with rounded ends at least 6 mm wide — not thin pointed
  slivers.**"

### 7.4 Correct the carve figure where it is stated

`peace.md:8`, `:17`, `:26`, `:28` say the border "eats the outer 3.5 mm". That
is the native-SVG carve; the raster carve is up to 2.5 mm
(`vectorize.py:369-375`). `reaper-spider.md:29` already uses the correct 2.5 mm.
Change the Peace figure to "**up to 3.5 mm**" (the conservative number keeps the
6 mm margin safe either way).

---

## 8. Fixes verified / not verified

| Fix | Status | Evidence |
|---|---|---|
| **Border config fix** (`border_black.yaml` + `--config` in all 7 Pipeline lines) | **VERIFIED** | `--config` is a value flag (`run.sh:24`) and is not in the raster drop-list (`run.sh:54-58`) → forwarded. `vectorize.py:126` reads `mode`; `:303` sets `force_black`; `:350-351` sets `(0,0,0)`. Empirical: `border: color (0,0,0)`. Controls: no config → cream `(237,227,207)`; old `--border-color` → dropped, still cream. Requires `--key-background` (`vectorize.py:301`), present in all 7. **Caveat:** the config is applied to all 7 but overrides Back's already-correct oxblood auto-pick to black, contradicting `back-nine-skulls.md:3`/`:27` (§4.2). |
| **Epicure blunt-anatomy fix** | **VERIFIED** | `midnight-epicure.md:8` now "a narrow blunt-ended beard at the lower-left edge, long drooping ears"; no "pointed" remains in the file. `nano_banana_prompts.md:82` matches. **Residual:** "narrow" is unquantified; horns still "sweep" (tip clipped by the edge). |
| **Skyfowl fletching fix** | **VERIFIED** | `skyfowl.md:8` now "Near-black blunt fletching blocks"; `nano_banana_prompts.md:178` matches; zero "chevron" occurrences in the whole set. **Residual:** the talon/toes and the crescent remain the taper risks. |
| **Pipeline command runnable for raster input** | **VERIFIED at the digitize stage** | Ran `tools/digitize/run.sh --key-background --colors 3 --size-mm 40 --config patch_descriptions/border_black.yaml --no-export /tmp/opencode/dummy.png` → exit 0, flags forwarded, black border, SVG written. Path is repo-relative (run.sh:37 `cd "$ROOT"`), so `patch_descriptions/border_black.yaml` resolves. **Not verified:** the full VP3 export (needs Ink/Stitch; not run) and any real Nano Banana render (none exists in `input/`). The `<image>` placeholder must be substituted by the operator. |
| **Crescent tapers** | **Not fixed — accepted residual** | Deliberate operator decision; 6/7 prompts still carry a crescent and the proposed blunt-band clause was not added (§1.2, §7.3). |
| **White-margin guard (§4.3)** | **Not applied** | No prompt gained a white-margin clause; the full-bleed keying risk remains open. |

---

## 9. Ranked: likelihood of producing a stitch defect

Defect = dropped/merged feature, unstitched hole ≥ 1 mm², or an unusable/wrong
border. Ranked worst-first. The border defect that dominated the prior ranking
is now fixed, so this list is driven by geometry.

1. **Reaper Spider** — the most complex silhouette; eight appendages whose
   satin edge depends on the model honouring 6 mm. Any thinner leg falls under
   the inscribed-radius gate (`vectorize.py:343`) and gets no satin edge;
   inter-leg gaps can close. The border colour is now correct.
2. **Four-Leaf Clover** — five repeated four-leaf clovers at 75 mm with no
   specified clover diameter; if they render small, leaflets approach
   `MIN_COMP_MM2 = 0.8` (`vectorize.py:107`) and drop. Border now correct.
3. **Bomb** — the curvy rope fuse can pinch below 5 mm at a bend, and the
   4 mm lobe notches are the tightest fill feature in the set. Border now
   correct; no longer #1 as in the prior round.
4. **Skyfowl** — well-guarded and dimensioned, but the talon toes and crescent
   are unquantified tapers, and the light sand field is exposed to the
   full-bleed keying risk (§4.3). Border now correct.
5. **Midnight Epicure** — the "narrow" beard and sweeping horns are the residual
   taper risks; the low-contrast grey/bone pair survives only if the ≥2 mm
   keyline is obeyed. Border is black, matching its near-black field.
6. **Peace** — the hole-based symbol is clean at ~5 mm strokes and 1 thread; the
   failure mode (symbol merging with white) is guarded by the 6 mm margin
   (`peace.md:8`) and the hairline follow-up (`:17`). Border correct.
7. **Back (9 skulls)** — every feature dimensioned, 190 mm inside the 200 mm fit
   box, compound rotation guarded. Its only new issue is cosmetic (black border
   vs the Spec's oxblood, §4.2), not a stitch defect. Lowest defect likelihood.

---

## 10. Unverified

- No prompt was executed against Nano Banana; no image was digitized. All claims
  about model behaviour (claws rendering pointed, clovers rendering small, legs
  rendering thin) are inferences from wording.
- The full `run.sh` VP3 export path was not exercised (requires Ink/Stitch); only
  the digitize stage was run, with `--no-export`.
- The `--border-color` / `--config` findings were verified on synthetic images
  (a light square and an oxblood circle), not on real patch PNGs; the code path
  is image-independent (`run.sh:48-64`, `vectorize.py:47-48`, `:301-356`).
- The white-margin keying risk (§4.3) is reasoned from
  `key_background.py:47-51` and RGB distances; it was not tested on a real
  render.
- ΔE76 values for Epicure grey/bone and Back's oxbloods are computed, not
  measured on thread; no repo source sets an intra-patch contrast threshold.
- Whether a 6 mm leg, a 6 mm leaflet or an 8 mm talon toe survives a real render
  is not measured; the gates (`vectorize.py:107`, `:343`) are read from source.
