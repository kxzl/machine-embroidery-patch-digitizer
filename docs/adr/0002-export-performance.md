# Export performance: cache, input diet, and batch

Exporting a finished design to VP3 is the slowest step in the pipeline. The
Scavenger's Daughter test design (58,469 stitches, ~260x167 mm) takes **7-8.5
minutes of wall clock on one core**, while the machine has twelve. This ADR
records where that time actually goes and which of the proposed fixes are worth
doing. It is measurement only: no pipeline code was changed.

## Measured baseline

The baseline is `output_inkstitch_svg/Scavenger's Daughter Upgrade Patch2.svg`
(194 KB) exported through the vendored headless Ink/Stitch:

```
PYTHONPATH=tools/wxstub INKSTITCH_OFFLINE_SCRIPT=true \
  .venv/bin/python inkstitch/inkstitch.py --extension=zip --format-vp3=True <svg>
```

A cold-cache `cProfile` run finished in **488 s wall** (`total_tt` 487.6 s) and
produced the same 58,469-stitch / 117,794-byte VP3 as the recorded baseline.
cProfile overhead is negligible here because ~72% of the time is spent inside
GEOS C calls that the profiler does not instrument, so 488 s is a fair cold
baseline and sits inside the previously measured 7-8.5 min range.

All stitch counts in this ADR are compared against that **58,469-stitch
profiled baseline**. (The committed `output_vp3/Scavenger's Daughter Upgrade
Patch2.vp3` is now 58,189 stitches after later border/trim fixes; the diet
variants were generated from the same SVG the profile used, so 58,469 is the
consistent reference.)

## Profile hotspots

223M function calls, 487.6 s of profiler time. Ordered by cumulative time:

| phase | cumtime | share | notes |
|---|---:|---:|---|
| `elements_to_stitch_groups` | 468.0 s | 96% | everything after SVG parse |
| fill `to_stitch_groups` | 464.0 s | 95% | 30 tatami fills |
| `tatami_fill` | 462.4 s | 95% | 458 calls |
| `clamp_path_to_polygon` | 385.3 s | 79% | travel-path clamping, 15,365 calls |
| **shapely `buffer`** | **350.3 s** | **72%** | **26,239 calls, ~13 ms each** |
| `do_tatami_fill` (top layer) | 344.6 s | 71% | |
| `do_underlay` | 118.4 s | 24% | |
| `which_outline` | 37.9 s | 8% | |
| `build_fill_stitch_graph` | 23.1 s | 5% | |
| satin `to_stitch_groups` | 2.6 s | 0.5% | border satin is free |
| `stitch_groups_to_stitch_plan` | 1.2 s | 0.3% | |
| `write_embroidery_file` | 0.55 s | 0.1% | output/encoding is free |

The whole cost is one thing: **tatami fill travel planning buffers the fill
polygon**. `clamp_path_to_polygon` (clamp_path.py:114) calls
`polygon.buffer(1e-9)` once per travel segment to build a prepared geometry for
containment tests. On a polygon with thousands of vertices and many holes — the
large `#030503` fill alone has 7,632 points, the green fill 3,732 — that buffer
is expensive, and it is repeated for every one of the 15,365 travel segments.
Satin, stitch-plan assembly and VP3 encoding are rounding errors.

## Input diet

The emitted SVG is **already rounded to 2 decimals** (24,657 numbers, every one
at 1-2 decimal places), so "fewer coordinate digits" is a no-op. The lever is
geometry, not digits: the input artwork is flattened at `TOLERANCE_MM = 0.15` mm,
producing 12,058 fill vertices. The experiment re-emitted the same design from
the existing SVG with Douglas-Peucker simplification
(`shapely.simplify(preserve_topology=True)`) applied to each fill ring; the
satin border was left byte-identical. The three variants were exported
concurrently, each with its own cache directory, and each reported
`wall ≈ user` — they stayed single-threaded and did not contend.

