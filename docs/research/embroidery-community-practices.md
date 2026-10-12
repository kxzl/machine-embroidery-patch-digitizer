# Embroidery community practices: travel, longevity, quality, ease of use

Research date 2026-10-11. Scope: what manufacturers, software vendors and experienced digitizers recommend, compared with what this pipeline does today (`tools/digitize/vectorize.py`, `svg_digitize.py`, `run.sh`, `trim_vp3.py`, vendored Ink/Stitch at commit `d59c9ab1e`).

**Marks.** NEW: we do not do it. ALREADY: we do it. CONFLICTS: we do the opposite or a different value.

**Confidence.**
- Consensus: two or more independent primary sources agree (machine or software maker, Ink/Stitch, thread or needle maker).
- Primary: one primary document says it (a manual, a datasheet, Ink/Stitch docs or source).
- Common: several practitioner or vendor blogs agree. Digitizing-service blogs (PlixaLabs, SewFlow, HoopingStation, MaggieFrames, Custom Patch Factory, Sassy Digitizing) count here at most.
- Single source: one secondary page or one forum post.

**Method.** All web searches went through Kagi (37 searches). There was no WebSearch fallback. WebFetch failed DNS for inkstitch.org, so pages and PDFs were fetched with curl and read as text. Repo facts were checked in the code and on four recent VP3 files in `output_vp3/`.

**Machine model.** The repo says "Husqvarna/Viking, auto thread cutter" but names no model. The Designer Topaz 25 user's guide is used as the example manual. The Ruby, Diamond and Topaz manual snippets found in search say the same about jump stitch trim.

---

## 1. Do first

Ranked by (impact on quality or reliability) / (effort in this pipeline).

| # | Recommendation | Mark | Parameter | Source |
|---|---|---|---|---|
| 1 | Replace trims between same-colour objects with a sewn travel run hidden under later-sewn geometry. Trim only when no hidden path exists. (Being implemented now; spec in 2.6.) | CONFLICTS (today a move is cut when it is longer than 4 mm, or when its straight line touches area sewn earlier or not at all. Most moves between same-colour patches are over 4 mm, so they are cut even when fully hidden.) | Running stitch 1.5 to 2.5 mm. First and last travel stitch within 3 mm of the exit and entry points, so Ink/Stitch adds no lock stitches. Every travel stitch under 8 mm, or `trim_vp3.py` cuts it again. Do not run travel parallel to the covering fill's rows. | https://hatch.embroideryhelp.net/v3/en/OnlineHelp/Editing/edit_advanced/Automatic_connectors.htm , https://inkstitch.org/tutorials/routing/ , https://github.com/inkstitch/inkstitch/issues/622 |
| 2 | Turn on satin underlay for the patch border by default. | NEW for the default profile (ALREADY in `vadmel`) | Centre-walk for a 2 to 3 mm border; add contour (edge-walk) at 0.4 mm inset for wider borders. Check `jam_check` at hairpins and sew one swatch first. | https://docs.wilcom.com/embroiderystudio/26/en/OnlineHelp/Quality/underlays/Run_stitch_underlay_settings.htm , https://inkstitch.org/docs/stitches/satin-column/ |
| 3 | Write thread brand and catalog number into the VP3 by setting Ink/Stitch's `thread-palette` metadata. Verified on export: `bomb_web_2.svg` with this metadata gave VP3 threads such as `1800 Black, Madeira Polyneon` with RGB unchanged. | NEW (our VP3 threads carry only the hex as the name) | `<inkstitch:thread-palette>"Madeira Polyneon"</inkstitch:thread-palette>` inside `<metadata>` (the value is JSON, so keep the quotes). Use the operator's actual thread line. The nearest thread can differ visibly from the RGB, so print both on the operator sheet. | https://inkstitch.org/docs/thread-color/ ; vendored `lib/threads/catalog.py`, `lib/extensions/zip.py:69` |
| 4 | Write an operator sheet next to each VP3: colour sequence with thread name and number, stitches per block, trims, colour changes, estimated run time, bobbin metres, and a short preflight list (see 5.1). | NEW | Time = stitches / 650 spm + trims x 3 to 8 s + colour changes x (measured rethread time). Bobbin = 3 m per 1000 stitches. | https://inkstitch.org/docs/print-pdf/ , https://wilcom.com/resources/blog/high-impact-low-stitch-count-designs , https://www.madeira.co.uk/wp-content/uploads/2021/10/Stitch_Density_2021_v3.pdf |
| 5 | Raise the "never cut" floor to 3 mm for moves where the thread colour is close to the fabric colour. Keep 2 mm where they contrast (light thread on black vadmel). | CONFLICTS (fixed 2 mm today; the jam recipe already uses 3) | `trim.min_mm` 3 when thread and fabric are close in tone, 2 otherwise. | https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Automatic_trim_settings.htm , Hatch link in row 1 |
| 6 | Break down where the short stitches in our VP3s come from before choosing a minimum stitch length. 13 to 18 % of sewn segments are under 0.5 mm (measured, see 3.3). | NEW | Measure first. If plain fill or run stitches dominate, test `min_stitch_len_mm` 0.3 on a swatch (Ink/Stitch default 0.1; we write 0.1). | https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/quality/Eliminating_small_stitches.htm , https://inkstitch.org/docs/preferences/ |
| 7 | Within each colour layer, order components centre-out instead of starting from the carried needle position. | NEW | Sort by distance from the design centre, then keep nearest-neighbour inside rings. Medium effort, and it competes with travel length; test on the 260 mm designs first. | https://www.embird.net/studio/manual/0050digit.htm , https://www.custompatchfactory.com/guides/how-to-digitize-embroidery-patches-how-to-digitize-a-patch |

