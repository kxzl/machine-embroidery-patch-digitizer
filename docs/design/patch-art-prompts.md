# Patch art prompts: design contract

Status: CONFIRMED by the operator on 2026-10-10. Progress:
- G0 (route): web UI first (D12 amended). The Firefox MCP tools are NOT in this
  session's tool list (checked 2026-10-10 with a tool search). The operator must
  restart or resume the session so they load, and log in to Google by hand in the
  controlled Firefox window. I never read or ask for credentials or cookies. The
  API key is needed only for the fallback.
- G1 (spike): ran. Results in section 6. Operator verdict 2026-10-10: likes the
  gradient look in the preview and wants gradient stitching ("it looks so cool").
  D1 stands. A sewn test of the spike is still the only proof of how it reads in
  thread (the render is not thread). The raster pipeline cannot emit gradients yet
  (follow-up D11).
- G2 (canon): done, see `docs/design/patch-canon-check.md`. Bomb decision recorded
  in section 3.
- Session restarted 2026-10-10: the Firefox MCP tools are now available (deferred,
  loaded by tool search). Not yet used.
- G3: eight prompts drafted 2026-10-10 in `patch_descriptions/prompts/` (earth, peace,
  reaper-spider, skyfowl, four-leaf-clover, midnight-epicure, bomb, book-burner),
  old files removed as the operator confirmed. Gradient clauses are marked
  `GRADIENT:` with a `## Gradient swap` section for the tonal fallback. Mechanical
  checks passed (parser, colour counts, no em-dashes) and a DeepSeek review found two
  real issues (Earth atmosphere ring keyline, Epicure colour wording), both fixed.
  WAITING for the operator to read the prompts.
- T0 (2026-10-10, operator skipped the prompt read and asked for images instead):
  PASSED on the web route. Signed-out Gemini cannot send a prompt, so the operator
  signed in by hand (a Work account with Pro, noted for the terms risk in D12; the
  cookie dialog in the controlled Firefox profile was answered "Reject all"). Skyfowl
  prompt gave a 2048 x 2048 JPG, white margin about 9 percent, all four corners pure
  white, no visible watermark. Daily limit: no message seen after 2 generations.
- Detail-limit test (section 9): FAILED. Skyfowl image 1 keylines: median 0.52 mm,
  77 percent of line length under the 1.2 mm limit the prompt asked for. A
  redraw request ("three times thicker") moved the median only to 0.64 mm. The
  percentage-of-width wording is not honoured. Colour count also not honoured: 402
  quantised colours, soft shading in fletching and feathers.
- Pipeline on the images (75 mm, `--colors 7`): `output_vp3/skyfowl_web_1.vp3`
  (30,927 stitches, 6 colour changes) collapses feathers and talons into black masses.
  Thickening the keylines first made it worse. `output_vp3/skyfowl_web_2.vp3`
  (28,326 stitches) keeps readable feather scallops but the talons and fletching are
  still black masses. Flame is banded (no gradient emit yet).
- Peace (web 2026-10-10): image 2752 x 1536 (16:9, NOT square: the web UI does not
  enforce the aspect ratio, add "square 1:1 image" to prompts; the pipeline works
  from the artwork bounding box so it does not matter for stitching). Light strokes
  median 4.7 mm, 3 percent of length under 1.2 mm: detail limit honoured (bold subject).
  Pipeline at 60 mm, 3 pinned threads: `output_vp3/peace_web_1.vp3`, 9,034 stitches,
  reads well (stencil bridges, grey ghost shadow kept).
- Peace v2 (operator chose the "middle" version, web 2026-10-10): 2048 x 2048, perfect
  disc (edge radius variation 0.09 percent), exact symbol, 5 chips (asked for 2 or 3),
  grey slip shadow, no watermark. Pipeline: `output_vp3/peace_web_2.vp3`, 9,802
  stitches, 69 trims, packing 69 points (OK). BUG FOUND on the way: `key_background.py`
  keys by colour distance from the background, so the off-white symbol (about 33
  from the white margin) came out 99 percent semi-transparent (19.84 percent
  feathered), giving 23,139 stitches, 364 points per 1.5 mm and 171 mm of thread in a
  1 mm cell. Fix: new opt-in `--keep-enclosed` (only background connected to the image
  edge becomes transparent), passed through by `run.sh`; default unchanged and
  byte-identical on the 3 `regress.sh` designs; with the flag Book Burner and Goat
  change (pale interiors stay opaque), so the default stays off until the operator
  rebaselines. 4 tests, mutation-checked. Use `--keep-enclosed` for any prompt with
  off-white or cream parts near the margin colour.