| variant | fill points | wall | stitches vs 58,469 | VP3 bytes | quality note |
|---|---:|---:|---:|---:|---|
| baseline (0.15 mm flatten, 2 dp) | 12,058 | 488 s (cold, profiled) | reference | 117,794 | reference |
| coords -> 2 dp (control) | 12,058 | not exported | — | — | no-op: emitted SVG is already 2 dp |
| simplify 0.25 mm | 6,583 (54.6%) | **324.8 s** | 57,987 (-0.8%) | 116,824 | visually indistinguishable |
| simplify 0.40 mm | 5,364 (44.5%) | **266.3 s** | 56,816 (-2.8%) | 114,488 | minor edge rounding |
| simplify 0.60 mm | 4,483 (37.2%) | **217.3 s** | 55,981 (-4.3%) | 112,854 | visible edge/feature erosion |

Speedups over the 488 s baseline: 1.50x at 0.25 mm, 1.83x at 0.40 mm, 2.25x at
0.60 mm. Fewer vertices cut the per-segment polygon buffer roughly
proportionally, so the hypothesis is confirmed: **the fill vertex count, not the
coordinate text, drives export time**. This is a post-hoc proxy for changing
`TOLERANCE_MM`; the real one-line change would re-flatten the input curves and
should land in the same range.

## diskcache

Ink/Stitch caches stitch groups per element (`_load_cached_stitch_groups`) in a
`diskcache` SQLite store. A repeat export of the unchanged SVG was **9.1 s**
versus 488 s cold — about **54x faster**, identical 58,469 stitches and
117,794-byte VP3. This held both with an isolated cache directory and with the
default `~/.config/inkstitch` cache, where the baseline was already warm. The
cache key is content-based (params, parsed path, style), so it hits only while
the emitted SVG is byte-identical; any geometry edit re-pays the full cost.

## Recommendation

1. **Input diet — adopt, one line.** Change
   `tools/digitize/svg_digitize.py:96` from `TOLERANCE_MM = 0.15` to
   `TOLERANCE_MM = 0.25` (and, for the raster path,
   `tools/digitize/vectorize.py:107`). 0.25 mm buys 1.5x for a 0.8% stitch
   change; 0.40 mm buys 1.83x for 2.8%. Start at 0.25 and eyeball the stitch
   plan; go to 0.40 only if the rounding is acceptable. This is a follow-up, not
   applied here.
2. **Batch parallelism — worth it.** Each export is single-threaded, so N
   independent designs on N cores scale almost linearly: the three diet exports
   ran concurrently and all finished in 324.8 s wall versus 808 s serial — 2.5x
   throughput on 3 workers, with 12 cores available. Wrap the pipeline with
   something like
   `find input -name '*.svg' | xargs -P "$(nproc)" -I{} tools/digitize/run.sh {}`.
   Give each worker its own `XDG_CONFIG_HOME` (or a per-worker cache dir) so the
   `diskcache` SQLite store is not written concurrently; budget ~200 MB RSS per
   worker, so `-P 12` is ~2.5 GB.
3. **Keep the cache enabled.** Repeat exports of unchanged SVGs are ~9 s, the
   single biggest win for iterating. Don't disable it.
4. **Single-design multicore — not worth it.** The cost is concentrated in one
   element's tatami travel clamping, inside GEOS. There is no clean split: fill
   elements are stitched in document order and share previous-stitch/trim state,
   and the dominant polygon (7,632 points) cannot be divided further. Splitting
   elements across workers would add serialization and duplicate the expensive
   per-polygon buffers for little gain, while batch parallelism already uses the
   idle cores.

## What was not changed

No pipeline code was touched. `svg_digitize.py`, `vectorize.py`, `run.sh`,
`preview.py` and `skeleton.py` are unmodified. The experiment SVGs and VP3s and
all throwaway scripts live under `/tmp/opencode/`. The only repository file
added is this ADR.
