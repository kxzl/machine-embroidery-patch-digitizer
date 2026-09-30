# Implementation Spec — Digitize Improvements (Dumb-Model-Proof)

Single source of truth for the executing model. Work **one step at a time**, run
**only** the listed commands, capture output **verbatim**, report back after each
step. Do NOT improvise, do NOT skip verification.

## Rules for the executor model

1. Execute exactly one step, then stop and report.
2. Copy command output **verbatim** (never paraphrase).
3. On any error: stop, report the exact error, do NOT "fix and continue".
4. Never run interactive commands (no prompts) — non-interactive flags only.
5. Any install uses explicit timeouts; report the full tail of output.

## Decisions (locked)

- Fill order: perceptual **luma** `0.2126*R + 0.7152*G + 0.0722*B`, lightest first
  (bottom), darkest last (top). Border always topmost.
- Per-image YAML `<name>.yaml`, loaded **only** via `--config`.
- YAML keys: `order`, `skip_colors`, `density`, `border`, `trim`.
- Black border: `mode: auto` (fallback when no ring) | `force_black` | `off`.
  Border color fixed `#000000`.
- Travel minimization: nearest-neighbor TSP **within each color layer only**.
- Trim: threshold-based, jump > `trim.threshold_mm` (default 5 mm, `0` = always).
- Dependencies: add `pyyaml` (pure-python wheel).

## YAML schema

```yaml
order:              # first = bottom/stitched first; unlisted -> default luma sort
  - "#d3d8c7"
  - "#0b0806"
skip_colors:        # never stitched
  - "#ffffff"
density:            # per-color row_spacing_mm override (default 0.5)
  "#0b0806": 0.4
border:
  mode: auto        # auto | off | force_black
  thickness_mm: 3.0 # overrides --border-mm
trim:
  enabled: true
  threshold_mm: 7.0 # jump > this emits a cut; 0 = trim after every object
```

---

## Step 0 — Verify pyyaml installs / imports

Run (single commands, copy output):

```
.venv/bin/python -m pip install pyyaml 2>&1 | tail -20
.venv/bin/python -c "import yaml; print('YAML_OK', yaml.__version__)" 2>&1
```

Report both outputs verbatim. Stop on failure.

---

## Step 1 — Add flag parsing + YAML merge to vectorize.py

Edit `tools/digitize/vectorize.py`:

Add near the top (after imports, before existing `flag()`):

```python
import yaml

def load_config(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg
```

Add flags (next to existing `--colors`, `--border-mm`, `--trim` flags):

```python
CONFIG = flag("config", None)
TRIM_MM = flag("trim-mm", None)          # None = unset (fall back to YAML/default)
```

After `TRIM` is defined and before `SIZE_MM`, load + merge:

```python
cfg = load_config(CONFIG)
if cfg.get("trim", {}).get("enabled"):
    TRIM = True
_border_cfg = cfg.get("border", {}) or {}
_border_mode = _border_cfg.get("mode", "auto")
if _border_cfg.get("thickness_mm") is not None:
    BORDER_MM = float(_border_cfg["thickness_mm"])
_extratrim = TRIM_MM if TRIM_MM is not None else cfg.get("trim", {}).get("threshold_mm")
TRIM_THRESHOLD_MM = float(_extratrim) if _extratrim is not None else 5.0
if TRIM_THRESHOLD_MM < 0:
    TRIM_THRESHOLD_MM = 0.0
_ORDER = cfg.get("order") or []
_SKIP = {s.lower() for s in (cfg.get("skip_colors") or [])}
_DENSITY = cfg.get("density") or {}
```

All variable names above MUST be used exactly as written in later steps.

Verify (no crash, prints nothing new yet):

```
.venv/bin/python tools/digitize/vectorize.py --config /nonexistent.yml "Bomb_patch.webp" work/_step1.svg 2>&1 | tail -20
```

Report output. Stop on error/exception.

---

## Step 2 — Luma sort + order override + skip_colors

Edit `vectorize.py`. Replace the line:

```python
fill_colors = [c for c in range(len(centroids)) if c != bg]
```

with a helper + sorted list:

```python
def luma(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

# default: all non-background colors sorted light->dark (bottom->top)
_default_colors = sorted(
    [c for c in range(len(centroids)) if c != bg],
    key=lambda c: luma(cluster_rgb[c]),
)

def hexkey(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in cluster_rgb[c])

# map hex(lowercase) -> color index for order/skip/density resolution
hex_to_idx = {hexkey(c).lower(): c for c in range(len(centroids))}

# apply explicit order: listed colors first (in list order), then unlisted by luma
listed = [c for c in
          (hex_to_idx[h.lower()] for h in _ORDER if h.lower() in hex_to_idx)
          if c != bg]
fill_colors = listed + [c for c in _default_colors if c not in listed]

# skip colors
fill_colors = [c for c in fill_colors if hexkey(c).lower() not in _SKIP]
```

Note: `lw` (linework) selection must also respect `_SKIP`; find the darkest
non-skipped fill color — replace the existing `lw = min(fill_colors, ...)` result
with (it already keys off `fill_colors`, which now excludes skipped colors, so it
is already correct; leave `lw` line as-is).

Add an explicit print so we can verify ordering:

```python
print("order:", [hexkey(c) for c in fill_colors])
```

Verify using a scratch image with a known palette (Bomb patch):

```
.venv/bin/python tools/digitize/vectorize.py "Bomb_patch.webp" work/_step2.svg 2>&1 | tail -20
```

Report the `order:` line and the `fills:` block. Confirm black is emitted last
among fills.

---

## Step 3 — Component TSP (nearest-neighbor within each color)

The current `contour_paths()` returns only path strings. It must also return each
component's centroid so we can order them. Edit `contour_paths` so that for each
component it records a centroid (`(cy, cx)` = mean of the first kept polygon's
points), and returns `(ordered_paths, ordered_centroids, dropped)`.

Implementation guidance (concrete, do NOT improvise):

- In the loop `for c in range(1, n + 1)`, after computing `keep` (the kept
  polygons), compute:
  ```python
  first = np.asarray(keep[0])
  centroid = (float(first[:, 0].mean()), float(first[:, 1].mean()))
  ```
- Collect `sub` (the path string) and `centroid` into parallel lists.
- After the component loop, order components by nearest-neighbor starting from the
  centroid nearest to `(0, 0)`:
  ```python
  pts = list(centroids)          # list of (cy, cx)
  order = []
  if pts:
      cur = min(range(len(pts)), key=lambda i: pts[i][0] ** 2 + pts[i][1] ** 2)
      order.append(cur)
      used = {cur}
      while len(order) < len(pts):
          last = pts[order[-1]]
          best, bd = None, None
          for i in range(len(pts)):
              if i in used:
                  continue
              d = (pts[i][0] - last[0]) ** 2 + (pts[i][1] - last[1]) ** 2
              if bd is None or d < bd:
                  best, bd = i, d
          order.append(best)
          used.add(best)
  paths = [paths[i] for i in order]
  centroids = [centroids[i] for i in order]
  ```
- Return `paths, centroids, dropped` (add `centroids` to the return tuple).

Update all callers:
- the fills loop must capture `centroids` per color and store them in a dict
  `cent[c]`, then use them in Step 4 for trim ordering.
- the `linework` call must also capture its centroids.

Update the fills loop to record centroids:

```python
for c in fill_colors:
    paths, cen, dropped = contour_paths(mask_for(c, use_border_exclusion=has_transparency))
    groups[c] = paths
    cent[c] = cen
    print(...)
```

Same shape for `linework` (store `cent=[lw] = cen` under a key, e.g.
`cent[lw] = cen`).

Border centroid: the border element is a single path; its centroid is the mean of
the outer contour used to build `border_path_d` (already computed as `outer`); if
not available, use `(H / 2, W / 2)`.

Verify ordering is deterministic (run twice, diff output):