- Bomb (web 2026-10-10): 2048 x 2048, a real pixel grid (cells about 51 px, about 2.6
  mm at 90 mm). Misses: no iron band or rivets (drew a diagonal seam), more greys than
  the six asked for, and "white field" is indistinguishable from the white margin so
  background keying removes it (die-cut sprite, no square patch). Pipeline: with the
  default border the 2.5 mm black satin border swallows the one-cell fuse; use
  `--no-border --no-satin-outlines` (config `patch_descriptions/bomb_web.yaml`):
  `output_vp3/bomb_web_1_noborder.vp3`, 13,304 stitches, fuse and spark intact.
  A finishing edge is then the sprite's own black outline, not a satin border.
- Jam check (Haiku subagent, branch `feat/jam-check` 839532a on top of gradient-fill,
  10 tests): `tools/digitize/qa/jam_check.py` checks needle packing, thread per 1 mm
  cell and trim clusters, and run.sh prints it. Finding: detailed designs have about 470
  trims and clusters of 25 to 28 cuts within 6 mm (Skyfowl at 120 mm), flat and
  gradient versions alike, so gradients are not the cause. `--trim-mm 8` gives 318
  trims (cluster 14), `--trim-mm 12` gives 288 (cluster 12), with a longer exposed
  jump as the price. Thread per cell exceeds 20 mm on 6 of 9 reference VP3s, so that
  threshold flags most designs and is uncalibrated.
- Thin-line fix, outline order, minimum jump: DONE 2026-10-10 and landed on
  `review-round-1` (merges aad46c2 and cefb58f, local, nothing pushed), all opt-in
  YAML keys, default output byte-identical. The sandbox classifier refused an
  autonomous DeepSeek agent the first time; a retry later launched (the operator said
  it is not blocked), and DeepSeek wrote the USAGE.md section. Operator reported the
  Skyfowl black overlap broke thread and needles and the machine stopped constantly.
  Measured causes: 329 trims in the black block alone (one per outline satin, plus
  exposed jumps in the last layer), lock stitches near trims (about 28 percent of the
  dense points), and hairline outlines widened to 1.2 mm satins that pile up at
  junctions (up to 5 layers at one spot). Result on Skyfowl image 2 at 120 mm
  (`output_vp3/skyfowl_web_2_120_safe.vp3`, config `patch_descriptions/skyfowl_safe.yaml`
  plus `outline_order: endpoint` and `trim.min_mm: 3`): trims 469 to 188, worst trim
  cluster 28 to 7 cuts, peak needle packing 157 to 122 points (inside the 140 limit),
  colour changes 13 to 10 with all flame regions as gradients. Thread per cell peaks
  at 21.5 mm (limit 20), still borderline. NOT sewn yet.
- G4, G5: not started. 5 web generations logged in `input/nano_banana/web_log.md`.

Implementation, subagents and later sessions work from this file, not from memory of
the interview.

Vocabulary: `GLOSSARY.md` (new terms: Style family, Tonal step, Gradient region,
Detail limit, Thread budget, Candidate).

## 1. Problem

The seven Nano Banana prompts in `patch_descriptions/prompts/` all follow
`BOLD_STYLE_BRIEF.md`: flat colours only, at most 6 threads, "no gradients, no
shading", one heavy near-black keyline on every shape, every feature at least 8 mm,
every tip at least 3 mm. Result (6 of 6 generated PNGs viewed): the images read as
one sticker pack. The operator finds them childish, and on being asked picked one
cause: **rounded, simplified shapes** (toy proportions). Keylines and saturated
colour were not picked, so they are not banned.