---

## 2. Travel and trims (topic 1)

### 2.1 What the Husqvarna machine does with trims

| Finding | Mark | Confidence | Source |
|---|---|---|---|
| With "Automatic Jump Stitch Trim" on (SET menu), the machine cuts at every trim command in the file and pulls the tail to the back. It also cuts after each colour change. Designs without trim commands are not cut. | context | primary (Husqvarna manuals; Ruby, Diamond and Topaz snippets agree) | Topaz 25 guide: https://svpworldwide.widen.net/content/jozhdb6ugy/original/DesignerTopaz25_EN.pdf |
| The manual says to turn the setting off "if the front and back of your embroidery will be visible" and cut by hand. | context | primary | Topaz 25 guide |
| The trigger (a cut on every move between same-colour patches) is our file asking for those cuts. The machine only executes them. | CONFLICTS | measured in code | `plan_trims()` in `vectorize.py`: a move is cut when longer than 4 mm, or when the straight line touches area sewn earlier or not at all. A second loop cuts every layer boundary over 2 mm, also when both layers share one thread. `svg_digitize.py` has its own planner (min 1.5 mm, threshold 4 mm, coverage tested against later objects' geometry). |
| Some machines trim by connector length themselves and ignore trim data. Husqvarna's manual describes command-driven trims only. | context | primary (Hatch help) | https://hatch.embroideryhelp.net/v3/en/OnlineHelp/Basics/view_designs/View_connectors.htm |
| Pfaff creative machines offer three modes: no thread cuts, automatic thread cut, and automatic thread cut plus automatic jump stitch trim. | context | single source (manual snippet only, not read in full) | https://svpworldwide.widen.net/content/bt5bmrtexo/pdf/471184526D-creative-elevate-680-full_web_en.pdf |
| Husqvarna's own editor has "Automatically Add Trim Commands" that adds trims "before most movement stitches in the visible stitch area". It also has "Break Up Stitches", which splits visible stitches above a maximum: range 2 to 12 mm, default 8 mm. | ALREADY (our 8 mm `trim_vp3.py` threshold and 7 mm border split fit this) | primary (vendor manual) | https://download.mysewnet.com/Education/MSW/120/PDF/mySewnetStitchEditor_RefGuide_Win120.pdf |
| VP3 has no jump command. pystitch skips Ink/Stitch's JUMP records and writes the move as one long stitch record (16-bit delta when over 12.7 mm). | ALREADY documented | primary (code) | `.venv/.../pystitch/Vp3Writer.py`; `docs/EMBROIDERY_QUALITY.md` section 7 |

### 2.2 What a trim costs

| Finding | Confidence | Source |
|---|---|---|
| A trim takes 3 to 4 s ("the machine slows to a stop, cuts, restarts with a few slow stitches"). | single source (Wilcom staff quote) | https://wilcom.com/resources/blog/high-impact-low-stitch-count-designs |
| A trim takes "around 8 seconds" to pause, trim and get back to full speed. | single source (Wilcom blog) | https://wilcom.com/resources/blog/on-screen-quality-assurance-tool-travel-toolbar |
| No machine maker publishes a trim time. | single source (one survey of Brother, Melco and Tajima manuals) | https://kitparlor.com/guides/embroidery-stitch-count-run-time/ |
| Wilcom offers a "no trims" mode, "useful if trimming causes your machine to slow down, or the needle to lose the thread". | primary (vendor docs) | https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Automatic_trim_settings.htm |
| Ink/Stitch: "Trims produce chaos on the backside of the embroidery and slow down the machine quite a bit." Do not hide jumps with trims. | primary (Ink/Stitch docs) | https://inkstitch.org/tutorials/routing/ , https://inkstitch.org/docs/commands/ |
| Home machines can unthread or leave tails on top after a trim. | single source each (anecdotes) | https://github.com/inkstitch/inkstitch/issues/612 (Eversewn, Janome), https://www.reddit.com/r/MachineEmbroidery/comments/16pakya/trim_slips/ |
| Trimmer knife wear: no source quantifies wear per trim. Vendor blogs list a dull or misaligned knife as the usual cause of failed cuts. | single source, weak | https://etcsupplies.com/blogs/help-centre/threads-are-not-trimming |

**Our numbers (measured on `output_vp3/`, time derived).** At 650 spm and 3 to 8 s per trim:

| File | Sewn segments | Trims | Stitching time | Trim stops |
|---|---|---|---|---|
| bookburner_web_1 | 32,557 | 167 | 50 min | 8 to 22 min |
| skyfowl_web_3_75_r03 | 22,512 | 91 | 35 min | 5 to 12 min |
| clover_web_3 | 18,874 | 83 | 29 min | 4 to 11 min |
| bomb_web_2 | 12,309 | 46 | 19 min | 2 to 6 min |

Each trim also adds a tie-off and a tie-in (Ink/Stitch default "half stitch" locks).

### 2.3 When to trim and when to travel

| Case | Community practice | Our pipeline | Mark | Confidence |
|---|---|---|---|---|
| Layer boundary with a colour change | The machine cuts anyway (Husqvarna manual). | Trims at every layer boundary over 2 mm. | ALREADY (harmless duplicate) | primary |
| Layer boundary without a colour change (darkest fills to outlines to border, all in one block with `border: force_black`) | No cut needed when the move can be hidden; the border sews last and covers a lot. | Always cut when over 2 mm (second loop in `plan_trims()`). | CONFLICTS; the travel code must cover these moves too | consensus (same rules as the next rows) |
| Gap under 3 mm | Do not trim. Hatch trims connectors of 3 mm or more by default. Wilcom: connectors under 3 mm "are not visible", except when the thread contrasts with the background. Ink/Stitch adds no locks under 3 mm. | Never cut under 2 mm. | CONFLICTS (mild; see Do first 5) | consensus |
| Connector hidden under a later object | Use a sewn travel run, no trim. Hatch: "if the connecting run is hidden beneath another object, it is more efficient to use a connecting run rather than a trim and tie-off." Wilcom, Embird and Ink/Stitch say the same. | Left uncut as one straight jump of 4 mm or less. Ink/Stitch puts a lock pair on both ends when it is over 3 mm. `trim_vp3.py` cuts it when it is over 8 mm. Longer hidden moves are cut. | CONFLICTS | consensus |
| Connector visible and over 3 mm | Tie off and trim. | Tie off and trim. | ALREADY | consensus |
| Inside one fill element (between sections) | Ink/Stitch underpath, on by default. | Default kept. | ALREADY | primary |

Sources: Hatch link in Do first 1; https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Types_of_connectors.htm ; https://www.embird.net/studio/manual/0050digit.htm ; https://inkstitch.org/docs/stroke-tools/ (Jump to Stroke).

### 2.4 Lock stitches (tie-in, tie-off)

| Finding | Mark | Confidence | Source |
|---|---|---|---|
| Ink/Stitch adds a tie-off on the earlier object and a tie-in on the later one at every colour change, every trim, and every same-colour gap longer than the minimum jump length (3 mm). It does this whether or not the gap is trimmed. | context; matters for the travel spec | primary (docs and code) | https://inkstitch.org/docs/stitches/lock-stitches/ ; `inkstitch/lib/stitch_plan/stitch_plan.py` lines 61-87 |
| Hatch inserts tie-ins when the previous connector exceeds a set length ("e.g. 2mm"). Tie-offs go before trims. | context | primary | https://hatch.embroideryhelp.net/v4/en/OnlineHelp/Digitizing/connectors/Automatic_tie-ins_tie-offs.htm |
| Wilcom/Hatch: on narrow columns and small lettering use one tie-off stitch. Stacked tie-offs ("method 2") risk thread breakage; on large areas use method 1. | ALREADY in part (fills under 2.5 mm² or 1 mm thin get `ties="3"`) | primary (Wilcom and Hatch share one help text) | Hatch link above; https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Automatic_tie-off_settings.htm |
| Embird: place the tie-in where later stitching hides it; keep the tie-off small and plain, because it sits on top. | NEW (we accept Ink/Stitch's default position) | primary (vendor manual) | https://www.embird.net/machine-embroidery-tutorials/studio-next/tieup.htm |
| Travel runs need no locks. Locks belong around cuts. | NEW rule for the travel code | consensus (derived from the tools above) | as above |

### 2.5 How the tools handle it automatically

| Tool | Behaviour | Source |
|---|---|---|
| Ink/Stitch | Underpath (travel inside the shape, before the rows that cover it) only inside one fill element. Between elements it makes a straight jump, with locks if over 3 mm, and cuts only on `trim_after` or a trim command. "Jump to Stroke" converts a jump into a straight running stitch that the user then moves under later stitching by hand. Auto-route satin, auto-route running stitch and Redwork route strokes. Underpath "avoids traveling in the same direction as the rows" so it stays hidden. | https://inkstitch.org/tutorials/routing/ , https://inkstitch.org/docs/stitches/fill-stitch/ , https://github.com/inkstitch/inkstitch/issues/622 (lexelby, Ink/Stitch founder) |
| Wilcom EmbroideryStudio | Default connector is a jump. Trims: off, always, or when the connector exceeds a set length. Travel runs connect segments inside objects and "are usually covered by fill stitches". Branching groups touching or overlapping objects so "overlapped segments will be hidden behind objects that are later in the stitch order", with one entry and one exit. Closest Join aligns exit and entry points. | https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Types_of_connectors.htm , https://docs.wilcom.com/embroiderystudio/27/en/OnlineHelp/Quality/connectors/connectors-20.htm , https://wilcom.com/resources/blog/branching , https://wilcom.com/resources/blog/minimizing-thread-trims-in-embroidery |
| Hatch | Automatic trims at 3 mm or more by default. Connecting runs can replace trims where hidden. | Hatch links in 2.3 |
| Embird Studio | Explicit "connection" objects (running stitch) placed where hidden under other objects. Rules: proper order, connections where hidden, correct start and end points. | https://www.embird.net/studio/manual/0050digit.htm |
| Embrilliance | Jumps "are normally trimmed by hand or machine". "Run when jumps are small" turns small jumps into run stitches when merging designs. | https://embrilliance.com/Help/Platform%20Mac%201170/jumpsremoveoverlaps.htm |
| mySewnet (Husqvarna) | Adds trims before visible movement stitches, splits visible stitches over 8 mm by default, and its Stitch Optimizer removes unnecessary short stitches. | mySewnet guide in 2.1 |

### 2.6 Spec for the travel implementation

Each line is tagged with its basis.

1. **Emit travel as its own running-stitch element** with `trim_after` false, in the same colour, between object A and object B. Use stitch length 1.5 to 2.5 mm. We pin 1.5 mm for fill underpath today; Ink/Stitch's running stitch default is 2.5 mm. [Ink/Stitch docs and source; Wilcom: travel run length can be raised to cut stitch count.]
2. **Start within 3 mm of A's last stitch and end within 3 mm of B's first stitch.** Then Ink/Stitch adds no tie-off or tie-in at either joint. Fill start and end points are chosen by Ink/Stitch near the previous and next element, so place the travel ends at the nearest points, or attach start and end commands. [`stitch_plan.py`; Ink/Stitch routing doc.]
3. **Keep every travel stitch under 8 mm.** `run.sh` always runs `trim_vp3.py ... 8` on the VP3, and it cuts any longer move that is not a satin fan. [Repo code.]
4. **Route only through area that a later object will cover.** Use the existing `stitch_index` raster (later index = covered later). Shrink the corridor by a safety margin so pull and registration error cannot expose the run. No source gives a number. 0.5 mm is suggested, close to our 0.6 mm underlap. [Inference. Wilcom says to adjust travel stitch length so runs "do not protrude from the cover stitching".]
5. **Do not travel parallel to the covering fill's rows.** A parallel run can show between rows. Prefer crossing at a large angle. [lexelby, Ink/Stitch issue 622.]
6. **Avoid open or light covers.** Underpath "will show" under a looser fill. Our layer order is light to dark, so a travel run usually lies under a darker, dense later layer. A light cover (white highlight on black) is the case to exclude. [lexelby, issue 622; colour show-through itself is inference.]
7. **Prefer covers that sew last.** In our order these are satin outlines, then the border. A run under the border band is covered by the densest, last layer. [Inference from Wilcom branching ("hidden behind objects later in the stitch order").]
8. **Trim only when no hidden path exists within a detour budget.** Detour budget, derived: a trim costs 3 to 8 s plus two locks. At 650 spm, 3 to 8 s is about 30 to 90 stitches. At 2 mm per stitch that is 60 to 180 mm of travel. Start with a 60 mm budget. [Derived from the Wilcom figures; no source gives a limit.]
9. **Do not reuse a corridor segment for a second travel run.** The border band and outline satins will attract many runs, and this repo has a pile-up history. Compare `qa/jam_check.py` before and after (warns above 20 mm thread per 1 mm cell and above 140 points within 1.5 mm). [Repo QA; inference.]
10. **Cover both trim planners.** `vectorize.py` (raster path) decides coverage on the `stitch_index` raster. `svg_digitize.py` (native SVG path) has its own planner: never cut under 1.5 mm, threshold 4 mm, coverage tested by point-in-polygon against later objects' geometry. Its union of later geometry can serve as the corridor there. [Repo code.]
11. **Handle same-colour layer boundaries.** With `border: force_black`, the darkest fills, the outlines and the border share one thread block. `plan_trims()` cuts every boundary between them over 2 mm. These moves are travel candidates too. [Repo code.]
12. **Verify on the exported VP3, not the SVG.** Per colour block, count: TRIM records; same-colour moves over 3 mm between groups (each one means a lock pair was added); untrimmed moves over 8 mm (must be 0 apart from satin fans); and exposed travel from `qa/travelmap.py` (must be 0). [Repo QA; EMBROIDERY_QUALITY section 10 lesson "measure the file that ships".]

### 2.7 Route planning ideas (inference)

- Corridor = union of everything sewn after A, eroded by the margin. Use the shortest path on the mask raster (A* or a distance transform), then simplify to stitches of at most 2.5 mm.
- Also count same-colour objects not yet sewn as corridor, as in Wilcom branching: travel inside B's own area before B is filled is covered by B.
- If no corridor exists, try re-ordering same-colour objects so the next one is reachable. Our nearest-neighbour order with a carried needle position (ALREADY) is the base. Closest-join of exit and entry points is the commercial equivalent.
- Ink/Stitch's edge-walk alternative (travel around a shape's border) can end up exposed when the fabric pulls (lexelby). Prefer interior corridors.

---

## 3. Machine and needle longevity (topic 2)

### 3.1 Needles

| Finding | Mark | Parameter | Confidence | Source |
|---|---|---|---|---|
| 40 wt polyester wants a 65/9 to 75/11 needle (Madeira chart). The Polyneon 40 datasheet says 60/8 to 75/11. | ALREADY (75/11) | 75/11 sharp | primary (thread maker) | https://www.madeirausa.com/_resources/common/userfiles/file/Quick%20Reference%20Needle%20Guide.pdf , https://www.madeira.co.uk/wp-content/uploads/2024/05/TDS_Polyneon40.pdf |
| Change the needle after about 8 hours of sewing, and at the start of a project. | NEW (operator sheet) | 8 h at 650 spm is about 310,000 stitches, about 10 patches of 30k (derived) | primary (needle maker) | https://www.schmetzneedles.com/blogs/blog/change-your-needle |
| Titanium-coated needles last 25 to 30 h. | NEW (option) | 25-30 h | single source (vendor product page) | https://oesd.com/organ-needles-titanium-sharp-7511/ |
| A damaged needle causes skipped stitches and thread breaks, and can damage the needle plate. Do not pull or push fabric while stitching: it deflects the needle. | operator | | primary (manual) | Topaz 25 guide |
| On felt and wool, step up to 80/12 if stitches skip. | ALREADY (in `work/review_artifacts/RESEARCH_vadmel.md`) | 75/11 to 80/12 | common | see that file |

### 3.2 Density, speed and machine load

| Finding | Mark | Parameter | Confidence | Source |
|---|---|---|---|---|
| Fill density for 40 wt: 0.40 mm. | ALREADY on the raster path; CONFLICTS on the SVG path (0.30 mm, chosen after a coverage test; see `docs/adr/0003`) | 0.40 mm | primary (thread maker) | https://www.madeira.co.uk/wp-content/uploads/2021/10/Stitch_Density_2021_v3.pdf |
| Do not fix gaps by raising density first. Check compensation and underlay. | ALREADY | | common | https://embroiderylegacy.com/embroidery-digitizing-problems-how-to-avoid/ |
| Safe speed for standard fabrics: about 600 to 700 spm. Slow down for lettering and small details. High speed deflects the needle because the frame moves before the needle is clear. | NEW (operator sheet) | 600-700 spm | common (experienced practitioner) | https://embroiderylegacy.com/how-to-set-embroidery-machine-speed/ |
| Commercial "optimum" is 700 to 800 spm. | context | | single source | Wilcom low stitch-count blog |
| The Topaz 25 has five embroidery speed levels. The manual says to lower the speed for metallic or specialty threads. | NEW (operator sheet) | | primary (manual) | Topaz 25 guide |

### 3.3 Short stitches

Wilcom: "Small stitches can damage fabric and cause thread or needle breakage." Its filter removes stitches below a set length. Husqvarna's Stitch Optimizer removes "unnecessary short stitches" by default. Ink/Stitch drops stitches below `min_stitch_len_mm` (default 0.1 mm) and suggests 0.3 mm for W6 machines. Ink/Stitch also warns that a higher minimum distorts small satins.

Measured on our files (all STITCH segments, trims and colour changes excluded):

| File | Under 0.3 mm | Under 0.5 mm |
|---|---|---|
| skyfowl_web_3_75_r03 | 5.3 % | 17.7 % |
| bomb_web_2 | 2.6 % | 15.4 % |
| bookburner_web_1 | 3.5 % | 13.9 % |
| clover_web_3 | 3.2 % | 13.2 % |

These counts include lock stitches, satin short-stitch insets and fill row ends, which are short by design. The breakdown by cause is not done. Mark: NEW. Confidence: consensus that short stitches are a risk; the threshold value is single source.

Sources: https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/quality/Eliminating_small_stitches.htm , mySewnet guide (Stitch Optimizer), https://inkstitch.org/docs/preferences/

### 3.4 Tension, bobbin, maintenance

| Finding | Mark | Parameter | Confidence | Source |
|---|---|---|---|---|
| Correct tension shows 1/3 bobbin thread and 2/3 top thread on the back. Test with a satin "H". | NEW (operator sheet) | 1/3 rule | primary (thread maker) | Madeira density guide; https://embroiderylegacy.com/how-to-set-embroidery-machine-speed/ |
| Use embroidery bobbin thread: it is fine and "will not build up under embroidery". | operator | | primary (manual) | Topaz 25 guide |
| Thread use: about 5 m top and 3 m bobbin per 1000 stitches. | NEW (operator sheet) | 30k-stitch patch: about 150 m top, 90 m bobbin | primary (thread maker) | Madeira density guide |
| Topaz: no oiling needed. Clean lint from the bobbin case area often. | operator | | primary (manual) | Topaz 25 guide |
| Each colour change on a single-needle machine is a stop and a manual rethread. | ALREADY (border merged into the darkest thread's block) | | primary (manual) | Topaz 25 guide |
| Dense pile-ups (stacked satins, ladders) break needles. | ALREADY (`qa/jam_check.py`, hotspot rules in ADR 0003) | | consensus | `docs/EMBROIDERY_QUALITY.md` section 4 |

### 3.5 Hooping and stabiliser for patches

| Finding | Mark | Confidence | Source |
|---|---|---|---|
| Stabiliser is always needed. Cut-away for unstable fabrics; tear-away for stable wovens. | ALREADY (operator uses stiff stabiliser) | primary (manual) | Topaz 25 guide |
| For patches, a sticky or firm tear-away stops the patch material creeping between colour changes. Twill fused to cut-away is a common alternative. | operator | common | https://www.custompatchfactory.com/guides/how-to-digitize-embroidery-patches-how-to-digitize-a-patch ; https://www.facebook.com/groups/3811085882465079/posts/4340358716204457/ (single post) |
| Felt and wool want a water-soluble topping so stitches do not sink. | ALREADY (vadmel research) | common | `work/review_artifacts/RESEARCH_vadmel.md` |
| Husqvarna machines have a FIX/baste function to baste fabric to stabiliser around the design. | NEW (operator sheet) | primary (manual) | Topaz 25 guide |

---

## 4. Quality (topic 3)

| Topic | Community practice | Our pipeline | Mark | Confidence | Source |
|---|---|---|---|---|---|
| Push-pull compensation | Widen satins and fills against pull. | Satin 0.2 mm per side; raster pull on fills; underlap at seams. | ALREADY | consensus | https://inkstitch.org/docs/stitches/fill-stitch/ ; `docs/USAGE.md` |
| Satin underlay | Centre run for 2 to 3 mm columns; edge run plus zigzag ("German") for wide columns. | Off on the default border and outlines; on in `vadmel`. | NEW (default) | consensus | Wilcom run underlay; https://inkstitch.org/docs/stitches/satin-column/ |
| Fill underlay | Tatami underlay at 90 degrees, wider rows. | Ink/Stitch default kept. | ALREADY | primary | Ink/Stitch fill docs |
| Sequence | Back to front, large to small, outlines last, border last. | Light to dark, fills, then outlines, then border. Light to dark matches back to front only when light areas are background. A white highlight on black is sewn first and gets covered. | ALREADY in part; CONFLICTS for light details on dark | common | https://www.plixalabs.com/learn/techniques/trims-and-stitch-sequencing ; Custom Patch Factory |
| Centre-out | "Digitize it from center out if possible, to prevent fabric puckering." | Nearest-neighbour from the carried needle position. | NEW | common (vendor manual plus patch maker) | Embird manual; Custom Patch Factory |
| Satin width | Satin from about 1 mm to 7 mm; split longer stitches. Husqvarna's editor splits visible stitches over 8 mm by default. | Gate 1 mm; border `max_stitch_length_mm` 7; satinize columns up to 4.5 mm. | ALREADY | consensus | `docs/EMBROIDERY_QUALITY.md` section 2; mySewnet guide |
| Fill angle | Keep one dominant angle per element. On big designs, alternate 30 to 45 degrees between neighbouring sections to cancel pull. | Raster path uses one angle (default 0, horizontal) for all fills; SVG path keeps authored angles or `angle_cycle`. | Open question (see 7) | single source each | Custom Patch Factory; https://www.veloradigitizing.com/blog/jacket-back-embroidery-digitizing-guide |
| Colour registration | Neighbouring areas overlap slightly. | Underlap 0.6 mm (raster), overlap carve 1.0 mm (SVG). | ALREADY | consensus | Embird manual; `docs/USAGE.md` |
| Border | Sews last. Edge-walk underlay. Overlaps the interior fills. Patch makers say "more patches fail at the border than everywhere else combined." | Last; overlaps via underlap; no underlay by default. | ALREADY / NEW (underlay) | common | Custom Patch Factory; https://sassydigitizing.com/blog/digitizing/custom-applique-digitizing-and-fabric-patches |
| Border density | Dense satin, 0.36 to 0.38 mm, on patch borders. | 0.4 default; 0.35 in `vadmel`; 0.3 on the authored border (SVG path). | ALREADY (in range) | single source | Sassy Digitizing |
| Corners | Short stitches on the inside of tight turns. | `short_stitch_inset` 20 on the border. | ALREADY | consensus | `docs/EMBROIDERY_QUALITY.md` section 5 |
| Thin lines and small text | Satin at 1 mm or more; thinner lines as running stitch. | `thin_lines: run`, satin gate. | ALREADY | consensus | `docs/USAGE.md` |
| Test sew-out | Never send an untested file. Test on the production twill and stabiliser. Change one variable per round. | `swatch.py` calibration; operator sews tests. | ALREADY | common | Custom Patch Factory |

---

## 5. Ease of use (topic 4)

### 5.1 Preflight list operators use

From the Husqvarna manual and a Husqvarna-focused checklist (https://quiltsocial.com/9-check-list-items-for-successful-machine-embroidery-before-you-press/), plus the needle and tension items above:

1. Correct hoop selected; fabric and stabiliser hooped tight; design fits (our `qa/fit_check.py`).
2. "Automatic Jump Stitch Trim" on. Our files rely on it.
3. Embroidery bobbin thread in the bobbin, enough metres for the design.
4. Needle under about 8 hours of use, 75/11 sharp.
5. First colour threaded; speed level set (slower for small detail).
6. Optional: baste with the machine's FIX function.

Mark: NEW (as a printed sheet). Confidence: primary for items 1 to 4 (Husqvarna manual, Schmetz).

### 5.2 Findings

| Finding | Mark | Confidence | Source |
|---|---|---|---|
| Ink/Stitch's Print PDF has an "operator layout": colour blocks, thread names, stitch counts, notes. Commercial tools print similar worksheets. | NEW | primary | https://inkstitch.org/docs/print-pdf/ |
| VP3 stores thread brand, number and name per colour. Ink/Stitch writes them when a thread palette is set. The headless catalog loads 75 palettes, including Madeira Polyneon, Isacord Polyester and Robison-Anton (verified). Our VP3s carry only the hex as the name (verified on `bomb_web_2.vp3`). Setting the palette metadata and re-exporting gave Madeira Polyneon names and numbers in the VP3 (verified on export). | NEW | primary, verified | https://inkstitch.org/docs/thread-color/ |
| Designer Diamond and Ruby show VP3 thread names as range abbreviation, weight and number. A mySewnet help passage suggests files opened straight from USB show only RGB and numbered colour changes. Whether the operator's model shows names is unknown. | context | primary (vendor help, two models only) | https://softwarehelp.mysewnet.com/MSW/100/Configure/Topics/Thread_Colors_and_the_Husqvarna_Viking_Designer_Diamond_deLuxe_Diamond_Ruby_deLuxe_and_Ruby.htm |
| Minimise colour changes; on a single-needle machine each one is a rethread. `bomb_web_2.vp3` has two near-black blocks (#212027 and #01010e), which is one extra rethread if both are sewn in the same black thread. | NEW (merge threads that are visually the same) | consensus for the rule; measured example | https://inkstitch.org/tutorials/routing/ ; Embird manual |
| Common patch failure modes: base fabric visible at the edge, border fraying, long jumps or stray trims, puckering from density. | ALREADY (coverage, pullsim, travelmap, jam check) | common | Custom Patch Factory |
| Naming: name files with design, size and colour count so the operator picks the right hoop. | NEW (minor) | single source, weak | no primary source found |

---

## 6. Things the pipeline does not consider at all (topic 5)

1. **The machine setting is part of the contract.** The file relies on "Automatic Jump Stitch Trim" being on. With it off, our trims are ignored and every cut becomes a loose jump to clip by hand. Nothing tells the operator this. (Husqvarna manual.)
2. **Machine time and operator stops are not optimised.** Trims and colour changes cost more time than the stitches they replace (2.2). Ordering and trimming optimise travel distance and exposure only.
3. **Physical thread identity.** The palette is RGB only. Operators thread by brand and number (5.2).
4. **Short-stitch filtering.** Both Wilcom and Husqvarna's software filter short stitches before export. We keep Ink/Stitch's 0.1 mm (3.3).
5. **Needle and bobbin budget per design.** Nothing reports when a needle or bobbin will run out. The Madeira and Schmetz figures make this a one-line calculation (3.1, 3.4).

---

## 7. Open questions

| Question | Side A | Side B |
|---|---|---|
| How does the Husqvarna sew a long VP3 stitch record? | Repo docs (`review.md` item 8, EMBROIDERY_QUALITY section 7): every untrimmed jump is a sewn stitch. | pystitch writer comment: long-coded stitches "count as jumps". mySewnet calls them "movement stitches" and Stitch Toolbox says "the machine moves without stitching". Not verified on the machine. Either way, building travel from short stitches (2.6 item 1) gives a sewn, tacked run. |
| Time per trim | 3 to 4 s (Wilcom, low stitch-count blog). | About 8 s (Wilcom, travel toolbar blog). No maker publishes a figure. Time one trim on the operator's machine. |
| Patch satin border width | 2.5 to 3.5 mm "workhorse" (Custom Patch Factory); 2.5 mm or more (HoopingStation). | 3 mm minimum (MaggieFrames); 3.5 to 5 mm for appliqué cover borders (Sassy). All are service blogs. Keep 2.5 mm until a cut-edge swatch frays. |
| Trim floor 2 mm or 3 mm | 3 mm: Hatch default, Wilcom "not visible", Ink/Stitch min jump. | Wilcom's own caveat: shorter when thread contrasts with the background. Light thread on black vadmel contrasts. |
| Satin underlay on narrow borders | Wilcom and Ink/Stitch: centre run for 2 to 3 mm columns. | The hand-digitized samples in `learnings_from_embroidery_projects.md` use no satin underlay at all and still sewed well. Our jam history shows extra passes add density at hairpins. Decide with a swatch. |
| Fill angle | One dominant angle per element (Custom Patch Factory); keep angles consistent on stretchy fabric (Embroidery Legacy). | Alternate 30 to 45 degrees between neighbours to cancel pull on large designs (Velora, single source). |
| Fill density | Madeira: 0.40 mm for 40 wt. | Patches want 0.3 mm or less for full cover (StitchFast, in EMBROIDERY_QUALITY). Our SVG path uses 0.30 on measured coverage. |
| Which machine model? | Needed for speed range, thread-name display and trim behaviour. | Unknown; the Topaz 25 manual is used as an example. |

---

## 8. Not applicable

- Cap sequencing (centre-out, bottom-up for caps): we do not sew caps.
- Ballpoint needles for knits: patches are sewn on woven twill or felted vadmel.
- Merrow borders: they need an overlock machine after cutting; there is nothing to digitize.
- Do not resize stitch files more than 10 to 15 %: we regenerate stitches from vectors at every size.
- Commercial speeds of 1000 to 1500 spm and oiling at every bobbin: the home machine manual says no oiling, and speeds are lower.
- DST maximum stitch of 12.1 or 12.7 mm: that is a DST/Tajima/Barudan code limit, not VP3's.
- "Sew lights first so dark fibres do not fall on light areas": the source is about hand embroidery.
- Appliqué placement, tack-down and stop commands: our patches are full-coverage embroidery on the base fabric, with no placed fabric.
- Water-soluble topping on twill: twill has no pile; topping matters only for felt and vadmel (already covered).
- Hidden-stitch removal when merging designs (Embrilliance RHS): we generate one design and already carve hidden fragments.

---

## Sources

Primary (manufacturer, Ink/Stitch, Wilcom/Hatch, thread and needle makers):

- Husqvarna Viking Designer Topaz 25 User's Guide: https://svpworldwide.widen.net/content/jozhdb6ugy/original/DesignerTopaz25_EN.pdf
- mySewnet Stitch Editor Reference Guide (Win 12.0): https://download.mysewnet.com/Education/MSW/120/PDF/mySewnetStitchEditor_RefGuide_Win120.pdf
- mySewnet, Insert Trim Command: https://softwarehelp.mysewnet.com/MSW/140/StitchEditor/Topics/Insert_Trim_Command.htm
- mySewnet, thread colours on Designer Diamond and Ruby: https://softwarehelp.mysewnet.com/MSW/100/Configure/Topics/Thread_Colors_and_the_Husqvarna_Viking_Designer_Diamond_deLuxe_Diamond_Ruby_deLuxe_and_Ruby.htm
- Ink/Stitch: routing https://inkstitch.org/tutorials/routing/ , preferences https://inkstitch.org/docs/preferences/ , lock stitches https://inkstitch.org/docs/stitches/lock-stitches/ , commands https://inkstitch.org/docs/commands/ , stroke tools https://inkstitch.org/docs/stroke-tools/ , fill https://inkstitch.org/docs/stitches/fill-stitch/ , satin https://inkstitch.org/docs/stitches/satin-column/ , thread colour https://inkstitch.org/docs/thread-color/ , print PDF https://inkstitch.org/docs/print-pdf/
- Ink/Stitch issues: underpath explained https://github.com/inkstitch/inkstitch/issues/622 , home-machine trims https://github.com/inkstitch/inkstitch/issues/612
- Ink/Stitch source (vendored, `d59c9ab1e`): `lib/stitch_plan/stitch_plan.py`, `lib/elements/element.py`, `lib/elements/fill_stitch.py`, `lib/threads/catalog.py`, `lib/extensions/jump_to_stroke.py`, `lib/output.py`
- Wilcom docs: trims https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Automatic_trim_settings.htm , tie-offs https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Automatic_tie-off_settings.htm , connector types https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Types_of_connectors.htm , stitch and jump length https://docs.wilcom.com/embroiderystudio/26/en/OnlineHelp/Setup/machines/Stitch_jump_length_settings.htm , travel run https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/connectors/Adjusting_travel_run_stitch_length.htm , branching https://docs.wilcom.com/embroiderystudio/27/en/OnlineHelp/Quality/connectors/connectors-20.htm , small stitches https://docs.wilcom.com/embroiderystudio/e4/en/MainHelp/Quality/quality/Eliminating_small_stitches.htm , run underlay https://docs.wilcom.com/embroiderystudio/26/en/OnlineHelp/Quality/underlays/Run_stitch_underlay_settings.htm
- Wilcom blogs: https://wilcom.com/resources/blog/high-impact-low-stitch-count-designs , https://wilcom.com/resources/blog/on-screen-quality-assurance-tool-travel-toolbar , https://wilcom.com/resources/blog/branching , https://wilcom.com/resources/blog/minimizing-thread-trims-in-embroidery
- Hatch help: https://hatch.embroideryhelp.net/v3/en/OnlineHelp/Editing/edit_advanced/Automatic_connectors.htm , https://hatch.embroideryhelp.net/v3/en/OnlineHelp/Basics/view_designs/View_connectors.htm , https://hatch.embroideryhelp.net/v4/en/OnlineHelp/Digitizing/connectors/Automatic_tie-ins_tie-offs.htm
- Embird: https://www.embird.net/studio/manual/0050digit.htm , https://www.embird.net/machine-embroidery-tutorials/studio-next/tieup.htm
- Embrilliance: https://embrilliance.com/Help/Platform%20Mac%201170/jumpsremoveoverlaps.htm
- Madeira: density guide https://www.madeira.co.uk/wp-content/uploads/2021/10/Stitch_Density_2021_v3.pdf , Polyneon 40 datasheet https://www.madeira.co.uk/wp-content/uploads/2024/05/TDS_Polyneon40.pdf , needle chart https://www.madeirausa.com/_resources/common/userfiles/file/Quick%20Reference%20Needle%20Guide.pdf
- Schmetz: https://www.schmetzneedles.com/blogs/blog/change-your-needle

Practitioners and service blogs (common or single source):

- Embroidery Legacy (John Deer): https://embroiderylegacy.com/how-to-set-embroidery-machine-speed/ , https://embroiderylegacy.com/embroidery-digitizing-problems-how-to-avoid/
- KitParlor run-time survey: https://kitparlor.com/guides/embroidery-stitch-count-run-time/
- Custom Patch Factory: https://www.custompatchfactory.com/guides/how-to-digitize-embroidery-patches-how-to-digitize-a-patch
- Sassy Digitizing: https://sassydigitizing.com/blog/digitizing/custom-applique-digitizing-and-fabric-patches
- PlixaLabs: https://www.plixalabs.com/learn/techniques/trims-and-stitch-sequencing
- QuiltSocial (Husqvarna Topaz checklist): https://quiltsocial.com/9-check-list-items-for-successful-machine-embroidery-before-you-press/
- OESD (Organ titanium needles): https://oesd.com/organ-needles-titanium-sharp-7511/
- Velora Digitizing (fill angles): https://www.veloradigitizing.com/blog/jacket-back-embroidery-digitizing-guide
- Anecdotes: https://www.reddit.com/r/MachineEmbroidery/comments/16pakya/trim_slips/ , https://etcsupplies.com/blogs/help-centre/threads-are-not-trimming