```
.venv/bin/python tools/digitize/vectorize.py "Bomb_patch.webp" work/_step3a.svg 2>&1 | tail -5
.venv/bin/python tools/digitize/vectorize.py "Bomb_patch.webp" work/_step3b.svg 2>&1 | tail -5
diff work/_step3a.svg work/_step3b.svg && echo "DETERMINISTIC_OK"
```

Report the `diff` result (should print `DETERMINISTIC_OK`).

---

## Step 4 — Threshold-based trim

Currently `TRIM` adds `inkstitch:trim_after="true"` on every element. Replace the
unconditional logic with jump-distance logic.

Concrete changes:

- Build the **global emit order** as a list of `(kind, color_index, path_index)`
  for fills (in `fill_colors` order), then linework (if any), then border (if any).
- For each consecutive pair, use the stored `cent` centroids to compute distance in
  **mm**: `d_mm = sqrt((dy)^2 + (dx)^2) / px_per_mm`. Note centroids are stored as
  `(cy, cx)` (y first) — use that consistently.
- The first element never trims. For element `i > 0`, if `d_mm > TRIM_THRESHOLD_MM`
  then set `trim_after` on element `i - 1`.
- If `TRIM_THRESHOLD_MM == 0`, set `trim_after` on every element except the last.

Implementation: modify the `el()` and `satin_el()` helpers to accept a
`trim_after=False` parameter, and drop `TRIM` from the global trim decision (keep
`TRIM` as the master on/off switch). Pass `trim_after` per element from the global
order loop.

Concretely restructure the SVG assembly (the loop currently at lines ~272-289) so
it walks the global emit order, computes jump distances via `cent`, and passes
`trim_after` accordingly.

Same as before, `TRIM` gates whether ANY trim is emitted: if `TRIM` is False, no
trims at all (regardless of threshold).

Verify — generate a trimmed SVG and count `trim_after="true"` occurrences; compare
to the old "every object" behavior (should be FEWER for a patch with contiguous
colors):

```
.venv/bin/python tools/digitize/vectorize.py --trim "Bomb_patch.webp" work/_step4.svg 2>&1 | tail -5
grep -c 'trim_after="true"' work/_step4.svg
```

Report the count.

---

## Step 5 — Black border fallback / force / off

Edit the border section (currently guarded by `if has_transparency and not NO_BORDER:`).

New rules using `_border_mode` (from Step 1) and existing `NO_BORDER`:

- Effective mode:
  - if `NO_BORDER` or `_border_mode == "off"`: skip border entirely.
  - if `_border_mode == "force_black"`: emit black border (ignore ring detection).
  - else (`auto`): current detect-ring behavior; **if no ring is detected** (current
    code would leave `border_path_d = None`), **emit a black border** over the
    silhouette outer contour (the fallback).
- Border color: if mode is `force_black` OR the auto-fallback fired, set
  `border_color = np.array([0, 0, 0])`. If a ring was detected normally, keep
  `border_color` as detected.

Concretely:
- Keep the outer-contour extraction (`contours`/`outer`/`border_path_d`) as-is, but
  run it whenever `has_transparency` and border is not off, not only when
  `not NO_BORDER`.
- Set `border_ring` (for interior exclusion) only when a real dark ring is used;
  for forced/fallback black border, use the outer contour only and do NOT mask a
  ring out of the interior palette.
- Ensure `border_path_d` is always produced for force_black/fallback so a border
  element is emitted.

Verify all three modes:

```
.venv/bin/python tools/digitize/vectorize.py --no-border "Bomb_patch.webp" work/_step5_off.svg 2>&1 | grep -i border
```

Confirm no border element and no `border:` print.

For `force_black` and `auto`, create a throwaway config and run; report whether a
border path element appears in the SVG (`grep -c 'satin_column' work/....svg`).

---

## Step 6 — Per-color density override

In `el()`, the caller already can pass `spacing=`. Change the fill emit loop so it
uses `_DENSITY` when a hex key matches:

```python
spacing = _DENSITY.get(hexkey(c)) or None   # None -> default ROW_SPACING_MM in el()
```