The operator wants: variety of look across the set (gritty, detailed, truly
cartoon, pixel art), shading and blending, more detail than the old rules allow,
and everything still easy to embroider, with the code removing fine spots.

## 2. Decisions

| # | Decision | Choice | Why |
|---|---|---|---|
| D1 | How shading is expressed | True gradient blends (Ink/Stitch linear gradient fill), plus Tonal steps where gradients do not apply | Operator's choice. Tonal steps alone were the recommended, lower-risk option. |
| D2 | Order of work | Spike first, then prompts | Gradient output is unverified in our pipeline. One hand-made SVG de-risks the choice. |
| D3 | Patches in scope | 8: Earth, Peace, Reaper Spider, Skyfowl, Four-Leaf Clover, Midnight Epicure, Bomb, Book Burner | Scavenger's Daughter stays on the artist's art (quality reference). The "Back (nine spinning skulls)" patch is dropped: operator says it is the same patch as Scavenger's Daughter. |
| D4 | Style per patch | One Style family each, fixed (section 3) | Guarantees all four looks appear in the set. |
| D5 | Detail limit | Line >= 1.2 mm and isolated spot >= ~2 mm at sewn size, written into each prompt as a share of patch width | Matches the pipeline's own cutoffs; scales with patch size. |
| D6 | Thread budget | 7 threads for 60 to 75 mm patches, 8 threads for 80 to 100 mm patches. Gradient stops and the border thread count. | Operator's own digitized samples run 7 threads at 100 mm and 10 at 200 mm. |
| D7 | Canon fidelity | Canon subject and canon colour anchors fixed. Style, angle, composition and extra detail free. | Recognisable to fans, room for variety. |
| D8 | Gradient families | Detailed and Cartoon only (Skyfowl, Earth, Book Burner, Reaper Spider, Clover). Gritty and Pixel use Tonal steps only. | Keylines give closed regions to fit. Rough ink and pixel stair-steps do not. |
| D9 | Cartoon meaning | Angular adult-animation / underground comix: sharp shapes, exaggerated expression, real construction. Not rounded mascots. | Operator dislikes rounded, simplified shapes but wants "truly cartoonish". |
| D10 | Pixel size | 3 mm cells, about 30 across on the 90 mm Bomb. Gritty roguelike sprite, no dithering. | Above the detail limit, clean stair-steps. Dithering would create dozens of separate 9 mm2 fills and many trims. |
| D11 | Gradient pipeline build | BUILT 2026-10-10 in worktree `.claude/worktrees/gradient-fill` (branch `feat/gradient-fill`, uncommitted): `tools/digitize/gradient.py` (fit), hooks in `vectorize.py`, `gradients:` YAML key (stops, `min_area_mm2` 20, `min_r2` 0.5, `row_spacing_mm` 0.3). 20 tests pass (mutation-checked). Default output byte-identical on the 3 `regress.sh` designs (SVG and VP3). Findings: gradient rows at 0.4 mm leave 2.9 % gaps, 0.3 mm leaves 0.05 %, so gradient regions default to 0.3 mm. Each gradient region adds one colour block per stop (3 regions = 9 blocks). The palette must be pinned to the prompt's palette, or the auto palette can merge two stops (seen on Skyfowl image 2). Original wording: out of scope here, separate follow-up contract after prompts are approved. | Needs its own design and is better aimed at real approved candidates. Until then gradient regions stitch as banded flat colours. |
| D12 | Experiments | AMENDED 2026-10-10 (operator, via a handoff from the session digitize-patches-c5, reconfirmed in this session): Gemini web UI through the `firefox-devtools` MCP first, free, ONE test image before any batch (T0, section 8). The API through `generate_images.py` (4 candidates per patch per round, 3 rounds, hard cap 96 images) is the fallback if the watermark, size, daily limit or login block the web route. The operator owns the account and terms risk of automating the consumer UI. | Real evidence per prompt. The old set was written blind and rejected. The web route costs nothing but the operator is near their usage limit, so steps stay small. |
| D16 | Helper model | `opencode run --model opencode/deepseek-v4.1-flash` (headless, from Bash) for bulk drafting and mechanical checks. The main session reviews its output. | Operator asked for it explicitly (AGENTS.md allows another model only on explicit request). Cheap model, so never trust its output unreviewed. |
| D13 | Research re-check | Claim-by-claim pass: each canon claim tagged verified (link) or unverified. Operator settles the rest. | The wiki blocks fetching (HTTP 402). |
| D14 | Prompt files | Overwrite `patch_descriptions/prompts/*.md` in place, no snapshot (operator's explicit choice, against the recommendation). | Old files are the rejected set. One-line reconfirmation immediately before the overwrite. |
| D15 | Review gates | Five gates, prompts read before any API spend (section 8). | Never pay for images from a prompt the operator has not read. |

## 3. Patch table

| Patch | Style family | Size (mm) | Shape | Threads | Min line | Min spot | Gradient regions | Canon anchor |
|---|---|---|---|---|---|---|---|---|
| Earth | Detailed | 60 | circle | 7 | 2.0% | 3.3% | ocean, atmosphere | planet, optional smoke plume |
| Peace | Gritty | 60 | circle | 7 | 2.0% | 3.3% | none | white peace symbol on black |
| Reaper Spider | Cartoon | 70 | die-cut | 7 | 1.7% | 2.9% | glow | merchant spider |
| Skyfowl | Detailed | 75 | square | 7 | 1.6% | 2.7% | flame | flaming arrows in an eagle claw |
| Four-Leaf Clover | Cartoon | 75 | rounded square | 7 | 1.6% | 2.7% | burst | clovers under a bare human foot |
| Midnight Epicure | Gritty | 80 | circle | 8 | 1.5% | 2.5% | none | grey goat head on black |
| Bomb | Pixel | 90 | square | 8 (6 expected) | 1.3% | 2.2% | none | white field, black and grey bomb (canon: black blackwork on white), one small orange fuse spark (an addition, not canon) |
| Book Burner | Detailed | 100 | square (assumption) | 8 | 1.2% | 2.0% | flame | book on fire |

Percentages are of patch width (1.2 mm line, 2 mm spot divided by size).

## 4. Pinned values

Every identifier used in code, config or prompts. No value outside this table gets
typed into code. Environment-specific values go in configuration.

| Item | Value | Status |
|---|---|---|
| Maximum patch size | 120 x 120 mm (operator, 2026-10-10: "bigger patches are acceptable"). Sizes in section 3 are defaults, not ceilings. A larger size widens every line by size/old size, so it helps the detail limit (Skyfowl image 2: keyline median 0.64 mm at 75 mm would be about 1.02 mm at 120 mm). Thread budget for 101 to 120 mm: 8 (not yet decided by the operator). | operator confirmed the ceiling; effect on sizes per patch still open |
| Hoop (fit box) | 260 x 200 mm | read from `HANDOFF.md:133` |
| Machine file format | VP3 (Husqvarna/Viking) | read from `docs/USAGE.md:5` |
| Needle count | single-needle, so each thread is a manual swap | ASSUMPTION, not verified |
| Image size and ratio | 2048 x 2048, 1:1, white margin reaching all four corners, no text, no drawn border ring | confirmed by operator |
| Image model | `gemini-3-pro-image` | operator confirmed; availability to be checked with `--list-models` at G0 |
| Key file | `~/.config/opencode/gemini_key`, mode 600 | operator confirmed; operator stores it, I never read it |
| Key lookup order in the script | `$GEMINI_API_KEY`, then `/tmp/opencode/gemini_key`, then `~/.config/opencode/gemini_key` | read from `generate_images.py:48-57`. The old `/tmp` file shadows the new one until deleted. |
| Spend cap | 96 images (8 patches x 4 x 3 rounds), every attempt counts including failures and safety blocks | derived |
| Price per image | about $0.134 at 1K or 2K, so a cap of about $13 | UNVERIFIED, secondary sources only |
| Candidate files | `input/nano_banana/<slug>_r<round>_<n>.png` | confirmed. Old `<slug>.png` files are never overwritten. |
| Prompt files | `patch_descriptions/prompts/<slug>.md`, structure `## Prompt` (fenced block) / `## Follow-up edits` / `## Spec` | the script parses `## Prompt` |
| Border config | `patch_descriptions/border_black.yaml` (`border.mode: force_black`) | read |
| Pipeline command | `tools/digitize/run.sh --key-background --colors N --size-mm S --config patch_descriptions/border_black.yaml <image>` with N and S from section 3 | read from the old prompt Spec lines |
| Speck cutoff | components under 0.8 mm2 dropped, holes under 0.2 mm2 filled | read from `vectorize.py:67-68` |
| Satin gate | satin under 1.0 mm not stitched, outline runs widened to 1.2 mm | read from `vectorize.py:62-63` |
| Contour simplification | 0.25 mm | read from `vectorize.py:71` |
| Colour palette flag | `--colors N` is an upper bound for the automatic palette | read from `docs/USAGE.md:71` |
| Glossary | `GLOSSARY.md` (the repo has no `CONTEXT.md`) | |
| This contract | `docs/design/patch-art-prompts.md` | tracked |
| Prompt folder tracking | `patch_descriptions/` is gitignored (commit a795612), so prompts are not committed | operator decides at G5 |

## 5. Prompt-writing rules (derived from the decisions)

1. Positive construction wording: angular forms, believable proportions, real
   anatomy (leg joints, toes, feather planes), sharp tapering tips. Do not carry
   over the old 8 mm shape minimum, the 3 mm blunt-tip rule, merged arrow bundles
   or the 6-colour and no-gradient rules.
2. State limits as shares of patch width (section 3), never as millimetres. The
   model sees pixels. Wording to be tested in round 1.
3. Name the Style family in plain words, no artist names. Detailed: trad tattoo
   flash and engraving. Gritty: linocut, screenprint, hand-cut stencil, ink wear.
   Cartoon: underground comix, angular, ink and flat colour. Pixel: gritty
   roguelike sprite, 3 mm cells, no dithering.
4. Gradient regions (Detailed and Cartoon only): smooth blend in one straight
   direction, inside a closed keyline-bounded region, between 2 or 3 colours that
   are already used elsewhere in the palette.
5. Tonal steps: 3 or 4 hard-edged tones per colour family, no soft airbrush.
6. Keep: canon anchor, white margin to all four corners, no text, no drawn border
   ring (the pipeline adds the satin border), square 1:1 composition.
7. Every prompt file keeps the three-section structure the script parses, and its
   Spec records size, threads, limits and the pipeline command from section 4.

## 6. Edge cases and resolutions

| Edge | Resolution |
|---|---|
| Smallest patches (60 mm) need a 2.0% line | Fixed by the size-scaled limit. Earth and Peace carry the least detail. |
| Peace is canon two-colour but budget is 7 | The budget is a cap, not a target. Peace is expected to use 2 or 3 threads. |
| Gradient stops add colour changes on a single-needle machine | Gradient stops reuse palette colours. Report unique threads and colour changes separately for each candidate. |
| A gradient needs a minimum ramp length to show | Measured in the spike (G1). Result sets a minimum region size, written into section 5 before prompts are finalised. |
| Pixel art from Nano Banana is often on an irregular grid | Regularity check on the first Bomb candidate. If irregular, add a pixel-snap step (shrink to grid, enlarge without smoothing) before the pipeline. This is the only possible pipeline change in this contract. |
| Round 1 cannot show real gradients | Candidates are judged on look and on the banded fallback stitch plan. True gradient stitch verification belongs to the follow-up contract (D11). |
| Safety filters may block prompts (skulls, "satanic" goat) | A blocked or failed call still counts toward the cap. If any call is blocked, stop and report. |
| Spend cap reached mid-round | Stop and ask. No further calls. |
| Old `<slug>.png` images vs new candidates | Different filenames, no overwrite. |
| Two Gritty patches (Epicure, Peace) are both black-ground | Accepted. They differ in technique (linocut goat, hand-cut stencil symbol). Revisit at G4 if they look alike. |
| Spike fails | Gradients are dropped for all patches. Detailed and Cartoon fall back to Tonal steps. Prompt rules 4 and 5 are rewritten. |
| Spike result (G1, measured on `work/gradient_spike/gradient_spike.vp3`) | Ink/Stitch gradient fill runs headless through our setup with no errors: 3,761 stitches, 9 colour blocks, 8 colour changes for 3 gradient shapes plus 1 flat control. Each gradient region emits one block per stop colour, and blocks are not merged across regions, so every gradient region adds colour changes on a single-needle machine. The blend is interleaved rows: the coverage render shows visible stripes (about 14 in a 20 mm 2-stop ramp). The render draws rows at 0.5 mm and probably overstates the banding. Whether it reads as a blend at arm's length is UNVERIFIED until the file is sewn. Tentative minimum ramp length about 15 to 20 mm (one test, not a rule). |
| Bomb canon colours | Canon is black blackwork on white. Bomb uses a white field with a black and grey pixel bomb and one small orange spark (operator confirmed). |

## 7. Changes to existing code

All edits are minimal diffs to files whose latest edits are not in git (the script
differs from the last tracked version), so no wholesale rewrite.

- `patch_descriptions/generate_images.py`: DONE 2026-10-10. Added `--round`,
  `--candidates` (files `<slug>_r<round>_<n>.png`; without `--round` the old
  `<slug>.png` scheme is unchanged), `--cap` (default 96) with a counter persisted
  in `input/nano_banana/spend.json` that counts every attempt, including failed and
  blocked ones and the no-imageConfig retry, and hard-stops at the cap. It prints
  which key source it used (never the value). Tests:
  `patch_descriptions/test_generate_images.py` (5 tests, fake HTTP, no key). Mutation
  check: with the cap check disabled, 3 of the 5 fail.
- Possible, conditional: a pixel-snap pre-step for the Bomb (section 6).
- Docs: `GLOSSARY.md` terms (done, uncommitted). Update `patches.md` with the canon
  table after G2.
- Not changed: the digitizing pipeline, Scavenger's Daughter, old PNGs.

## 8. Phases and review gates

| Gate | Work before it | Operator action |
|---|---|---|
| G0 | Web route: Firefox MCP tools loaded after a session restart, operator logged in by hand. API fallback only: operator stores the new key and says "done", then I run `generate_images.py --list-models` (free, names only) to confirm access and pin the model ID. One test call confirms the Pro model is usable on the account (counts toward the cap). | Store key, delete old `/tmp/opencode/gemini_key`. |
| G1 | Spike: one SVG with a 3-stop `linearGradient`, sewn at real size (75 to 90 mm), stitched by calling Ink/Stitch directly with `fill_method=linear_gradient_fill` (bypassing `svg_digitize.py`). Inspect the VP3 for the expected colour blocks. Render hairline and 0.5 mm coverage stitch plans. | View the stitch plan. Decide whether blends read well. |
| G2 | DONE. Canon table in `docs/design/patch-canon-check.md`. Findings: Bomb canon is black blackwork on white (operator chose canon base plus one orange spark); no separate nine-skull Back patch found; the hub lists 9 patches, not 10. | Settled. Still open, low priority: any patch missing from the hub list (Book 8 or 9), and whether Clover should stay in the set (Carl does not equip it). |
| G3 | Eight prompts written (after one-line reconfirmation of the overwrite). | Read all eight BEFORE any API spend. |
| T0 | Before round 1, after G3: ONE image through the web UI. Check (a) a visible watermark in any corner (breaks the white-margin rule), (b) image size in pixels, (c) any daily-limit or terms message, (d) whether login holds. Pass: no watermark in the margin, size at least 1024 px, no block. Fail on any: stop and fall back to the API. | Log in by hand if asked. |
| G4 | Round 1: 8 patches x 4 = 32 images (web UI free; API fallback about $4.3, unverified price). Number of web generations logged in `input/nano_banana/web_log.md`. Contact sheets. Best 1 or 2 per patch run through the real pipeline. Mechanical results reported. | Pick or reject per patch. Rounds 2 and 3 only for rejected patches. |
| G5 | Final prompt set and gradient-region spec per patch. | Decide on commit, on tracking `patch_descriptions/`, and on starting the gradient follow-up contract. |

Nothing is committed or pushed without the operator's say-so.

## 9. Verification plan

Mechanical checks per Candidate (computed, not eyeballed):

1. Pipeline runs end to end at the patch's `--colors` budget with no error.
2. Unique threads, including the border thread, are within the Thread budget.
   Colour changes are reported.
3. Speck and hole cleanup removes at most 2% of coloured area. The 2% is a guess.
   Round 1 records the real numbers and G4 resets the threshold from them.
4. White margin reaches all four corners and background keying succeeds.
5. No text in the image.

Human checks at G4: Style family recognisable, canon anchor present, does not feel
childish, stitch-plan crop looks right.

Falsifying tests (each fails if the claim is false):

| Claim | Test that would fail if it were false |
|---|---|
| Spend never exceeds the cap | Run the script with cap 2 on 3 prompts. The third call must be refused before any HTTP request. Failed calls must count. |
| Pipeline cleanup is the safety net for fine detail | Synthetic image with a 0.5 mm line and a 0.7 mm dot at sewn size. The dot must be dropped. The line must be widened to at least 1.2 mm or dropped. No satin under 1.0 mm may be emitted. |
| The model honours the Detail limit | Check 3 above on real candidates. A candidate with fine hatching exceeds the threshold and is rejected, which forces wording changes. |
| The Bomb is on a usable pixel grid | Cell-edge regularity check on the first Bomb candidate (threshold set after seeing round 1). An irregular grid triggers the pixel-snap step. |
| Gradient fill stitches in our headless run | The spike (G1). If the VP3 lacks the expected colour blocks, D1 is revisited. |

## 10. Evidence behind claims

- All 6 generated PNGs in `input/nano_banana/` and the 4 reference images in
  `input/` were viewed this session (6 of 6, 4 of 4).
- Four prompt files (back-nine-skulls, peace, reaper-spider, skyfowl), plus
  `nano_banana_prompts.md` and `generate_images.py`, differ from the last git
  version before untracking (checked with `diff -q` against `a795612^`, 6 of 12
  files differ). The other three prompt files and three documents match.
- Gradient fill exists in the vendored Ink/Stitch
  (`inkstitch/lib/stitches/linear_gradient_fill.py`, read, not yet run): it
  interleaves rows of neighbouring stop colours along one straight axis.
- Our pipeline emits flat fills only: no `gradient` match in `tools/digitize/*.py`,
  `tools/digitize/run.sh` or `docs/USAGE.md`.
- Canon: the wiki returns HTTP 402 to the fetch tool. A search showed the hub page
  listing Earth, Skyfowl, Bomb, Midnight Epicure, Peace, Scavenger's Daughter, Book
  Burner and Reaper Spider Minion as equipped and Four-Leaf Clover as not equipped
  by Carl, with floors for four patches (Skyfowl 6, Midnight Epicure 6, Peace 8,
  Clover 9). The Bomb description was not confirmed. This is search-snippet level
  evidence only.

## 11. Out of scope and follow-ups

- Gradient pipeline build (detect regions, fit, emit, test): new contract after G5.
- Scavenger's Daughter: stays as is.
- Four-Leaf Clover is not equipped by Carl in canon (search result). The operator
  still wants it in the set. Placement stays speculative.
- `patches.md` is stale on at least one point (it names Book 8 as latest; the wiki
  carries a Book 9 notice).
- Separate issue: `patch_descriptions/` is gitignored, so prompts and their review
  history are not versioned.

## 12. Assumptions still open

Single-needle machine; $0.134 per image; 2 mm minimum spot is a safety margin, not a
measured limit; 2% cleanup threshold is uncalibrated; Book Burner is square;
Earth's 60 mm size is inferred from the earlier digitized `earth.vp3` (60.5 x 60.4
mm); canon anchors are only partly re-verified; the model ID is unconfirmed until G0.
