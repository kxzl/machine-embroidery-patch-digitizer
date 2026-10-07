# Native SVG input path alongside the raster path

The pipeline started raster-only: `k-means` posterisation, contour tracing and
skeletonisation, all fed by `Image.open`. When the first vector input arrived
(`Scavenger's Daughter Upgrade Patch2.svg` — authored Layers with flat fills and
an explicit Layer order), we added a second input path that reads SVG paths
directly, instead of rasterising the SVG and re-tracing it.

Rasterising would have been roughly 30 lines and would have reused every tuning
constant in the existing path. We rejected it because it discards authored
geometry and Layer intent, and re-tracing is the step most likely to mangle
exact curve data an artist already got right. The cost is a second parser and a
second set of decisions (below), which is what the tradeoff buys.

What this path deliberately does **not** do, unlike the raster path:

- **It never skeletonises.** An authored `fill` is stitched as a fill, full stop.
  The raster path converts thin runs of its darkest colour into satin columns;
  here the artist already decided, and rewriting their shapes to save stitches
  is not ours to do. Adding it later is a flag away.
- **It reads `<path>` only.** No shape flattening, no Inkscape CLI subprocess.
  Non-path drawable elements raise a clear error instead of being silently
  handled by a second parser.
- **It ignores YAML `order`.** Stitch order is SVG document order. The other
  shared YAML keys (`skip_colors`, `density`, `border`, `trim`) still apply.