Then pass `spacing=spacing` (or leave the argument omitted when None). `el()` must
tolerate `spacing=None` (already does: `spacing if spacing is not None else ROW_SPACING_MM`).

Verify with a config that sets density for one color; grep the emitted SVG for
`row_spacing_mm="0.4"` vs `0.5`:

```
.venv/bin/python tools/digitize/vectorize.py --config work/_density_test.yml "Bomb_patch.webp" work/_step6.svg 2>&1 | tail -5
grep -o 'row_spacing_mm="[0-9.]*"' work/_step6.svg | sort | uniq -c
```

(First create `work/_density_test.yml` with a `density:` block for the darkest
color, value `0.4`.) Report the uniq count output.

---

## Step 7 — run.sh forwarding + make_config.py

### run.sh

Forward `--config PATH` and `--trim-mm N` (they already fall into `FLAGS[]` since
they start with `-`; confirm `--config <path>` (space-separated) is handled — the
current loop only collects a single token per `-*` flag, so `--config path` would
need `IMG` vs flag handling care; keep `--config=path` and `--trim-mm=N` `=`-style
to remain compatible). Add a `--no-export` flag that, if present, skips the
export step (lines after vectorize). Use `${FLAGS[*]}` as today.

Verify (dry, no export):

```
tools/digitize/run.sh --no-export "Bomb_patch.webp" 2>&1 | tail -5
```

Report output; confirm it stops before the export step.

### make_config.py

Create `tools/digitize/make_config.py`:

- Usage: `make_config.py <image> [--colors N] [--out <name>.yaml]`
- Reuse the k-means palette from `vectorize` logic (import the small
  `kmeans_palette`/luma helpers by copying them in, or import vectorize and call
  its functions — prefer copy-in to avoid side effects of running vectorize top
  level). Detect colors over the image silhouette (transparent-aware), sort by
  luma ascending, list them in the `order:` key.
- Write a starter YAML with `order:` (all detected colors), empty `skip_colors:`,
  `density:` (as a comment or empty), `border: {mode: auto}`, `trim: {enabled: false}`.
- Print the run command:
  `tools/digitize/run.sh --config <out> <image>`

Verify:

```
.venv/bin/python tools/digitize/make_config.py "Bomb_patch.webp" --out work/Bomb_patch.yaml 2>&1
cat work/Bomb_patch.yaml
```

Report the file contents.

---

## Step 8 — make_config.html (self-contained)

Create `tools/digitize/make_config.html` (single file, vanilla JS, no server):

- A textarea to paste palette hexes (one per line) OR a file input that when a
  `.png`/`.svg` is chosen, scans the text for `#rrggbb` tokens and populates the
  list.
- A reorderable list (up/down buttons; drag is optional to keep the JS simple).
- Per-color controls: density (number) and a "skip" checkbox.
- Border: mode select (auto/off/force_black) + thickness (number).
- Trim: enabled checkbox + threshold (number).
- "Copy YAML" and "Download <name>.yaml" buttons, and a "Copy command" button that
  builds `tools/digitize/run.sh --config <name>.yaml <image>` using a filename
  field for the image.

Do NOT use external libraries or CDN. Verify by opening the file locally (report
the file was written; browser testing is manual).

---

## Step 9 — End-to-end comparison

Run the full pipeline on all three available images with default settings and with
an override config, and report stitch counts / file sizes vs. the current baseline:

```
tools/digitize/run.sh --no-border "Bomb_patch.webp" 2>&1 | tail -3
tools/digitize/run.sh "Bomb_patch.webp" 2>&1 | tail -3
tools/digitize/run.sh --trim --trim-mm=7 "Bomb_patch.webp" 2>&1 | tail -3
```

Report the `.vp3` stitch counts and sizes produced. Compare against the prior
baseline numbers already in `work/` (e.g. `Bomb_patch.vp3`).

---

## Completion

After all steps, report: files changed, a summary table of before/after stitch
counts and trims, and anything that did not match the spec verbatim.
