# Travel under: design contract

Status: interview finished 2026-10-11 and the operator confirmed it. Everything below is built in the worktree and tested. Nothing is committed or pushed.

Research behind the choices: `docs/research/embroidery-community-practices.md` (copied onto this branch; the original is untracked in the main checkout). Terms: `GLOSSARY.md` (Fill region, Trim, Travel run, Cover).

## What and why

The machine cut the thread on every move between Fill regions of one colour. Each cut costs time and a thread tail, and each is a chance for a thread break. The community practice is a Travel run under later stitching. `tools/digitize/travel_vp3.py` does this on the finished VP3, before `trim_vp3.py`, for every Trim between two stitches of one colour block.

It works on the VP3 and not in `plan_trims()` because the file holds the real exit and entry points (Ink/Stitch picks them, so the planner's guess was wrong before, review.md 2.8), and one pass covers both digitizers.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | A Travel run replaces a Trim when a route exists under Cover. Otherwise the Trim stays. | Operator's request. A kept Trim is today's behaviour, so the fallback is safe. |
| 2 | Cover is dense stitching sewn after the Trim, in a thread not lighter than the run's thread by more than 15 L*. A single thread, a long travel stitch or a thin line is not Cover. | A dark run under a light fill shows. Operator chose this as the default. |
| 3 | Earlier dense stitching of the same colour may count as Cover only with `travel: surface: same_colour`. Default `later`. | Operator's choice. Unproven on fabric, so opt-in until sewn. |
| 4 | Run stays at least 0.5 mm inside the Cover (`margin_mm`). Run stitches may not come closer than `margin_mm - 0.15` to uncovered cells. | Research figure (inference), close to the 0.6 mm underlap. Costs 3 to 18 conversions per file against 0.3 mm. |
| 5 | Longest run 60 mm (`max_mm`). Run stitch 2.5 mm (`stitch_mm`). | Research budget (derived, no source). 2.5 mm is Ink/Stitch's own running stitch default. |
| 6 | A Trim whose real exit and entry are `trim.min_mm` or less apart (default 2) is removed with no run and no Cover needed. | Brings the real stitch points under the repo's existing never-cut rule. 3 mm is the queued tone-based follow-up. |
| 7 | On by default. Off with `run.sh --no-travel-under` or `travel: enabled: false`. | Operator's request is fewer cuts on every patch. |
| 8 | Ink/Stitch's lock stitches around a converted Trim stay in the file. | Stripping them risks the file for about 1% of stitches (estimate, not measured). Revisit if a swatch shows bumps. |
| 9 | No ADR. | Reversible by a flag, so it fails the "hard to reverse" test. |

## Pinned values

Nothing environment-specific goes into code beyond this table.

| Item | Value | Basis |
|---|---|---|
| Repo | `/home/roman/git/Digitize_patches` | session |
| Worktree | `/home/roman/git/Digitize_patches/.claude/worktrees/travel-under` | worktree skill output |
| Branch | `feat/travel-under` | worktree skill output |
| Base | `origin/master` at `ea82c5b` (contains all of `review-round-1`) | worktree skill output; `git rev-list` showed 0 commits only in review-round-1 |
| `travel.margin_mm` | 0.5 | decision 4 |
| `travel.max_mm` | 60 | decision 5 |
| `travel.stitch_mm` | 2.5 | decision 5; Ink/Stitch `stroke.py:173` |
| `travel.snap_mm` | 1.5 | built; connector from exit/entry to Cover |
| `travel.surface` | `later` (alt `same_colour`) | decisions 2 and 3 |
| `travel.enabled` | true | decision 7 |
| Short-hop floor | `trim.min_mm`, default 2.0 | decision 6; `vectorize.py` `TRIM_MIN_MM` |
| Raster cell | 0.2 mm | built |
| Drawn thread width | 0.4 mm | built |
| Longest stitch counted as Cover | 12 mm | built |
| Lightness tolerance | 15 L* | built |
| `trim_vp3.py` threshold | 8 mm (`run.sh`) | `run.sh`; every run stitch must stay well below it |
| Machine model | not confirmed | needed only by the follow-ups; ask when one starts |
| Thread brand/line | not confirmed | needed only by the thread-name follow-up; ask when it starts |

## Evidence behind each claim

Measured 2026-10-11 with the agreed defaults, on exports made with the pass off (`work/*.zip`, then `trim_vp3.py 8`).

| Claim | Check | Sample |
|---|---|---|
| Fewer cuts on the calibration Bomb | `bomb_web_2` through `run.sh` with and without `--no-travel-under` (command in the review pause below; the off run reproduces the 12,405 stitches and 46 trims of the recorded file) | Trims 46 to 16, stitches 12,406 to 12,469, 6 short hops dropped, 24 runs; jam check A 57 OK, B 16.7 to 17.2 OK, C 5 WARN to 2 OK; exposed travel 0 off and on |
| Fewer cuts on other designs | Same export with the pass off and on, both after `trim_vp3.py 8` | Trims: default-settings Bomb 318 to 182, Book Burner 158 to 82, Goat 93 to 38, Earth 41 to 4 |
| SVG-input path works | `Scavenger's Daughter Upgrade Patch2.vp3` (made by `svg_digitize.py`, rail-satin fans) through the pass and `trim_vp3.py 8` | No crash. Trims 68 to 24, stitches 66,297 to 66,390; 9 hops dropped, 6 of them between 1.5 and 2 mm (the SVG planner's own floor is 1.5); jam check unchanged (A 93 OK, B 41.0 WARN, C 3 to 2); exposed travel 1 off and 1 on (same move) |
| Short hops | Exit to entry at most 2 mm, trim removed | default-settings Bomb 86, Book Burner 38, Goat 28, Earth 7 |
| Runs | Trims turned into runs | default-settings Bomb 50, Book Burner 38, Goat 27, Earth 31 |
| Run points lie under later thread | k-d tree distance from every run sample to later sewn thread, 0.2 mm steps, independent of the raster | 1,003 (bomb_web_2) + 1,369 + 1,374 + 1,332 + 456 samples, 0 farther than 0.45 mm; longest run stitch 2.83 mm |
| No exposed travel added | `qa/travelmap.py --red-mm 4.5` | bomb_web_2, default-settings Bomb, Book Burner, Goat, Earth: 0 each, off and on. This number covers moves above 4.5 mm only; the dropped hops (at most 2 mm, sewn on the surface by decision 6) are below it and are not in the distance check either |
| No meaningful new hotspot | `qa/jam_check.py` off and on | Needle packing max 297 to 299, 125 to 126, 106 to 105, 72 to 72; thread per cell max 52.3 to 52.6, 26.9 to 27.0, 26.0 to 26.6, 21.3 to 21.3; trim cluster max 17 to 11, 12 to 6, 12 to 5, 5 to 1. The needle-packing warning on Bomb and the thread-per-cell warnings on all four exist with the pass off |
| Same-colour opt-in adds runs | dry runs with `--surface same_colour` | Runs 50 to 59 (Bomb), 38 to 52 (Book Burner), 27 to 41 (Goat) |
| Runtime | wall clock, 48,000-stitch file | 2.8 s default, 3.4 s with `same_colour` |
| Runs parallel to the Cover's rows | angle of each run stitch against nearby later stitches, within 20 degrees (earlier defaults, margin 0.3) | 12% of run length on Bomb, 13% on Book Burner, 2% on Goat (sample of 3 files) |
| Read-back is safe | pystitch write then read: only 2 block-start JUMPs move by 1 unit (0.1 mm) on Bomb; the pass restores the original file if its own read-back differs | 1 file |

Not checked, and not checkable off the machine: whether a run shows through a real fill on twill or vadmel, whether a run on its own colour shows (`same_colour`), and whether the leftover lock stitches make bumps.

## Built

1. Defaults: `margin_mm` 0.5, `max_mm` 60, `stitch_mm` 2.5.
2. Chord rule: a run stitch stays at least `margin_mm - 0.15` (0.35 mm) from uncovered cells on the grid.
3. Short hops: the Trim is removed when exit to entry is at most `trim.min_mm` (flag `--hop-mm`, default 2); reported on its own line.
4. `travel: surface: same_colour` and `--surface`: a forward sweep adds earlier stitching of the same colour block to the Cover mask.
5. 20 tests in `tools/digitize/tests/test_travel_vp3.py`; each new rule has a mutant that fails a named test (see below).
6. Docs: `docs/USAGE.md` (section Travel under, flag table, YAML), `README.md`, `docs/EMBROIDERY_QUALITY.md` section 7, `run.sh` header, `GLOSSARY.md`.

## Verification plan

Local, before anything is pushed:

1. `.venv/bin/python -m unittest discover -s tools/digitize/tests` passes.
2. Falsifying tests, each fails if its guarantee is false:
   - Lighter Cover keeps the Trim (fails if the lightness guard is removed; checked by mutation, `LIGHTER_TOL = 1000`).
   - A single travel-length thread is not Cover.
   - A 0.8 mm wide bar keeps the Trim at margin 0.5 and converts at 0.3 (fails if the margin is ignored).
   - Run stitches stay inside an L-shaped Cover with long stitches allowed (fails if the chord check is the old fixed 0.15 mm).
   - A hop of 2 mm or less is removed with no Cover; a hop of 2.2 mm without Cover keeps its Trim; `trim.min_mm: 3` in the config removes the 2.2 mm one.
   - `surface: later` keeps a Trim whose exit lies only on earlier same-colour satin; `surface: same_colour` converts it.
   - Untouched stitches keep their coordinates and order; a file with no eligible Trim is byte-identical.
   Mutation results, run 2026-10-11: removing the margin, the chord rule, the hop floor or the same-colour sweep each fails exactly the tests named above; the lightness guard was checked the same way earlier.
3. Real exports of `bomb_web_2` (the calibration Bomb), Book Burner, Goat, Earth and one SVG-input file: exposed travel 0, Trim counts before and after, `jam_check` before and after, the k-d tree distance check on every run. Done 2026-10-11, see the evidence table.
4. Overlay render of the runs on the Bomb stitch plan, shown to the operator.

Review pause: the operator looks at the render, the counts and the jam check. Only then `git push -u origin feat/travel-under`, on the operator's word. Merge to master after the operator sews the calibration Bomb twice and reports that no run shows and nothing breaks. The command, run from the worktree (each run overwrites `output_vp3/bomb_web_2.vp3`, so copy it away after each):

```bash
tools/digitize/run.sh --key-background --no-border --no-satin-outlines --size-mm 90 \
  --config patch_descriptions/bomb_web2.yaml input/nano_banana/web/bomb_web_2.jpg                      # pass on
tools/digitize/run.sh --no-travel-under --key-background --no-border --no-satin-outlines --size-mm 90 \
  --config patch_descriptions/bomb_web2.yaml input/nano_banana/web/bomb_web_2.jpg                      # pass off
```

Sew on a white fabric square (the sprite is die-cut, `docs/design/patch-art-prompts.md`). Look for a run showing through a fill, and note thread breaks and cuts. Nothing is committed before the operator asks.

## Edge cases walked

- Smallest: exit and entry within 2 mm. Removed with no run (decision 6).
- Zero distance: nothing to run; the Trim is removed.
- First and last record: a Trim at index 0, at the end, or before a colour change is the machine's and is left alone.
- Largest: 260 mm design, up to about 12 colour blocks. Memory is one 0.2 mm mask per block (about 1.7 MB each), about 2 s for 48,000 stitches.
- Margin against chord rule: the chord floor follows the margin, so a larger margin cannot be undone by corner cutting.
- Margin against `snap_mm`: the exit may lie 1.5 mm from allowed cells; the connector is the only exposed part of a run, at most 1.5 mm at each end, on the edge of the object just sewn.
- `max_mm` against `trim_vp3.py`: run stitches are 2.5 mm, far below the 8 mm threshold, so the safety net never recuts a run.
- Same-colour opt-in against the lightness guard: earlier stitching of the same block has the same lightness, so it passes.

## Follow-ups (separate tasks, none in this branch)

Queued by the operator: operator sheet next to each VP3; thread brand and number in the VP3 (needs the thread line and machine model); border satin underlay on by default (swatch and jam check first); 3 mm never-cut floor when thread and fabric tones are close.

Deferred, from the research: where the 13 to 18% of sewn segments under 0.5 mm come from; centre-out order within a colour; a check for runs parallel to the Cover's rows (single source, 12 to 13% of run length); stripping lock stitches around converted Trims.
